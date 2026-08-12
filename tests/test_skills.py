import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.classification import ALLOWED_CATEGORIES, normalize_classification
from agent.routing import EDUCATION_ACCOUNT_SUSPENSION_DRAFT, decide_initial_route

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




def test_education_reply_continuation_and_application_policy_is_explicit():
    education = _skill_text("education")
    for expected in [
        "Reply Continuation Policy",
        "how_to_apply",
        "Get Education Verified",
        "forwarded_keep_open",
        "Never call `linear_create_ticket` again",
        "front_add_comment",
        "education_review_followup",
        "preserve the existing `school_name`, `school_domain`, `linear_url`",
        "subscription-management#dify-for-education",
        "yearly Professional plan",
    ]:
        assert expected in education, f"education.md missing {expected!r}"

    classify = _skill_text("classify")
    assert "Education Plan Application Question" in classify
    assert "| education | how_to_apply |" in classify


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


def test_education_account_suspension_has_one_verbatim_draft_only():
    education = _skill_text("education")
    classify = _skill_text("classify")
    for expected in [
        "account_suspended",
        "An Education Plan application or verification that was rejected",
        "remains sub_type=`rejected`",
        "Call `front_create_draft` with the **Account suspension** template below verbatim",
        "Do not personalize, paraphrase, shorten",
        "Do not create a Linear ticket, notify Sybil, forward the conversation",
        "coordinated account abuse",
        "Your account will therefore remain suspended",
        "Education Verified benefits",
    ]:
        assert expected in education, f"education.md missing {expected!r}"

    assert "| education | account_suspended |" in classify
    assert '"sub_type": "account_suspended"' in classify

    template = education.split("### Account suspension", 1)[1].split("```", 2)[1].strip()
    assert template == EDUCATION_ACCOUNT_SUSPENSION_DRAFT


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


def test_invoice_credit_note_flow_is_draft_then_internal_comment_only():
    billing = _skill_text("billing")
    for expected in [
        "awaiting_credit_note_confirmation",
        "Thank you for reaching out.",
        "has already been issued",
        "we're unfortunately unable to make changes to or reissue the original invoice",
        "To ensure that your billing details appear correctly on future invoices",
        "could you please update and verify them in the Billing Portal?",
        "supplementary Credit Note",
        "containing the updated information",
        "would not modify or replace the original invoice",
        "If you would like us to request a Credit Note for you",
        "we'll be happy to assist.",
        "front_add_comment",
        "用户二次来信确认需要 Credit Note，应该交给 Elsie 处理。",
        "Workspace:",
        "Invoice:",
        "Organization:",
        "Tax ID:",
        "Billing Address:",
        "credit_note_requested",
        "Do not call `front_assign`",
        "Do not call `linear_create_ticket`",
        'Do not set step="manual_review"',
    ]:
        assert expected in billing, f"billing.md missing {expected!r}"

    invoice_section = billing.split("### invoice", 1)[1].split("### other", 1)[0]
    assert "@Elsie" not in invoice_section


def test_paid_subscription_cancellation_gives_exact_self_service_path():
    billing = _skill_text("billing")
    cancellation_section = billing.split(
        "### downgrade / paid subscription cancellation",
        1,
    )[1].split("### invoice", 1)[0]

    for expected in [
        "directly below the blue **Update payment method** button",
        "**Manage your subscriptions**",
        "current workspace name in the upper-left corner",
        "**Settings** -> **Billing**",
        "**Billing and Subscriptions** card -> **Manage**",
        "**Cancel plan**",
        "do not offer manual cancellation",
        "Do not add a fallback asking the customer to provide an account/workspace email for manual review",
    ]:
        assert expected in cancellation_section, (
            f"billing cancellation guidance missing {expected!r}"
        )

    assert "our team can review" not in cancellation_section


def test_mainland_china_vat_invoice_policy_is_explicit():
    billing = _skill_text("billing")
    classify = _skill_text("classify")
    for expected in [
        "Mainland China tax invoice / VAT fapiao",
        "LangGenius, Inc. is not a PRC-registered invoicing entity",
        "does not issue invoices through the PRC tax administration system",
        "including either a special VAT invoice or a general VAT invoice",
        "official commercial billing documents issued by LangGenius, Inc.",
        "Whether these documents can be accepted for reimbursement is subject to your institution's reimbursement policies",
        "If your institution requires additional billing information or supporting documentation",
        "we can check what we're able to provide",
        "Do not make broader tax-law conclusions",
        "Do not tell the customer to use them for reimbursement",
        "Do not suggest that downloading an Invoice/receipt or updating the Billing Portal can produce a PRC tax invoice",
    ]:
        assert expected in billing, f"billing.md missing {expected!r}"

    assert "Please note that the service provider for this transaction, LangGenius, is a non-PRC entity" not in billing
    assert "For reimbursement purposes, please use the commercial invoice" not in billing
    assert "Mainland China tax invoice/fapiao/VAT special invoice request" in classify


def test_invoice_credit_note_flow_has_classification_example():
    classify = _skill_text("classify")
    for expected in [
        "Existing Invoice Correction",
        '"category": "billing"',
        '"sub_type": "invoice"',
        "correct or reissue the existing paid invoice",
    ]:
        assert expected in classify, f"classify.md missing {expected!r}"


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
        "access to priority technical support",
        "question mark icon next to the personal avatar",
        "GitHub issues",
        "https://docs.dify.ai",
        "https://github.com/langgenius/dify/issues",
        "no clear paid-plan evidence",
        "Do not create Linear tickets for non-paid technical support",
    ]:
        assert expected in text, f"technical.md missing {expected!r}"


def test_premium_purchase_guidance_distinguishes_poc_from_enterprise():
    purchase = _skill_text("purchase")
    classify = _skill_text("classify")

    for expected in [
        "commercial deployment option based on Dify Community Edition",
        "one-click setup for a proof of concept (POC)",
        "large-scale production environment",
        "high-concurrency access",
        "collaboration across multiple teams",
        "enterprise-grade security management",
        "access control",
        "stronger stability requirements",
        "country or region",
        "Japan sales team",
        "Do not say that it has already been forwarded",
        "Do not forward the conversation to a sales team before the customer provides the requested location or consent",
    ]:
        assert expected in purchase, f"purchase.md missing {expected!r}"

    assert "| purchase | premium |" in classify
    assert "| purchase | pro_team | Asking about Pro/Team pricing |" in classify
    assert "A question about purchasing or evaluating Premium does not by itself make the sender an existing Premium user" in classify


def test_premium_custom_multi_az_active_active_guidance_is_explicit():
    technical = _skill_text("technical")
    purchase = _skill_text("purchase")
    classify = _skill_text("classify")

    for expected in [
        "Premium custom multi-AZ / Active-Active architecture",
        "dual-AZ or multi-AZ Active-Active deployment",
        "current standard one-click Premium deployment on AWS Marketplace",
        "Dify cannot predict the engineering complexity or issues that may arise during implementation",
        "this deployment approach is not recommended",
        "Do not provide environment-variable values, implementation steps, architecture validation",
        "Japan sales team",
        "高性能・高可用性要件に対応するため",
        "具体的な導入時の技術的な難易度や発生し得る問題を事前に予測できず",
        "この構成での運用は推奨しておりません",
        "您提到希望通过双 AZ Active-Active 架构部署 Dify Premium",
        "因此不建议采用该部署方式",
    ]:
        assert expected in technical, f"technical.md missing {expected!r}"

    for expected in [
        "Premium custom multi-AZ / Active-Active architecture",
        "approved architecture paragraph from `technical.md`",
        "engineering complexity and possible implementation issues cannot be predicted",
        "approach is therefore not recommended",
    ]:
        assert expected in purchase, f"purchase.md missing {expected!r}"

    assert "multi-AZ Active-Active" in classify
    assert "General plan-fit questions remain `purchase/premium`" in classify


def test_technical_paid_support_keeps_internal_linear_private_and_avoids_checklist():
    text = _skill_text("technical")
    for expected in [
        "Linear is strictly internal",
        "Never include a Linear issue URL, ID, title",
        "without any Linear reference",
        "Do not enumerate what the ticket should contain",
        "without asking them to repeat an exhaustive list of details",
    ]:
        assert expected in text, f"technical.md missing {expected!r}"

    assert "then include that URL in the Front draft" not in text


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
    for expected in [
        "docs_search",
        "github_search",
        "Linear ticket policy",
        "Do not open a reply by emphasizing that the customer is on a free",
        "The first substantive sentence must be about the user's issue, not their plan",
        "acknowledge the user's effort and specific symptom",
        "Do not present an unverified mechanism as what \"usually\" happens",
    ]:
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
        "authoritative English version",
        "For reference, a <Language> translation is provided below.",
        "Front automatically appends the configured default signature",
        "manual sign-off",
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


def test_global_saas_reply_language_policy_is_injected_into_agent_prompts():
    source = Path("agent/orchestrator.py").read_text(encoding="utf-8")
    for phrase in [
        "Every customer-facing draft must begin with a complete, authoritative English version",
        "For reference, a <Language> translation is provided below.",
        "Front automatically appends the configured default signature",
        "Do not put `Best regards,`",
        "preserve its English block exactly",
    ]:
        assert phrase in source
    assert source.count("{SAAS_CUSTOMER_REPLY_LANGUAGE_POLICY}") == 3

    schema_source = Path("agent/tool_registry.py").read_text(encoding="utf-8")
    assert "complete authoritative English version first" in schema_source

def test_same_sender_cross_conversation_context_prevents_duplicate_handling():
    classify = _skill_text("classify")
    account = _skill_text("account")
    education = _skill_text("education")
    for phrase in [
        "Same-Sender Cross-Conversation Context",
        "On every external customer email or reply",
        "conversations without local automation state",
        "changed subject or a new Front conversation ID",
        "Never create a duplicate ticket or repeat a first-contact response",
        "do not reason from only the current conversation",
    ]:
        assert phrase in classify
    assert "same normalized sender" in account
    assert "save the new conversation as `manual_review`" in account
    assert "supporting evidence, or existing review in another Front conversation" in education

    orchestrator_source = Path("agent/orchestrator.py").read_text(encoding="utf-8")
    for phrase in [
        "_load_linked_conversation_history",
        "get_contact_conversations",
        "_linked_suspension_cases",
        "linked_account_suspension_followup",
        "The automation suppressed a duplicate standardized suspension draft.",
    ]:
        assert phrase in orchestrator_source

    state_source = Path("tools/state.py").read_text(encoding="utf-8")
    assert "func.lower(func.trim(ConversationState.sender_email))" in state_source
    assert "exclude_conversation_id" in state_source

    front_source = Path("tools/front.py").read_text(encoding="utf-8")
    assert "/contacts/{contact_alias}/conversations" in front_source
    assert 'quote(f"alt:email:{normalized_email}"' in front_source



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
