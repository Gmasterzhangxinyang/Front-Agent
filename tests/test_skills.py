import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.classification import ALLOWED_CATEGORIES, normalize_classification
from agent.routing import decide_initial_route

SKILLS_DIR = Path("skills")

EXPECTED_ROUTE_CASES = {
    "technical": {"name": "technical_skill_flow", "handled": False, "customer_action": "draft"},
    "account": {"name": "account_skill_flow", "handled": False, "customer_action": "draft", "target": "bobby@dify.ai"},
    "purchase": {"name": "purchase_skill_flow", "handled": False, "customer_action": "draft"},
    "education": {"name": "education_skill_flow", "handled": False, "customer_action": "draft", "target": "sybil@dify.ai"},
    "billing": {"name": "billing_skill_flow", "handled": False, "customer_action": "draft"},
    "partnership": {"name": "marketing_forwarded_keep_open", "handled": True, "tool": "front_forward_to_community", "target": "marketing@dify.ai", "step": "forwarded_keep_open"},
    "marketing": {"name": "marketing_forwarded_keep_open", "handled": True, "tool": "front_forward_to_partnerships", "target": "marketing@dify.ai", "step": "forwarded_keep_open"},
    "security": {"name": "security_move_inbox", "handled": True, "tool": "front_forward_to_security", "inbox": "Security", "step": "moved_inbox"},
    "spam": {"name": "spam_auto_close", "handled": True, "tool": "front_close_conversation", "step": "closed_spam", "keep_open": False},
    "legal": {"name": "legal_forwarded_keep_open", "handled": True, "tool": "front_forward_to_legal", "target": "geyan@dify.ai", "step": "forwarded_keep_open"},
    "roadmap": {"name": "roadmap_skill_flow", "handled": False, "customer_action": "draft"},
    "investment": {"name": "investment_forwarded_keep_open", "handled": False, "customer_action": "none", "target": "claudia@dify.ai"},
    "business": {"name": "business_skill_flow", "handled": False, "customer_action": "none"},
    "data_export": {"name": "data_export_skill_flow", "handled": False, "customer_action": "draft"},
    "unclear": {"name": "manual_review_bobby", "handled": True, "tool": "front_forward_to_bobby", "target": "bobby@dify.ai", "step": "manual_review"},
}


def _skill_text(name: str) -> str:
    return (SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")


def test_skill_file_exists_for_every_category():
    missing = [category for category in sorted(ALLOWED_CATEGORIES) if not (SKILLS_DIR / f"{category}.md").exists()]
    assert not missing, f"Missing skill files: {missing}"


def test_each_skill_has_basic_structure():
    for category in sorted(ALLOWED_CATEGORIES):
        text = _skill_text(category)
        assert text.startswith("# Skill:"), f"{category}.md must start with '# Skill:'"
        assert "## Purpose" in text, f"{category}.md missing Purpose section"
        assert "## Steps" in text or "## Steps by Sub-type" in text, f"{category}.md missing Steps section"


def test_every_category_has_expected_route_policy():
    assert set(EXPECTED_ROUTE_CASES) == set(ALLOWED_CATEGORIES)
    for category, expected in EXPECTED_ROUTE_CASES.items():
        result = normalize_classification({
            "category": category,
            "sub_type": "general",
            "confidence": 0.1,
            "summary": f"Sample {category} email",
        })
        route = decide_initial_route(result, "cnv_test", "sender@example.com")
        assert route.name == expected["name"], category
        assert route.handled_before_skill is expected["handled"], category
        if "tool" in expected:
            assert route.tool_name == expected["tool"], category
        if "target" in expected:
            assert route.internal_target == expected["target"], category
        if "inbox" in expected:
            assert route.inbox_target == expected["inbox"], category
        if "step" in expected:
            assert route.state_step == expected["step"], category
        if "customer_action" in expected:
            assert route.customer_action == expected["customer_action"], category
        if "keep_open" in expected:
            assert route.keep_open is expected["keep_open"], category


def test_legal_threat_flag_routes_to_legal_even_if_category_differs():
    result = normalize_classification({
        "category": "account",
        "flags": ["legal_threat"],
        "summary": "User mentions a lawyer.",
    })
    route = decide_initial_route(result, "cnv_test", "sender@example.com")
    assert route.name == "legal_forwarded_keep_open"
    assert route.tool_name == "front_forward_to_legal"
    assert route.internal_target == "geyan@dify.ai"
    assert route.state_step == "forwarded_keep_open"


def test_only_spam_skill_instructs_auto_close():
    offenders = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        if path.name == "spam.md":
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "front_close_conversation" in line and "Do NOT" not in line:
                offenders.append(f"{path}:{line_no}: {line}")
    assert not offenders, "Only spam.md may instruct front_close_conversation:\n" + "\n".join(offenders)


def test_skills_do_not_instruct_direct_customer_reply():
    offenders = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            lower = line.lower()
            if "front_reply" in line and "do not" not in lower:
                offenders.append(f"{path}:{line_no}: {line}")
    assert not offenders, "Skills must not instruct direct customer replies:\n" + "\n".join(offenders)


def test_skills_do_not_reference_removed_feishu_runtime():
    offenders = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if "feishu" in text.lower() or "飞书" in text:
            offenders.append(str(path))
    assert not offenders, f"Skills still reference Feishu: {offenders}"


def test_internal_forwarding_skill_targets_are_current():
    checks = {
        "legal": ["geyan@dify.ai", "keep the conversation open"],
        "partnership": ["marketing@dify.ai", "original Front conversation"],
        "education": ["front_forward_to_sybil", "Linear"],
        "unclear": ["front_forward_to_bobby", "人工判断"],
        "security": ["front_forward_to_security", "security inbox"],
    }
    for category, expected_strings in checks.items():
        text = _skill_text(category)
        for expected in expected_strings:
            assert expected in text, f"{category}.md missing {expected!r}"



def test_technical_support_has_paid_and_non_paid_paths():
    text = _skill_text("technical")
    for expected in [
        "Settings -> Support -> Contact Us",
        "GitHub issues",
        "Dify community",
        "no clear paid-plan evidence",
        "Do not create Linear tickets for non-paid technical support",
    ]:
        assert expected in text, f"technical.md missing {expected!r}"

def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("skill policy tests passed")
