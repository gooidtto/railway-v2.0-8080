import base64
import os
import select
import socket
import threading
from pathlib import Path

PORT = 8080
XHTTP = ("127.0.0.1", 10086)
SITE = Path("/opt/xray/site")
SUB = Path(os.getenv("SUBSCRIPTION_FILE", "/data/subscription.txt"))
TOKEN = Path(os.getenv("SUBSCRIPTION_TOKEN_FILE", "/data/subscription_token.txt"))
READY = Path(os.getenv("XRAY_READY_FILE", "/data/.xray-ready"))
CONNECTIONS = threading.BoundedSemaphore(512)


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
        "X-Content-Type-Options: nosniff\r\n\r\n"
    ).encode() + body


def relay(a, b, first=b""):
    if first:
        b.sendall(first)
    while True:
        readable, _, exceptional = select.select((a, b), (), (a, b), 900)
        if exceptional or not readable:
            return
        for source in readable:
            target = b if source is a else a
            data = source.recv(65536)
            if not data:
                return
            target.sendall(data)


def handle(c):
    if not CONNECTIONS.acquire(blocking=False):
        try:
            c.sendall(reply(503, "text/plain", "Gateway busy\n"))
        finally:
            c.close()
        return
    try:
        c.settimeout(10)
        first = c.recv(16384)
        if not first:
            return
        methods = (b"GET ", b"HEAD ", b"POST ", b"PUT ", b"DELETE ", b"OPTIONS ", b"PATCH ")
        if not first.startswith(methods):
            return
        line = first.split(b"\r\n", 1)[0].decode("latin1", "ignore").split(" ", 2)
        if len(line) < 2:
            return
        path = line[1].split("?", 1)[0]
        if path == "/health":
            c.sendall(reply(200, "text/plain", "OK\n"))
            return
        if path == "/ready":
            ok = READY.exists() and SUB.is_file() and SUB.read_text().strip()
            c.sendall(reply(200 if ok else 503, "text/plain", "READY\n" if ok else "NOT READY\n"))
            return
        if path == "/":
            index = SITE / "index.html"
            if not index.is_file():
                c.sendall(reply(404, "text/plain", "Not Found\n"))
                return
            c.sendall(reply(200, "text/html; charset=utf-8", index.read_bytes()))
            return
        if path.startswith("/sub/"):
            token = TOKEN.read_text().strip() if TOKEN.exists() else ""
            if path == "/sub/" + token and SUB.is_file():
                raw = SUB.read_text().strip()
                try:
                    decoded = base64.b64decode(raw, validate=True).decode()
                except Exception:
                    decoded = ""
                lines = [x for x in decoded.splitlines() if x.strip()]
                if len(lines) == 4 and all(x.startswith("vless://") for x in lines):
                    c.sendall(reply(200, "text/plain; charset=utf-8", (raw + "\n").encode()))
                    return
            c.sendall(reply(404, "text/plain", "Not Found\n"))
            return
        if path.startswith("/xhttp"):
            u = socket.create_connection(XHTTP, 10)
            try:
                relay(c, u, first)
            finally:
                u.close()
            return
        c.sendall(reply(404, "text/plain", "Not Found\n"))
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
    s.listen(512)
    print("gateway listening on :8080", flush=True)
    while True:
        c, _ = s.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()
