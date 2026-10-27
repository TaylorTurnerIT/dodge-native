# Read-only exact-range scan. Reports integer and hex tokens inside the upper D pool 0xD0000040..0xD000007E
# (decimal 3489660992..3489661054). The endpoint 0xD000007F / 3489661055 is excluded: config files use it as range end.
# Skips sealed/qualification/student and standalone D3/B/E-token paths by name and files over 5 MB.
import os, re, sys, collections
ROOT = sys.argv[1]
LO, HI = 0xD0000040, 0xD000007E
SKIP = re.compile(r"(sealed|qualif|student|(?<![A-Za-z0-9])D3(?![0-9])|(?<![A-Za-z0-9])[BE](?=[-_/.]))", re.I)
INT = re.compile(r"(?<![0-9A-Za-z_.])(\d{9,10})(?![0-9A-Za-z_.])")
HEX = re.compile(r"0[xX]([dD]0000[0-9a-fA-F]{3})(?![0-9a-fA-F])")
EXTS = (".json", ".jsonl", ".py", ".md", ".txt", ".log", ".patch", ".toml", ".yaml", ".rs")
for dp, dn, fn in os.walk(ROOT):
    dn[:] = [d for d in dn if d not in (".git", "target", ".cache", "node_modules", "__pycache__")]
    for f in fn:
        p = os.path.join(dp, f); rel = os.path.relpath(p, ROOT)
        if SKIP.search(rel) or not f.endswith(EXTS) or os.path.getsize(p) > 5_000_000: continue
        try: txt = open(p, encoding="utf-8", errors="ignore").read()
        except Exception: continue
        ints = collections.Counter(int(m) for m in INT.findall(txt))
        up_i = {v: c for v, c in ints.items() if 3489660992 <= v <= 3489661054}
        hexes = collections.Counter(int(h, 16) for h in HEX.findall(txt))
        up_h = {hex(v): c for v, c in hexes.items() if LO <= v <= HI}
        if up_i or up_h:
            print(f"{rel}\tint={up_i}\thex={up_h}")
