import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from apscheduler.schedulers.asyncio import AsyncIOScheduler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.unanswered_reminders as reminder_module
import tasks.scheduler as scheduler_module
from config import settings
from services.unanswered_reminders import (
    evaluate_unanswered_timeline,
    is_china_weekday,
)


NOW = datetime(2026, 8, 28, 8, 0, 0)
def _utc_timestamp(value):
    return value.replace(tzinfo=timezone.utc).timestamp()




def _inbound(message_id="msg_customer", hours_ago=13):
    return {
        "id": message_id,
        "type": "email",
        "is_inbound": True,
        "is_draft": False,
        "created_at": _utc_timestamp(NOW - timedelta(hours=hours_ago)),
        "sender": {"handle": "customer@example.com"},
        "subject": "Need help",
        "text": "Please help",
    }


def _sent_reply(message_id="msg_reply", hours_ago=1):
    return {
        "id": message_id,
        "type": "email",
        "is_inbound": False,
        "is_draft": False,
        "created_at": _utc_timestamp(NOW - timedelta(hours=hours_ago)),
        "recipients": [{"role": "to", "handle": "customer@example.com"}],
        "text": "Handled",
    }


def _comment(author_email, author_id, hours_ago=1):
    return {
        "id": "com_1",
        "created_at": _utc_timestamp(NOW - timedelta(hours=hours_ago)),
        "author": {"id": author_id, "email": author_email},
        "body": "Taking this one",
    }


def _conversation(
    conversation_id="cnv_due",
    *,
    assignee_id=None,
    updated_at=None,
):
    assignee = (
        {
            "id": assignee_id,
            "email": "bobby@dify.ai"
            if assignee_id == settings.front_teammate_bobby
            else "other@dify.ai",
        }
        if assignee_id
        else None
    )
    return {
        "id": conversation_id,
        "status": "assigned" if assignee else "unassigned",
        "status_category": "open",
        "assignee": assignee,
        "recipient": {"handle": "customer@example.com"},
        "subject": "Need help",
        "updated_at": _utc_timestamp(updated_at or NOW),
    }


def test_latest_customer_message_without_reply_is_unhandled():
    decision = evaluate_unanswered_timeline([_inbound()], [])
    assert decision.latest_customer_message["id"] == "msg_customer"
    assert not decision.handled


def test_real_reply_after_latest_customer_message_is_handled():
    decision = evaluate_unanswered_timeline([_sent_reply(), _inbound()], [])
    assert decision.customer_replied
    assert decision.handled


def test_reply_before_a_new_customer_followup_does_not_count():
    messages = [
        _inbound("msg_followup", hours_ago=13),
        _sent_reply(hours_ago=15),
        _inbound("msg_original", hours_ago=20),
    ]
    decision = evaluate_unanswered_timeline(messages, [])
    assert decision.latest_customer_message["id"] == "msg_followup"
    assert not decision.customer_replied


def test_draft_does_not_count_as_customer_reply():
    draft = _sent_reply()
    draft["is_draft"] = True
    decision = evaluate_unanswered_timeline([draft, _inbound()], [])
    assert not decision.handled


def test_bobby_comment_after_latest_message_suppresses_reminder():
    decision = evaluate_unanswered_timeline(
        [_inbound()],
        [_comment("bobby@dify.ai", settings.front_teammate_bobby)],
    )
    assert decision.bobby_commented


def test_api_bot_comment_does_not_suppress_reminder():
    decision = evaluate_unanswered_timeline(
        [_inbound()],
        [_comment("api_jwt@example.invalid", "tea_api")],
    )
    assert not decision.bobby_commented


def test_old_bobby_comment_does_not_cover_new_customer_followup():
    decision = evaluate_unanswered_timeline(
        [_inbound(hours_ago=13)],
        [_comment("bobby@dify.ai", settings.front_teammate_bobby, hours_ago=20)],
    )
    assert not decision.bobby_commented


def test_scope_is_union_of_support_and_bobby_assigned_with_deduplication():
    async def run_case():
        shared = _conversation("cnv_shared", assignee_id=settings.front_teammate_bobby)
        support_only = _conversation("cnv_support")
        assigned_only = _conversation(
            "cnv_assigned",
            assignee_id=settings.front_teammate_bobby,
        )
        wrong_assignee = _conversation("cnv_wrong", assignee_id="tea_other")

        async def search_scope(query):
            if query.startswith("inbox:"):
                return [support_only, shared]
            return [shared, assigned_only, wrong_assignee]

        search = AsyncMock(
            side_effect=search_scope
        )
        with (
            patch.object(reminder_module, "_search_open_conversations", search),
            patch.object(
                reminder_module,
                "_last_sla_checks",
                AsyncMock(return_value={}),
            ),
        ):
            selected, stats, errors = (
                await reminder_module._candidate_conversations(
                    AsyncMock(),
                    limit=10,
                )
            )

        assert {item["id"] for item in selected} == {
            "cnv_support",
            "cnv_shared",
            "cnv_assigned",
        }
        assert stats == {
            "source_support": 2,
            "source_assigned": 2,
            "source_union": 3,
        }
        assert errors == 0
        queries = [call.args[0] for call in search.await_args_list]
        assert f"inbox:{reminder_module.SUPPORT_INBOX_ID} is:open" in queries
        assert (
            f"assignee:{settings.front_teammate_bobby} is:open"
            in queries
        )

    asyncio.run(run_case())


def test_scope_skips_conversations_checked_after_their_last_update():
    async def run_case():
        old = _conversation(
            "cnv_old",
            updated_at=NOW - timedelta(hours=2),
        )
        fresh = _conversation("cnv_fresh", updated_at=NOW)
        with (
            patch.object(
                reminder_module,
                "_search_open_conversations",
                AsyncMock(side_effect=[[old, fresh], []]),
            ),
            patch.object(
                reminder_module,
                "_last_sla_checks",
                AsyncMock(
                    return_value={
                        "cnv_old": NOW - timedelta(hours=1),
                    }
                ),
            ),
        ):
            selected, _, _ = await reminder_module._candidate_conversations(
                AsyncMock(),
                limit=10,
            )
        assert [item["id"] for item in selected] == ["cnv_fresh"]

    asyncio.run(run_case())


def test_due_conversation_sends_personal_reminder_with_front_link_once():
    async def run_case():
        conversation = _conversation()
        send = AsyncMock(return_value=True)
        record = AsyncMock()
        with (
            patch.object(
                reminder_module,
                "_candidate_conversations",
                AsyncMock(
                    return_value=(
                        [conversation],
                        {
                            "source_support": 1,
                            "source_assigned": 0,
                            "source_union": 1,
                        },
                        0,
                    )
                ),
            ),
            patch.object(
                reminder_module,
                "_front_snapshot",
                AsyncMock(return_value=([_inbound()], [])),
            ),
            patch.object(
                reminder_module,
                "get_action",
                AsyncMock(return_value=None),
            ),
            patch.object(reminder_module, "record_action", record),
            patch.object(
                reminder_module.feishu,
                "send_bobby_personal_text",
                send,
            ),
        ):
            result = await reminder_module.scan_unanswered_conversations(
                AsyncMock(),
                now=NOW,
            )

        assert result["due"] == 1
        assert result["reminded"] == 1
        reminder_text = send.await_args.args[0]
        assert "超过 12 小时未回复" in reminder_text
        assert f"{settings.front_app_base_url}/cnv_due" in reminder_text
        assert record.await_args.args[-1] == '{"status": "reminded"}'

    asyncio.run(run_case())


def test_customer_message_before_launch_date_is_ignored_permanently():
    async def run_case():
        conversation = _conversation("cnv_historical")
        historical = _inbound("msg_historical", hours_ago=17)
        send = AsyncMock()
        record = AsyncMock()
        with (
            patch.object(
                reminder_module,
                "_candidate_conversations",
                AsyncMock(
                    return_value=(
                        [conversation],
                        {
                            "source_support": 1,
                            "source_assigned": 0,
                            "source_union": 1,
                        },
                        0,
                    )
                ),
            ),
            patch.object(
                reminder_module,
                "_front_snapshot",
                AsyncMock(return_value=([historical], [])),
            ),
            patch.object(
                reminder_module,
                "get_action",
                AsyncMock(return_value=None),
            ),
            patch.object(reminder_module, "record_action", record),
            patch.object(
                reminder_module.feishu,
                "send_bobby_personal_text",
                send,
            ),
        ):
            result = await reminder_module.scan_unanswered_conversations(
                AsyncMock(),
                now=NOW,
            )

        assert reminder_module._timestamp(historical) < reminder_module.SLA_START_AT_UTC
        assert result["before_start"] == 1
        assert result["due"] == 0
        send.assert_not_awaited()
        assert record.await_args.args[-1] == '{"status": "ignored_before_start"}'

    asyncio.run(run_case())


def test_bobby_comment_records_terminal_check_without_sending():
    async def run_case():
        conversation = _conversation("cnv_owned")
        send = AsyncMock()
        record = AsyncMock()
        with (
            patch.object(
                reminder_module,
                "_candidate_conversations",
                AsyncMock(
                    return_value=(
                        [conversation],
                        {
                            "source_support": 1,
                            "source_assigned": 0,
                            "source_union": 1,
                        },
                        0,
                    )
                ),
            ),
            patch.object(
                reminder_module,
                "_front_snapshot",
                AsyncMock(
                    return_value=(
                        [_inbound()],
                        [
                            _comment(
                                "bobby@dify.ai",
                                settings.front_teammate_bobby,
                            )
                        ],
                    )
                ),
            ),
            patch.object(
                reminder_module,
                "get_action",
                AsyncMock(return_value=None),
            ),
            patch.object(reminder_module, "record_action", record),
            patch.object(
                reminder_module.feishu,
                "send_bobby_personal_text",
                send,
            ),
        ):
            result = await reminder_module.scan_unanswered_conversations(
                AsyncMock(),
                now=NOW,
            )

        assert result["bobby_commented"] == 1
        send.assert_not_awaited()
        assert record.await_args.args[-1] == '{"status": "bobby_commented"}'

    asyncio.run(run_case())


def test_feishu_failure_is_not_recorded_so_it_can_retry():
    async def run_case():
        conversation = _conversation("cnv_retry")
        record = AsyncMock()
        with (
            patch.object(
                reminder_module,
                "_candidate_conversations",
                AsyncMock(
                    return_value=(
                        [conversation],
                        {
                            "source_support": 1,
                            "source_assigned": 0,
                            "source_union": 1,
                        },
                        0,
                    )
                ),
            ),
            patch.object(
                reminder_module,
                "_front_snapshot",
                AsyncMock(return_value=([_inbound()], [])),
            ),
            patch.object(
                reminder_module,
                "get_action",
                AsyncMock(return_value=None),
            ),
            patch.object(reminder_module, "record_action", record),
            patch.object(
                reminder_module.feishu,
                "send_bobby_personal_text",
                AsyncMock(return_value=False),
            ),
        ):
            result = await reminder_module.scan_unanswered_conversations(
                AsyncMock(),
                now=NOW,
            )

        assert result["errors"] == 1
        record.assert_not_awaited()

    asyncio.run(run_case())


def test_china_workday_uses_asia_shanghai_weekdays():
    assert is_china_weekday(datetime(2026, 8, 28, 8, 0, 0))
    assert not is_china_weekday(datetime(2026, 8, 29, 8, 0, 0))


def test_weekend_scan_does_not_search_front_or_send_reminders():
    async def run_case():
        candidates = AsyncMock()
        send = AsyncMock()
        with (
            patch.object(
                reminder_module,
                "_candidate_conversations",
                candidates,
            ),
            patch.object(
                reminder_module.feishu,
                "send_bobby_personal_text",
                send,
            ),
        ):
            result = await reminder_module.scan_unanswered_conversations(
                AsyncMock(),
                now=datetime(2026, 8, 29, 8, 0, 0),
            )

        assert result["skipped_non_workday"] == 1
        candidates.assert_not_awaited()
        send.assert_not_awaited()

    asyncio.run(run_case())


def test_scheduler_registers_bounded_unanswered_reminder_job():
    isolated_scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    try:
        with (
            patch.object(scheduler_module, "scheduler", isolated_scheduler),
            patch.object(isolated_scheduler, "start") as start,
        ):
            scheduler_module.start_scheduler()
            start.assert_called_once_with()
            job = isolated_scheduler.get_job(
                "send_unanswered_email_reminders_every_15m"
            )
            assert job is not None
            assert job.func is scheduler_module.send_unanswered_email_reminders
            assert job.trigger.interval == timedelta(minutes=15)
            assert job.coalesce is True
            assert job.max_instances == 1
    finally:
        if isolated_scheduler.running:
            isolated_scheduler.shutdown(wait=False)
        else:
            isolated_scheduler.remove_all_jobs()


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS: {name}")


if __name__ == "__main__":
    run_all()
