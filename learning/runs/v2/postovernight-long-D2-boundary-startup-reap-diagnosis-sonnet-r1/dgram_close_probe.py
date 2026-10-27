"""Single-shot stdlib probe: is a DGRAM datagram sent immediately before peer close still readable?
No subprocess, no lifecycle code, no retry. Mirrors lifecycle.pair() (AF_UNIX/SOCK_DGRAM socketpair)
and Channel.receive's recvmsg(60001, CMSG_SPACE(4)). Raw outcomes are printed as JSON."""
import json, socket, sys, platform
def run(sends_before_close):
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    for i in range(sends_before_close):
        a.sendmsg([('msg%d' % i).encode()])
    a.close()
    b.settimeout(0.2)
    rows = []
    for attempt in range(sends_before_close + 2):
        try:
            raw, anc, flags, _ = b.recvmsg(60001, socket.CMSG_SPACE(4))
            rows.append(dict(attempt=attempt, raw=raw.decode(), flags=flags))
        except OSError as e:
            rows.append(dict(attempt=attempt, error=type(e).__name__, errno=e.errno))
    b.close()
    return rows
out = dict(platform=platform.platform(), python=sys.version, cases={str(n): run(n) for n in (0, 1, 2)})
print(json.dumps(out, indent=2, sort_keys=True))
