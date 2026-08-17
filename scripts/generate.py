import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import quote, urlparse


def env(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and not value:
        raise SystemExit(f"ERROR: missing {name}")
    return value


def write_atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(data, encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def hostname(value, name):
    value = (value or "").strip()
    if value.startswith(("http://", "https://")):
        value = urlparse(value).netloc or urlparse(value).path
    value = value.strip("[]").rstrip("/")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", value):
        raise SystemExit(f"ERROR: invalid {name}")
    return value


def port(value, name):
    try:
        number = int(str(value).strip())
    except ValueError:
        raise SystemExit(f"ERROR: invalid {name}") from None
    if not 1 <= number <= 65535:
        raise SystemExit(f"ERROR: invalid {name}")
    return number


DATA = Path(env("DATA_DIR", "/data"))
CONFIG = Path(env("XRAY_CONFIG", "/etc/xray/config.json"))
UUID = env("UUID", required=True)
PRIVATE_KEY = env("PRIVATE_KEY", required=True)
PUBLIC_KEY = env("PUBLIC_KEY", required=True)
VLESS_DECRYPTION = env("VLESS_DECRYPTION", required=True)

PUBLIC_DOMAIN = hostname(env("PUBLIC_DOMAIN", required=True), "PUBLIC_DOMAIN")
TCP1_HOST = hostname(env("TCP1_HOST", required=True), "TCP1_HOST")
TCP1_PORT = port(env("TCP1_PORT", required=True), "TCP1_PORT")
TCP2_HOST = hostname(env("TCP2_HOST", required=True), "TCP2_HOST")
TCP2_PORT = port(env("TCP2_PORT", required=True), "TCP2_PORT")
TCP3_HOST = hostname(env("TCP3_HOST", required=True), "TCP3_HOST")
TCP3_PORT = port(env("TCP3_PORT", required=True), "TCP3_PORT")

XHTTP_PATH = env("XHTTP_PATH", "/xhttp").strip()
XHTTP_MODE = env("XHTTP_MODE", "auto").strip()
FINGERPRINT = env("REALITY_FINGERPRINT", "chrome").strip()
REALITY_TARGET = env("REALITY_TARGET", "www.cloudflare.com:443").strip()
REALITY_SNI = hostname(env("REALITY_SNI", "www.cloudflare.com"), "REALITY_SNI")
SHORT_ID = env("SHORT_ID", required=True).strip()
GRPC_SERVICE = env("GRPC_SERVICE_NAME", "grpc-service").strip()
WS_PATH = env("WS_PATH", "/ws").strip()

if not XHTTP_PATH.startswith("/"):
    raise SystemExit("ERROR: XHTTP_PATH must start with /")
if XHTTP_MODE not in {"auto", "packet-up", "stream-up"}:
    raise SystemExit("ERROR: invalid XHTTP_MODE")
if not WS_PATH.startswith("/"):
    raise SystemExit("ERROR: WS_PATH must start with /")
if not GRPC_SERVICE:
    raise SystemExit("ERROR: GRPC_SERVICE_NAME is required")
if not re.fullmatch(r"[0-9a-fA-F]{8,32}", SHORT_ID):
    raise SystemExit("ERROR: SHORT_ID must be 8-32 hexadecimal characters")

# Fixed internal ports; Railway maps its public endpoints to these ports.
XHTTP_PORT = 10086
VISION_PORT = 10087
GRPC_PORT = 10088
WS_PORT = 10089

REALITY = {
    "show": False,
    "target": REALITY_TARGET,
    "xver": 0,
    "serverNames": [REALITY_SNI],
    "privateKey": PRIVATE_KEY,
    "shortIds": [SHORT_ID],
}

inbounds = [
    {
        "listen": "127.0.0.1",
        "port": XHTTP_PORT,
        "protocol": "vless",
        "settings": {
            "clients": [{"id": UUID}],
            "decryption": VLESS_DECRYPTION,
        },
        "streamSettings": {
            "network": "xhttp",
            "security": "none",
            "xhttpSettings": {"path": XHTTP_PATH, "mode": XHTTP_MODE},
        },
    },
    {
        "listen": "0.0.0.0",
        "port": VISION_PORT,
        "protocol": "vless",
        "settings": {
            "clients": [{"id": UUID, "flow": "xtls-rprx-vision"}],
            "decryption": VLESS_DECRYPTION,
        },
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": REALITY,
        },
    },
    {
        "listen": "0.0.0.0",
        "port": GRPC_PORT,
        "protocol": "vless",
        "settings": {
            "clients": [{"id": UUID}],
            "decryption": VLESS_DECRYPTION,
        },
        "streamSettings": {
            "network": "grpc",
            "security": "reality",
            "realitySettings": REALITY,
            "grpcSettings": {"serviceName": GRPC_SERVICE},
        },
    },
    {
        "listen": "0.0.0.0",
        "port": WS_PORT,
        "protocol": "vless",
        "settings": {
            "clients": [{"id": UUID}],
            "decryption": VLESS_DECRYPTION,
        },
        "streamSettings": {
            "network": "ws",
            "security": "tls",
            "tlsSettings": {
                "certificates": [
                    {
                        "certificateFile": "/data/ws/fullchain.pem",
                        "keyFile": "/data/ws/privkey.pem",
                    }
                ]
            },
            "wsSettings": {"path": WS_PATH},
        },
    },
]

CONFIG.parent.mkdir(parents=True, exist_ok=True)
write_atomic(
    CONFIG,
    json.dumps(
        {
            "log": {"loglevel": env("XRAY_LOGLEVEL", "warning")},
            "inbounds": inbounds,
            "outbounds": [{"protocol": "freedom", "tag": "direct"}],
        },
        indent=2,
    )
    + "\n",
)

nodes = [
    f"vless://{UUID}@{PUBLIC_DOMAIN}:443?encryption=none&security=tls&sni={quote(PUBLIC_DOMAIN, safe='')}&fp={quote(FINGERPRINT, safe='')}&alpn=h2%2Chttp%2F1.1&type=xhttp&path={quote(XHTTP_PATH, safe='')}&mode={quote(XHTTP_MODE, safe='')}#VLESS%20XHTTP%20TLS",
    f"vless://{UUID}@{TCP1_HOST}:{TCP1_PORT}?encryption=none&flow=xtls-rprx-vision&security=reality&sni={quote(REALITY_SNI, safe='')}&fp={quote(FINGERPRINT, safe='')}&pbk={quote(PUBLIC_KEY, safe='')}&sid={SHORT_ID}&type=tcp#VLESS%20RAW%20REALITY%20Vision",
    f"vless://{UUID}@{TCP2_HOST}:{TCP2_PORT}?encryption=none&security=reality&sni={quote(REALITY_SNI, safe='')}&fp={quote(FINGERPRINT, safe='')}&pbk={quote(PUBLIC_KEY, safe='')}&sid={SHORT_ID}&type=grpc&serviceName={quote(GRPC_SERVICE, safe='')}#VLESS%20gRPC%20REALITY",
    f"vless://{UUID}@{TCP3_HOST}:{TCP3_PORT}?encryption=none&security=tls&sni={quote(PUBLIC_DOMAIN, safe='')}&fp={quote(FINGERPRINT, safe='')}&type=ws&path={quote(WS_PATH, safe='')}#VLESS%20WS%20TLS",
]

if len(nodes) != 4:
    raise SystemExit(f"ERROR: NODE_COUNT invariant violated: {len(nodes)}")

text = "\n".join(nodes) + "\n"
write_atomic(DATA / "vless.txt", text)
write_atomic(DATA / "subscription.txt", base64.b64encode(text.encode()).decode() + "\n")
write_atomic(DATA / "node_count.txt", "4\n")

print("BUILD=railway-v2-fixed-4-node")
print("NODE_COUNT=4")
print(f"01 DOMAIN:443 -> {XHTTP_PORT} XHTTP TLS")
print(f"02 {TCP1_HOST}:{TCP1_PORT} -> {VISION_PORT} RAW REALITY Vision")
print(f"03 {TCP2_HOST}:{TCP2_PORT} -> {GRPC_PORT} gRPC REALITY")
print(f"04 {TCP3_HOST}:{TCP3_PORT} -> {WS_PORT} WS TLS")
