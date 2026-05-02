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

## 10. Phase 2 — Broker connections

Phase 2 adds a clean `BrokerAdapter` abstraction with two concrete adapters
(MT5 and OANDA), per-user encrypted credential storage, and 8 CRUD endpoints
under `/broker`. **No trade execution yet** — only connection management and
read-only live operations (account info, positions, ticks). All endpoints
require the JWT from Phase 1 and write to `audit_log`. **Credentials are
never logged, never returned in responses, and never appear in audit
metadata.**

### Endpoints

| Method | Path                              | Notes                                     |
| ------ | --------------------------------- | ----------------------------------------- |
| POST   | `/broker/test`                    | Test creds without storing (10/min)       |
| POST   | `/broker`                         | Connect — encrypts + stores (5/min)       |
| GET    | `/broker`                         | List own accounts (100/min)               |
| GET    | `/broker/{id}`                    | Detail + live account info                |
| POST   | `/broker/{id}/test`               | Re-test stored creds (10/min)             |
| PATCH  | `/broker/{id}/deactivate`         | Soft-disable (audit preserved)            |
| PATCH  | `/broker/{id}/reactivate`         | Re-enable                                 |
| DELETE | `/broker/{id}`                    | Hard delete (cascades health checks)      |

`VIEWER` role is rejected with 403 on every broker action; `OWNER` and
`MEMBER` can manage their own broker accounts only — `GET /broker/{id}`
returns 404 (not 403) for accounts owned by another user, to avoid leaking
existence.

### OANDA quick-test (end-to-end)

1. Get an OANDA practice token from
   `https://www.oanda.com/demo-account/tpa/personal_token` (signup is free).
2. Note your account id (looks like `001-001-1234567-001`) from the OANDA
   dashboard.
3. Test the credentials WITHOUT storing them:

   ```bash
   ACCESS=<your-jwt-from-passkey-login>
   curl -X POST https://anvisutra.com/broker/test \
     -H "Authorization: Bearer $ACCESS" \
     -H "Content-Type: application/json" \
     -d '{
       "broker_type": "OANDA",
       "credentials": {
         "account_id": "001-001-1234567-001",
         "api_token": "YOUR_OANDA_TOKEN",
         "environment": "practice"
       }
     }'
   ```
   Expected: `{"success": true, "account_number": "...", "currency": "USD", ...}`.

4. Persist them (test runs first; if the test fails, nothing is stored):

   ```bash
   curl -X POST https://anvisutra.com/broker \
     -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
     -d '{
       "broker_type": "OANDA",
       "account_label": "OANDA Practice",
       "credentials": {
         "account_id": "001-001-1234567-001",
         "api_token": "YOUR_OANDA_TOKEN",
         "environment": "practice"
       }
     }'
   ```
   Returns `{"id": "...", "broker_type": "OANDA", ...}` — store the id.

5. Read live account info (decrypts creds in-memory only for this call):

   ```bash
   curl https://anvisutra.com/broker/<id> -H "Authorization: Bearer $ACCESS"
   ```

### MT5 (Phase 2 limitation)

The `MetaTrader5` Python package is **Windows-only** and cannot run inside the
Linux backend container. Phase 2 ships:

* **`MT5Adapter`** with the full contract (`test_connection`,
  `get_account_info`, `get_positions`, `get_tick`).
* **`MT5_TEST_MODE`** environment flag (default **`true`** in
  `.env.example`) — every method returns canned successful results so
  end-to-end testing of the encrypted credential storage works without a
  real MT5 terminal.
* **`workers/mt5_runner.py`** — a fully implemented standalone Windows
  runner script that reads JSON over stdin, talks to the MetaTrader5
  package, and returns JSON over stdout. **Phase 4** will deploy this on
  a Windows host and set `WINDOWS_HOST_RUNNER` so the adapter can shell
  out to it.

This means: on this Linux stack, MT5 connections "work" (canned data) for
the API contract, but real live MT5 trades will only be possible after the
Phase 4 host bridge.

### Security hygiene (Phase 2 invariants)

* Credentials are encrypted at rest via libsodium `SecretBox` (XChaCha20-Poly1305)
  with a per-record 24-byte nonce. Master key from `MASTER_KEY` env var, validated
  at startup.
* Pydantic `SecretStr` is used on `password` / `api_token` fields, so any
  accidental `.model_dump()` or pretty-print emits `**********`.
* The audit-log writer (`app/core/audit.py`) scrubs known forbidden keys
  (`password`, `api_token`, `credentials`, etc.) from metadata before
  inserting; broker routes additionally never pass credentials INTO audit
  metadata in the first place. Tests assert no plaintext credential string
  ever reaches `audit_log` rows or any API response body.

---

## 11. Phase 3 — PWA frontend

Next.js 15.1.12 (patched), React 19, Tailwind 3.4, shadcn UI primitives,
TanStack Query 5. Service worker generated by `@ducanh2912/next-pwa` at
build time — `/auth/*`, `/me`, `/me/*`, `/broker`, `/broker/*`,
`/aurum/*`, `/healthz`, `/readyz` are explicitly **NetworkOnly** so they
never serve stale data; static assets are CacheFirst; HTML pages fall
back to `/offline` when network is down.

Pages: `/login` (passkey register + sign in), `/dashboard` (live runner
view — see §12), `/dashboard/trades` (filterable closed-trade history),
`/brokers` + `/brokers/new` + `/brokers/[id]` (broker connection
management), `/settings` (profile + passkey CRUD + sign-out-all),
`/offline`. Bottom-tab nav on mobile, sidebar on desktop.

PWA installable on iOS / Android / Windows / Mac via the browser's "add
to home screen" / "install app" affordance — manifest + 192/512/maskable
icons + apple-touch-icon are all served at the origin root.

## 12. Phase 4 — aurum_2 paper runner integration

The platform observes the locked, vault-validated paper runner at
`C:\Users\flevi\aurum_2`. **The platform never imports runner code.**
It reads the runner's append-only journal + atomic state snapshot, and
writes flag files the runner polls.

### Files involved

| Host path                                                  | Direction                | Purpose |
| ---------------------------------------------------------- | ------------------------ | ------- |
| `aurum_2/data/paper/journal/journal_YYYYMMDD.jsonl`        | runner → platform (RO)   | Event journal, ingested by `app/workers/journal_etl.py` into `paper_events` table |
| `aurum_2/data/paper/state/current_state.json`              | runner → platform (RO)   | Atomic ~10 s snapshot, read on every `/aurum/status` |
| `aurum_2/data/paper/control/pause.flag`                    | platform → runner (RW)   | Presence = paused. Atomic `tmp + os.replace` writes |
| `aurum_2/data/paper/control/stop.flag`                     | platform → runner (RW)   | **Latched** in runner memory after first read; restart needed |

These are bind-mounted into the backend container as `/aurum_2/journal`
(ro), `/aurum_2/state` (ro), `/aurum_2/control` (rw). No source code is
mounted — the platform never imports anything from the runner.

### Endpoints exposed

* `GET /aurum/status` · `GET /aurum/equity?days=N` · `GET /aurum/positions/open` · `GET /aurum/positions/closed?limit=&before=` · `GET /aurum/regime` · `GET /aurum/report/daily?date=YYYY-MM-DD` · `GET /aurum/control`
* `POST /aurum/pause` · `POST /aurum/resume` · `POST /aurum/stop` (OWNER role + `X-Confirm-Stop: yes` header required)

Every control write produces both an `audit_log` row AND a
`control_actions` row sharing the same `request_id`, which is also
embedded in the flag's JSON payload — so any future cross-system
forensics can join all three on `request_id`.

### Starting / stopping the runner

The platform never starts or stops the runner from the host — that
remains a deliberate manual / terminal operation governed by aurum_2's
own scripts. See `C:\Users\flevi\aurum_2\README.md`. From the dashboard
the OWNER can:

* **Pause** / **Resume** — soft control via `pause.flag`. Effect lands
  on the next bar after the runner reads the flag (typically <12 s).
* **Stop** — writes `stop.flag` after a type-the-word confirmation. The
  runner runs `force_close_all` at last mark price and exits with
  `exit_reason=STOP_REQUESTED`. Re-enabling requires a terminal
  restart.

Watchdog: the dashboard surfaces `LIVE` / `DELAYED` / `UNRESPONSIVE`
based on `now() - snapshot_ts` against a 60 s threshold. A persistent
banner appears under the topbar when the runner has been silent for
≥ 60 s.

### Smoke test

```bash
bash scripts/phase4_smoke_test.sh
```

Idempotent end-to-end check (~30 s) of all 10 `/aurum/*` endpoints +
auth + role gates + stop confirm + pause idempotency. See
`docs/PHASE4_SMOKE_TEST.md` for what it asserts and how to extend.

### Architecture reference

The full integration spec, ETL implementation notes, watchdog logic,
and control-authorization details live at
[`docs/integration_aurum2_to_platform.md`](docs/integration_aurum2_to_platform.md)
(v3, mirrors aurum_2's contract).

### Lighthouse PWA audit

To verify the PWA still scores ≥ 90:

1. Open Chrome DevTools on `https://anvisutra.com` (signed-in or signed-out, both should pass).
2. Lighthouse panel → "Progressive Web App" + "Performance" + "Accessibility" + "Best Practices" + "SEO" categories, "Mobile" device.
3. Click **Analyze page load**.
4. Confirm PWA score ≥ 90.

The audit can't be automated from this CLI environment; run it manually
after any sub-phase that touches the manifest, service worker, or
app-shell layout.

## 13. What is still NOT in scope

Phases 1–4 cover authentication, broker connection management, PWA
frontend, and aurum_2 runner integration. Out of scope until later
phases:

* **Phase 5** — invitation flow for the other 6–7 family members,
  per-user rate limiting refinement, real-money trading authorization.
* **Phase 6+** — observability, alerting, backups, disaster recovery,
  multi-runner orchestration.
