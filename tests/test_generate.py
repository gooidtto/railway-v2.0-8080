import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    data = tmp / "data"
    config = tmp / "config.json"
    sni = tmp / "sni.txt"
    sni.write_text("www.cloudflare.com\nwww.bing.com\nwww.canva.com\nwww.notion.so\nstore.epicgames.com\nwww.gog.com\nwww.gamespot.com\n")

    env = os.environ.copy()
    env.update(
        {
            "DATA_DIR": str(data),
            "XRAY_CONFIG": str(config),
            "UUID": "00000000-0000-4000-8000-000000000000",
            "PRIVATE_KEY": "private-key",
            "PUBLIC_KEY": "public-key",
            "VLESS_DECRYPTION": "decryption",
            "VLESS_ENCRYPTION": "encryption",
            "SERVER_HOST": "tcp.example.test",
            "SERVER_PORT": "443",
            "PUBLIC_DOMAIN": "edge.example.test",
            "REALITY_SNI_CANDIDATES_FILE": str(sni),
            "REALITY_SNI_LIMIT": "7",
        }
    )

    result = subprocess.run(
        ["python3", str(ROOT / "scripts" / "generate.py")],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "HTTPS XHTTP node generated" in result.stdout

    generated = json.loads(config.read_text())
    assert len(generated["inbounds"]) == 2
    assert generated["inbounds"][0]["port"] == 10087
    assert generated["inbounds"][1]["port"] == 10086

    subscription = data / "subscription.txt"
    decoded = base64.b64decode(subscription.read_text().strip()).decode()
    assert len([line for line in decoded.splitlines() if line]) == 8
    assert "edge.example.test:443" in decoded
    assert "tcp.example.test:443" in decoded
    assert not list(data.glob("*.tmp"))

print("generate.py smoke test: PASS")
