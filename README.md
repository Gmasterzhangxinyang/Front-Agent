# Front-Agent

Front-Agent 是 Dify 支持邮箱的自动化处理服务。它接收 Front webhook，读取完整邮件会话和附件，用 LLM 做分类，再经过 Python 确定性路由和受限工具集完成草稿、内部转发、移动 inbox、建 Linear 工单、状态保存等动作。

当前重构分支是 `refactor/stable-agent-v2`。这个分支不会影响正在 screen 里运行的生产进程，除非明确部署或重启。

## 当前默认状态

- 服务入口：`main.py`
- 技术栈：FastAPI + Front webhook + OpenAI-compatible LLM + SQLite + SQLAlchemy async
- 启动方式：`bash start.sh`
- 健康检查：`GET /health`
- 评分反馈系统：默认关闭，`ENABLE_FEEDBACK_SYSTEM=false`
- 客户回复：默认只创建 Front 草稿，不直接发送给客户
- 内部 handoff：统一使用 Front 普通邮件转发（conversations/{conversation_id}/messages），正文包含 AI summary 和原始 conversation thread，conversation 保持 open
- Feishu：仅 Sybil education/account handoff 使用群通知；其他内部 handoff 不走 Feishu

## 架构分层

系统分成五层，每层职责要保持清楚：

| 层级 | 文件 | 职责 |
|---|---|---|
| 应用生命周期 | `main.py`, `database.py`, `tasks/` | 启动 FastAPI、初始化 DB、启动定时任务、健康检查 |
| Webhook 边界 | `webhooks/front_webhook.py` | 校验 Front webhook、事件幂等、inbox 过滤、转交 agent |
| Agent 核心 | `agent/orchestrator.py`, `agent/classification.py`, `agent/routing.py` | 组装上下文、分类、确定性路由、运行 skill loop |
| 工具边界 | `agent/tool_registry.py`, `tools/` | 暴露允许的工具给 LLM，封装外部 API |
| 业务策略 | `skills/*.md`, `docs/stable-agent-v2-plan.md` | 分类规则、回复草稿、handoff 规则、升级策略 |

边界原则：

- `skills/` 写业务规则和话术，不写 Python 逻辑。
- `agent/routing.py` 写确定性高风险动作，不生成客户回复。
- `agent/tool_registry.py` 决定 LLM 能用哪些工具。
- `tools/` 只封装外部 API，不决定业务路径。
- `webhooks/` 只处理 webhook 接入、校验、幂等和过滤。

## 主流程

```text
Front 邮件事件
  -> POST /webhook/front
  -> 校验签名 / event_id 幂等 / inbox 过滤
  -> agent.handle_email()
  -> 拉取完整 Front conversation 和附件
  -> 必要时读取同一 sender 最近 30 天历史
  -> 使用 skills/classify.md 分类
  -> agent/routing.py 执行确定性路由
  -> 未被确定性路由完全处理时，进入对应 category skill loop
  -> 通过 agent/tool_registry.py 调用受限工具
  -> 写入 conversation state
  -> 除 spam 自动归档外，conversation 默认保持 open
```

Agent 会读取完整 Front conversation，不只看最新一封邮件。多轮对话依赖 `conversation_states`，`awaiting_*` 和 `waiting_user` 这类状态会继续原流程。

## 确定性路由

`agent/routing.py` 在 skill loop 之前执行，用 Python 固定关键路径，避免高风险动作完全依赖模型自由判断。

| 输入 | 路由 | 动作 | 最终状态 |
|---|---|---|---|
| `spam` / 明确广告 | `spam_auto_close` | Front 自动归档 | `closed_spam` |
| `unclear` | `manual_review_bobby` | Front forward 给 `bobby@dify.ai`，包含 summary 和原始 thread | `manual_review` |
| `security` | `security_move_inbox` | 移动到 Front inbox `Security` | `moved_inbox` |
| `partnership` / Marketplace / community | `marketing_forwarded_keep_open` | Front forward 给 `marketing@dify.ai` | `forwarded_keep_open` |
| `legal` 或 `legal_threat` flag | `legal_forwarded_keep_open` | Front forward 给 `geyan@dify.ai` | `forwarded_keep_open` |
| 其他支持分类 | `*_skill_flow` | 加载 `skills/<category>.md` | skill 规则决定 open state |

`confidence` 只做观察和评估，不使用固定阈值控制路由。代码里不应该再出现用 `0.3` 之类阈值决定业务动作的逻辑。

## 内部 Forward 规则

内部 handoff 必须是 Front forward 语义，不是客户回复，也不是普通新邮件。

每个内部 forward 优先包含：

- allowlisted 目标收件人，例如 Bobby、Sybil、Marketing、Geyan、Claudia
- AI summary
- 原始 Front conversation thread
- conversation id
- 必要时包含 Linear 链接等上下文

当前实现策略：统一走普通邮件转发（非 spam handoff），正文包含 AI summary + 原始 conversation thread；如转发失败会返回失败，由上游重试或告警处理。

Forward 后 conversation 保持 open。非 spam 的 handoff 状态应该使用 `forwarded_keep_open`、`manual_review`、`moved_inbox` 或 `draft_created`，不要用 `done`。

当前责任人：

| 场景 | 目标 |
|---|---|
| 分类不确定 / manual review | `bobby@dify.ai` |
| Account 登录/删除/转移/被盗类建 Linear 后 handoff（非额度异常） | `bobby@dify.ai`；额度/计划异常另外走 `sybil@dify.ai` 并 CC `bobby@dify.ai` |
| Education 审核 | `sybil@dify.ai` |
| Marketplace / community / external cooperation | `marketing@dify.ai` |
| Security report | Front inbox `Security` |
| Legal threat / lawyer letter / lawsuit | `geyan@dify.ai` |
| Investment / VC / IR | Claudia，依赖 `CLAUDIA_EMAIL` 配置 |

## 工具安全边界

LLM 不能直接访问外部系统，只能调用 `agent/tool_registry.py` 暴露的工具。

关键约束：

- 不暴露泛用 `front_forward`。
- 不向模型暴露 `front_close_conversation`，只有确定性 spam 路由能关闭。
- 旧的直接客户回复工具会被阻断。
- `front_create_draft` 只创建 Front 草稿，留给人工 review。
- 内部 handoff 只能走专用 `front_forward_to_*` 工具。
- `tools/handoff.py` 对同事 handoff 做 `@dify.ai` allowlist 校验。

## Skills

业务规则放在 `skills/` 目录下。

| Skill | 用途 |
|---|---|
| `classify.md` | 分类 JSON schema 和分类规则 |
| `technical.md` | 技术问题草稿、文档/GitHub 检索指导 |
| `account.md` | 登录、删号、账号转移、邮箱变更、账号异常 |
| `billing.md` | 退款、重复扣费、发票、降级草稿 |
| `education.md` | 教育版资格、Sybil handoff、身份校验 |
| `partnership.md` | Marketplace/community/external cooperation 转 Marketing |
| `legal.md` | 法律问题转 Geyan，不回复客户 |
| `security.md` | 安全问题移动到 Security inbox |

调整业务规则时，优先改对应 skill。只有当需要新的确定性路由、新工具或安全边界时，才改 Python。

## 状态模型

SQLite 表定义在 `models.py`，由 `database.py` 初始化。

| 表 | 用途 |
|---|---|
| `conversation_states` | 当前 category、sub_type、step、waiting、payload、sender |
| `webhook_events` | Front event 幂等 |
| `skill_feedback` | 反馈记录，当前 runtime 默认关闭 |
| `skill_examples` | 从反馈提取的案例 |
| `skill_suggestions` | 待审批 skill 修改建议 |
| `skill_versions` | skill 文件版本快照 |

重要状态：

| Step | 含义 |
|---|---|
| `awaiting_*` | 等用户补充信息，后续回复可以继续原流程 |
| `draft_created` | 已创建 Front 草稿，等待人工 review |
| `forwarded_keep_open` | 已发送内部 Front forward，conversation 保持 open |
| `manual_review` | Bobby 人工判断 |
| `moved_inbox` | 已移动到其他 Front inbox |
| `failed_needs_review` | 工具或 skill flow 未安全完成，需要人工看 |
| `closed_spam` | 确定性 spam 路由已归档 |

## 评分反馈系统

评分反馈系统当前默认关闭。

```bash
ENABLE_FEEDBACK_SYSTEM=false
```

关闭时：

- 不挂载 `/feedback/*` 路由。
- 不在 Front conversation 自动添加评分链接。
- 反馈分析相关代码保留，但 runtime 不启用。

以后要恢复时设置：

```bash
ENABLE_FEEDBACK_SYSTEM=true
```

启用后，`/feedback/form`、`/feedback/api/*` 和 Front 评分评论链路会重新生效。

## 代码结构

```text
.
├── main.py                    # FastAPI app，DB 初始化，scheduler，路由注册
├── config.py                  # pydantic-settings，从 .env 读取配置
├── database.py                # SQLAlchemy async engine/session 和 init
├── models.py                  # SQLite ORM models
├── start.sh                   # 启动脚本
├── railway.toml               # Railway 部署配置
├── agent/
│   ├── orchestrator.py        # 主邮件处理流程和 agent loop
│   ├── classification.py      # 分类解析和归一化
│   ├── routing.py             # 确定性路由和安全动作
│   └── tool_registry.py       # LLM 工具 schema 和执行分发
├── webhooks/
│   └── front_webhook.py       # Front webhook 边界
├── tools/
│   ├── front.py               # Front API wrapper
│   ├── handoff.py             # 内部 Front forward helper
│   ├── linear.py              # Linear 工单创建
│   ├── attachments.py         # 附件下载和提取
│   ├── state.py               # conversation state CRUD
│   ├── github.py              # GitHub issue/PR search
│   └── docs_search.py         # Dify docs search
├── skills/                    # Markdown 业务策略
├── routes/                    # feedback/admin routes，受 ENABLE_FEEDBACK_SYSTEM 控制
├── services/                  # feedback learning 和 skill 文件服务
├── tasks/                     # APScheduler jobs
└── tests/
    └── test_routing.py        # 路由和安全边界回归测试
```

## 环境变量

不要提交真实 secret。以 `.env.example` 为模板。

```bash
# Front
FRONT_API_TOKEN=
FRONT_WEBHOOK_SECRET=
FRONT_APP_BASE_URL=https://app.frontapp.com/open

# LLM
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.5
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.chat/v1

# Linear
LINEAR_API_KEY=
LINEAR_TEAM_ID=
LINEAR_CUS_PROJECT_ID=

# Internal Front forwards
INTERNAL_FORWARD_BOBBY_EMAIL=bobby@dify.ai
INTERNAL_FORWARD_LIMIN_EMAIL=bobby@dify.ai
INTERNAL_FORWARD_SYBIL_EMAIL=sybil@dify.ai
MARKETING_PARTNERSHIP_EMAIL=marketing@dify.ai
SECURITY_INBOX_NAME=Security
GEYAN_EMAIL=geyan@dify.ai
CLAUDIA_EMAIL=

# Optional Front inbox / teammate config
MARKETING_INBOX_NAME=
FRONT_TEAMMATE_XIAXI=
FRONT_TEAMMATE_ZHAOHQ=
FRONT_TEAMMATE_ZHAOYAWEN=

# App
DATABASE_URL=sqlite+aiosqlite:///./email_automation.db
STREAMLIT_URL=http://localhost:8000
ENABLE_FEEDBACK_SYSTEM=false
PORT=8000
```

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

也可以使用项目脚本：

```bash
bash start.sh
```

`start.sh` 会加载 `.env`，停止已有 `uvicorn main:app` 进程，并用 `${PORT:-8000}` 启动服务。

## Front Webhook

Front webhook endpoint：

```text
https://<host>/webhook/front
```

本地 tunnel 示例：

```bash
ngrok http 8000
```

健康检查：

```bash
curl http://localhost:8000/health
```

## Railway 部署

`railway.toml` 当前配置：

```toml
[build]
builder = "RAILPACK"

[deploy]
startCommand = "bash start.sh"
healthcheckPath = "/health"
healthcheckTimeout = 120
restartPolicyType = "on_failure"
```

部署 checklist：

1. Railway 连接 GitHub repo。
2. 在 Railway 配环境变量，不依赖仓库里的 `.env`。
3. 如果生产 SQLite 状态要持久化，把 `DATABASE_URL` 指到 volume 路径。
4. 把 Railway public URL 配到 Front webhook rule。
5. 部署后检查 `/health`。

## 修改流程

尽量在最小层级表达改动：

| 改动 | 优先位置 |
|---|---|
| 分类规则、分类例子 | `skills/classify.md` |
| 回复草稿、handoff 文案 | `skills/<category>.md` |
| 新确定性路由或安全规则 | `agent/routing.py` |
| 新外部动作 | `tools/` + `agent/tool_registry.py` |
| 新 webhook 或后台 endpoint | `webhooks/` 或 `routes/`，再到 `main.py` 注册 |
| runtime 配置 | `config.py` 和 `.env.example` |

提交前建议跑：

```bash
python3 tests/test_routing.py
python3 tests/test_skills.py
python3 -m compileall main.py tools config.py agent webhooks routes tests
git diff --check
```

## 维护注意事项

- 不提交 `.env`、本地 SQLite DB、screen logs、virtualenv、生成缓存。
- `screenlog.*` 是运行日志，不是代码。
- `email_automation.db` 是本地状态；生产要使用持久化路径。
- 当前运行中的 production screen 和这个分支是分离的，除非明确重启或部署。
- Feedback routes 代码保留，但默认关闭，除非 `ENABLE_FEEDBACK_SYSTEM=true`。
- 如果以后启用 feedback/admin UI，后台修改 skill 后仍需要人工 review、commit、push。
