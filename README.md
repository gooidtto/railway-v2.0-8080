# railway-v2.0-8080

Railway + Xray XHTTP/REALITY deployment with a verified 7-SNI pool and a persistence-first runtime design.

## Long-term stability baseline

The production transport baseline is intentionally preserved:

- 1 HTTPS + XHTTP node
- 7 Railway TCP Proxy + XHTTP + REALITY nodes
- UUID, REALITY keys, VLESS material, and subscription token persisted under `/data`
- Xray configuration tested before launch
- `/ready` reflects live gateway, Xray, listener, and subscription state
- Runtime configuration and subscription files are written atomically
- Gateway connection count is bounded to prevent runaway thread growth
- Runtime state is snapshotted after successful startup; only the newest 5 snapshots are retained
- Subscription token rotation is manual, never automatic

Do not change transport, SNI, or Xray version together with operational hardening changes. Validate one class of change at a time.

## Architecture

```text
Public HTTPS :443
        |
Railway gateway :8080
        +-- /health -> gateway liveness
        +-- /ready  -> live runtime readiness
        +-- /sub/*  -> authenticated subscription
        +-- /xhttp/* -> Xray XHTTP :10086
        `-- non-HTTP/TCP -> Xray REALITY + XHTTP :10087
```

The subscription contains 8 nodes: 1 HTTPS + XHTTP node and 7 Railway TCP Proxy + XHTTP + REALITY nodes.

## Verified SNI pool

Only verified SNI values belong in the production pool:

- www.cloudflare.com
- www.bing.com
- www.canva.com
- www.notion.so
- store.epicgames.com
- www.gog.com
- www.gamespot.com

The pool count is validated at startup. A mismatch fails closed instead of generating a partial production configuration.

## Persistent state and recovery

When a Railway Volume is mounted at `/data`, identity material survives container restarts:

```text
/data/uuid.txt
/data/reality_private_key.txt
/data/reality_public_key.txt
/data/vless_decryption.txt
/data/vless_encryption.txt
/data/subscription_token.txt
/data/subscription_url.txt
/data/subscription.txt
/data/vless.txt
/data/reality-sni-list.txt
```

After a successful startup, `scripts/backup_state.py` creates a restricted `tar.gz` snapshot under `/data/backups/`. The snapshot contains identity material and runtime configuration, so it is sensitive. Keep an external/offline copy if the deployment identity must survive loss of the Railway Volume. The runtime retains only the newest five snapshots.

Do not delete or replace identity files during normal maintenance unless intentionally rotating the deployment identity.

## Subscription token rotation

The subscription token is intentionally stable across normal restarts. If the URL is exposed, rotate it manually:

```text
python3 /opt/xray/scripts/rotate_subscription_token.py /data
```

Rotation invalidates the previous token immediately. Existing clients using the old URL must be updated with the new subscription URL. Never automate token rotation as part of normal startup.

## Required Railway settings

The runtime expects a public HTTP service on port `8080` and a TCP Proxy for the REALITY nodes. Railway-provided values are used automatically when available:

- `RAILWAY_PUBLIC_DOMAIN`
- `RAILWAY_TCP_PROXY_DOMAIN`
- `RAILWAY_TCP_PROXY_PORT`

You can override them with:

- `PUBLIC_DOMAIN`
- `SERVER_HOST`
- `SERVER_PORT`

There is no hard-coded production-domain fallback. A missing public domain or TCP proxy configuration fails closed during startup.

A persistent Volume mounted at `/data` is strongly recommended for long-term stability.

## Health and readiness

- `/health` confirms the gateway process is accepting HTTP requests.
- `/ready` returns `200` only when the readiness marker exists, both supervised processes are alive, both Xray listeners are reachable, and subscription/token state is present.
- Railway uses `/ready` as its deployment healthcheck.

The startup supervisor exits the container if either Xray or the gateway process dies, allowing Railway's restart policy to recover the service.

## Configuration safety

Runtime configuration is generated into temporary files and atomically renamed into place. Identity files are also written atomically. This prevents a restart or interrupted write from leaving truncated credentials, `config.json`, or subscription files.

The gateway also has configurable limits:

```text
GATEWAY_BACKLOG=512
GATEWAY_MAX_CONNECTIONS=512
RELAY_IDLE_TIMEOUT=900
READY_TIMEOUT=60
```

These defaults are conservative and can be overridden through Railway environment variables.

## CI

Every push to `main`, `stability-hardening`, or `long-term-stable`, and every pull request to `main`, runs:

1. Shell syntax validation
2. Python compilation
3. Deterministic configuration-generation smoke test
4. Production Docker image build
5. Production container runtime smoke test
6. `/health` and `/ready` checks
7. Subscription and runtime backup existence checks

The CI runtime test uses synthetic credentials and a temporary volume. No production secrets are stored in the repository.

## Deployment rule

Treat the currently working production configuration as the baseline. Operational hardening should not silently alter the verified transport or SNI set. Changes that affect transport, Xray version, or the SNI pool should be validated separately before promotion.
