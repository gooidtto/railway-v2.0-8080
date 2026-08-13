import base64,json,os,re
from pathlib import Path
from urllib.parse import quote,urlparse
def env(n,d=None,r=False):
 v=os.getenv(n,d)
 if r and not v: raise SystemExit(f"ERROR: missing {n}")
 return v
D=Path(env("DATA_DIR","/data")); C=Path(env("XRAY_CONFIG","/etc/xray/config.json"))
u=env("UUID",r=True); priv=env("PRIVATE_KEY",r=True); pub=env("PUBLIC_KEY",r=True)
dec=env("VLESS_DECRYPTION",r=True); enc=env("VLESS_ENCRYPTION",r=True)
def target(v):
 v=(v or "").strip()
 if v.startswith(("http://","https://")): v=urlparse(v).netloc or urlparse(v).path
 v=v.strip("[]").rstrip("/")
 if ":" not in v: v+=":443"
 h,p=v.rsplit(":",1)
 if not re.fullmatch(r"[A-Za-z0-9.-]+",h) or not p.isdigit() or not 1<=int(p)<=65535: raise SystemExit("ERROR: invalid REALITY_TARGET")
 return f"{h}:{int(p)}"
rt=target(env("REALITY_TARGET","www.cloudflare.com:443")); fp=env("REALITY_FINGERPRINT","chrome"); path=env("XHTTP_PATH","/xhttp"); mode=env("XHTTP_MODE","auto"); sid=env("SHORT_ID","50175c035ee132")
domain=env("PUBLIC_DOMAIN","railway-v10-8080-production.up.railway.app").strip(); sh=env("SERVER_HOST","").strip(); sp=env("SERVER_PORT","").strip()
if not sh or not sp: raise SystemExit("ERROR: SERVER_HOST and SERVER_PORT are required")
sf=Path(env("REALITY_SNI_CANDIDATES_FILE","/opt/xray/config/reality-sni-candidates.txt"))
pool=list(dict.fromkeys(x.strip() for x in sf.read_text().splitlines() if x.strip() and not x.startswith("#")))
if len(pool)!=int(env("REALITY_SNI_LIMIT","7")): raise SystemExit("ERROR: verified SNI pool count mismatch")
base={"listen":"127.0.0.1","port":int(env("XRAY_PORT","10087")),"protocol":"vless","settings":{"clients":[{"id":u}],"decryption":dec},"streamSettings":{"network":"xhttp","security":"reality","realitySettings":{"show":False,"target":rt,"xver":0,"serverNames":pool,"privateKey":priv,"shortIds":[sid]},"xhttpSettings":{"path":path,"mode":mode}}}
plain={"listen":"127.0.0.1","port":int(env("XRAY_HTTP_PORT","10086")),"protocol":"vless","settings":{"clients":[{"id":u}],"decryption":dec},"streamSettings":{"network":"xhttp","security":"none","xhttpSettings":{"path":path,"mode":mode}}}
C.parent.mkdir(parents=True,exist_ok=True); tmp=str(C)+".tmp"; Path(tmp).write_text(json.dumps({"log":{"loglevel":env("XRAY_LOGLEVEL","info")},"inbounds":[base,plain],"outbounds":[{"protocol":"freedom","tag":"direct"}]},indent=2)+"\n"); os.chmod(tmp,0o600); os.replace(tmp,C)
nodes=[f"vless://{u}@{domain}:443/?encryption={quote(enc,safe='')}&security=tls&type=xhttp&fp={fp}&sni={quote(domain,safe='')}&alpn=h2%2Chttp%2F1.1&path={quote(path,safe='')}&mode={quote(mode,safe='')}#railway-xhttp-https-{domain}"]
for s in pool: nodes.append(f"vless://{u}@{sh}:{sp}/?encryption={quote(enc,safe='')}&security=reality&type=xhttp&fp={fp}&sni={quote(s,safe='')}&pbk={quote(pub,safe='')}&sid={sid}&path={quote(path,safe='')}&mode={quote(mode,safe='')}#railway-xhttp-reality-{s}")
text="\n".join(nodes)+"\n"; D.mkdir(parents=True,exist_ok=True); (D/"vless.txt").write_text(text); (D/"subscription.txt").write_text(base64.b64encode(text.encode()).decode()+"\n"); os.chmod(D/"subscription.txt",0o600); (D/"reality-sni-list.txt").write_text("\n".join(pool)+"\n")
print(f"HTTPS XHTTP node generated: {domain}:443"); print(f"REALITY SNI nodes generated: {len(pool)}")
