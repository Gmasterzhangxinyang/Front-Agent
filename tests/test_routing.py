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
    assert route.name == "skill_flow"
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


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("routing tests passed")
