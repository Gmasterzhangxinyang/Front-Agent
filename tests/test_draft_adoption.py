import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.draft_adoption import (
    STATUS_EXACT_ADOPTED,
    STATUS_MODIFIED_OR_MANUAL,
    STATUS_NOT_SENT,
    STATUS_PENDING_REVIEW,
    TRACKING_START_AT,
    classify_draft_adoption,
    effective_since,
    text_hash,
)


def test_exact_draft_adoption_matches_body_hash():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    body = "Thanks for reaching out. Please try the documented workflow setting."
    result = classify_draft_adoption(
        text_hash(body),
        created_at,
        [
            {
                "type": "email",
                "is_inbound": False,
                "is_draft": False,
                "created_at": "2026-07-01T10:05:00",
                "text": body,
            }
        ],
        now=created_at + timedelta(hours=2),
    )
    assert result.status == STATUS_EXACT_ADOPTED
    assert result.sent_at == datetime(2026, 7, 1, 10, 5, 0)


def test_modified_or_manual_when_outbound_differs():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    result = classify_draft_adoption(
        text_hash("original draft"),
        created_at,
        [
            {
                "type": "email",
                "is_inbound": False,
                "is_draft": False,
                "created_at": "2026-07-01T10:30:00",
                "text": "human edited reply",
            }
        ],
        now=created_at + timedelta(hours=2),
    )
    assert result.status == STATUS_MODIFIED_OR_MANUAL


def test_pending_then_not_sent_without_outbound():
    created_at = datetime(2026, 7, 1, 10, 0, 0)
    draft_hash = text_hash("draft")
    pending = classify_draft_adoption(draft_hash, created_at, [], now=created_at + timedelta(hours=2))
    stale = classify_draft_adoption(draft_hash, created_at, [], now=created_at + timedelta(hours=25))
    assert pending.status == STATUS_PENDING_REVIEW
    assert stale.status == STATUS_NOT_SENT


def test_effective_since_does_not_scan_before_rollout():
    assert effective_since(datetime(2026, 1, 1, 0, 0, 0)) == TRACKING_START_AT
    later = TRACKING_START_AT + timedelta(minutes=1)
    assert effective_since(later) == later


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("draft adoption tests passed")
