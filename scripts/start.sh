#!/bin/sh
set -eu
umask 077

D="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"
C="${XRAY_CONFIG:-/etc/xray/config.json}"
mkdir -p "$D" "$(dirname "$C")" "$D/ws"
chmod 700 "$D"
rm -f "$D/.xray-ready"

UUID_FILE="$D/uuid.txt"
PRIVATE_FILE="$D/reality_private_key.txt"
PUBLIC_FILE="$D/reality_public_key.txt"
DECRYPTION_FILE="$D/vless_decryption.txt"
TOKEN_FILE="$D/subscription_token.txt"

if [ -s "$UUID_FILE" ]; then UUID=$(tr -d '[:space:]' <"$UUID_FILE"); else UUID=$(xray uuid); printf '%s\n' "$UUID" >"$UUID_FILE"; fi

if [ -s "$PRIVATE_FILE" ] && [ -s "$PUBLIC_FILE" ]; then
  PRIVATE_KEY=$(tr -d '[:space:]' <"$PRIVATE_FILE")
  PUBLIC_KEY=$(tr -d '[:space:]' <"$PUBLIC_FILE")
else
  OUT=$(xray x25519 2>&1)
  PRIVATE_KEY=$(printf '%s\n' "$OUT" | awk '/^PrivateKey/{sub(/^[^:]*:[[:space:]]*/,"");print;exit}')
  PUBLIC_KEY=$(printf '%s\n' "$OUT" | awk '/^Password/{sub(/^[^:]*:[[:space:]]*/,"");print;exit}')
  [ -n "$PRIVATE_KEY" ] && [ -n "$PUBLIC_KEY" ] || { echo "ERROR: failed to generate REALITY key pair" >&2; exit 1; }
  printf '%s\n' "$PRIVATE_KEY" >"$PRIVATE_FILE"
  printf '%s\n' "$PUBLIC_KEY" >"$PUBLIC_FILE"
fi

if [ -s "$DECRYPTION_FILE" ]; then
  VLESS_DECRYPTION=$(tr -d '[:space:]' <"$DECRYPTION_FILE")
else
  VLESS_DECRYPTION=$(xray vlessenc 2>/dev/null | awk '/"decryption"[[:space:]]*:/{sub(/^.*"decryption"[[:space:]]*:[[:space:]]*"/,"");sub(/".*$/,"");print;exit}')
  [ -n "$VLESS_DECRYPTION" ] || { echo "ERROR: failed to generate VLESS decryption material" >&2; exit 1; }
  printf '%s\n' "$VLESS_DECRYPTION" >"$DECRYPTION_FILE"
fi

if [ -s "$TOKEN_FILE" ]; then TOKEN=$(tr -d '[:space:]' <"$TOKEN_FILE"); else TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))'); printf '%s\n' "$TOKEN" >"$TOKEN_FILE"; fi

PUBLIC_DOMAIN="${RAILWAY_PUBLIC_DOMAIN:-${PUBLIC_DOMAIN:-}}"
TCP1_HOST="${RAILWAY_TCP_PROXY_DOMAIN:-${TCP1_HOST:-}}"
TCP1_PORT="${RAILWAY_TCP_PROXY_PORT:-${TCP1_PORT:-}}"
TCP2_HOST="${TCP2_HOST:-${RAILWAY_TCP_PROXY_2_DOMAIN:-}}"
TCP2_PORT="${TCP2_PORT:-${RAILWAY_TCP_PROXY_2_PORT:-}}"
TCP3_HOST="${TCP3_HOST:-${RAILWAY_TCP_PROXY_3_DOMAIN:-}}"
TCP3_PORT="${TCP3_PORT:-${RAILWAY_TCP_PROXY_3_PORT:-}}"

[ -n "$PUBLIC_DOMAIN" ] || { echo "ERROR: RAILWAY_PUBLIC_DOMAIN is required" >&2; exit 1; }
[ -n "$TCP1_HOST" ] && [ -n "$TCP1_PORT" ] || { echo "ERROR: TCP Proxy #1 host/port missing" >&2; exit 1; }
[ -n "$TCP2_HOST" ] && [ -n "$TCP2_PORT" ] || { echo "ERROR: TCP Proxy #2 host/port missing" >&2; exit 1; }
[ -n "$TCP3_HOST" ] && [ -n "$TCP3_PORT" ] || { echo "ERROR: TCP Proxy #3 host/port missing" >&2; exit 1; }

export DATA_DIR="$D" XRAY_CONFIG="$C" UUID PRIVATE_KEY PUBLIC_KEY VLESS_DECRYPTION
export PUBLIC_DOMAIN TCP1_HOST TCP1_PORT TCP2_HOST TCP2_PORT TCP3_HOST TCP3_PORT
export XHTTP_PATH="${XHTTP_PATH:-/xhttp}" XHTTP_MODE="${XHTTP_MODE:-auto}"
export REALITY_TARGET="${REALITY_TARGET:-www.cloudflare.com:443}" REALITY_SNI="${REALITY_SNI:-www.cloudflare.com}" REALITY_FINGERPRINT="${REALITY_FINGERPRINT:-chrome}"
export SHORT_ID="${SHORT_ID:-50175c035ee132}" GRPC_SERVICE_NAME="${GRPC_SERVICE_NAME:-grpc-service}" WS_PATH="${WS_PATH:-/ws}"
export XRAY_LOGLEVEL="${XRAY_LOGLEVEL:-warning}"

# WS/TLS requires a certificate/key. Refuse to start rather than creating a broken node.
[ -s "$D/ws/fullchain.pem" ] && [ -s "$D/ws/privkey.pem" ] || {
  echo "ERROR: /data/ws/fullchain.pem and /data/ws/privkey.pem are required for node 04 (WS+TLS)" >&2
  exit 1
}

# Never reuse legacy generated subscriptions or manifests.
rm -f "$D/subscription.txt" "$D/vless.txt" "$D/node_count.txt" "$D/manifest.json" "$D/state.json" "$D/reality-sni-list.txt"

python3 /opt/xray/scripts/generate.py
[ "$(tr -d '[:space:]' < "$D/node_count.txt")" = "4" ] || { echo "ERROR: NODE_COUNT invariant failed" >&2; exit 1; }

xray run -test -config "$C"
python3 /opt/xray/scripts/health_proxy.py & HP=$!
xray run -config "$C" & XP=$!
trap 'rm -f "$D/.xray-ready"; kill "$XP" "$HP" 2>/dev/null || true; wait "$XP" 2>/dev/null || true; wait "$HP" 2>/dev/null || true' INT TERM EXIT

for P in 10086 10087 10088 10089; do
  i=0
  while ! python3 -c "import socket; s=socket.create_connection(('127.0.0.1',$P),1); s.close()" 2>/dev/null; do
    i=$((i + 1))
    [ "$i" -lt 60 ] || { echo "ERROR: Xray listener $P not ready" >&2; exit 1; }
    sleep 1
  done
done

printf '%s/sub/%s\n' "https://${PUBLIC_DOMAIN}" "$TOKEN" >"$D/subscription_url.txt"
touch "$D/.xray-ready"

echo "BUILD=railway-v2-fixed-4-node"
echo "NODE_COUNT=4"
echo "MAP=443->10086, TCP1->10087, TCP2->10088, TCP3->10089"

while kill -0 "$XP" 2>/dev/null && kill -0 "$HP" 2>/dev/null; do sleep 5; done
echo "ERROR: supervised process exited" >&2
exit 1
