"""Build the timeline deck.

Inlines reveal.js's core CSS, the live-game runtime (live.js) and the
WebAssembly module (web/, built with
`RUSTFLAGS="-C target-feature=+simd128" cargo build --release --lib --target wasm32-unknown-unknown`).

Usage: python build.py [deck|spine]   (default: deck)

Writes two files next to this script:
  artifact.html  page body for publishing (the host adds doctype/head)
  index.html     standalone document for presenting from a local browser
For the story deck (spine.src.html) they are spine.artifact.html and spine.html.
"""
import base64
import sys
from pathlib import Path

here = Path(__file__).parent
name = sys.argv[1] if len(sys.argv) > 1 else "deck"
src = (here / f"{name}.src.html").read_text(encoding="utf-8")
out_artifact, out_index = ("artifact.html", "index.html") if name == "deck" else (f"{name}.artifact.html", f"{name}.html")
core = (here / "reveal.min.css").read_text(encoding="utf-8")
live = (here / "live.js").read_text(encoding="utf-8")
worker = (here / "sim_worker.js").read_text(encoding="utf-8")
wasm = (here / "web" / "target" / "wasm32-unknown-unknown" / "release" / "dodge_web.wasm").read_bytes()

wasm_b64 = base64.b64encode(wasm).decode("ascii")
live = live.replace("/*WORKER_B64*/", base64.b64encode(worker.encode("utf-8")).decode("ascii"))
live = live.replace("/*WASM_B64*/", wasm_b64)
page = src.replace("/*REVEAL_CORE*/", core)
page = page.replace('id="wasm-size">772 KB', f'id="wasm-size">{round(len(wasm) / 1000)} KB')
page = page.rstrip() + "\n<script>\n" + live + "\n</script>\n"

with (here / out_artifact).open("w", encoding="utf-8", newline="\n") as f:
    f.write(page)
standalone = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
              '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
              + page.replace("<div class=\"reveal\">", "</head>\n<body>\n<div class=\"reveal\">", 1)
              + "\n</body>\n</html>\n")
with (here / out_index).open("w", encoding="utf-8", newline="\n") as f:
    f.write(standalone)
print("built", out_artifact, len(page), "bytes; wasm", len(wasm), "bytes")
