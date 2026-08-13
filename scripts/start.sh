#!/bin/sh
set -eu
D="${RAILWAY_VOLUME_MOUNT_PATH:-${DATA_DIR:-/data}}"; G="${GATEWAY_PORT:-${PORT:-8080}}"; C="${XRAY_CONFIG:-/etc/xray/config.json}"
mkdir -p "$D" "$(dirname "$C")"; chmod 700 "$D"; rm -f "$D/.xray-ready"
UFILE="$D/uuid.txt"; PFILE="$D/reality_private_key.txt"; PUBFILE="$D/reality_public_key.txt"; DFILE="$D/vless_decryption.txt"; EFILE="$D/vless_encryption.txt"; TFILE="$D/subscription_token.txt"
if [ -s "$UFILE" ];then UUID=$(tr -d '[:space:]'<"$UFILE");else UUID=$(xray uuid);printf '%s\n' "$UUID">"$UFILE";fi
if [ -s "$PFILE" ]&&[ -s "$PUBFILE" ];then PRIVATE_KEY=$(tr -d '[:space:]'<"$PFILE");PUBLIC_KEY=$(tr -d '[:space:]'<"$PUBFILE");else OUT=$(xray x25519 2>&1);PRIVATE_KEY=$(printf '%s\n' "$OUT"|awk '/^PrivateKey/{sub(/^[^:]*:[[:space:]]*/,"");print;exit}');PUBLIC_KEY=$(printf '%s\n' "$OUT"|awk '/^Password/{sub(/^[^:]*:[[:space:]]*/,"");print;exit}');printf '%s\n' "$PRIVATE_KEY">"$PFILE";printf '%s\n' "$PUBLIC_KEY">"$PUBFILE";fi
if [ -s "$DFILE" ]&&[ -s "$EFILE" ];then VLESS_DECRYPTION=$(tr -d '[:space:]'<"$DFILE");VLESS_ENCRYPTION=$(tr -d '[:space:]'<"$EFILE");else T="$D/.vlessenc.tmp";xray vlessenc>"$T" 2>&1;VLESS_DECRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/{m=1;next}m&&/"decryption"[[:space:]]*:/{sub(/^.*"decryption"[[:space:]]*:[[:space:]]*"/,"");sub(/".*$/,"");print;exit}' "$T");VLESS_ENCRYPTION=$(awk '/Authentication:[[:space:]]*ML-KEM-768,[[:space:]]*Post-Quantum/{m=1;next}m&&/"encryption"[[:space:]]*:/{sub(/^.*"encryption"[[:space:]]*:[[:space:]]*"/,"");sub(/".*$/,"");print;exit}' "$T");rm -f "$T";printf '%s\n' "$VLESS_DECRYPTION">"$DFILE";printf '%s\n' "$VLESS_ENCRYPTION">"$EFILE";fi
if [ -s "$TFILE" ];then TOKEN=$(tr -d '[:space:]'<"$TFILE");else TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))');printf '%s\n' "$TOKEN">"$TFILE";fi
export PORT="$G" GATEWAY_PORT="$G" DATA_DIR="$D" XRAY_CONFIG="$C" UUID PRIVATE_KEY PUBLIC_KEY VLESS_DECRYPTION VLESS_ENCRYPTION
export XRAY_PORT="${XRAY_PORT:-10087}" XRAY_HTTP_PORT="${XRAY_HTTP_PORT:-10086}" XRAY_LISTEN=127.0.0.1 REALITY_TARGET="${REALITY_TARGET:-www.cloudflare.com:443}" REALITY_FINGERPRINT="${REALITY_FINGERPRINT:-chrome}" XHTTP_PATH="${XHTTP_PATH:-/xhttp}" XHTTP_MODE="${XHTTP_MODE:-auto}" SHORT_ID="${SHORT_ID:-50175c035ee132}" REALITY_SNI_LIMIT="${REALITY_SNI_LIMIT:-7}" REALITY_SNI_CANDIDATES_FILE="${REALITY_SNI_CANDIDATES_FILE:-/opt/xray/config/reality-sni-candidates.txt}" PUBLIC_DOMAIN="${PUBLIC_DOMAIN:-railway-v10-8080-production.up.railway.app}" SERVER_HOST="${SERVER_HOST:-${RAILWAY_TCP_PROXY_DOMAIN:-}}" SERVER_PORT="${SERVER_PORT:-${RAILWAY_TCP_PROXY_PORT:-}}"
python3 /opt/xray/scripts/generate.py
python3 /opt/xray/scripts/health_proxy.py&HP=$!
xray run -test -config "$C";xray run -config "$C"&XP=$!
trap 'kill "$XP" "$HP" 2>/dev/null||true;wait "$XP" 2>/dev/null||true' INT TERM EXIT
for _ in $(seq 1 60);do python3 -c 'import socket;s=socket.create_connection(("127.0.0.1",10087),1);s.close()'&&break;sleep 1;done
printf '%s/sub/%s\n' "https://${PUBLIC_DOMAIN}" "$TOKEN">"$D/subscription_url.txt";touch "$D/.xray-ready";wait "$XP"
