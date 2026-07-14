import json
import re
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
    "partnership": {"name": "partnership_forwarded_keep_open", "handled": True, "tool": "front_forward_to_community", "target": "marketing@dify.ai", "step": "forwarded_keep_open"},
    "marketing": {"name": "marketing_move_inbox", "handled": True, "tool": "front_forward_to_marketing", "inbox": "Marketing", "step": "moved_inbox"},
    "security": {"name": "security_move_inbox", "handled": True, "tool": "front_forward_to_security", "inbox": "Security", "step": "moved_inbox"},
    "spam": {"name": "spam_auto_close", "handled": True, "tool": "front_close_conversation", "step": "closed_spam", "keep_open": False},
    "legal": {"name": "legal_forwarded_keep_open", "handled": True, "tool": "front_forward_to_legal", "target": "geyan@dify.ai", "step": "forwarded_keep_open"},
    "roadmap": {"name": "roadmap_skill_flow", "handled": False, "customer_action": "draft"},
    "investment": {"name": "investment_forwarded_keep_open", "handled": False, "customer_action": "none", "target": "claudia@dify.ai"},
    "business": {"name": "business_move_inbox", "handled": True, "tool": "front_forward_to_business", "inbox": "Business", "step": "moved_inbox"},
    "data_export": {"name": "data_export_skill_flow", "handled": False, "customer_action": "draft"},
    "recruiting": {"name": "recruiting_skill_flow", "handled": False, "customer_action": "draft"},
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


def test_skills_only_reference_sybil_feishu_tool():
    offenders = []
    allowed = {"account.md", "education.md"}
    for path in sorted(SKILLS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if "feishu" not in text.lower() and "飞书" not in text:
            continue
        if path.name not in allowed or "feishu_notify_sybil_group" not in text:
            offenders.append(str(path))
    assert not offenders, f"Unexpected Feishu skill references: {offenders}"


def test_internal_forwarding_skill_targets_are_current():
    checks = {
        "legal": ["geyan@dify.ai", "keep the conversation open"],
        "partnership": ["marketing@dify.ai", "original Front conversation"],
        "education": ["feishu_notify_sybil_group", "Linear", "education_review"],
        "unclear": ["front_forward_to_bobby", "人工判断"],
        "security": ["front_forward_to_security", "security inbox"],
        "business": ["front_forward_to_business", "Business inbox"],
    }
    for category, expected_strings in checks.items():
        text = _skill_text(category)
        for expected in expected_strings:
            assert expected in text, f"{category}.md missing {expected!r}"




def test_education_card_binding_without_supported_card_is_final_draft():
    text = _skill_text("education")
    for expected in [
        "card binding cannot be bypassed",
        "no supported international credit card",
        "Do NOT create Linear tickets",
        "Do NOT notify Sybil",
        'step="draft_created"',
    ]:
        assert expected in text, f"education.md missing {expected!r}"


def test_account_login_requires_deployment_and_saas_handoff():
    text = _skill_text("account")
    for expected in [
        "awaiting_deployment_and_plan_confirmation",
        "Dify Cloud/SaaS",
        "self-hosted",
        "linear_create_ticket",
        "front_forward_to_bobby",
        "SaaS login issue",
    ]:
        assert expected in text, f"account.md missing {expected!r}"


def test_billing_invoice_correction_requires_verified_manual_credit_note():
    text = _skill_text("billing")
    for expected in [
        "A finalized or paid invoice cannot be modified or reissued",
        "apply to future invoices only",
        "awaiting_invoice_details",
        "awaiting_credit_note_acceptance",
        "front_add_comment",
        "Customer accepted supplementary Credit Note: yes",
        'step="manual_review"',
        "There is no billing-provider tool in this agent",
        'Never claim a Credit Note "has been issued"',
        "Only a human operator may send the final issuance confirmation",
    ]:
        assert expected in text, f"billing.md missing {expected!r}"


def test_billing_is_an_explicit_multi_turn_category():
    source = Path("agent/orchestrator.py").read_text(encoding="utf-8")
    assert 'category not in {"education", "billing"}' in source
    assert "without a multi-turn flow" in source
    assert 'category == "billing" and step == "manual_review"' in source
    assert "pending human review" in source


def test_invoice_correction_classifies_as_billing_invoice():
    text = _skill_text("classify")
    for expected in [
        "Existing Invoice Correction After Billing Details Update",
        '"category": "billing"',
        '"sub_type": "invoice"',
        "correction/reissue, or Credit Note request",
    ]:
        assert expected in text, f"classify.md missing {expected!r}"


def test_sybil_forward_tool_supports_bobby_cc():
    tool_source = Path("agent/tool_registry.py").read_text(encoding="utf-8")
    handoff_source = Path("tools/handoff.py").read_text(encoding="utf-8")
    assert "cc_email" in tool_source
    assert 'cc_email=args.get("cc_email", "")' in tool_source
    assert "cc_email=cc_email or None" in handoff_source


def test_sybil_group_message_is_single_mention_prefixed_body():
    source = Path("tools/feishu.py").read_text(encoding="utf-8")
    assert "@Sybil" in source
    assert "return f\"{mention} {normalized_message}\".strip()" in source
    assert "has_linear_url = bool(_extract_linear_url(normalized_message))" in source
    assert "placeholder_pattern" in source
    assert "Front-Agent handoff" not in source
    assert "Conversation ID:" not in source


def test_technical_support_has_paid_and_non_paid_paths():
    text = _skill_text("technical")
    for expected in [
        "question mark icon next to the personal avatar",
        "GitHub issues",
        "https://docs.dify.ai",
        "https://github.com/langgenius/dify/issues",
        "no clear paid-plan evidence",
        "Do not create Linear tickets for non-paid technical support",
    ]:
        assert expected in text, f"technical.md missing {expected!r}"


def test_skills_do_not_reference_unavailable_tools_or_url_placeholders():
    forbidden = [
        "move_conversation_to_inbox",
        'linear_url="[',
        "Linear: [actual URL",
        "Linear: [URL",
        "[actual URL returned above]",
    ]
    offenders = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for item in forbidden:
            if item in text:
                offenders.append(f"{path}: contains {item!r}")
    assert not offenders, "Unsafe skill references found:\n" + "\n".join(offenders)


def test_skill_guardrails_are_current():
    technical = _skill_text("technical")
    for expected in ["docs_search", "github_search", "Linear ticket policy"]:
        assert expected in technical, f"technical.md missing {expected!r}"

    education = _skill_text("education")
    for expected in ["Tool Sequencing and Hard Stops", "exact URL returned", "school_name", "school_domain", "linear_url"]:
        assert expected in education, f"education.md missing {expected!r}"

    account = _skill_text("account")
    for expected in ["Tool Sequencing and Hard Stops", "waiting=true", "exact Linear URL", "payload should include the Linear URL"]:
        assert expected in account, f"account.md missing {expected!r}"

    business = _skill_text("business")
    assert "business_move_inbox" in business
    assert "front_forward_to_business" in business
    assert "No customer draft" in business


def test_reply_skills_have_draft_quality_bar():
    reply_skills = [
        "account",
        "billing",
        "data_export",
        "education",
        "purchase",
        "recruiting",
        "roadmap",
        "technical",
    ]
    required = [
        "Do not invent",
        "If required facts are missing",
        "Do not mention internal tools",
        "Do not promise",
        "clear next step",
    ]
    for skill in reply_skills:
        text = _skill_text(skill)
        assert "## Draft Quality Bar" in text, f"{skill}.md missing Draft Quality Bar"
        for phrase in required:
            assert phrase in text, f"{skill}.md missing draft quality rule {phrase!r}"


def test_classify_few_shot_examples_are_complete_json():
    text = _skill_text("classify")
    examples = text.split("## Few-Shot Examples", 1)[1].split("## Routing-Oriented Classification Rules", 1)[0]
    required = {
        "category",
        "sub_type",
        "is_paid_user",
        "is_premium",
        "urgency",
        "sender_email",
        "summary",
        "confidence",
        "flags",
        "secondary_intents",
        "evidence",
    }
    blocks = re.findall(r"```json\n(.*?)\n```", examples, flags=re.DOTALL)
    assert blocks, "classify.md must include JSON few-shot examples"
    for block in blocks:
        data = json.loads(block)
        assert required <= set(data), f"classification example missing fields: {required - set(data)}"
        assert data.get("sub_type") != "null"
        assert isinstance(data.get("flags"), list)
        assert isinstance(data.get("secondary_intents"), list)
        assert isinstance(data.get("evidence"), list)


def test_recruiting_reply_points_to_joinus_email_only():
    text = _skill_text("recruiting")
    assert "joinus@dify.ai" in text
    assert "official careers page" not in text


def test_technical_support_uses_channel_guidance_not_direct_fixes():
    text = _skill_text("technical")
    for expected in [
        "Do not provide step-by-step technical fixes",
        "https://docs.dify.ai",
        "https://github.com/langgenius/dify/issues",
        "business@dify.ai",
        "subscription verification details",
        "not to remove",
    ]:
        assert expected in text, f"technical.md missing {expected!r}"

def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
    print("skill policy tests passed")
