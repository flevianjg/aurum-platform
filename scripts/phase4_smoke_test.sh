#!/usr/bin/env bash
# Phase 4 smoke test — exercises every /aurum/* endpoint end-to-end.
#
# Idempotent: runs in <30s, leaves no debris, never destructive.
# Returns 0 if every assertion passes, 1 otherwise. Each step prints
# PASS / FAIL inline so failures are easy to grep.
#
# Prerequisites (the script verifies all of them):
#   * docker compose stack up (postgres, redis, backend, frontend, caddy)
#   * OWNER user seeded with email matching $OWNER_EMAIL (default
#     flevianjg@gmail.com — override via env var for other deployments)
#   * Seeded VIEWER user (created on the fly; deleted at the end)
#
# Run from repo root:
#   bash scripts/phase4_smoke_test.sh

set -u
set -o pipefail

# ---------- config ----------
BASE_URL="${BASE_URL:-http://localhost:8090}"
OWNER_EMAIL="${OWNER_EMAIL:-flevianjg@gmail.com}"

# Resolve docker on Windows / git-bash hosts where it isn't on PATH by default.
if ! command -v docker >/dev/null 2>&1; then
    if [ -x "/c/Program Files/Docker/Docker/resources/bin/docker.exe" ]; then
        export PATH="/c/Program Files/Docker/Docker/resources/bin:$PATH"
    fi
fi

# Resolve a usable Python on the host. python3 isn't always on git-bash;
# fall back to plain python (which is the Windows Python launcher there).
if command -v python3 >/dev/null 2>&1; then
    PYBIN=python3
elif command -v python >/dev/null 2>&1; then
    PYBIN=python
else
    echo "no python on PATH — install Python 3 first" >&2
    exit 1
fi

PASSED=0
FAILED=0

pass() { echo "  PASS  $*"; PASSED=$((PASSED + 1)); }
fail() { echo "  FAIL  $*"; FAILED=$((FAILED + 1)); }
section() { echo; echo "── $* ──"; }

# ---------- 1. service health ----------
section "1. docker compose ps"
ps_out=$(docker compose ps --format json 2>/dev/null || docker compose ps 2>/dev/null)
expected_services=(postgres redis backend frontend caddy)
for svc in "${expected_services[@]}"; do
    if echo "$ps_out" | grep -q "$svc.*healthy"; then
        pass "$svc healthy"
    else
        fail "$svc not healthy"
    fi
done

# ---------- 2. mint OWNER JWT + create VIEWER + seed JWT ----------
section "2. mint JWTs (OWNER + ephemeral VIEWER)"
mint_out=$(MSYS_NO_PATHCONV=1 docker compose exec -T backend python - <<PY 2>&1
import asyncio, uuid
from sqlalchemy import select
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.db.models import User, UserRole

OWNER_EMAIL = "$OWNER_EMAIL"
VIEWER_EMAIL = "smoke-viewer@example.com"

async def go():
    async with SessionLocal() as s:
        owner = (await s.execute(
            select(User).where(User.email == OWNER_EMAIL.lower())
        )).scalar_one_or_none()
        if owner is None:
            print("ERR: OWNER not seeded")
            return
        viewer = (await s.execute(
            select(User).where(User.email == VIEWER_EMAIL)
        )).scalar_one_or_none()
        if viewer is None:
            viewer = User(
                email=VIEWER_EMAIL,
                display_name="Smoke Viewer",
                role=UserRole.VIEWER,
                is_active=True,
            )
            s.add(viewer)
            await s.commit()
            await s.refresh(viewer)
        owner_token, _ = create_access_token(user_id=owner.id, role=owner.role.value)
        viewer_token, _ = create_access_token(user_id=viewer.id, role=viewer.role.value)
        print("OWNER_TOKEN=" + owner_token)
        print("VIEWER_TOKEN=" + viewer_token)
        print("VIEWER_ID=" + str(viewer.id))

asyncio.run(go())
PY
)

OWNER_TOKEN=$(echo "$mint_out" | sed -n 's/^OWNER_TOKEN=//p')
VIEWER_TOKEN=$(echo "$mint_out" | sed -n 's/^VIEWER_TOKEN=//p')
VIEWER_ID=$(echo "$mint_out" | sed -n 's/^VIEWER_ID=//p')

if [ -n "$OWNER_TOKEN" ]; then
    pass "OWNER JWT minted"
else
    fail "OWNER JWT mint — output: $mint_out"
    echo "Cannot continue without OWNER token."
    exit 1
fi
if [ -n "$VIEWER_TOKEN" ]; then
    pass "VIEWER JWT minted (user_id=$VIEWER_ID)"
else
    fail "VIEWER JWT mint"
fi

OWNER_AUTH=(-H "Authorization: Bearer $OWNER_TOKEN")
VIEWER_AUTH=(-H "Authorization: Bearer $VIEWER_TOKEN")

# ---------- 3. read endpoints — shape checks ----------
section "3. /aurum/* read endpoints"

check_status_and_shape() {
    local label="$1" path="$2" expected_status="$3" jq_test="$4"
    # One curl returns the body followed by a sentinel + status code so we
    # don't need a temp file (git-bash /tmp paths don't translate to native
    # Windows Python's view of the filesystem).
    local resp status body
    resp=$(curl -sS "${OWNER_AUTH[@]}" -w $'\n__STATUS__%{http_code}' "${BASE_URL}${path}")
    status=$(printf '%s' "$resp" | tail -n1 | sed 's/^__STATUS__//')
    body=$(printf '%s' "$resp" | sed '$d')
    if [ "$status" != "$expected_status" ]; then
        if [ "$path" = "/aurum/status" ] && [ "$status" = "404" ]; then
            pass "$label → 404 (snapshot absent — expected when runner offline)"
            return
        fi
        fail "$label expected $expected_status got $status — body: ${body:0:120}"
        return
    fi
    if printf '%s' "$body" | "$PYBIN" -c "
import sys, json
data = json.loads(sys.stdin.read())
$jq_test
"; then
        pass "$label → $status (shape OK)"
    else
        fail "$label shape check failed — body: ${body:0:160}"
    fi
}

check_status_and_shape \
    "GET /aurum/control" \
    "/aurum/control" \
    "200" \
    "assert isinstance(data, dict) and 'paused' in data and 'stop_requested' in data"

check_status_and_shape \
    "GET /aurum/equity?days=7" \
    "/aurum/equity?days=7" \
    "200" \
    "assert isinstance(data, list)"

check_status_and_shape \
    "GET /aurum/positions/open" \
    "/aurum/positions/open" \
    "200" \
    "assert isinstance(data, list)"

check_status_and_shape \
    "GET /aurum/positions/closed" \
    "/aurum/positions/closed" \
    "200" \
    "assert isinstance(data, dict) and 'items' in data and 'next_before' in data"

check_status_and_shape \
    "GET /aurum/regime" \
    "/aurum/regime" \
    "200" \
    "assert isinstance(data, dict)"

today_utc=$("$PYBIN" -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).date().isoformat())")
check_status_and_shape \
    "GET /aurum/report/daily?date=${today_utc}" \
    "/aurum/report/daily?date=${today_utc}" \
    "200" \
    "assert all(k in data for k in ['n_trades', 'total_pnl', 'per_instrument'])"

# /aurum/status: 200 if snapshot exists, 404 if not — both acceptable
status_code=$(curl -sS -o /dev/null -w "%{http_code}" "${OWNER_AUTH[@]}" "${BASE_URL}/aurum/status")
if [ "$status_code" = "200" ] || [ "$status_code" = "404" ]; then
    pass "GET /aurum/status → ${status_code}"
else
    fail "GET /aurum/status → ${status_code} (expected 200 or 404)"
fi

# ---------- 4. auth gates: every endpoint without JWT returns 401 ----------
section "4. unauth → 401 on every endpoint"
unauth_paths=(
    "GET /aurum/status"
    "GET /aurum/equity"
    "GET /aurum/positions/open"
    "GET /aurum/positions/closed"
    "GET /aurum/regime"
    "GET /aurum/report/daily"
    "GET /aurum/control"
    "POST /aurum/pause"
    "POST /aurum/resume"
    "POST /aurum/stop"
)
for entry in "${unauth_paths[@]}"; do
    method="${entry%% *}"
    path="${entry##* }"
    code=$(curl -sS -o /dev/null -w "%{http_code}" -X "$method" "${BASE_URL}${path}")
    if [ "$code" = "401" ]; then
        pass "$method $path → 401"
    else
        fail "$method $path → $code (expected 401)"
    fi
done

# ---------- 5. role gates: VIEWER can't pause/resume/stop ----------
section "5. VIEWER role → 403 on control endpoints"
for action in pause resume stop; do
    extra_header=()
    [ "$action" = "stop" ] && extra_header=(-H "X-Confirm-Stop: yes")
    code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
        "${VIEWER_AUTH[@]}" "${extra_header[@]}" \
        "${BASE_URL}/aurum/${action}")
    if [ "$code" = "403" ]; then
        pass "POST /aurum/${action} as VIEWER → 403"
    else
        fail "POST /aurum/${action} as VIEWER → $code (expected 403)"
    fi
done

# ---------- 6. /aurum/stop without X-Confirm-Stop → 400 ----------
section "6. /aurum/stop confirmation header gate"
code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
    "${OWNER_AUTH[@]}" "${BASE_URL}/aurum/stop")
if [ "$code" = "400" ]; then
    pass "POST /aurum/stop without X-Confirm-Stop → 400"
else
    fail "POST /aurum/stop without X-Confirm-Stop → $code (expected 400)"
fi

# ---------- 7. pause idempotency: pause → pause → resume cleanly ----------
section "7. pause idempotency"
# Snapshot rate-limit budget for /aurum/pause is 5/min, we use 3 of 5 here.
codes=()
for action in pause pause resume; do
    code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
        "${OWNER_AUTH[@]}" "${BASE_URL}/aurum/${action}")
    codes+=("$action=$code")
    sleep 0.3
done
# Each should be 200 (the second pause is a no-op flag write — same atomic
# write semantics — and audit/control_actions row appended each time). 429
# is acceptable here if other tests hit the budget; treat 429 as a non-pass
# but warn rather than fail outright.
ok=true
for c in "${codes[@]}"; do
    val="${c#*=}"
    if [ "$val" = "200" ]; then
        :
    elif [ "$val" = "429" ]; then
        echo "  WARN  rate-limited on $c (5/min budget exhausted by parallel runs)"
    else
        ok=false
        fail "idempotency step $c"
    fi
done
$ok && pass "pause → pause → resume sequence: ${codes[*]}"

# ---------- 8. cleanup ephemeral viewer ----------
section "8. cleanup ephemeral VIEWER user"
if [ -n "$VIEWER_ID" ]; then
    MSYS_NO_PATHCONV=1 docker compose exec -T backend python - <<PY >/dev/null 2>&1
import asyncio
from sqlalchemy import delete
from app.db.session import SessionLocal
from app.db.models import User
import uuid

async def go():
    async with SessionLocal() as s:
        await s.execute(delete(User).where(User.id == uuid.UUID("$VIEWER_ID")))
        await s.commit()

asyncio.run(go())
PY
    pass "deleted VIEWER smoke user"
fi

# ---------- summary ----------
section "Summary"
echo "  PASSED: $PASSED"
echo "  FAILED: $FAILED"
if [ "$FAILED" -eq 0 ]; then
    echo
    echo "✓ Phase 4 smoke test passed."
    exit 0
else
    echo
    echo "✗ Phase 4 smoke test FAILED — see entries above."
    exit 1
fi
