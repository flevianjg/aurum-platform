# Phase 4 smoke test

`scripts/phase4_smoke_test.sh` is a fast (<30 s), idempotent end-to-end
verification of every `/aurum/*` endpoint plus the auth and role gates
that protect them. It's safe to run any time the stack is up — it
creates an ephemeral VIEWER user, runs its checks, then deletes it.

## When to run it

* Right after `docker compose up -d` to confirm a fresh deploy is wired
  end-to-end.
* After any change to `backend/app/api/aurum.py`, the Caddyfile, or the
  ETL worker.
* When the dashboard misbehaves and you need a quick "is the API the
  problem or the UI the problem?" answer.

## How to run

From the repo root:

```bash
bash scripts/phase4_smoke_test.sh
```

Override the public origin or the OWNER email if you're running against
a non-default deployment:

```bash
BASE_URL=https://anvisutra.com OWNER_EMAIL=flevianjg@gmail.com \
    bash scripts/phase4_smoke_test.sh
```

The script auto-detects:
* a usable `python3` / `python` on the host (uses whichever it finds),
* the docker CLI (it adds Docker Desktop's `resources/bin` to PATH if
  `docker` isn't on the default PATH).

## What it checks (30 assertions)

| Section | Asserts |
| --- | --- |
| 1. Service health | All five compose services report `healthy` |
| 2. JWT mint | OWNER + ephemeral VIEWER tokens generated server-side via `app.db.session.SessionLocal` and `app.core.security.create_access_token` |
| 3. Read endpoints | `GET /aurum/control` returns `{paused, stop_requested}` · `GET /aurum/equity?days=7` returns a list · `GET /aurum/positions/open` returns a list · `GET /aurum/positions/closed` returns `{items, next_before}` · `GET /aurum/regime` returns a dict · `GET /aurum/report/daily?date=$today` returns a daily report · `GET /aurum/status` returns 200 (or 404 if the runner has never written a snapshot — both acceptable) |
| 4. Auth gates | All 10 `/aurum/*` paths return **401** without an `Authorization: Bearer` header |
| 5. Role gates | A VIEWER token gets **403** on POST `/aurum/{pause,resume,stop}` |
| 6. Stop confirm | `POST /aurum/stop` without `X-Confirm-Stop: yes` header returns **400** |
| 7. Idempotency | A `pause → pause → resume` sequence all return 200 (the second pause is a no-op atomic flag re-write) |
| 8. Cleanup | Ephemeral VIEWER user removed from the `users` table |

## Reading the output

```
  PASS  ...     individual assertion succeeded
  FAIL  ...     individual assertion failed (script exits 1 at the end)
  WARN  ...     non-fatal anomaly (e.g. rate-limit budget exhausted by
                a previous run within the same minute)

── Summary ──
  PASSED: 30
  FAILED: 0
```

The script returns exit code **0** when every assertion passed, **1** if
any failed. Wire it into CI / a `make check` target as you wish.

## Common failures

| Symptom | Likely cause |
| --- | --- |
| `OWNER not seeded` during JWT mint | `python -m scripts.seed_owner` hasn't been run yet against this DB |
| `*_TOKEN=` lines missing | `app.db.session` export name changed — script uses `SessionLocal` |
| `aurum/control shape check failed` | A new field is missing from the response or shape was changed; update the assertion |
| `pause=429` on idempotency | Rate-limit bucket of 5/min was already half-spent by a previous run; wait ~60 s and re-run |
| `frontend not healthy` | Frontend container often takes 30 s to first-respond; if persistent, check `docker compose logs frontend` |

## Adding new assertions

Each check follows the same shape:

```bash
check_status_and_shape \
    "Label for the report"   \
    "/aurum/your/path"       \
    "200"                    \
    "assert ...python expression on `data`..."
```

`data` is the parsed JSON response. The Python assertion runs in a
fresh interpreter for each check, fed via stdin.
