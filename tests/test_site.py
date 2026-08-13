from pathlib import Path
import re

html = (Path(__file__).resolve().parents[1] / "site" / "index.html").read_text(encoding="utf-8")
low = html.lower()

for forbidden in ("xray", "railway", "vless", "reality", "proxy", "subscription", "node"):
    assert forbidden not in low, f"forbidden infrastructure term in landing page: {forbidden}"

assert "3D 元素周期表" in html
assert "118 种元素" in html
assert "表面模式" in html
assert "球体模式" in html
assert "螺旋模式" in html
assert "网格模式" in html
assert "粒子模式" in html
assert "波浪模式" in html
assert "Three.js R160" in html
assert "WebGL 渲染" in html
assert "three@0.160.0/build/three.module.min.js" in html
assert "canvas" in low
assert "drawAll" in html
assert "bootFallback" in html

urls = re.findall(r"https?://[^'\"\\s]+", html)
assert len(urls) == 1, f"unexpected external URLs in landing page: {urls}"
assert urls[0] == "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js"

size = len(html.encode("utf-8"))
assert size < 120_000, f"landing page is too large: {size} bytes"

print(f"site smoke test: PASS ({size} bytes)")
