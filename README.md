# railway-v1.0-8080

Railway + Xray XHTTP/REALITY deployment with a verified 7-SNI pool.

## Architecture

```text
Public HTTPS :443
        |
Railway gateway :8080
        +-- /sub/* /health /ready /site -> HTTP handler
        +-- /xhttp/* -> Xray XHTTP :10086
        `-- non-HTTP/TCP -> Xray REALITY + XHTTP :10087
```

The subscription contains 8 nodes: 1 HTTPS + XHTTP node and 7 Railway TCP Proxy + XHTTP + REALITY nodes.

## Verified SNI pool

- www.cloudflare.com
- www.bing.com
- www.canva.com
- www.notion.so
- store.epicgames.com
- www.gog.com
- www.gamespot.com

Only tested SNI values belong in the production pool.

## Layout

```text
config/reality-sni-candidates.txt
scripts/generate.py
scripts/health_proxy.py
scripts/start.sh
site/index.html
Dockerfile
railway.toml
.gitignore
.dockerignore
```

## Deployment

Railway should provide public HTTP port 8080, a TCP Proxy for REALITY nodes, and preferably a persistent volume mounted at /data.

The public domain is controlled by PUBLIC_DOMAIN. Runtime UUID, REALITY keys, VLESS material and subscription token are stored under /data.

Subscription endpoint:

```text
https://<public-domain>/sub/<subscription-token>
```

Health endpoints: `/health` and `/ready`.

## Stability baseline

The current production baseline is the verified HTTPS/XHTTP node plus the 7 verified REALITY SNI nodes. Preserve this baseline when testing future transport or SNI changes.
