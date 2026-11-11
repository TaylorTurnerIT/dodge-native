"""Build the timeline deck.

Inlines reveal.js's core CSS, the live-game runtime (live.js) and the
WebAssembly module (web/, built with
`RUSTFLAGS="-C target-feature=+simd128" cargo build --release --lib --target wasm32-unknown-unknown`).

Writes two files next to this script:
  artifact.html  page body for publishing (the host adds doctype/head)
  index.html     standalone document for presenting from a local browser
"""
import base64
from pathlib import Path

here = Path(__file__).parent
src = (here / "deck.src.html").read_text(encoding="utf-8")
core = (here / "reveal.min.css").read_text(encoding="utf-8")
live = (here / "live.js").read_text(encoding="utf-8")
wasm = (here / "web" / "target" / "wasm32-unknown-unknown" / "release" / "dodge_web.wasm").read_bytes()

live = live.replace("/*WASM_B64*/", base64.b64encode(wasm).decode("ascii"))
page = src.replace("/*REVEAL_CORE*/", core)
page = page.replace('id="wasm-size">772 KB', f'id="wasm-size">{round(len(wasm) / 1000)} KB')
page = page.rstrip() + "\n<script>\n" + live + "\n</script>\n"

(here / "artifact.html").write_text(page, encoding="utf-8", newline="\n")
standalone = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
              '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
              + page.replace("<div class=\"reveal\">", "</head>\n<body>\n<div class=\"reveal\">", 1)
              + "\n</body>\n</html>\n")
(here / "index.html").write_text(standalone, encoding="utf-8", newline="\n")
print("built", len(page), "bytes; wasm", len(wasm), "bytes")
