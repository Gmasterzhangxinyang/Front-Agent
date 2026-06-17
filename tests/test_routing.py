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
    assert route.name == "marketing_forwarded_keep_open"
    assert route.tool_name == "front_forward_to_community"
    assert route.tool_args["summary"] == "Marketplace plugin cooperation request"
    assert route.state_step == "forwarded_keep_open"


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


def test_forward_tools_do_not_create_forward_drafts():
    source = Path("agent/tool_registry.py").read_text()
    assert "front.forward_conversation(" not in source


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("routing tests passed")
