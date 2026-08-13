from pathlib import Path
import re

html = (Path(__file__).resolve().parents[1] / "site" / "index.html").read_text(encoding="utf-8")
low = html.lower()

for forbidden in ("xray", "railway", "vless", "reality", "proxy", "subscription", "node"):
    assert forbidden not in low, f"forbidden infrastructure term in landing page: {forbidden}"

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

assert html.count('<canvas') >= 6, "six visual panels must have canvas elements"
assert "requestAnimationFrame" in html
assert "prefers-reduced-motion" in html
assert "pointerdown" in html and "onwheel" in html

urls = re.findall(r"https?://[^'\"\\s]+", html)
assert not urls, f"landing page must not depend on external URLs: {urls}"

size = len(html.encode("utf-8"))
assert size < 120_000, f"landing page is too large: {size} bytes"

print(f"site smoke test: PASS ({size} bytes)")
