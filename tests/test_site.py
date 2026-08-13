from pathlib import Path

html = (Path(__file__).resolve().parents[1] / "site" / "index.html").read_text(encoding="utf-8")
low = html.lower()

for forbidden in ("xray", "railway", "vless", "reality", "proxy", "subscription", "node"):
    assert forbidden not in low, f"forbidden infrastructure term: {forbidden}"

for required in (
    "3D 元素周期表",
    "Interactive 3D Periodic Table",
    "118 种元素",
    "表面模式",
    "球体模式",
    "螺旋模式",
    "网格模式",
    "粒子模式",
    "波浪模式",
    "实时数据",
    "技术支持",
    "Three.js R160",
    "WebGL 渲染",
    "拖拽旋转",
    "滚轮缩放",
    "悬停查看",
    "点击高亮",
    "自动旋转",
):
    assert required in html, f"missing visual text: {required}"

assert html.count('data-mode="') == 6
assert html.count('data-target="') == 6
assert "requestAnimationFrame" not in html
assert "setInterval" not in html
assert "setTimeout" not in html
assert "https://" not in html and "http://" not in html

size = len(html.encode("utf-8"))
assert size < 100_000, f"landing page too large: {size} bytes"

print(f"site smoke test: PASS ({size} bytes, 6 modes, no JS animation loop)")
