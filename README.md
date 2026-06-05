# Dify Email Automation

Front 收件箱的邮件自动化处理系统。新邮件到达时，AI 自动分类、回复、创建 Linear 工单、飞书通知，Bobby 通过飞书卡片按钮完成人工兜底。

**核心思路：规则驱动，代码不动** — 所有邮件处理逻辑写在 `skills/` 目录下的 Markdown 文件里，新增分类或修改回复模板只需改 Markdown，无需改代码或重新部署。

---

## 系统架构

### 技术栈

| 组件 | 技术 |
|---|---|
| Web 框架 | FastAPI |
| AI 模型 | OpenAI GPT-4o / MiniMax（OpenAI 兼容接口） |
| 数据库 | SQLite（通过 aiosqlite 异步操作） |
| 定时任务 | APScheduler |
| 通讯 | 飞书交互卡片 + Front API |

### 处理流程

```
用户发送邮件 → Front 收到
                    │
                    ▼
         /webhook/front  ← Front Rule 触发
                    │
                    ▼
         orchestrator.py
                    │
        ┌─────────┴─────────┐
         ▼                   ▼
  1. 拉取对话历史      2. 下载附件（图片/PDF）
  （Front API）        （转 base64 供 Vision 模型）
         │ │
         ▼                   ▼
  3. 分类（classify.md + GPT-4o）
         │
         ├─ 置信度 ≥ 75%  → 直接加载对应 skill
         └─ 置信度 < 75%  → 飞书卡片 12 按钮让 Bobby 选分类
                                │
                                ▼
                    Bobby 点击卡片 → /webhook/feishu/card
                                │
                                ▼
                        重新走 skill 处理
         │
         ▼
  4. 加载对应 skill（skills/<category>.md）
         │
         ▼
  5. Agent Loop（GPT-4o function calling，最多 10 轮）
         │
         ▼
  6. 调用工具（回复邮件 / 创建工单 / 飞书通知 / 标记已处理）
         │
         ▼
  7. 保存状态（SQLite）
```

### 多轮对话

用户回复邮件时，Front 再次触发 webhook。系统从数据库读取上次的 `category`、`sub_type`、`step`，从断点继续处理，不重新分类。

### 10 天自动关闭

等待用户回复超过 10 天的对话，定时任务（每 6 小时检查一次）自动 resolve 并生成结案草稿。

---

## 目录结构

```
.
├── main.py                  # FastAPI 入口，注册路由，启动定时任务
├── config.py                # 所有环境变量（pydantic-settings BaseSettings）
├── database.py              # SQLite 异步连接（aiosqlite）
├── models.py                # 数据库模型（ConversationState、WebhookEvent 等）
├── agent/
│   ├── orchestrator.py      # 主逻辑：分类 → 加载 skill → agent loop
│   └── tool_registry.py     # GPT-4o function calling 工具定义 + 执行
├── webhooks/
│   ├── front_webhook.py     # 接收 Front 事件，幂等处理，调用 orchestrator
│   └── feishu_card.py       # 接收飞书卡片按钮点击，执行对应动作
├── tools/
│   ├── front.py             # Front API（回复、resolve、assign、forward、tag）
│   ├── linear.py            # Linear API（创建工单）
│   ├── feishu.py            # 飞书 API（发送/更新交互卡片、通知）
│   ├── state.py             # 对话状态读写（SQLite）
│   └── attachments.py       # 下载附件并转 base64（供 GPT-4o Vision）
├── skills/                  # ← 修改处理规则只需改这里
│   ├── classify.md          # 分类规则 + 输出格式（JSON）
│   ├── technical.md         # 技术/Bug 类
│   ├── account.md           # 账户类（登录/删号/转移/异常）
│   ├── billing.md           # 账单/退款
│   ├── education.md         # 教育版申请
│   ├── purchase.md          # 购买/询价
│   ├── partnership.md       # 市场合作/Plugin/代理商
│   ├── marketing.md # 市场活动/合作
│   ├── security.md          # 安全相关
│   ├── legal.md             # 律师函/法律威胁
│   ├── spam.md              # 广告/推销
│   ├── roadmap.md           # Roadmap/功能上线咨询
│   ├── data_export.md       # 数据导出请求
│   ├── investment.md # 投资/融资咨询
│   ├── business.md          # 企业版/销售/演示请求
│   └── unclear.md           # 分类不确定（通用回复 + 通知 Bobby）
├── tasks/
│   └── scheduler.py         # APScheduler：每 6 小时自动关闭 10 天无回复对话
└── routes/
    └── feedback.py          # 用户评分反馈 API
```

---

## 邮件分类体系

| category | sub_type | 说明 |
|---|---|---|
| technical | workflow_issue / bug_report / how_to / feasibility / api_issue / outage / data_privacy / self_hosted | 技术问题 |
| account | cant_login / delete_account / transfer_account / change_email / account_anomaly / account_hacked / merge_accounts | 账户问题 |
| purchase | enterprise / pro_team / promo_code / reseller | 购买询价 |
| education | rejected / no_discount / cancel_subscription | 教育版 |
| billing | refund / duplicate_charge / downgrade / invoice / other | 账单退款 |
| partnership | plugin / marketplace / plugin_takedown | 插件/合作 |
| marketing | campaign / collaboration / event | 市场活动 |
| security | general / urgent | 安全事件 |
| spam | — | 垃圾广告 |
| legal | — | 法律威胁 |
| roadmap | — | Roadmap 咨询 |
| investment | fundraising | 投资咨询 |
| business | enterprise_inquiry | 企业版/商务 |
| data_export | — | 数据导出 |
| unclear | — | 无法分类 |

---

## 飞书交互卡片

Bobby 收到的飞书通知是**可点击的交互卡片**，点击后 POST 到 `/webhook/feishu/card`。

| 卡片类型 | 触发场景 | 按钮 |
|---|---|---|
| `general` | 需人工跟进（账号/账单/教育版等） | 已转告 / 已解决 |
| `security` | 安全紧急事件 | 已转安全团队 / 已解决 |
| `reply_needed` | AI 草稿需 Bobby 确认 | 通过发送 / 我来改 |
| `classify` | 分类置信度 < 75% | 12 个分类选项按钮 |

Bobby 点击后，卡片自动更新为"已处理"状态，防止重复操作。

**卡片更新机制：**
- Feishu 会发送两次回调（旧格式 + Schema 2.0），两次都会处理，但通过 event_id 幂等去重
- 卡片 reload 时，系统根据数据库当前状态返回正确卡片，确保 UI 不回退

---

## 数据库表

| 表名 | 用途 |
|---|---|
| `conversation_states` | 每个对话的分类、处理步骤、等待状态、附加数据 |
| `webhook_events` | 已处理的 Front event ID，防止重复处理 |
| `skill_examples` | Bobby 确认的分类例子，用于向量检索提升分类准确率 |
| `skill_suggestions` | 待审批的 skill 修改建议（diff 格式） |
| `skill_versions` | skill 文件版本快照，每 3 次更新存一个 |
| `skill_feedback` | 原始反馈记录（用户问题、AI回答、Bobby纠正、评分） |

---

## 环境变量

所有配置通过 `.env` 文件注入，常用变量：

```bash
# Front
FRONT_API_TOKEN= # Front API Token
FRONT_WEBHOOK_SECRET=    # Front Webhook 验签密钥

# AI（OpenAI 或 MiniMax）
OPENAI_API_KEY=         # OpenAI API Key
OPENAI_MODEL=gpt-4o # 模型名称
MINIMAX_API_KEY=        # MiniMax API Key（可选）
MINIMAX_BASE_URL=       # MiniMax API 地址

# Linear
LINEAR_API_KEY=         # Linear API Key
LINEAR_TEAM_ID=         # Linear Team ID
LINEAR_CUS_PROJECT_ID=   # 项目 ID

# 飞书 App（Bobby的小猫）
FEISHU_APP_ID=          # 飞书应用 ID
FEISHU_APP_SECRET=      # 飞书应用密钥
FEISHU_BOT_CHAT_ID=     # 你和机器人的单聊 chat_id
FEISHU_WEBHOOK_BOBBY=   # Bobby 通知 Webhook

# 飞书群聊 ID（任务通知群）
FEISHU_GROUP_CHAT_ID=

# 特定人员（用于转发和@通知）
FEISHU_LIMIN_OPEN_ID=           # 李敏 open_id
FEISHU_SYBIL_OPEN_ID=           # Sybil open_id（教育版群）
FEISHU_EDUCATION_GROUP_CHAT_ID= # 教育版群 chat_id

# Linear 成员 ID（用于 assignee）
LINEAR_USER_YUANQING=    # 张苑晴
LINEAR_USER_YONGLE=      # 杨永乐
LINEAR_USER_XIAXI=      # 徐小茜

# Front teammate ID
FRONT_TEAMMATE_XIAXI=
FRONT_TEAMMATE_ZHAOHQ=
FRONT_TEAMMATE_ZHAOYAWEN=

# 特定邮箱（转发用）
ZHAOHQ_EMAIL=
ZHAOYAWEN_EMAIL=

# 市场/合作路由
YAWEN_EMAIL=           # 赵雅雯（亚太区）
MARUDAN_KJ_EMAIL=     # 日本区
LUSHACHEN_EMAIL=       # CN & APAC
BYRON_EMAIL=           # CN & APAC
XINRUILIU_EMAIL=       # EU

# 投资关系
CLAUDIA_EMAIL=        # 刘景媛 claudia@dify.ai

# 法律
GEYAN_EMAIL=          # 葛岩 geyan@dify.ai

# 数据库
DATABASE_URL=sqlite+aiosqlite:////tmp/email_automation.db

# 端口
PORT=8080
```

---

## 快速启动

### 本地开发

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入必填项

# 4. 启动服务
uvicorn main:app --reload --port 8000
```

### 测试 Webhook（本地）

```bash
# 用 ngrok 暴露本地端口
ngrok http 8000
# 把 https://xxxx.ngrok.io/webhook/front 填入 Front Rule
```

### 生产环境（Railway）

1. 新建项目，连接 GitHub 仓库
2. 添加 Volume，挂载到 `/data`（持久化 SQLite 数据）
3. 在 Variables 中填入所有 `.env` 变量
4. 部署完成后，把 Railway 分配的域名 + `/webhook/front` 填入 Front Rule

### 启动脚本

```bash
./start.sh
# 等价于：加载 .env → pkill uvicorn → uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
```

---

## 新增或修改邮件分类

### 新增分类

1. 在 `skills/` 下新建 `<类别名>.md`，参考现有文件格式
2. 在 `skills/classify.md` 的分类表中添加新类别
3. 无需改代码，Railway 会在下次 push 时自动更新

### 修改回复模板

直接编辑对应的 `skills/<类别>.md`，AI 会立即使用新模板。

### Skill 文件格式

每个 skill 文件包含：

- **Instructions**：AI代理的行为指令（用什么工具、如何回复）
- **Reply Templates**：不同场景的标准回复文案
- **Escalation Rules**：何时升级/通知人工

---

## 健康检查

```bash
curl http://<host>:<port>/health
# 返回 {"status": "ok"}
```