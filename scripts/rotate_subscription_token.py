#!/usr/bin/env python3
import os
import secrets
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: rotate_subscription_token.py DATA_DIR")

root = Path(sys.argv[1]).resolve()
token_file = root / "subscription_token.txt"
url_file = root / "subscription_url.txt"
old = token_file.read_text().strip() if token_file.exists() else ""
new = secrets.token_urlsafe(32)
tmp = root / ".subscription_token.rotate.tmp"
tmp.write_text(new + "\n")
os.chmod(tmp, 0o600)
os.replace(tmp, token_file)

public_domain = os.getenv("PUBLIC_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
if public_domain:
    tmp_url = root / ".subscription_url.rotate.tmp"
    tmp_url.write_text(f"https://{public_domain}/sub/{new}\n")
    os.chmod(tmp_url, 0o600)
    os.replace(tmp_url, url_file)

print("subscription token rotated")
print("previous token invalidated:", bool(old))
print("new subscription URL:", url_file.read_text().strip() if url_file.exists() else "set PUBLIC_DOMAIN and read subscription_url.txt")
