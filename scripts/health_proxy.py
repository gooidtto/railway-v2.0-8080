import os
import select
import socket
import threading
from pathlib import Path

PORT = int(os.getenv("PORT", "8080"))
REALITY = ("127.0.0.1", int(os.getenv("XRAY_PORT", "10087")))
XHTTP = ("127.0.0.1", int(os.getenv("XRAY_HTTP_PORT", "10086")))
SITE = Path(os.getenv("SITE_DIR", "/opt/xray/site"))
DATA = Path(os.getenv("DATA_DIR", "/data"))
SUB = Path(os.getenv("SUBSCRIPTION_FILE", str(DATA / "subscription.txt")))
TOKEN = Path(os.getenv("SUBSCRIPTION_TOKEN_FILE", str(DATA / "subscription_token.txt")))
READY = Path(os.getenv("XRAY_READY_FILE", str(DATA / ".xray-ready")))
XRAY_PID = Path(os.getenv("XRAY_PID_FILE", str(DATA / "xray.pid")))
GATEWAY_PID = Path(os.getenv("GATEWAY_PID_FILE", str(DATA / "gateway.pid")))
BACKLOG = int(os.getenv("GATEWAY_BACKLOG", "512"))
MAX_CONNECTIONS = int(os.getenv("GATEWAY_MAX_CONNECTIONS", "512"))
RELAY_IDLE_TIMEOUT = int(os.getenv("RELAY_IDLE_TIMEOUT", "900"))

CONNECTIONS = threading.BoundedSemaphore(MAX_CONNECTIONS)


def pid_alive(path):
    try:
        pid = int(path.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, FileNotFoundError):
        return False


def backend_ready(endpoint):
    try:
        with socket.create_connection(endpoint, 1):
            return True
    except OSError:
        return False


def runtime_ready():
    return all((READY.exists(), pid_alive(XRAY_PID), pid_alive(GATEWAY_PID), backend_ready(REALITY), backend_ready(XHTTP), SUB.is_file(), SUB.stat().st_size > 0 if SUB.exists() else False, TOKEN.is_file(), TOKEN.stat().st_size > 0 if TOKEN.exists() else False))


def relay(a, b, first=b""):
    if first:
        b.sendall(first)
    while True:
        readable, _, exceptional = select.select((a, b), (), (a, b), RELAY_IDLE_TIMEOUT)
        if exceptional or not readable:
            return
        for source in readable:
            target = b if source is a else a
            data = source.recv(65536)
            if not data:
                return
            target.sendall(data)


def reply(code, content_type, body):
    if isinstance(body, str):
        body = body.encode()
    reason = {200: "OK", 404: "Not Found", 503: "Service Unavailable"}[code]
    return (
        f"HTTP/1.1 {code} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n"
        "X-Content-Type-Options: nosniff\r\n"
        "\r\n"
    ).encode() + body


def connect_backend(endpoint):
    return socket.create_connection(endpoint, 10)


def handle(c):
    acquired = CONNECTIONS.acquire(blocking=False)
    if not acquired:
        try:
            c.sendall(reply(503, "text/plain", "Gateway busy\n"))
        except OSError:
            pass
        finally:
            c.close()
        return

    try:
        c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        c.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        c.settimeout(10)
        first = c.recv(16384)
        if not first:
            return

        methods = (b"GET ", b"HEAD ", b"POST ", b"PUT ", b"DELETE ", b"OPTIONS ", b"PATCH ")
        if first.startswith(methods):
            line = first.split(b"\r\n", 1)[0].decode("latin1", "ignore").split(" ", 2)
            if len(line) < 2:
                return
            path = line[1].split("?", 1)[0]

            if path == "/health":
                c.sendall(reply(200, "text/plain", "OK\n"))
                return
            if path == "/ready":
                c.sendall(reply(200 if runtime_ready() else 503, "text/plain", "READY\n" if runtime_ready() else "NOT READY\n"))
                return
            if path == "/":
                index = SITE / "index.html"
                if not index.is_file():
                    c.sendall(reply(404, "text/plain", "Not Found\n"))
                    return
                c.sendall(reply(200, "text/html; charset=utf-8", index.read_bytes()))
                return
            if path.startswith("/sub/"):
                tok = TOKEN.read_text().strip() if TOKEN.exists() else ""
                if path == "/sub/" + tok and SUB.is_file():
                    c.sendall(reply(200, "text/plain; charset=utf-8", SUB.read_bytes()))
                    return
                c.sendall(reply(404, "text/plain", "Not Found\n"))
                return
            if path.startswith("/xhttp"):
                u = connect_backend(XHTTP)
                try:
                    relay(c, u, first)
                finally:
                    u.close()
                return

            c.sendall(reply(404, "text/plain", "Not Found\n"))
            return

        u = connect_backend(REALITY)
        try:
            relay(c, u, first)
        finally:
            u.close()
    except (OSError, TimeoutError):
        pass
    finally:
        try:
            c.close()
        except OSError:
            pass
        CONNECTIONS.release()


with socket.socket() as s:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    s.bind(("0.0.0.0", PORT))
    s.listen(BACKLOG)
    print(f"gateway listening on :{PORT} backlog={BACKLOG} max_connections={MAX_CONNECTIONS}", flush=True)
    while True:
        c, _ = s.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()
