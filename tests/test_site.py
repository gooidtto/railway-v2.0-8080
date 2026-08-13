from pathlib import Path

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
assert "canvas" in low
assert "https://" not in low
assert "http://" not in low

size = len(html.encode("utf-8"))
assert size < 120_000, f"landing page is too large: {size} bytes"

print(f"site smoke test: PASS ({size} bytes)")
