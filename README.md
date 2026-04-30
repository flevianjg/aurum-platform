# aurum-platform

## 1. What this is

`aurum-platform` is the multi-user web platform that will eventually host the AURUM
trading system for Flevian and a small set of family members. **Phase 1** (this
codebase, today) is the foundation: a Docker Compose stack that brings up
Postgres, Redis, a FastAPI backend with passkey (WebAuthn) authentication, and a
Caddy reverse proxy ready to sit behind a Cloudflare Tunnel. There is no
frontend, no broker connectivity, and no AURUM integration yet — those land in
later phases.

The existing AURUM core at `C:\Users\flevi\aurum` is **not** touched by this
project. aurum-platform will consume AURUM as a dependency in Phase 4.

---

## 2. Prerequisites

| Requirement                                                                 | Notes                                                |
| --------------------------------------------------------------------------- | ---------------------------------------------------- |
| **Docker Desktop** with the WSL2 backend                                    | Required for `docker compose`. Start Docker Desktop. |
| **Python 3.12**                                                             | Only needed for running `scripts/generate_keys.py`.  |
| **Cloudflare account** with `anvisutra.com` already added as a managed zone | Needed for the public tunnel (Section 6).            |
| **`cloudflared`** CLI installed on Windows                                  | Only needed once the tunnel is being set up.         |
| **`git`**                                                                   | Repo is git-tracked from the first commit.           |

---

## 3. First-time setup

```bash
# 1. Clone (or just cd into the repo if already on disk)
cd C:\Users\flevi\aurum-platform

# 2. Generate cryptographic material — DO NOT reuse across environments
python scripts/generate_keys.py

# 3. Copy the env template and paste in the generated values
cp .env.example .env
# then edit .env: paste MASTER_KEY, JWT_SECRET, POSTGRES_PASSWORD,
# update DATABASE_URL with the new password, and set OWNER_EMAIL/OWNER_DISPLAY_NAME

# 4. Sanity-check (.env must NOT be committed)
git status            # .env should not appear
```

> The `.env` file lives at the repo root and is consumed by both
> `docker-compose.yml` and the backend container.

---

## 4. Running locally

Bring the whole stack up:

```bash
docker compose up --build
```

What happens:

1. `postgres` and `redis` start and become healthy.
2. `backend` runs `alembic upgrade head`, then launches Uvicorn on `:8000`.
3. `caddy` reverse-proxies `:8080` → `backend:8000`, adding security headers.

Once `backend` reports healthy, seed your owner user (one-time):

```bash
docker compose exec backend python -m scripts.seed_owner
# or: docker compose run --rm backend python /app/../scripts/seed_owner.py
```

Verify locally:

```bash
curl -i http://localhost:8090/healthz
# HTTP/1.1 200 OK
# {"status":"ok"}

curl -i http://localhost:8090/readyz
# HTTP/1.1 200 OK
# {"status":"ready"}
```

To shut down without losing data:

```bash
docker compose down
```

To wipe Postgres / Redis volumes too:

```bash
docker compose down -v
```

---

## 5. Running tests

The test suite spins up its own database (`aurum_test` by default) on the same
Postgres container, applies all migrations, runs against the real Postgres +
Redis, and tears down at the end.

```bash
docker compose run --rm backend pip install -e .[dev]
docker compose run --rm backend pytest -v
```

Or in a single shot the first time:

```bash
docker compose run --rm backend sh -c "pip install -e .[dev] && pytest -v"
```

Targets:

* `tests/test_health.py` — `/healthz`, `/readyz`
* `tests/test_auth.py`  — passkey register/login (WebAuthn signature mocked),
  refresh rotation, refresh-reuse detection, logout, `/me`
* `tests/test_audit.py` — every covered endpoint writes to `audit_log`,
  `audit_log` is append-only at the DB layer

---

## 6. Cloudflare Tunnel setup (one-time, manual)

Phase 1 exposes the local Caddy on `127.0.0.1:8090` (port 8080 was in use by another local service on this host). Cloudflare Tunnel is what
gives you `https://anvisutra.com` from your phone.

```powershell
# 1. Install cloudflared on Windows (winget or download from cloudflare.com)
winget install --id Cloudflare.cloudflared

# 2. Authenticate (opens browser, pick the anvisutra.com zone)
cloudflared tunnel login

# 3. Create the tunnel
cloudflared tunnel create aurum-platform
#  → records a tunnel UUID; remember it

# 4. Route the hostname to this tunnel
cloudflared tunnel route dns aurum-platform anvisutra.com

# 5. Create the config file at %USERPROFILE%\.cloudflared\config.yml
```

Contents of `%USERPROFILE%\.cloudflared\config.yml`:

```yaml
tunnel: aurum-platform
credentials-file: C:\Users\flevi\.cloudflared\<TUNNEL-UUID>.json

ingress:
  - hostname: anvisutra.com
    service: http://localhost:8090
  - service: http_status:404
```

Then run it:

```powershell
# Foreground (for testing)
cloudflared tunnel run aurum-platform

# OR install as a Windows service so it survives reboots
cloudflared service install
```

In Cloudflare DNS for `anvisutra.com`, confirm there is a CNAME
`anvisutra.com → <tunnel-uuid>.cfargotunnel.com` (proxied — orange cloud).
This is created automatically by `tunnel route dns`, but worth checking.

---

## 7. Registering the OWNER passkey

After Phase 1 is deployed and the OWNER user has been seeded:

```bash
# 1. Begin registration — returns a WebAuthn challenge
curl -X POST https://anvisutra.com/auth/passkey/register/begin \
  -H "Content-Type: application/json" \
  -d '{"email": "<your-OWNER_EMAIL>", "nickname": "Flevian iPhone"}'
```

The response includes a `publicKey` block that the browser hands to
`navigator.credentials.create()`. In Phase 1 there is no UI, so registering a
passkey realistically requires a small WebAuthn helper page (curl alone cannot
produce a valid attestation). Phase 3 will ship this UI; for early validation
you can use any of the WebAuthn debug pages such as
`https://webauthn.io` against a private dev instance, or write a 30-line static
page.

```bash
# 2. Finish registration with the browser-produced credential payload
curl -X POST https://anvisutra.com/auth/passkey/register/finish \
  -H "Content-Type: application/json" \
  -d '{"challenge_id": "<from-begin>", "credential": <browser-output>}'
```

Login follows the same begin/finish pattern at `/auth/passkey/login/begin` and
`/auth/passkey/login/finish`. The finish response returns an access token and
sets the `aurum_refresh` cookie (HttpOnly, Secure, SameSite=Strict).

---

## 8. Verifying the deployment

From your phone (on cellular, not WiFi — proves the tunnel works):

```
https://anvisutra.com/healthz   → {"status":"ok"}
https://anvisutra.com/readyz    → {"status":"ready"}
```

After login (and with an access token in hand):

```bash
curl https://anvisutra.com/me -H "Authorization: Bearer <access-token>"
# → {"id": "...", "email": "...", "role": "OWNER", ...}
```

Inspect the audit trail directly:

```bash
docker compose exec postgres psql -U aurum -d aurum -c \
  "SELECT ts, action, status, user_id FROM audit_log ORDER BY ts DESC LIMIT 20;"
```

You should see one row per request you've made.

---

## 9. Project structure

```
aurum-platform/
├── .env.example              # template (real .env is gitignored)
├── .gitignore
├── README.md
├── docker-compose.yml        # postgres, redis, backend, caddy
├── Caddyfile                 # reverse proxy + security headers
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml        # all deps version-pinned
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_initial.py
│   ├── app/
│   │   ├── main.py           # FastAPI app factory
│   │   ├── config.py         # pydantic-settings
│   │   ├── db/
│   │   │   ├── session.py    # async SQLAlchemy engine
│   │   │   └── models.py     # ORM (users, passkeys, broker_accounts,
│   │   │                       audit_log, refresh_tokens)
│   │   ├── api/
│   │   │   ├── deps.py       # get_current_user, ip/ua helpers
│   │   │   ├── health.py     # /healthz, /readyz
│   │   │   ├── auth.py       # passkey + refresh + logout
│   │   │   └── me.py         # /me
│   │   ├── core/
│   │   │   ├── security.py   # JWT, refresh hashing, libsodium SecretBox
│   │   │   ├── audit.py      # append-only writer with redaction
│   │   │   ├── rate_limit.py # slowapi (Redis-backed)
│   │   │   └── errors.py     # exception handlers + AppError hierarchy
│   │   └── schemas/          # pydantic request/response DTOs
│   └── tests/
│       ├── conftest.py
│       ├── test_health.py
│       ├── test_auth.py
│       └── test_audit.py
└── scripts/
    ├── generate_keys.py      # MASTER_KEY + JWT_SECRET + DB password
    └── seed_owner.py         # creates the OWNER user from .env
```

---

## 10. What Phase 1 does NOT include

Phase 1 is intentionally narrow. The following are explicitly **out of scope**
and will land in subsequent phases:

* **Phase 2** — broker connection logic (MT5, OANDA), credential vaulting in
  `broker_accounts`, account discovery, balance polling.
* **Phase 3** — frontend (SPA) for login, dashboard, account management, and
  trade visualization. The Content-Security-Policy in `Caddyfile` is currently
  locked down (`default-src 'none'`); it will be tightened/loosened per the
  SPA's needs.
* **Phase 4** — AURUM brain integration (importing `C:\Users\flevi\aurum` as a
  dependency, signal generation, position management).
* **Phase 5** — invitation flow for the other 6–7 family members,
  role-based authorization (MEMBER / VIEWER), per-user rate limiting refinement.
* **Phase 6+** — observability, alerting, backups, disaster recovery.

Until those phases land, `aurum-platform` is a self-contained skeleton: auth,
DB, audit, tunnel. Nothing more.
