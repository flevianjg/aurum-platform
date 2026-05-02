# aurum_2 ↔ aurum-platform integration (v3)

This document describes the **read-mostly file-based contract** between
the aurum_2 paper runner and the aurum-platform observer/control surface.
The runner is locked, vault-validated, and frozen — nothing in this
document changes its behaviour. The platform reads what the runner
writes, and writes flag files the runner polls.

> **Canonical source for the runner side**: aurum_2's own
> `ARCHITECTURE.md` and `LOCKED.md`. If the two ever disagree, aurum_2
> wins; this document is the platform-side mirror.

## Filesystem contract

| Path (host)                                          | Direction              | Purpose                          |
| ---------------------------------------------------- | ---------------------- | -------------------------------- |
| `aurum_2/data/paper/journal/journal_YYYYMMDD.jsonl`  | runner → platform (RO) | Append-only event log; rotated by UTC date in the filename |
| `aurum_2/data/paper/state/current_state.json`        | runner → platform (RO) | Atomic snapshot, ~10 s cadence, written via `tmp + os.replace` |
| `aurum_2/data/paper/control/pause.flag`              | platform → runner      | Presence = paused; absence = running |
| `aurum_2/data/paper/control/stop.flag`               | platform → runner      | Latched on first read; restart needed to clear |

These directories are bind-mounted into the backend container as:

```
/aurum_2/journal  (ro)
/aurum_2/state    (ro)
/aurum_2/control  (rw — only path the platform mutates)
```

## Journal event contract

Each line in `journal_YYYYMMDD.jsonl` is one JSON object. Required keys
on every line, post-contract (lines emitted on or after
`2026-05-02T02:06:27Z`):

| Field      | Type   | Notes |
| ---------- | ------ | ----- |
| `event_id` | UUID4  | Stable, unique per event. Platform uses it as the dedup PK |
| `ts`       | string | RFC-3339 UTC timestamp (both `T` and space separators tolerated by the platform parser) |
| `type`     | string | Discriminator. Examples: `equity_snapshot`, `bar_close`, `signal`, `fill`, `position_closed`, `control_event` |
| (others)   | varies | Type-specific payload — preserved verbatim by the platform |

Lines emitted before that cutoff (the integration warm-up window) lack
an `event_id`. The platform synthesizes one as
`uuid5(<a7e3...>, f"{source_file}:{source_line}:{ts}:{type}")` and
flags the row with `event_id_synthetic = TRUE` so analytics queries can
filter pre-contract events out if needed.

## Snapshot contract

`current_state.json` is rewritten atomically by the runner roughly
every 10 seconds. Top-level keys the platform consumes:

| Field                  | Used in |
| ---------------------- | ------- |
| `snapshot_ts`          | watchdog freshness; both T-separator and space-separator parses |
| `snapshot_seq`         | display |
| `runner_pid`, `runner_started_ts`, `instruments` | display |
| `final` (bool)         | display only — runner sets `true` on graceful exit |
| `broker.{equity, peak_equity, drawdown_pct, today_pnl_dollars, currency, ...}` | dashboard status header + equity tile |
| `engine.{INSTRUMENT}.{last_regime, last_bar_utc, model_ready, skipped, ...}`  | per-instrument grid |
| `open_positions[]`     | open positions panel |
| `control_flags.{paused, stop_requested, last_pause_meta, last_stop_meta}` | control-panel state |
| `health` (free-form)   | reserved for future watchdog detail |

The platform never caches the snapshot in Redis or the app process —
the file *is* the cache. Each `/aurum/status` request reads it.

When `now() - snapshot_ts ≥ 60 s`, the platform marks the runner as
**unresponsive** and surfaces the watchdog banner. The endpoint still
returns `200` with the last-known data so the dashboard can render
"offline" gracefully — only a missing file produces `404`.

## Platform-side ETL implementation

`backend/app/workers/journal_etl.py` runs as an asyncio task started
in the FastAPI lifespan:

* **Polling**: 1 s default (`AURUM_ETL_POLL_INTERVAL_SECONDS`). The
  Docker bind mount from a Windows host doesn't propagate inotify
  events reliably across the WSL2/Windows boundary, so polling is the
  baseline strategy. On a future Linux-only deploy, swap in inotify.
* **File walk**: every `journal_*.jsonl` matching the
  `^journal_\d{8}\.jsonl$` pattern, sorted lexicographically. Rotation
  is detected by **filename**, not host clock.
* **Resume**: read `etl_checkpoints[source='paper_journal']` on
  startup; re-process the file named in `last_processed_file` from
  line 1. `INSERT ... ON CONFLICT (event_id) DO NOTHING` makes the
  replay idempotent.
* **Batching**: up to `AURUM_ETL_BATCH_SIZE` (500) rows or 1 s — first
  to fire, wins. After each batch, checkpoint is updated in the same
  transaction.
* **Error policy**:
  - Malformed JSON line: log + skip + don't advance checkpoint past it.
    The next pass replays from the last good `last_processed_file`,
    not from the bad line — so the bad line is silently retried but
    never blocks newer lines (because `ON CONFLICT` absorbs duplicates
    that come *after* a bad line).
  - DB error: exponential backoff, max 30 s ceiling, retries forever.
    Worker auto-restarts when the container restarts.
  - Missing journal directory: warn + sleep + retry, never crash
    backend startup.

## Watchdog logic

```python
threshold = AURUM_RUNNER_RESPONSIVE_THRESHOLD_SECONDS  # 60.0
if snapshot_ts is None:
    return None  # treat as missing
tick_age_seconds = (now - snapshot_ts).total_seconds()
is_runner_responsive = tick_age_seconds < threshold
```

Three UI tones are derived in the frontend:
* `< 30 s` → `LIVE` (green)
* `30–60 s` → `DELAYED` (yellow)
* `≥ 60 s` (or snapshot missing entirely) → `UNRESPONSIVE` / `OFFLINE` (red)

## Control flag write authorization

Every `/aurum/{pause,resume,stop}` POST:

1. Requires a valid JWT (Phase 1 auth).
2. Requires `user.role == OWNER` (HTTP 403 otherwise — verified by
   smoke test).
3. For `/aurum/stop`, requires `X-Confirm-Stop: yes` header (HTTP 400
   otherwise — keeps a tap-misclick from killing the runner).
4. Writes the flag atomically via `tmp + os.replace`. Linux: kernel
   guarantee. Windows: `os.replace` is atomic since Python 3.3.
5. Inserts a row in `audit_log` AND a row in `control_actions`,
   sharing the same `request_id`. The `request_id` is also embedded in
   the JSON payload of the flag file, which the runner echoes into its
   own `control_event` journal line — so a future cross-system query
   on `request_id` can join all three.

`pause.flag` removal (resume) is `os.unlink` and is idempotent —
re-resuming when not paused is a no-op + audit row.

`stop.flag` is **latched** on the runner side: once read, the runner
holds the stop in memory and ignores subsequent removals. Clearing it
requires a host-side restart of the runner. The platform UI reflects
this with a sticky banner under the dashboard status header.

## Endpoints (platform → operator)

| Method | Path | Auth | Notes |
| ------ | ---- | ---- | ----- |
| GET | `/aurum/status` | JWT | Returns the snapshot dict + computed `tick_age_seconds`, `is_runner_responsive`. 404 only when the file has never been written |
| GET | `/aurum/equity?days=N` | JWT | Postgres time-series, 1-min bars via `DISTINCT ON (date_trunc('minute', ts))`, `days` capped at 30 |
| GET | `/aurum/positions/open` | JWT | Snapshot field passthrough; `[]` when snapshot missing |
| GET | `/aurum/positions/closed?limit=&before=` | JWT | Cursor-paginated, limit capped at 200 |
| GET | `/aurum/regime` | JWT | Snapshot's `engine` block; `{}` when missing |
| GET | `/aurum/report/daily?date=YYYY-MM-DD` | JWT | Aggregates `position_closed` events for the UTC date |
| GET | `/aurum/control` | JWT | Live read of pause/stop flag files |
| POST | `/aurum/pause` | OWNER | Writes pause.flag + audit + control_actions row |
| POST | `/aurum/resume` | OWNER | Removes pause.flag + audit + control_actions row |
| POST | `/aurum/stop` | OWNER + `X-Confirm-Stop: yes` | Writes stop.flag + audit + control_actions row |

## Audit dedup for high-frequency reads

`/aurum/status`, `/aurum/positions/open`, `/aurum/regime`, and
`/aurum/control` are polled by the dashboard at 5-30 s. To prevent the
audit log from drowning under that traffic, the API tracks a
process-local set keyed by `(user_id, endpoint)`. The first read in a
process lifetime audits; subsequent reads skip. Reset on backend
restart is by design — that produces one audit row per restart per
session, which is exactly the granularity we want.

Low-frequency endpoints (`equity`, `positions/closed`, `report/daily`)
audit on every call.

## Versioning

This is **v3** of the integration spec.

* v1: original Phase 4 spec — pre-contract; aurum_2 hadn't yet emitted
  `event_id` or written `current_state.json`.
* v2: refined after on-disk inspection — chose Option 1 dedup (UUID5
  fallback for pre-contract lines, `event_id_synthetic` boolean column).
* v3 (current): post-implementation mirror; documents the actual ETL,
  watchdog, and control authorization implementations as built and
  smoke-tested.
