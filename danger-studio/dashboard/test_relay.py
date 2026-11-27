"""Lightweight relay lifecycle tests using a local fake native executable."""

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen
from unittest import mock

import relay


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.binary = Path(self.temp.name) / "fake-native"
        self.write_fake("""
import json, sys, time
count = int(sys.argv[sys.argv.index('--seed') + 1])
print(json.dumps({'meta': {'fake': True}}), flush=True)
for i in range(count):
    print(json.dumps({'frame': i}), flush=True)
print(json.dumps({'result': {'dead': False, 'survival_frames': count}}), flush=True)
""")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.shutdown_relays)
        self.relays = []

    def write_fake(self, body):
        self.binary.write_text("#!/usr/bin/env python3\n" + body)
        self.binary.chmod(0o755)

    def shutdown_relays(self):
        for instance in self.relays:
            with instance._guard:
                session = instance._session
                instance._session = None
            if session:
                session.stop()
            instance._server.shutdown()
            instance._server.server_close()

    def start(self, frames):
        instance = relay.Relay(self.binary)
        self.relays.append(instance)
        with mock.patch.object(relay.os, "getloadavg", return_value=(0, 0, 0)):
            response = instance.start({"seed": str(frames)})
        return instance, response

    def test_streams_more_than_1800_frames_and_keeps_natural_result(self):
        instance, started = self.start(1850)
        collected = []
        ended = False
        result = None
        while not ended:
            batch = instance.next({"sid": started["sid"], "n": "120"})
            collected.extend(row["frame"] for row in batch["frames"])
            ended, result = batch["ended"], batch["result"]
        self.assertEqual(collected, list(range(1850)))
        self.assertEqual(result, {"dead": False, "survival_frames": 1850})

    def test_stop_and_replacement_release_reader_and_expire_old_session(self):
        instance, first = self.start(1_000_000)
        old = instance._session
        replacement = instance.start({"seed": "1000000"})
        self.assertFalse(old.reader.is_alive())
        with self.assertRaisesRegex(ValueError, "unknown or expired"):
            instance.next({"sid": first["sid"]})
        instance.stop({"sid": replacement["sid"]})
        self.assertFalse(instance._session)

    def test_stalled_stream_is_stopped_and_session_expires(self):
        self.write_fake("""
import json, time
print(json.dumps({'meta': {'fake': True}}), flush=True)
time.sleep(30)
""")
        instance, started = self.start(1)
        reader = instance._session.reader
        with mock.patch.object(relay, "READ_TIMEOUT", 0.05):
            with self.assertRaisesRegex(ValueError, "stalled"):
                instance.next({"sid": started["sid"]})
        self.assertFalse(reader.is_alive())
        terminal = instance.next({"sid": started["sid"]})
        self.assertTrue(terminal["ended"])
        self.assertEqual(terminal["frames"], [])

    def request_keepalive(self, instance, token, sid):
        query = urlencode({"k": token, "sid": sid})
        with urlopen(f"{instance.base_url}/keepalive?{query}", timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_keepalive_refreshes_valid_session_without_reading_output(self):
        self.write_fake("""
import json, time
print(json.dumps({'meta': {'fake': True}}), flush=True)
time.sleep(30)
""")
        instance, started = self.start(10)
        session = instance._session
        session.touched = time.monotonic() - 1

        status, response = self.request_keepalive(instance, instance.token, started["sid"])

        self.assertEqual(status, 200)
        self.assertEqual(response, {"kept_alive": True})
        self.assertGreater(session.touched, 0)
        self.assertEqual(session.frames, 0)
        self.assertEqual(session.lines.qsize(), 0)
        self.assertIsNone(instance._reap_idle())
        self.assertIs(instance._session, session)

    def test_keepalive_rejects_bad_token_and_unknown_or_ended_sessions(self):
        instance, started = self.start(10)
        with self.assertRaises(HTTPError) as unauthorized:
            self.request_keepalive(instance, "wrong-token", started["sid"])
        self.assertEqual(unauthorized.exception.code, 403)
        with self.assertRaises(HTTPError) as unknown:
            self.request_keepalive(instance, instance.token, "wrong-sid")
        self.assertEqual(unknown.exception.code, 400)

        instance._session.ended = True
        with self.assertRaises(HTTPError) as ended:
            self.request_keepalive(instance, instance.token, started["sid"])
        self.assertEqual(ended.exception.code, 400)

        instance._session.ended = False
        instance._session.touched = 0
        with self.assertRaises(HTTPError) as expired:
            self.request_keepalive(instance, instance.token, started["sid"])
        self.assertEqual(expired.exception.code, 400)

    def test_keepalive_does_not_change_idle_reaping(self):
        instance, started = self.start(1_000_000)
        session = instance._session
        session.touched = 0

        expired = instance._reap_idle()

        self.assertIs(expired, session)
        self.assertIsNone(instance._session)
        with self.assertRaises(HTTPError) as stale:
            self.request_keepalive(instance, instance.token, started["sid"])
        self.assertEqual(stale.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
