# Front-Agent

Front-Agent 是一套面向 Dify 支持邮箱的自动化处理服务。它接收 Front webhook，读取完整会话和附件，用 LLM 分类邮件，再按 `skills/` 中的 Markdown 规则调用 Front、Linear、Front 转发通知、GitHub 和文档检索等工具完成处理。

核心设计是把业务策略放在 `skills/*.md`，把外部系统调用放在 `tools/`，把编排逻辑放在 `agent/orchestrator.py`。日常新增分类、调整回复口径或改变升级规则，优先改 skill 文件，而不是改主流程代码。

## 稳定版重构计划

新版本的架构优化计划见 [`docs/stable-agent-v2-plan.md`](docs/stable-agent-v2-plan.md)。该计划合并了分类/skill/工具架构优化，以及最新的 Front 转发人工介入方案。

## 当前状态

- 主分支：`main`
- 远端：`origin` 指向 GitHub 仓库
- 服务入口：`main.py`
- 生产启动：`bash start.sh`
- 健康检查：`GET /health`
- 当前主要服务形态：FastAPI + Front webhook + Front 转发通知 + SQLite 状态库

## 系统职责

Front-Agent 负责五件事：

1. 接收 Front 支持邮箱事件，并做签名校验和事件幂等。
2. 拉取完整 Front conversation、附件和必要的用户历史。
3. 用 `skills/classify.md` 对邮件分类，再加载对应业务 skill。
4. 通过 LLM function calling 调用工具：回信、建 Linear 工单、转发、移动 inbox、Front 转发通知、保存状态等。
5. 在 Front 内部评论里生成反馈入口，让 Bobby 的修正沉淀为 skill 修改建议。

## 主流程

```text
Front 新邮件
  |
  v
POST /webhook/front
  |
  |-- 校验 X-Front-Signature
  |-- 用 event_id 写 webhook_events 做幂等
  |-- 只处理允许的 Front inbox
  v
agent.handle_email()
  |
  |-- 读取 conversation_states，判断是否新会话或可继续处理
  |-- 拉取 Front 完整会话历史
  |-- 下载图片/PDF/Word 附件，供视觉或文本分析
  |-- 必要时读取同一 sender 最近 30 天历史
  v
分类阶段
  |
  |-- 使用 skills/classify.md
  |-- spam/广告可直接关闭；unclear 进入人工判断并保持打开
  |-- unclear 或规则无法安全判断时通过 Front 转发给 Bobby 做人工审查
  v
执行阶段
  |
  |-- 加载 skills/<category>.md
  |-- LLM 最多进行 10 轮 tool calling
  |-- 工具集中由 agent/tool_registry.py 分发
  v
处理完成
  |
  |-- 写入或更新 conversation_states
  |-- 在 Front 添加反馈评分链接
  |-- 等待后续邮件或人工动作
```

## 代码结构

```text
.
├── main.py                    # FastAPI 入口：初始化数据库、启动调度器、挂载路由
├── config.py                  # pydantic-settings 配置入口，读取 .env
├── database.py                # SQLAlchemy async engine/session 和建表
├── models.py                  # SQLite 表模型
├── start.sh                   # Railway/本地启动脚本
├── railway.toml               # Railway 构建和健康检查配置
├── agent/
│   ├── orchestrator.py        # 核心编排：分类、路由决策、加载 skill、运行 agent loop
│   ├── classification.py      # 分类 JSON 解析、字段归一化、spam 识别
│   ├── routing.py             # 确定性路由层：spam/security/unclear/marketing 等安全动作
│   └── tool_registry.py       # LLM 可调用工具 schema 和执行映射
├── webhooks/
│   ├── front_webhook.py       # Front webhook 接入、签名、幂等、inbox 过滤
├── tools/
│   ├── front.py               # Front API：回复、草稿、转发、关闭、移动 inbox、评论
│   ├── linear.py              # Linear 工单创建
│   ├── handoff.py             # 内部同事 handoff：通过 Front 转发原始会话，不给客户发信
│   ├── attachments.py         # 附件下载、图片 base64、文档文本抽取
│   ├── state.py               # conversation_states 读写
│   ├── github.py              # GitHub issue/PR 检索
│   └── docs_search.py         # Dify 文档检索
├── skills/
│   ├── classify.md            # 分类规则和 JSON 输出格式
│   ├── technical.md           # 技术问题处理规则
│   ├── account.md             # 账号问题处理规则
│   ├── billing.md             # 账单/退款处理规则
│   └── ...                    # 其他业务分类 skill
├── routes/
│   ├── feedback.py            # 反馈提交接口，会拉取 Front 会话上下文
│   ├── feedback_api.py        # 反馈后台、skill 建议审批、skill 编辑接口
│   └── static/                # feedback/admin 静态页面
├── services/
│   ├── skill_analyzer.py      # 把 Bobby 反馈转成 skill 修改建议
│   ├── file_git.py            # 本地写入 skill 文件
│   ├── skill_*_store.py       # feedback/example/suggestion/version 存储服务
│   └── ...
└── tasks/
    └── scheduler.py           # APScheduler 定时任务
```

## 模块边界

| 模块 | 责任 | 不应该做的事 |
|---|---|---|
| `main.py` | 应用生命周期、路由注册、健康检查 | 写业务判断 |
| `webhooks/` | 接收外部回调、校验、幂等、转交业务处理 | 直接写复杂处理策略 |
| `agent/orchestrator.py` | 串联分类、确定性路由、skill 执行和反馈评论 | 直接实现外部 API 细节 |
| `agent/classification.py` | 解析和校验 LLM 分类 JSON，做字段兜底 | 调用外部 API 或决定业务副作用 |
| `agent/routing.py` | 把可信分类结果转换为稳定路由动作 | 生成客户回复内容或调用外部 API |
| `agent/tool_registry.py` | 暴露工具 schema，分发工具调用 | 写分类规则 |
| `tools/` | 封装 Front/Linear/内部 Front handoff/GitHub/文档等外部能力 | 决定业务路径 |
| `skills/` | 描述分类、回复模板、升级规则、工具使用策略 | 写 Python 逻辑 |
| `services/` | 反馈学习、skill 建议、文件写入、版本快照 | 处理 webhook |
| `tasks/` | 定时后台任务 | 接收用户请求 |

## 邮件分类

分类由 `skills/classify.md` 控制，当前主要分类如下：

| category | 说明 |
|---|---|
| `technical` | 技术问题、bug、how-to、API、故障、隐私、自托管 |
| `account` | 登录、删号、转移账号、改邮箱、账号异常 |
| `billing` | 退款、重复扣费、降级、发票 |
| `purchase` | 企业版、团队版、优惠码、代理商购买咨询 |
| `education` | 教育版申请和资格问题 |
| `partnership` | 插件、marketplace、合作、下架请求 |
| `marketing` | 市场活动、推广合作、活动邀请 |
| `security` | 安全漏洞、紧急安全事件 |
| `legal` | 律师函、法律威胁、诉讼相关 |
| `spam` | 广告、群发、无关推销；可自动归档 |
| `roadmap` | 产品路线、功能上线咨询 |
| `investment` | 投资、融资、IR |
| `business` | 企业版、商务咨询、演示请求 |
| `data_export` | 数据导出请求 |
| `unclear` | 无法明确分类；转给 Bobby 人工判断并保持打开 |

分类结果包含 `category`、`sub_type`、`confidence`、`urgency`、`flags`、`secondary_intents`、`evidence` 和 `summary`。`confidence` 只用于观察和评估，不使用固定阈值控制路由。`agent/classification.py` 会把模型输出归一化；`agent/routing.py` 会先执行确定性安全路由：spam 自动归档、security 移动到 Security inbox、unclear/规则无法安全判断转 Bobby、Marketplace/社区合作转 `marketing@dify.ai`。其余复杂场景才进入对应 skill 的 agent loop。

## Agent 工具

LLM 不直接访问外部系统，只能通过 `agent/tool_registry.py` 暴露的工具行动。主要工具包括：

| 工具 | 用途 |
|---|---|
| `front_create_draft` | 在 Front 创建草稿，并添加内部说明 |
| 专用 `front_forward_to_*` | 发送内部 Front forward，不是普通直发邮件；正文包含 summary 和原始 Front thread；Marketplace/社区合作统一到 `marketing@dify.ai`，conversation 保持 open |
| `front_forward_to_bobby` | 通过 Front forward 转发原始会话和摘要给 Bobby；不发送给客户，保持 open |
| `front_forward_to_limin` | 账号/黑名单兼容路径，当前通过 Front forward 转发给 Bobby；不发送给客户，保持 open |
| `front_forward_to_sybil` | 教育版审核 handoff，通过 Front forward 转发给 Sybil；不发送给客户，保持 open |
| `front_forward_to_marketing` | 移动到 Marketing inbox |
| `front_forward_to_security` | 移动到 Security inbox |
| `front_assign` | 分配给指定 Front teammate |
| `front_add_comment` | 添加 Front 内部评论 |
| `linear_create_ticket` | 创建 Linear CUS 工单 |
| `state_set` | 保存多轮会话状态 |
| `github_search` | 检索 Dify GitHub issue/PR |
| `docs_search` | 检索 Dify 官方文档 |

`front_close_conversation` 不暴露给模型，只由 Python 确定性 spam/广告路由内部调用。

## 状态和定时任务

SQLite 由 SQLAlchemy async 管理，启动时会自动建表。

| 表 | 用途 |
|---|---|
| `conversation_states` | conversation 当前分类、步骤、等待状态和 payload |
| `webhook_events` | Front event id 幂等 |
| `skill_feedback` | Bobby 原始反馈 |
| `skill_examples` | 从反馈提取出的语义/案例/流程记忆 |
| `skill_suggestions` | 待审批的 skill 修改建议 |
| `skill_versions` | skill 文件版本快照 |

当前启用的定时任务：

- `auto_close_stale_conversations`：每 6 小时检查一次，关闭等待用户回复超过 10 天的会话。

代码里还保留了 `sync_missing_conversations`，用于扫描 Front 最近未处理会话，但当前没有启用。

## Front 转发人工介入

新版本的人工兜底通知全部通过 Front forward 发送给同事，不是普通直发邮件。转发内容包含 AI 摘要、Linear 链接等关键信息，并附带原始 Front conversation 内容；forward 后 conversation 保持 open。

active code 不再暴露 `feishu_notify_*` 工具名，也不再暴露泛用 `front_forward`。内部 handoff 只能走专用 allowlisted 工具：Bobby/Limin 兼容路径、Sybil 教育审核、Marketing 合作承接、Security inbox、Legal/Investment 专用路径。`tools/handoff.py` 对同事邮箱转发做 `@dify.ai` allowlist 校验。

| 通知场景 | Front 转发方式 |
|---|---|
| 分类不确定 | 通过 Front 转发给 Bobby，附候选分类和原始会话，保持打开 |
| 需要人工跟进 | 通过 Front 转发给对应负责人，附摘要和原始会话，保持打开 |
| 安全问题 | 移动到 Security inbox，不再单独转发给杨永乐 |
| 草稿确认 | 通过 Front 转发提醒人工审核 |

Front 转发通知不提供交互按钮能力；需要人工判断或审核时，同事直接在 Front 或后台页面处理。

## 反馈和 Skill 迭代

每次 agent loop 完成后，系统会在 Front conversation 添加内部反馈链接：

```text
/feedback/form?conv=<conversation_id>&category=<category>
```

Bobby 提交评分、正确回复或修改建议后：

1. `routes/feedback.py` 或 `routes/feedback_api.py` 接收反馈。
2. `services/skill_analyzer.py` 用 LLM 提取三层记忆：semantic、episodic、procedural。
3. 系统写入 `skill_feedback`、`skill_examples` 和 `skill_suggestions`。
4. Bobby 在后台审批建议。
5. 审批通过后，`services/file_git.py` 会把新内容写回本地 `skills/<category>.md`。

注意：当前 `file_git.py` 只负责本地写文件，不会自动 `git commit` 或 `git push`。如果线上通过后台改了 skill，需要人工检查、提交并推送。

## 环境变量

配置从 `.env` 读取，`config.py` 里定义了所有字段。不要把真实 token 提交到仓库。

必填或常用变量：

```bash
# Front
FRONT_API_TOKEN=
FRONT_WEBHOOK_SECRET=

# LLM
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o
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
FRONT_APP_BASE_URL=https://app.frontapp.com/open


# Front teammates
FRONT_TEAMMATE_XIAXI=
FRONT_TEAMMATE_ZHAOHQ=
FRONT_TEAMMATE_ZHAOYAWEN=

# Routing emails and inbox names
ZHAOHQ_EMAIL=
ZHAOYAWEN_EMAIL=
MARKETING_INBOX_NAME=
MARKETING_PARTNERSHIP_EMAIL=marketing@dify.ai
SECURITY_INBOX_NAME=Security
YAWEN_EMAIL=
MARUDAN_KJ_EMAIL=
LUSHACHEN_EMAIL=
BYRON_EMAIL=
XINRUILIU_EMAIL=
CLAUDIA_EMAIL=
GEYAN_EMAIL=

# App
DATABASE_URL=sqlite+aiosqlite:///./email_automation.db
STREAMLIT_URL=http://localhost:8000
PORT=8000
```

## 本地启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入真实配置

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

也可以使用启动脚本：

```bash
bash start.sh
```

`start.sh` 会加载 `.env`，停止已有 `uvicorn main:app` 进程，然后用 `${PORT:-8000}` 启动服务。

## Webhook 配置

本地测试可以用 ngrok 暴露服务：

```bash
ngrok http 8000
```

Front Rule webhook 地址：

```text
https://<your-host>/webhook/front
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

部署步骤：

1. Railway 连接 GitHub 仓库。
2. 配置环境变量，不要依赖仓库里的 `.env`。
3. 如需持久化 SQLite，给 `DATABASE_URL` 指向持久化 volume 路径。
4. 部署后把公网域名配置到 Front webhook。
5. 用 `/health` 确认服务正常。

## 修改业务规则

优先改 `skills/`：

1. 分类不准：改 `skills/classify.md`。
2. 某类回复口径不对：改对应 `skills/<category>.md`。
3. 需要新增分类：新增 `skills/<category>.md`，再把分类写进 `skills/classify.md`。
4. 需要新增外部动作：在 `tools/` 封装 API，再在 `agent/tool_registry.py` 增加 schema 和执行映射。
5. 需要新增入口：在 `webhooks/` 或 `routes/` 增加路由，并在 `main.py` 注册。

修改后建议至少做三项检查：

```bash
python -m compileall .
curl http://localhost:8000/health
git diff -- README.md skills/ agent/ tools/ webhooks/ routes/
```

## 维护注意事项

- `.env`、数据库文件、screen 日志和虚拟环境不应该提交。
- `screenlog.*` 是运行日志，不是代码变更。
- `email_automation.db` 是本地 SQLite 数据文件，生产环境应使用持久化路径。
- `skills/` 是业务策略源头，改动前后最好保留清晰 commit message。
- 线上后台审批 skill 建议后只会改本地文件，仍需人工提交和推送。
