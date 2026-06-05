from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Front
    front_api_token: str
    front_webhook_secret: str = ""

    # OpenAI / MiniMax (OpenAI-compatible)
    openai_api_key: str
    openai_model: str = "gpt-4o"
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.chat/v1"

    # Linear
    linear_api_key: str
    linear_team_id: str
    linear_cus_project_id: str = ""

    # Feishu webhooks
    feishu_webhook_bobby: str
    feishu_webhook_yuanqing: str = ""
    feishu_webhook_yongle: str = ""

    # Feishu App (Bobby的小猫 - 交互卡片)
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_bot_chat_id: str = ""  # 你和机器人的单聊 chat_id

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

    # 李敏 (账号验证、黑名单查询)
    feishu_limin_open_id: str = ""

    # Sybil (教育版群)
    feishu_sybil_open_id: str = ""
    feishu_education_group_chat_id: str = ""

    # 飞书群聊 ID (任务通知群)
    feishu_group_chat_id: str = ""

    # Partner emails for forwarding
    # ⚠️ 需填写
    zhaohq_email: str = ""             # 赵晗青邮箱
    zhaoyawen_email: str = ""          # 赵雅雯邮箱

    # Marketing inbox (use inbox name from Front, e.g. "Marketing")
    marketing_inbox_name: str = ""    # 市场团队邮箱

    # Security inbox (e.g. "Security")
    security_inbox_name: str = ""    # 安全团队邮箱

    # Community / Partnership regional routing
    yawen_email: str = ""                # 赵雅雯邮箱（亚太区接口人）yawen@dify.ai
    marudan_kj_email: str = ""          # 日本区 marudan.kj@dify.ai
    lushachen_email: str = ""            # CN & APAC lushachen@dify.ai
    byron_email: str = ""               # CN & APAC byron@dify.ai
    xinruiliu_email: str = ""           # EU xinruiliu@dify.ai

    # Investment / Investor Relations
    claudia_email: str = ""             # 刘景媛 (Claudia) - claudia@dify.ai

    # Legal
    geyan_email: str = ""               # 葛岩 - geyan@dify.ai

    # Database
    database_url: str = "sqlite+aiosqlite:////tmp/email_automation.db"

    # Base URL for feedback form (set in Railway env vars)
    streamlit_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
