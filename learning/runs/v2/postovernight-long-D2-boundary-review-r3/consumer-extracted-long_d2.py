def require(condition, message, outcome='identity_or_lease_failure'):
    if not condition:
        raise Stop(message, outcome)

def sha(path):
    digest = hashlib.sha256()
    bytes_hashed = 0
    if HASH_OBSERVER is not None:HASH_OBSERVER()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            if HASH_OBSERVER is not None:HASH_OBSERVER()
            digest.update(block)
            bytes_hashed += len(block)
    if HASH_OBSERVER is not None:HASH_OBSERVER()
    stats = getattr(VERIFY_LOCAL, "stats", None)
    if stats is not None:
        stats["files"] += 1
        stats["bytes"] += bytes_hashed
    return digest.hexdigest()

def read_json(path):
    # Repeated or nonfinite JSON keys/values cannot silently redefine authority.
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON field: ' + key)
            value[key] = item
        return value
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(Stop('Nonfinite JSON: ' + value)))

def verify_files(pins):
    for path, digest in pins.items():
        require(Path(path).is_file() and sha(path) == digest, 'Input hash mismatch: ' + str(path))
