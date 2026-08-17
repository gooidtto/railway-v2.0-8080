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
    ws = data / "ws"
    ws.mkdir(parents=True)
    (ws / "fullchain.pem").write_text("test-cert")
    (ws / "privkey.pem").write_text("test-key")

    env = os.environ.copy()
    env.update(
        {
            "DATA_DIR": str(data),
            "XRAY_CONFIG": str(config),
            "UUID": "00000000-0000-4000-8000-000000000000",
            "PRIVATE_KEY": "private-key",
            "PUBLIC_KEY": "public-key",
            "VLESS_DECRYPTION": "decryption",
            "PUBLIC_DOMAIN": "edge.example.test",
            "TCP1_HOST": "tcp1.example.test",
            "TCP1_PORT": "23337",
            "TCP2_HOST": "tcp2.example.test",
            "TCP2_PORT": "23389",
            "TCP3_HOST": "tcp3.example.test",
            "TCP3_PORT": "17903",
            "SHORT_ID": "50175c035ee132",
        }
    )

    result = subprocess.run(
        ["python3", str(ROOT / "scripts" / "generate.py")],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "NODE_COUNT=4" in result.stdout

    generated = json.loads(config.read_text())
    assert len(generated["inbounds"]) == 4
    assert [x["port"] for x in generated["inbounds"]] == [10086, 10087, 10088, 10089]
    assert generated["inbounds"][0]["streamSettings"]["network"] == "xhttp"
    assert generated["inbounds"][1]["streamSettings"]["network"] == "tcp"
    assert generated["inbounds"][2]["streamSettings"]["network"] == "grpc"
    assert generated["inbounds"][3]["streamSettings"]["network"] == "ws"

    decoded = base64.b64decode((data / "subscription.txt").read_text().strip()).decode()
    lines = [line for line in decoded.splitlines() if line]
    assert len(lines) == 4
    assert lines[0].startswith("vless://") and "edge.example.test:443" in lines[0]
    assert "tcp1.example.test:23337" in lines[1]
    assert "tcp2.example.test:23389" in lines[2]
    assert "tcp3.example.test:17903" in lines[3]
    assert "type=grpc" in lines[2]
    assert "type=ws" in lines[3]
    assert not list(data.glob("*.tmp"))

print("generate.py four-node smoke test: PASS")
