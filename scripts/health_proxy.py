import os,select,socket,threading
from pathlib import Path
PORT=int(os.getenv("PORT","8080")); REALITY=("127.0.0.1",int(os.getenv("XRAY_PORT","10087"))); XHTTP=("127.0.0.1",int(os.getenv("XRAY_HTTP_PORT","10086")))
SITE=Path(os.getenv("SITE_DIR","/opt/xray/site")); SUB=Path(os.getenv("SUBSCRIPTION_FILE","/data/subscription.txt")); TOKEN=Path(os.getenv("SUBSCRIPTION_TOKEN_FILE","/data/subscription_token.txt")); READY=Path(os.getenv("XRAY_READY_FILE","/data/.xray-ready"))
def relay(a,b,first=b""):
 if first:b.sendall(first)
 while 1:
  r,_,e=select.select((a,b),(),(a,b),300)
  if e or not r:return
  for s in r:
   d=b if s is a else a; x=s.recv(65536)
   if not x:return
   d.sendall(x)
def reply(code,ct,body):
 if isinstance(body,str):body=body.encode()
 reason={200:"OK",404:"Not Found",503:"Service Unavailable"}[code]
 return (f"HTTP/1.1 {code} {reason}\r\nContent-Type: {ct}\r\nContent-Length: {len(body)}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n").encode()+body
def handle(c):
 try:
  c.settimeout(10); first=c.recv(16384)
  if not first:return
  methods=(b"GET ",b"HEAD ",b"POST ",b"PUT ",b"DELETE ",b"OPTIONS ",b"PATCH ")
  if first.startswith(methods):
   line=first.split(b"\r\n",1)[0].decode("latin1","ignore").split(" ",2); path=line[1].split("?",1)[0]
   if path=="/health":c.sendall(reply(200,"text/plain","OK\n"));return
   if path=="/ready":c.sendall(reply(200 if READY.exists() else 503,"text/plain","READY\n" if READY.exists() else "NOT READY\n"));return
   if path=="/":c.sendall(reply(200,"text/html",(SITE/"index.html").read_bytes()));return
   if path.startswith("/sub/"):
    tok=TOKEN.read_text().strip() if TOKEN.exists() else ""
    if path=="/sub/"+tok and SUB.is_file():c.sendall(reply(200,"text/plain",SUB.read_bytes()));return
    c.sendall(reply(404,"text/plain","Not Found\n"));return
   if path.startswith("/xhttp"):
    u=socket.create_connection(XHTTP,10);relay(c,u,first);u.close();return
   c.sendall(reply(404,"text/plain","Not Found\n"));return
  u=socket.create_connection(REALITY,10);relay(c,u,first);u.close()
 except (OSError,TimeoutError):pass
 finally:
  try:c.close()
  except OSError:pass
with socket.socket() as s:
 s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(("0.0.0.0",PORT));s.listen(256)
 print(f"gateway listening on :{PORT}",flush=True)
 while 1:
  c,_=s.accept();threading.Thread(target=handle,args=(c,),daemon=True).start()
