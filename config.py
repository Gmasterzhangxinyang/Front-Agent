from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Front
    front_api_token: str
    front_webhook_secret: str = ""
    # Local-only opt-out. Production should always verify Front signatures.
    allow_unsigned_front_webhooks: bool = False
    # Attachment downloads carry the Front token and must stay bounded.
    front_attachment_allowed_hosts: str = "api2.frontapp.com"
    max_attachment_count: int = 5
    max_attachment_bytes: int = 10 * 1024 * 1024
    max_attachment_text_chars: int = 50_000

    # OpenAI / MiniMax (OpenAI-compatible)
    openai_api_key: str
    openai_model: str = "gpt-5.5"
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.chat/v1"

    # Linear
    linear_api_key: str
    linear_team_id: str
    linear_cus_project_id: str = ""

    # Internal colleague forwards sent through Front.
    internal_forward_bobby_email: str = "bobby@dify.ai"
    internal_forward_limin_email: str = "bobby@dify.ai"
    internal_forward_sybil_email: str = "sybil@dify.ai"
    front_app_base_url: str = "https://app.frontapp.com/open"

    # Feishu messaging. Sybil education handoffs use the existing Bobby custom bot webhook first.
    feishu_webhook_bobby: str = ""
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_sybil_open_id: str = ""
    feishu_education_group_chat_id: str = ""

    # Linear user IDs for assignment
    # ⚠️ 需填写: 在 Linear Settings → Members 查找各人的 User ID
    linear_user_yuanqing: str = ""   # 张苑晴
    linear_user_yongle: str = ""     # 杨永乐
    linear_user_xiaxi: str = ""      # 徐小茜

    # Front teammate IDs
    # ⚠️ 需填写: 在 Front Settings → Teammates 查找各人的 ID
    front_teammate_xiaxi: str = ""      # 徐小茜
    front_teammate_zhaohq: str = ""     # 赵晗青
    front_teammate_zhaoyawen: str = ""  # 赵雅雯 (cc)

    # Partner emails for forwarding
    # ⚠️ 需填写
    zhaohq_email: str = ""             # 赵晗青邮箱
    zhaoyawen_email: str = ""          # 赵雅雯邮箱

    # Marketing inbox (use inbox name from Front, e.g. "Marketing")
    marketing_inbox_name: str = ""    # 市场团队邮箱
    marketing_partnership_email: str = "marketing@dify.ai"  # Marketplace/community external cooperation intake

    # Security inbox (e.g. "Security")
    security_inbox_name: str = "Security"    # 安全团队邮箱

    # Business inbox (e.g. "Business")
    business_inbox_name: str = "Business"

    # Community / Partnership regional routing
    yawen_email: str = ""                # 赵雅雯邮箱（亚太区接口人）yawen@dify.ai
    marudan_kj_email: str = ""          # 日本区 marudan.kj@dify.ai
    lushachen_email: str = ""            # CN & APAC lushachen@dify.ai
    byron_email: str = ""               # CN & APAC byron@dify.ai
    xinruiliu_email: str = ""           # EU xinruiliu@dify.ai

    # Investment / Investor Relations
    claudia_email: str = ""             # 刘景媛 (Claudia) - claudia@dify.ai

    # Legal
    geyan_email: str = "geyan@dify.ai"  # 葛岩 - geyan@dify.ai

    # Database
    database_url: str = "sqlite+aiosqlite:////tmp/email_automation.db"

    # Scheduler runs production background jobs. Disable only for local UI previews.
    enable_scheduler: bool = True

    # Ops dashboard login. Keep the password in environment configuration only.
    ops_admin_username: str = ""
    ops_admin_password: str = ""
    ops_session_hours: int = 12
    ops_cookie_secure: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
