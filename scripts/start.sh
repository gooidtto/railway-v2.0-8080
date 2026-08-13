#!/bin/sh
set -eu
umask 077

D="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"
G="${GATEWAY_PORT:-${PORT:-8080}}"
C="${XRAY_CONFIG:-/etc/xray/config.json}"
mkdir -p "$D" "$(dirname "$C")" "$D/backups"
chmod 700 "$D" "$D/backups"
rm -f "$D/.xray-ready" "$D/xray.pid" "$D/gateway.pid"

atomic_write() {
  _path="$1"
  _value="$2"
  _tmp="${_path}.tmp"
  printf '%s\n' "$_value" >"$_tmp"
  chmod 600 "$_tmp"
  mv -f "$_tmp" "$_path"
}

UFILE="$D/uuid.txt"
PFILE="$D/reality_private_key.txt"
PUBFILE="$D/reality_public_key.txt"
DFILE="$D/vless_decryption.txt"
EFILE="$D/vless_encryption.txt"
TFILE="$D/subscription_token.txt"

if [ -s "$UFILE" ]; then UUID=$(tr -d '[:space:]' <"$UFILE"); else UUID=$(xray uuid); atomic_write "$UFILE" "$UUID"; fi

if [ -s "$PFILE" ] && [ -s "$PUBFILE" ]; then
  PRIVATE_KEY=$(tr -d '[:space:]' <"$PFILE")
  PUBLIC_KEY=$(tr -d '[:space:]' <"$PUBFILE")
else
  OUT=$(xray x25519 2>&1)
  PRIVATE_KEY=$(printf '%s\n' "$OUT" | awk '/^PrivateKey/{sub(/^[^:]*:[[:space:]]*/,"");print;exit}')
  PUBLIC_KEY=$(printf '%s\n' "$OUT" | awk '/^Password/{sub(/^[^:]*:[[:space:]]*/,"");print;exit}')
  [ -n "$PRIVATE_KEY" ] && [ -n "$PUBLIC_KEY" ] || { echo "ERROR: failed to generate REALITY key pair" >&2; exit 1; }
  atomic_write "$PFILE" "$PRIVATE_KEY"
  atomic_write "$PUBFILE" "$PUBLIC_KEY"
fi

if [ -s "$DFILE" ] && [ -s "$EFILE" ]; then
  VLESS_DECRYPTION=$(tr -d '[:space:]' <"$DFILE")
  VLESS_ENCRYPTION=$(tr -d '[:space:]' <"$EFILE")
else
  T="$D/.vlessenc.tmp"
  rm -f "$T"
  xray vlessenc >"$T" 2>&1
  VLESS_DECRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/{m=1;next}m&&/"decryption"[[:space:]]*:/{sub(/^.*"decryption"[[:space:]]*:[[:space:]]*"/,"");sub(/".*$/,"");print;exit}' "$T")
  VLESS_ENCRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/{m=1;next}m&&/"encryption"[[:space:]]*:/{sub(/^.*"encryption"[[:space:]]*:[[:space:]]*"/,"");sub(/".*$/,"");print;exit}' "$T")
  rm -f "$T"
  [ -n "$VLESS_DECRYPTION" ] && [ -n "$VLESS_ENCRYPTION" ] || { echo "ERROR: failed to generate VLESS encryption material" >&2; exit 1; }
  atomic_write "$DFILE" "$VLESS_DECRYPTION"
  atomic_write "$EFILE" "$VLESS_ENCRYPTION"
fi

if [ -s "$TFILE" ]; then
  TOKEN=$(tr -d '[:space:]' <"$TFILE")
else
  TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
  atomic_write "$TFILE" "$TOKEN"
fi

export PORT="$G" GATEWAY_PORT="$G" DATA_DIR="$D" XRAY_CONFIG="$C" UUID PRIVATE_KEY PUBLIC_KEY VLESS_DECRYPTION VLESS_ENCRYPTION
export XRAY_PORT="${XRAY_PORT:-10087}" XRAY_HTTP_PORT="${XRAY_HTTP_PORT:-10086}" XRAY_LISTEN=127.0.0.1
export REALITY_TARGET="${REALITY_TARGET:-www.cloudflare.com:443}" REALITY_FINGERPRINT="${REALITY_FINGERPRINT:-chrome}"
export XHTTP_PATH="${XHTTP_PATH:-/xhttp}" XHTTP_MODE="${XHTTP_MODE:-auto}" SHORT_ID="${SHORT_ID:-50175c035ee132}"
export REALITY_SNI_LIMIT="${REALITY_SNI_LIMIT:-7}" REALITY_SNI_CANDIDATES_FILE="${REALITY_SNI_CANDIDATES_FILE:-/opt/xray/config/reality-sni-candidates.txt}"
export PUBLIC_DOMAIN="${PUBLIC_DOMAIN:-${RAILWAY_PUBLIC_DOMAIN:-}}"
export SERVER_HOST="${SERVER_HOST:-${RAILWAY_TCP_PROXY_DOMAIN:-}}" SERVER_PORT="${SERVER_PORT:-${RAILWAY_TCP_PROXY_PORT:-}}"

[ -n "$PUBLIC_DOMAIN" ] || { echo "ERROR: PUBLIC_DOMAIN or RAILWAY_PUBLIC_DOMAIN is required" >&2; exit 1; }
[ -n "$SERVER_HOST" ] && [ -n "$SERVER_PORT" ] || { echo "ERROR: SERVER_HOST and SERVER_PORT are required for REALITY nodes" >&2; exit 1; }

python3 /opt/xray/scripts/generate.py
xray run -test -config "$C"

python3 /opt/xray/scripts/health_proxy.py & HP=$!
printf '%s\n' "$HP" >"$D/gateway.pid"
xray run -config "$C" & XP=$!
printf '%s\n' "$XP" >"$D/xray.pid"
trap 'rm -f "$D/.xray-ready" "$D/xray.pid" "$D/gateway.pid"; kill "$XP" "$HP" 2>/dev/null || true; wait "$XP" 2>/dev/null || true; wait "$HP" 2>/dev/null || true' INT TERM EXIT

READY_TIMEOUT="${READY_TIMEOUT:-60}"
i=0
while :; do
  if kill -0 "$XP" 2>/dev/null && kill -0 "$HP" 2>/dev/null && \
     python3 -c 'import socket; s=socket.create_connection(("127.0.0.1",10087),1); s.close()' 2>/dev/null && \
     python3 -c 'import socket; s=socket.create_connection(("127.0.0.1",10086),1); s.close()' 2>/dev/null && \
     [ -s "$D/subscription.txt" ] && [ -s "$TFILE" ]; then
    break
  fi
  i=$((i + 1))
  [ "$i" -lt "$READY_TIMEOUT" ] || { echo "ERROR: runtime did not become ready within ${READY_TIMEOUT}s" >&2; exit 1; }
  sleep 1
done

printf '%s/sub/%s\n' "https://${PUBLIC_DOMAIN}" "$TOKEN" >"$D/subscription_url.txt"
chmod 600 "$D/subscription_url.txt"
touch "$D/.xray-ready"
python3 /opt/xray/scripts/backup_state.py "$D" "$C" || echo "WARNING: state backup failed; service will continue" >&2

echo "READY: gateway=$G xray_reality=$XRAY_PORT xray_xhttp=$XRAY_HTTP_PORT"

while kill -0 "$XP" 2>/dev/null && kill -0 "$HP" 2>/dev/null; do
  sleep 5
done

echo "ERROR: supervised process exited; restarting container" >&2
exit 1
