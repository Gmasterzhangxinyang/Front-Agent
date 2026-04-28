from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Front
    front_api_token: str
    front_webhook_secret: str = ""

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o"

    # Linear
    linear_api_key: str
    linear_team_id: str
    linear_cus_project_id: str

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

    # Partner emails for forwarding
    # ⚠️ 需填写
    zhaohq_email: str = ""             # 赵晗青邮箱
    zhaoyawen_email: str = ""          # 赵雅雯邮箱

    # Database — on Railway, use /data/email_automation.db (persistent volume)
    database_url: str = "sqlite+aiosqlite:////data/email_automation.db"

    class Config:
        env_file = ".env"


settings = Settings()
