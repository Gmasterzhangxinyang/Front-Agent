import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Mapping


ALLOWED_CATEGORIES = {
    "technical",
    "account",
    "purchase",
    "education",
    "billing",
    "partnership",
    "marketing",
    "security",
    "spam",
    "legal",
    "roadmap",
    "investment",
    "business",
    "data_export",
    "recruiting",
    "unclear",
}

ALLOWED_URGENCIES = {"normal", "high"}

PARTNERSHIP_SUB_TYPES = {
    "marketplace",
    "plugin",
    "plugin_takedown",
    "technology_integration",
    "strategic_partnership",
}

_TECHNOLOGY_PARTNERSHIP_TARGET_PATTERN = re.compile(
    r"\bdify\b|\byour\s+(?:stack|platform|product|cloud|ecosystem)\b",
    re.IGNORECASE,
)
_TECHNOLOGY_PARTNERSHIP_PRODUCT_PATTERN = re.compile(
    r"\b(?:openai[- ]compatible|api|endpoint|sdk|integration|integrate|"
    r"model\s+inference|inference\s+(?:cloud|platform|infrastructure|service)|"
    r"llm\s+infrastructure|compute|model\s+provider|agent(?:ic)?\s+platform|"
    r"rag\s+pipeline|developer\s+platform|cloud\s+routing|technology\s+stack)\b",
    re.IGNORECASE,
)
_TECHNOLOGY_PARTNERSHIP_COOPERATION_PATTERN = re.compile(
    r"\b(?:partner|partnering|partnership|collaborate|collaboration|ecosystem|"
    r"pilot|proof\s+of\s+concept|poc|free\s+access|technical\s+alliance|"
    r"integrate|integration|quick\s+chat|discuss)\b",
    re.IGNORECASE,
)
_GENERIC_VENDOR_SPAM_PATTERN = re.compile(
    r"\b(?:seo|backlinks?|guest\s+posts?|lead\s+generation|staffing\s+services?|"
    r"recruiting\s+services?|outsourcing\s+services?|web\s+design\s+services?|"
    r"digital\s+marketing\s+services?)\b",
    re.IGNORECASE,
)

_EXPLICIT_EDUCATION_TOPIC_PATTERNS = (
    re.compile(
        r"\b(?:(?:education(?:al)?|academic)\s+"
        r"(?:plan|discount|pricing|coupon|verification|verified|benefits?|account|programme|program)"
        r"|student\s+(?:plan|account|discount|pricing|coupon|programme|program))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:plan|discount|pricing|coupon)\s+"
        r"(?:for\s+)?(?:students?|teachers?|educators?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bedu\s+(?:account|plan|benefits?|verified)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:教育|學生|学生)"
        r"(?:版|方案|計畫|计划|優惠|优惠|折扣|認證|认证|認証)"
    ),
)

_ACCOUNT_SUSPENSION_PATTERNS = (
    re.compile(
        r"\b(?:account|access|workspace)\b.{0,50}"
        r"\b(?:suspend(?:ed|ing)?|suspensions?|banned?|blocked|disabled|deactivated|terminated|locked)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:suspend(?:ed|ing)?|suspensions?|banned?|blocked|deactivated|terminated|locked)\b.{0,50}"
        r"\b(?:account|access|workspace|education plan|education benefits?)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:教育|學生|学生)(?:版|方案|計畫|计划).{0,25}"
        r"(?:封禁|封號|封号|被封|被誤封|被误封|誤封|误封|停權|停权|停用|凍結|冻结)"
    ),
    re.compile(
        r"(?:帳號|账号|帳戶|账户).{0,25}"
        r"(?:封禁|封號|封号|被封|被誤封|被误封|誤封|误封|停權|停权|停用|凍結|冻结)"
    ),
)

_EDUCATION_CANCEL_PATTERNS = (
    re.compile(r"\b(?:cancel|stop|end|terminate|not renew|no longer renew)\b", re.IGNORECASE),
    re.compile(r"(?:取消|停止|終止|终止|不再續訂|不再续订|不要續訂|不要续订)"),
)

_SCHOOL_EMAIL_CONTEXT_PATTERNS = (
    re.compile(
        r"\b(?:school|student|university|college)(?:-issued)?\s+email\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bemail\b.{0,40}\b(?:school|university|college)\b|"
        r"\b(?:school|university|college)\b.{0,40}\bemail\b",
        re.IGNORECASE | re.DOTALL,
    ),
)

_TRIAL_OR_SUBSCRIPTION_PATTERNS = (
    re.compile(r"\b(?:trial|subscription)\b", re.IGNORECASE),
    re.compile(r"(?:試用|试用|訂閱|订阅)"),
)

_AVOID_BILLING_PATTERNS = (
    re.compile(
        r"\b(?:cancel|not\s+be\s+(?:billed|charged)|avoid\s+(?:billing|charges?)|"
        r"not\s+(?:renew|renewed)|stop\s+(?:billing|charges?))\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:取消|避免扣款|不要扣款|不被扣款|停止扣款|不再續訂|不再续订)"),
)

_EDUCATION_EXPIRED_EMAIL_PATTERNS = (
    re.compile(r"\bgraduat(?:e|ed|ing|ion)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:school|student|university|college)\s+email\b.{0,40}"
        r"\b(?:expired|disabled|inaccessible|unavailable|no longer)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"(?:畢業|毕业|學校|学校).{0,20}(?:信箱|邮箱).{0,20}(?:失效|無法使用|无法使用|不能使用|停用)"),
)

_EDUCATION_REJECTED_PATTERNS = (
    re.compile(
        r"\b(?:application|verification|education plan)\b.{0,50}"
        r"\b(?:rejected|denied|declined|failed|not approved|unsuccessful)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"(?:教育|學生|学生).{0,20}(?:申請|申请|認證|认证|驗證|验证).{0,20}(?:拒絕|拒绝|失敗|失败|未通過|未通过)"),
)

_EDUCATION_NO_DISCOUNT_PATTERNS = (
    re.compile(
        r"\b(?:verified|approved|education badge|edu badge)\b.{0,60}"
        r"\b(?:discount|coupon)\b.{0,30}"
        r"\b(?:missing|not showing|not applied|unavailable|cannot see|can't see)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:discount|coupon)\b.{0,30}"
        r"\b(?:missing|not showing|not applied|unavailable|cannot see|can't see)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"(?:已通過|已通过|已認證|已认证|已驗證|已验证).{0,30}(?:優惠|优惠|折扣).{0,20}(?:沒有|没有|未顯示|未显示|看不到)"),
)

_EDUCATION_CREDIT_ALLOWANCE_PATTERNS = (
    re.compile(
        r"\b(?:200|5,?000)\b.{0,60}\b(?:message\s+)?credits?\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:message\s+)?credits?\b.{0,60}\b(?:200|5,?000)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"(?:200|5,?000).{0,30}(?:積分|积分|點數|点数|訊息額度|消息额度)"),
    re.compile(
        r"(?:メッセージ|AI)クレジット.{0,60}"
        r"(?:200|5,?000|毎月|月毎|月ごと|月次|リセット|付与)"
    ),
    re.compile(
        r"(?:毎月|月毎|月ごと|月次).{0,60}(?:メッセージ|AI)クレジット"
    ),
)

CLASSIFICATION_OPTIONS = [
    {"label": "技术问题(technical)", "category": "technical"},
    {"label": "账号问题(account)", "category": "account"},
    {"label": "购买咨询(purchase)", "category": "purchase"},
    {"label": "教育版(education)", "category": "education"},
    {"label": "账单退款(billing)", "category": "billing"},
    {"label": "合作洽谈(partnership)", "category": "partnership"},
    {"label": "营销活动(marketing)", "category": "marketing"},
    {"label": "安全问题(security)", "category": "security"},
    {"label": "垃圾邮件(spam)", "category": "spam"},
    {"label": "法律相关(legal)", "category": "legal"},
    {"label": "产品路线(roadmap)", "category": "roadmap"},
    {"label": "投资融资(investment)", "category": "investment"},
    {"label": "企业销售(business)", "category": "business"},
    {"label": "数据导出(data_export)", "category": "data_export"},
    {"label": "招聘求职(recruiting)", "category": "recruiting"},
    {"label": "无法分类(unclear)", "category": "unclear"},
]


@dataclass
class ClassificationResult:
    category: str = "unclear"
    sub_type: str | None = None
    is_paid_user: bool = False
    is_premium: bool = False
    urgency: str = "normal"
    sender_email: str = ""
    summary: str = ""
    confidence: float = 0.0
    flags: list[str] = field(default_factory=list)
    secondary_intents: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "sub_type": self.sub_type,
            "is_paid_user": self.is_paid_user,
            "is_premium": self.is_premium,
            "urgency": self.urgency,
            "sender_email": self.sender_email,
            "summary": self.summary,
            "confidence": self.confidence,
            "flags": self.flags,
            "secondary_intents": self.secondary_intents,
            "evidence": self.evidence,
        }


def classify_explicit_account_suspension(
    message: str | None,
    sender_email: str = "",
) -> ClassificationResult | None:
    """Recognize an explicit account-level suspension or ban appeal."""
    text = (message or "").strip()
    if not text or not any(
        pattern.search(text) for pattern in _ACCOUNT_SUSPENSION_PATTERNS
    ):
        return None

    is_education = any(
        pattern.search(text) for pattern in _EXPLICIT_EDUCATION_TOPIC_PATTERNS
    )
    return ClassificationResult(
        category="education" if is_education else "account",
        sub_type="account_suspended",
        sender_email=sender_email,
        summary=(
            "User is contacting support about a suspended Education account"
            if is_education
            else "User is contacting support about a suspended account"
        ),
        confidence=1.0,
        evidence=[text[:240]],
        raw={"source": "deterministic_account_suspension"},
    )


def classify_explicit_education_account_suspension(
    message: str | None,
    sender_email: str = "",
) -> ClassificationResult | None:
    """Recognize an explicit Education account suspension or ban appeal."""
    result = classify_explicit_account_suspension(message, sender_email)
    return result if result is not None and result.category == "education" else None


def classify_explicit_education_topic(
    message: str | None,
    sender_email: str = "",
) -> ClassificationResult | None:
    """Recognize an unambiguous education-plan topic in the latest reply.

    This deliberately requires plan/discount/verification wording. A sender
    merely saying that they are a student must not redirect an unrelated
    technical or billing conversation.
    """
    text = (message or "").strip()
    if not text or not any(pattern.search(text) for pattern in _EXPLICIT_EDUCATION_TOPIC_PATTERNS):
        return None

    suspended = classify_explicit_education_account_suspension(text, sender_email)
    if suspended is not None:
        return suspended

    if any(pattern.search(text) for pattern in _EDUCATION_CREDIT_ALLOWANCE_PATTERNS):
        sub_type = "credit_allowance_200"
    elif any(pattern.search(text) for pattern in _EDUCATION_CANCEL_PATTERNS):
        sub_type = "cancel_subscription"
    elif any(pattern.search(text) for pattern in _EDUCATION_EXPIRED_EMAIL_PATTERNS):
        sub_type = "email_expired_graduated"
    elif any(pattern.search(text) for pattern in _EDUCATION_REJECTED_PATTERNS):
        sub_type = "rejected"
    elif any(pattern.search(text) for pattern in _EDUCATION_NO_DISCOUNT_PATTERNS):
        sub_type = "no_discount"
    else:
        sub_type = "how_to_apply"

    return ClassificationResult(
        category="education",
        sub_type=sub_type,
        sender_email=sender_email,
        summary="User has an explicit Education Plan question in the latest reply",
        confidence=1.0,
        evidence=[text[:240]],
        raw={"source": "deterministic_latest_reply_topic_switch"},
    )


def classify_school_email_cancellation_needing_plan_confirmation(
    message: str | None,
    sender_email: str = "",
) -> ClassificationResult | None:
    """Route ambiguous school-email cancellations to a confirmation step.

    A school email or graduation alone does not prove that a trial/subscription
    is an Education Plan. Keep the case in the education flow so the agent asks
    which plan it is before giving either no-auto-renew or paid-plan guidance.
    """
    text = (message or "").strip()
    if not text:
        return None
    if any(pattern.search(text) for pattern in _EXPLICIT_EDUCATION_TOPIC_PATTERNS):
        return None
    if not any(pattern.search(text) for pattern in _SCHOOL_EMAIL_CONTEXT_PATTERNS):
        return None
    if not any(pattern.search(text) for pattern in _TRIAL_OR_SUBSCRIPTION_PATTERNS):
        return None
    if not any(pattern.search(text) for pattern in _AVOID_BILLING_PATTERNS):
        return None

    return ClassificationResult(
        category="education",
        sub_type="cancel_subscription",
        sender_email=sender_email,
        summary=(
            "User wants to avoid billing for a trial or subscription tied to a "
            "school email, but has not confirmed that it is an Education Plan"
        ),
        confidence=1.0,
        flags=["education_plan_unconfirmed"],
        evidence=[text[:240]],
        raw={"source": "deterministic_school_email_cancellation_confirmation"},
    )


def parse_classification_json(raw: str | None) -> dict[str, Any] | None:
    """Parse model output that should contain one JSON object."""
    if not raw:
        return None

    text = raw.strip()
    parsed = _loads_object(text)
    if parsed is not None:
        return parsed

    fenced = _strip_code_fence(text)
    if fenced != text:
        parsed = _loads_object(fenced)
        if parsed is not None:
            return parsed

    for candidate in _balanced_json_candidates(text):
        parsed = _loads_object(candidate)
        if parsed is not None:
            return parsed

    return None


def normalize_classification(
    data: Mapping[str, Any] | None,
    fallback_sender_email: str = "",
) -> ClassificationResult:
    if not data:
        return ClassificationResult(sender_email=fallback_sender_email)

    raw = dict(data)
    category = _clean_string(raw.get("category")).lower() or "unclear"
    confidence = _clamp_float(raw.get("confidence"), default=0.0)

    if category not in ALLOWED_CATEGORIES:
        category = "unclear"
        confidence = min(confidence, 0.2)

    sub_type = _normalize_optional_string(raw.get("sub_type"))
    urgency = _clean_string(raw.get("urgency")).lower()
    if urgency not in ALLOWED_URGENCIES:
        urgency = "normal"

    sender_email = _clean_string(raw.get("sender_email")) or fallback_sender_email

    return ClassificationResult(
        category=category,
        sub_type=sub_type,
        is_paid_user=_to_bool(raw.get("is_paid_user")),
        is_premium=_to_bool(raw.get("is_premium")),
        urgency=urgency,
        sender_email=sender_email,
        summary=_clean_string(raw.get("summary")),
        confidence=confidence,
        flags=_normalize_string_list(raw.get("flags")),
        secondary_intents=_normalize_categories(raw.get("secondary_intents")),
        evidence=_normalize_string_list(raw.get("evidence")),
        raw=raw,
    )


def is_explicit_technology_partnership(text: str | None) -> bool:
    """Recognize a targeted B2B product or infrastructure integration proposal.

    These messages can be commercially motivated, but they are materially
    different from generic vendor advertising because they propose a concrete
    integration with Dify's product, platform, or technology stack.
    """
    searchable = (text or "").strip()
    if not searchable or _GENERIC_VENDOR_SPAM_PATTERN.search(searchable):
        return False
    return all(
        pattern.search(searchable) is not None
        for pattern in (
            _TECHNOLOGY_PARTNERSHIP_TARGET_PATTERN,
            _TECHNOLOGY_PARTNERSHIP_PRODUCT_PATTERN,
            _TECHNOLOGY_PARTNERSHIP_COOPERATION_PATTERN,
        )
    )


def protect_explicit_technology_partnership(
    classification: ClassificationResult,
    latest_message: str | None,
) -> ClassificationResult:
    """Prevent a concrete technology partnership pitch from auto-closing as spam."""
    if classification.category != "spam":
        return classification

    searchable = "\n".join(
        part
        for part in (
            latest_message or "",
            classification.summary,
            " ".join(classification.evidence),
        )
        if part
    )
    if not is_explicit_technology_partnership(searchable):
        return classification

    raw = dict(classification.raw)
    raw.update(
        {
            "original_category": classification.category,
            "source": "deterministic_technology_partnership_guard",
        }
    )
    return replace(
        classification,
        category="partnership",
        sub_type="technology_integration",
        confidence=max(classification.confidence, 0.99),
        raw=raw,
    )


def should_auto_close_spam(classification: ClassificationResult) -> bool:
    """Allow destructive archive only for an unambiguous spam classification.

    Summary keywords such as "promotion" are supporting evidence, not an
    independent reason to close a non-spam conversation. Contradictory route
    signals always keep the conversation open.
    """
    if classification.category != "spam":
        return False
    if "legal_threat" in classification.flags:
        return False
    classification_context = " ".join(
        [classification.summary or "", " ".join(classification.evidence)]
    )
    if is_explicit_technology_partnership(classification_context):
        return False
    return classification.sub_type not in PARTNERSHIP_SUB_TYPES


def _loads_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _strip_code_fence(text: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else text


def _balanced_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start : index + 1])
                start = None

    return candidates


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_optional_string(value: Any) -> str | None:
    cleaned = _clean_string(value)
    if not cleaned or cleaned.lower() in {"none", "null", "n/a", "na"}:
        return None
    return cleaned


def _clamp_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_string(item) for item in value if _clean_string(item)]


def _normalize_categories(value: Any) -> list[str]:
    categories = []
    for item in _normalize_string_list(value):
        category = item.lower()
        if category in ALLOWED_CATEGORIES and category not in categories:
            categories.append(category)
    return categories
