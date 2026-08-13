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
    tmp.write_text(data)
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


def target(value):
    value = (value or "").strip()
    if value.startswith(("http://", "https://")):
        value = urlparse(value).netloc or urlparse(value).path
    value = value.strip("[]").rstrip("/")
    if ":" not in value:
        value += ":443"
    host, port = value.rsplit(":", 1)
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise SystemExit("ERROR: invalid REALITY_TARGET")
    return f"{host}:{int(port)}"


D = Path(env("DATA_DIR", "/data"))
C = Path(env("XRAY_CONFIG", "/etc/xray/config.json"))
uuid = env("UUID", required=True)
private_key = env("PRIVATE_KEY", required=True)
public_key = env("PUBLIC_KEY", required=True)
vless_decryption = env("VLESS_DECRYPTION", required=True)
vless_encryption = env("VLESS_ENCRYPTION", required=True)

reality_target = target(env("REALITY_TARGET", "www.cloudflare.com:443"))
fingerprint = env("REALITY_FINGERPRINT", "chrome").strip()
xhttp_path = env("XHTTP_PATH", "/xhttp").strip()
xhttp_mode = env("XHTTP_MODE", "auto").strip()
short_id = env("SHORT_ID", "50175c035ee132").strip()
domain = hostname(env("PUBLIC_DOMAIN", required=True), "PUBLIC_DOMAIN")
server_host = hostname(env("SERVER_HOST", required=True), "SERVER_HOST")
server_port = env("SERVER_PORT", required=True).strip()

if not 1 <= int(server_port) <= 65535:
    raise SystemExit("ERROR: invalid SERVER_PORT")
if not xhttp_path.startswith("/"):
    raise SystemExit("ERROR: XHTTP_PATH must start with /")
if xhttp_mode not in {"auto", "packet-up", "stream-up"}:
    raise SystemExit("ERROR: invalid XHTTP_MODE")
if not re.fullmatch(r"[0-9a-fA-F]{8,32}", short_id):
    raise SystemExit("ERROR: SHORT_ID must be 8-32 hexadecimal characters")
if not fingerprint:
    raise SystemExit("ERROR: REALITY_FINGERPRINT is required")

sni_file = Path(env("REALITY_SNI_CANDIDATES_FILE", "/opt/xray/config/reality-sni-candidates.txt"))
limit = int(env("REALITY_SNI_LIMIT", "7"))
pool = list(dict.fromkeys(x.strip() for x in sni_file.read_text().splitlines() if x.strip() and not x.startswith("#")))
if len(pool) != limit:
    raise SystemExit("ERROR: verified SNI pool count mismatch")
for sni in pool:
    hostname(sni, "REALITY SNI")

base = {
    "listen": "127.0.0.1",
    "port": int(env("XRAY_PORT", "10087")),
    "protocol": "vless",
    "settings": {"clients": [{"id": uuid}], "decryption": vless_decryption},
    "streamSettings": {
        "network": "xhttp",
        "security": "reality",
        "realitySettings": {
            "show": False,
            "target": reality_target,
            "xver": 0,
            "serverNames": pool,
            "privateKey": private_key,
            "shortIds": [short_id],
        },
        "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode},
    },
}
plain = {
    "listen": "127.0.0.1",
    "port": int(env("XRAY_HTTP_PORT", "10086")),
    "protocol": "vless",
    "settings": {"clients": [{"id": uuid}], "decryption": vless_decryption},
    "streamSettings": {
        "network": "xhttp",
        "security": "none",
        "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode},
    },
}

config = {
    "log": {"loglevel": env("XRAY_LOGLEVEL", "info")},
    "inbounds": [base, plain],
    "outbounds": [{"protocol": "freedom", "tag": "direct"}],
}
write_atomic(C, json.dumps(config, indent=2) + "\n")

nodes = [
    f"vless://{uuid}@{domain}:443/?encryption={quote(vless_encryption, safe='')}&security=tls&type=xhttp&fp={quote(fingerprint, safe='')}&sni={quote(domain, safe='')}&alpn=h2%2Chttp%2F1.1&path={quote(xhttp_path, safe='')}&mode={quote(xhttp_mode, safe='')}#railway-xhttp-https-{domain}"
]
for sni in pool:
    nodes.append(
        f"vless://{uuid}@{server_host}:{int(server_port)}/?encryption={quote(vless_encryption, safe='')}&security=reality&type=xhttp&fp={quote(fingerprint, safe='')}&sni={quote(sni, safe='')}&pbk={quote(public_key, safe='')}&sid={short_id}&path={quote(xhttp_path, safe='')}&mode={quote(xhttp_mode, safe='')}#railway-xhttp-reality-{sni}"
    )

text = "\n".join(nodes) + "\n"
D.mkdir(parents=True, exist_ok=True)
write_atomic(D / "vless.txt", text)
write_atomic(D / "subscription.txt", base64.b64encode(text.encode()).decode() + "\n")
write_atomic(D / "reality-sni-list.txt", "\n".join(pool) + "\n")

print(f"HTTPS XHTTP node generated: {domain}:443")
print(f"REALITY SNI nodes generated: {len(pool)}")
