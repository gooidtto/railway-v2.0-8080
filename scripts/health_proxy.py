import os
import select
import socket
import threading
from pathlib import Path
from urllib.parse import urlsplit

HTTP_LISTEN_HOST = "0.0.0.0"
HTTP_LISTEN_PORT = int(os.getenv("PUBLIC_HTTP_PORT", "8080"))
GATEWAY_LISTEN_HOST = "0.0.0.0"
GATEWAY_LISTEN_PORT = int(os.getenv("GATEWAY_PORT", os.getenv("PORT", "8080")))
REALITY_HOST = "127.0.0.1"
REALITY_PORT = int(os.getenv("XRAY_PORT", "10085"))
HTTP_XHTTP_HOST = "127.0.0.1"
HTTP_XHTTP_PORT = int(os.getenv("XRAY_HTTP_PORT", "10086"))
READY_FILE = os.getenv("XRAY_READY_FILE", "/data/.xray-ready")
SITE_DIR = Path(os.getenv("SITE_DIR", "/opt/xray/site")).resolve()
SUB_FILE = Path(os.getenv("SUBSCRIPTION_FILE", "/data/subscription.txt"))
SUB_TOKEN_FILE = Path(os.getenv("SUBSCRIPTION_TOKEN_FILE", "/data/subscription_token.txt"))
XHTTP_PATH = os.getenv("XHTTP_PATH", "/xhttp")
PROXY_PROTOCOL = os.getenv("TCP_PROXY_PROTOCOL", "auto").lower()
PROXY_V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"


def log(message):
    print(f"[tcp-proxy] {message}", flush=True)


def ready():
    return Path(READY_FILE).exists()


def tune(sock):
    for level, opt, value in (
        (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
    ):
        try:
            sock.setsockopt(level, opt, value)
        except OSError:
            pass


def response(status, content_type, body, head=False):
    if isinstance(body, str):
        body = body.encode()
    reason = {
        200: "OK",
        404: "Not Found",
        405: "Method Not Allowed",
        503: "Service Unavailable",
    }.get(status, "OK")
    header = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n"
        "X-Content-Type-Options: nosniff\r\n"
        "\r\n"
    ).encode()
    return header if head else header + body


def parse_http(data):
    try:
        head = data.split(b"\r\n\r\n", 1)[0]
        first = head.split(b"\r\n", 1)[0].decode("ascii")
        parts = first.split(" ", 2)
        if len(parts) != 3 or not parts[2].startswith("HTTP/"):
            return None
        return parts[0], urlsplit(parts[1]).path or "/"
    except (UnicodeDecodeError, ValueError):
        return None


def is_tls(data):
    return len(data) >= 3 and data[0] == 0x16 and data[1] == 0x03 and data[2] in (1, 2, 3, 4)


def proxy_header_length(data):
    if PROXY_PROTOCOL == "off":
        return 0
    if data.startswith(b"PROXY "):
        end = data.find(b"\r\n")
        return None if end < 0 else end + 2
    if data.startswith(PROXY_V2_SIGNATURE):
        if len(data) < 16:
            return None
        total = 16 + int.from_bytes(data[14:16], "big")
        return total if len(data) >= total else None
    return 0


def strip_proxy_header(data):
    length = proxy_header_length(data)
    if length is None:
        return data, True
    return (data[length:], False) if length else (data, False)


def recv_initial(sock, timeout=10):
    sock.settimeout(timeout)
    data = bytearray()
    methods = (
        b"GET ", b"HEAD ", b"POST ", b"PUT ", b"DELETE ",
        b"OPTIONS ", b"PATCH ", b"CONNECT ",
    )
    proxy_header_seen = False

    while len(data) < 16384:
        chunk = sock.recv(min(4096, 16384 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        raw = bytes(data)

        if not proxy_header_seen:
            raw, pending = strip_proxy_header(raw)
            if pending:
                continue
            proxy_header_seen = True
            data = bytearray(raw)

        if not raw:
            continue
        if is_tls(raw):
            return raw, "tls"
        if b"\r\n\r\n" in raw or b"\n\n" in raw:
            return raw, "http"
        if len(raw) >= 3 and not raw.startswith(methods):
            return raw, "tcp"

    raw = bytes(data)
    if not proxy_header_seen:
        raw, _ = strip_proxy_header(raw)
    if not raw:
        return b"", "empty"
    if is_tls(raw):
        return raw, "tls"
    return raw, "http" if raw.startswith(methods) else "tcp"


def relay(client, upstream, initial=b""):
    tune(client)
    tune(upstream)
    client.settimeout(None)
    upstream.settimeout(None)
    if initial:
        upstream.sendall(initial)

    client_to_server = len(initial)
    server_to_client = 0
    while True:
        readable, _, bad = select.select((client, upstream), (), (client, upstream), 300)
        if bad or not readable:
            return client_to_server, server_to_client
        for source in readable:
            target = upstream if source is client else client
            chunk = source.recv(65536)
            if not chunk:
                return client_to_server, server_to_client
            target.sendall(chunk)
            if source is client:
                client_to_server += len(chunk)
            else:
                server_to_client += len(chunk)


def connect(host, port):
    upstream = socket.create_connection((host, port), timeout=10)
    tune(upstream)
    return upstream


def token():
    try:
        return SUB_TOKEN_FILE.read_text().strip()
    except OSError:
        return ""


def handle_http(client, method, path):
    if path == XHTTP_PATH or path.startswith(XHTTP_PATH + "/"):
        return False
    if method not in {"GET", "HEAD"}:
        client.sendall(response(405, "text/plain; charset=utf-8", "Method Not Allowed\n"))
        return True

    head = method == "HEAD"
    if path == "/health":
        client.sendall(response(200, "text/plain; charset=utf-8", "OK\n", head))
        return True
    if path == "/ready":
        ok = ready()
        client.sendall(response(200 if ok else 503, "text/plain; charset=utf-8", "READY\n" if ok else "NOT READY\n", head))
        return True
    if path.startswith("/sub/"):
        current_token = token()
        if not current_token or path != "/sub/" + current_token or not SUB_FILE.is_file():
            client.sendall(response(404, "text/plain; charset=utf-8", "Not Found\n", head))
        else:
            client.sendall(response(200, "text/plain; charset=utf-8", SUB_FILE.read_bytes(), head))
        return True
    if path == "/sub":
        client.sendall(response(404, "text/plain; charset=utf-8", "Not Found\n", head))
        return True

    relative = "index.html" if path == "/" else path.lstrip("/")
    target = (SITE_DIR / relative).resolve()
    if (SITE_DIR not in target.parents and target != SITE_DIR) or not target.is_file():
        client.sendall(response(404, "text/plain; charset=utf-8", "Not Found\n", head))
        return True

    body = target.read_bytes()
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    client.sendall(response(200, content_types.get(target.suffix.lower(), "application/octet-stream"), body, head))
    return True


def handle(client, allow_tls=True, listener="gateway"):
    peer = "unknown"
    upstream = None
    try:
        address = client.getpeername()
        peer = f"{address[0]}:{address[1]}"
    except OSError:
        pass

    tune(client)
    log(
        f"ACCEPT listener={listener} peer={peer} "
        f"reality={REALITY_HOST}:{REALITY_PORT} "
        f"http_xhttp={HTTP_XHTTP_HOST}:{HTTP_XHTTP_PORT} "
        f"ready={ready()} proxy_protocol={PROXY_PROTOCOL}"
    )

    try:
        initial, kind = recv_initial(client)
        if not initial:
            log(f"CLOSE listener={listener} peer={peer} reason=no-initial-data")
            return

        log(f"CLASSIFY listener={listener} peer={peer} kind={kind} bytes={len(initial)} head={initial[:12].hex()}")

        if kind == "tls":
            if not allow_tls:
                return
            upstream = connect(REALITY_HOST, REALITY_PORT)
            log(f"UPSTREAM_CONNECTED listener={listener} peer={peer} target={REALITY_HOST}:{REALITY_PORT} kind=tls-reality")
            sent, received = relay(client, upstream, initial)
            log(f"RELAY_END listener={listener} peer={peer} kind=tls-reality c2s={sent} s2c={received}")
            return

        parsed = parse_http(initial)
        if parsed:
            method, path = parsed
            log(f"HTTP listener={listener} peer={peer} method={method} path={path}")
            if handle_http(client, method, path):
                log(f"HTTP_END listener={listener} peer={peer} path={path}")
                return
            kind = "http-xhttp"

        target = (HTTP_XHTTP_HOST, HTTP_XHTTP_PORT) if kind == "http-xhttp" else (REALITY_HOST, REALITY_PORT)
        upstream = connect(*target)
        log(f"UPSTREAM_CONNECTED listener={listener} peer={peer} target={target[0]}:{target[1]} kind={kind}")
        sent, received = relay(client, upstream, initial)
        log(f"RELAY_END listener={listener} peer={peer} kind={kind} c2s={sent} s2c={received}")
    except (OSError, TimeoutError) as exc:
        log(f"ERROR listener={listener} peer={peer} type={type(exc).__name__} detail={exc}")
    finally:
        if upstream:
            try:
                upstream.close()
            except OSError:
                pass
        try:
            client.close()
        except OSError:
            pass
        log(f"CLOSE listener={listener} peer={peer}")


def serve(port, allow_tls, listener):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", port))
        server.listen(256)
        log(
            f"LISTEN listener={listener} 0.0.0.0:{port} tls={allow_tls} "
            f"reality={REALITY_HOST}:{REALITY_PORT} http_xhttp={HTTP_XHTTP_HOST}:{HTTP_XHTTP_PORT}"
        )
        while True:
            client, _ = server.accept()
            threading.Thread(target=handle, args=(client, allow_tls, listener), daemon=True).start()


def main():
    if HTTP_LISTEN_PORT == GATEWAY_LISTEN_PORT:
        serve(GATEWAY_LISTEN_PORT, True, "gateway")
        return

    threads = [
        threading.Thread(target=serve, args=(HTTP_LISTEN_PORT, False, "http"), daemon=True),
        threading.Thread(target=serve, args=(GATEWAY_LISTEN_PORT, True, "gateway"), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
