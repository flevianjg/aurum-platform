"""Read aurum_2's atomic state snapshot.

The brain writes data/paper/state/current_state.json via tmp+rename every ~10s.
We read it on every /aurum/status request — no caching at this layer, since
the file IS the cache. A stale snapshot (e.g. brain stopped) is NOT an error;
the platform shows last-known state plus a "RUNNER OFFLINE" badge driven by
is_runner_responsive.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        # aurum_2 emits both `2026-05-02T02:07:12.806991+00:00` and
        # `2026-05-02 02:07:12.806991+00:00` (str(datetime)). Both parse with
        # fromisoformat in 3.11+; do an explicit replace just in case.
        try:
            return datetime.fromisoformat(value.replace(" ", "T", 1))
        except ValueError:
            return None
    return None


def read_current_state() -> dict[str, Any] | None:
    """Read and decorate the snapshot. Returns None if the file is missing
    or unparseable. Callers must tolerate None (treat as "snapshot not
    available yet") — that is a legitimate state, not an error."""
    settings = get_settings()
    path = Path(settings.AURUM_STATE_FILE)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("snapshot read failed: %s", exc)
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Concurrent atomic rename can race in theory; in practice os.replace
        # is atomic on the same filesystem. If we still see partial JSON it's
        # safe to skip this read.
        logger.warning("snapshot json parse error: %s", exc)
        return None
    if not isinstance(data, dict):
        return None

    snapshot_ts = _parse_ts(data.get("snapshot_ts"))
    now = datetime.now(timezone.utc)
    if snapshot_ts is not None:
        tick_age_seconds = max(0.0, (now - snapshot_ts).total_seconds())
    else:
        tick_age_seconds = None

    threshold = settings.AURUM_RUNNER_RESPONSIVE_THRESHOLD_SECONDS
    is_responsive = (
        tick_age_seconds is not None and tick_age_seconds < threshold
    )

    # Re-emit canonical ISO-8601 ts for predictable client-side parsing.
    if snapshot_ts is not None:
        data["snapshot_ts"] = snapshot_ts.astimezone(timezone.utc).isoformat()

    data["tick_age_seconds"] = tick_age_seconds
    data["is_runner_responsive"] = is_responsive
    return data
