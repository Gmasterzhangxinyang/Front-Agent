import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.classification import normalize_classification, parse_classification_json, should_auto_close_spam
from agent.routing import decide_initial_route


def test_parse_fenced_json_with_extra_text():
    raw = """Here is the result:
```json
{"category":"technical","sub_type":"how_to","confidence":0.8,"summary":"How-to question"}
```
"""
    parsed = parse_classification_json(raw)
    assert parsed["category"] == "technical"
    assert parsed["sub_type"] == "how_to"


def test_invalid_category_falls_back_to_unclear_low_confidence():
    result = normalize_classification({"category": "random", "confidence": 0.9}, "user@example.com")
    assert result.category == "unclear"
    assert result.confidence == 0.2
    assert result.sender_email == "user@example.com"


def test_spam_category_auto_closes():
    result = normalize_classification({
        "category": "spam",
        "confidence": 0.99,
        "summary": "Promotional event sponsorship package",
    })
    assert should_auto_close_spam(result)
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "spam_auto_close"
    assert route.tool_name == "front_close_conversation"
    assert route.keep_open is False
    assert route.state_step == "closed_spam"


def test_video_channel_collaboration_routes_to_marketing_not_spam():
    result = normalize_classification({
        "category": "marketing",
        "sub_type": "collaboration",
        "confidence": 0.9,
        "summary": "YouTube channel video collaboration sponsorship opportunity for Dify",
        "evidence": ["channel generated 112,800 views", "explore a collaboration"],
    })
    assert not should_auto_close_spam(result)
    route = decide_initial_route(result, "cnv_test", "creator.com")
    assert route.name == "marketing_move_inbox"
    assert route.tool_name == "front_forward_to_marketing"
    assert route.state_step == "moved_inbox"
    assert route.inbox_target == "Marketing"


def test_low_confidence_does_not_control_route():
    result = normalize_classification({
        "category": "technical",
        "confidence": 0.1,
        "summary": "A technical question with low model confidence",
    })
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "technical_skill_flow"
    assert route.customer_action == "draft"
    assert route.tool_name is None
    assert route.state_step == "skill_in_progress"


def test_unclear_goes_to_bobby_manual_review():
    result = normalize_classification({
        "category": "unclear",
        "confidence": 0.9,
        "summary": "Cannot determine the request",
    })
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "manual_review_bobby"
    assert route.tool_name == "front_forward_to_bobby"
    assert route.state_step == "manual_review"


def test_security_moves_to_security_inbox():
    result = normalize_classification({
        "category": "security",
        "sub_type": "urgent",
        "confidence": 0.95,
        "summary": "Responsible disclosure report",
    })
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "security_move_inbox"
    assert route.tool_name == "front_forward_to_security"
    assert route.keep_open is True
    assert route.state_step == "moved_inbox"


def test_partnership_forwards_to_marketing():
    result = normalize_classification({
        "category": "partnership",
        "sub_type": "marketplace",
        "confidence": 0.9,
        "summary": "Marketplace plugin cooperation request",
    })
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "partnership_forwarded_keep_open"
    assert route.tool_name == "front_forward_to_community"
    assert route.tool_args["summary"] == "Marketplace plugin cooperation request"
    assert route.state_step == "forwarded_keep_open"


def test_marketing_moves_to_marketing_inbox():
    result = normalize_classification({
        "category": "marketing",
        "sub_type": "campaign",
        "confidence": 0.9,
        "summary": "Marketing campaign collaboration request",
    })
    route = decide_initial_route(result, "cnv_test", "sender.com")
    assert route.name == "marketing_move_inbox"
    assert route.tool_name == "front_forward_to_marketing"
    assert route.state_step == "moved_inbox"
    assert route.inbox_target == "Marketing"


def test_business_routes_to_business_inbox():
    result = normalize_classification({
        "category": "business",
        "sub_type": "enterprise_inquiry",
        "confidence": 0.9,
        "summary": "Enterprise procurement team requests a quote and vendor onboarding",
    })
    route = decide_initial_route(result, "cnv_test", "buyer@example.com")
    assert route.name == "business_move_inbox"
    assert route.handled_before_skill is True
    assert route.tool_name == "front_forward_to_business"
    assert route.state_step == "moved_inbox"
    assert route.inbox_target == "Business"
    assert route.customer_action == "none"


def test_legal_routes_to_geyan_and_stays_open():
    result = normalize_classification({
        "category": "legal",
        "sub_type": "lawyer_letter",
        "confidence": 0.9,
        "summary": "Lawyer letter about contract dispute",
    })
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "legal_forwarded_keep_open"
    assert route.tool_name == "front_forward_to_legal"
    assert route.internal_target == "geyan@dify.ai"
    assert route.state_step == "forwarded_keep_open"
    assert route.keep_open is True
    assert route.customer_action == "none"


def test_legal_threat_flag_overrides_to_geyan_route():
    result = normalize_classification({
        "category": "account",
        "sub_type": "cant_login",
        "confidence": 0.7,
        "flags": ["legal_threat"],
        "summary": "User says their lawyer will contact Dify",
    })
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "legal_forwarded_keep_open"
    assert route.state_category == "legal"
    assert route.tool_name == "front_forward_to_legal"
    assert route.internal_target == "geyan@dify.ai"


def test_account_route_has_explicit_policy():
    result = normalize_classification({
        "category": "account",
        "sub_type": "cant_login",
        "confidence": 0.8,
        "summary": "Paid user cannot receive verification code",
    })
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "account_skill_flow"
    assert route.customer_action == "draft"
    assert route.internal_target == "bobby@dify.ai"


def test_education_route_has_explicit_policy():
    result = normalize_classification({
        "category": "education",
        "sub_type": "rejected",
        "confidence": 0.8,
        "summary": "University education plan review",
    })
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "education_skill_flow"
    assert route.customer_action == "draft"
    assert route.internal_target == "sybil@dify.ai"


def test_handoff_rejects_external_recipient():
    from tools.handoff import _is_allowed_internal_recipient

    assert _is_allowed_internal_recipient("bobby@dify.ai")
    assert not _is_allowed_internal_recipient("customer@example.com")


def test_generic_front_forward_not_exposed():
    source = Path("agent/tool_registry.py").read_text()
    assert '"name": "front_forward"' not in source
    assert 'tool_name == "front_forward"' not in source


def test_tool_registry_does_not_send_direct_customer_replies():
    source = Path("agent/tool_registry.py").read_text()
    assert "reply_to_conversation" not in source


def test_close_tool_is_not_exposed_to_model():
    source = Path("agent/tool_registry.py").read_text()
    schemas_source = source.split("async def execute_tool_call", 1)[0]
    assert '"name": "front_close_conversation"' not in schemas_source


def test_legal_threat_does_not_notify_bobby_from_orchestrator():
    source = Path("agent/orchestrator.py").read_text()
    assert 'or "legal_threat" in flags' not in source
    assert 'if "legal_threat" in flags' not in source


def test_forward_tools_send_forward_with_original_thread_body():
    tool_source = Path("agent/tool_registry.py").read_text()
    front_source = Path("tools/front.py").read_text()
    assert "front.forward_conversation(" not in tool_source
    assert "_build_forward_body(conversation_id, summary" in front_source
    assert "Original Front conversation:" in front_source


def test_feedback_system_is_disabled_by_default_and_gated():
    config_source = Path("config.py").read_text()
    main_source = Path("main.py").read_text()
    orchestrator_source = Path("agent/orchestrator.py").read_text()
    assert "enable_feedback_system: bool = False" in config_source
    assert "if settings.enable_feedback_system:" in main_source
    assert "from routes.feedback_api" not in main_source.split("if settings.enable_feedback_system:", 1)[0]
    assert "if not settings.enable_feedback_system:" in orchestrator_source


def test_default_model_is_gpt_5_5():
    assert 'openai_model: str = "gpt-5.5"' in Path("config.py").read_text()
    assert "OPENAI_MODEL=gpt-5.5" in Path(".env.example").read_text()


def test_chat_completion_kwargs_are_gpt_5_compatible():
    from agent.llm_client import chat_completion_kwargs

    params = chat_completion_kwargs(
        "gpt-5.5",
        [{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=10,
    )
    assert "temperature" not in params
    assert "max_tokens" not in params
    assert params["max_completion_tokens"] == 1024


def test_chat_completion_kwargs_preserve_legacy_model_params():
    from agent.llm_client import chat_completion_kwargs

    params = chat_completion_kwargs(
        "gpt-4o",
        [{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=10,
    )
    assert params["temperature"] == 0
    assert params["max_tokens"] == 10
    assert "max_completion_tokens" not in params


def test_openai_models_ignore_minimax_base_url():
    from types import SimpleNamespace

    from agent.llm_client import is_openai_model

    settings = SimpleNamespace(openai_model="gpt-5.5", minimax_api_key="set")
    assert is_openai_model(settings.openai_model)


def test_non_openai_models_can_use_minimax_provider():
    from agent.llm_client import is_openai_model

    assert not is_openai_model("abab6.5-chat")



def test_front_webhook_has_concurrency_guards():
    source = Path("webhooks/front_webhook.py").read_text()
    assert "MAX_CONCURRENT_WEBHOOKS" in source
    assert "asyncio.Semaphore" in source
    assert "_conversation_locks" in source
    assert "_get_conversation_lock" in source
    assert "async with _webhook_semaphore" in source
    assert "async with lock" in source

def test_front_webhook_reopens_handler_errors():
    source = Path("webhooks/front_webhook.py").read_text()
    assert "front.reopen_conversation(conversation_id)" in source
    assert "failed_needs_review" in source
    assert "handler_error" in source


def test_front_has_reopen_conversation_helper():
    source = Path("tools/front.py").read_text()
    assert "async def reopen_conversation" in source
    assert 'json={"status": "open"}' in source


def test_action_log_and_original_sender_guards_exist():
    models_source = Path("models.py").read_text()
    state_source = Path("tools/state.py").read_text()
    registry_source = Path("agent/tool_registry.py").read_text()
    orchestrator_source = Path("agent/orchestrator.py").read_text()
    front_source = Path("tools/front.py").read_text()

    assert "class ConversationAction" in models_source
    assert 'UniqueConstraint("conversation_id", "action_type", "action_key"' in models_source
    assert "async def record_action" in state_source
    assert "not state.sender_email" in state_source
    assert "DEDUPE_TOOL_NAMES" in registry_source
    assert "state_tool.get_action" in registry_source
    assert "state_tool.record_action" in registry_source
    assert 'args["to_email"] = sender_email' in orchestrator_source
    assert "to_email: str | None = None" in front_source
    assert "if not sender_email:" in front_source


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("routing tests passed")
