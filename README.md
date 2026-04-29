# Dify Email Automation

Front 收件箱的邮件自动化处理系统。新邮件到达时，AI 自动分类、回复、创建 Linear 工单、飞书通知，Bobby 通过飞书卡片按钮完成人工兜底。

---

## 设计思路

### 核心理念：规则驱动，代码不动

所有邮件处理逻辑写在 `skills/` 目录下的 Markdown 文件里，而不是硬编码在 Python 中。新增分类、修改回复模板、调整处理流程，只需改 Markdown，不需要改代码或重新部署。

### 处理流程

```
Front 收到邮件
    │
    ▼
/webhook/front  ← Front Rule 触发
    │
    ▼
orchestrator.py
    │
    ├─ 1. 拉取完整对话历史（Front API）
    ├─ 2. 下载附件（支持图片/PDF，传给 GPT-4o Vision）
    ├─ 3. 分类（classify.md + GPT-4o）
    │       ├─ 置信度 ≥ 75%  → 直接进入对应 skill 处理
    │       └─ 置信度 < 75%  → 飞书通知 Bobby 手动选分类
    │                              └─ Bobby 点击卡片按钮
    │                                     └─ /webhook/feishu/card
    │                                            └─ 重新走 skill 处理
    │
    ├─ 4. 加载对应 skill（skills/<category>.md）
    ├─ 5. Agent loop（GPT-4o function calling，最多 10 轮）
    │       └─ 调用工具：回复邮件 / 创建工单 / 飞书通知 / 转发 / resolve 等
    └─ 6. 保存对话状态（SQLite）
```

### 多轮对话

用户回复邮件时，Front 再次触发 webhook。系统从数据库读取上次的 `category`、`sub_type`、`step`，从断点继续处理，不重新分类。

### 10 天自动关闭

等待用户回复超过 10 天的对话，定时任务（每 6 小时检查一次）自动 resolve。

---

## 仓库结构

```
.
├── main.py                  # FastAPI 入口，注册路由，启动定时任务
├── config.py                # 所有环境变量（pydantic-settings）
├── database.py              # SQLite 异步连接（aiosqlite）
├── models.py                # 数据库模型
│
├── webhooks/
│   ├── front_webhook.py     # 接收 Front 事件，幂等处理，调用 orchestrator
│   └── feishu_card.py       # 接收飞书卡片按钮点击，执行对应动作
│
├── agent/
│   ├── orchestrator.py      # 主逻辑：分类 → 加载 skill → agent loop
│   └── tool_registry.py     # GPT-4o function calling 工具定义 + 执行
│
├── tools/
│   ├── front.py             # Front API（回复、resolve、assign、forward、tag）
│   ├── linear.py            # Linear API（创建工单）
│   ├── feishu.py            # 飞书 API（发送/更新交互卡片、webhook fallback）
│   ├── state.py             # 对话状态读写（SQLite）
│   ├── attachments.py       # 下载附件并转 base64（供 GPT-4o Vision）
│   ├── docs_search.py       # 搜索 docs.dify.ai
│   └── github.py            # 搜索 langgenius/dify GitHub issues
│
├── skills/                  # ← 修改处理规则只需改这里
│   ├── classify.md          # 分类规则 + 输出格式（JSON）
│   ├── technical.md         # 技术/Bug 类
│   ├── account.md           # 账户类（登录/删号/转移/异常）
│   ├── billing.md           # 账单/退款
│   ├── education.md         # 教育版申请
│   ├── purchase.md          # 购买/询价
│   ├── partnership.md       # 市场合作/Plugin/代理商
│   ├── security.md          # 安全相关
│   ├── legal.md             # 律师函/法律威胁
│   ├── spam.md              # 广告/推销
│   ├── roadmap.md           # Roadmap/功能上线咨询
│   ├── data_export.md       # 数据导出请求
│   └── unclear.md           # 分类不确定（通用回复 + 通知 Bobby）
│
└── tasks/
    └── scheduler.py         # APScheduler：每 6 小时自动关闭 10 天无回复对话
```

---

## 数据库

SQLite（Railway 上挂载持久化 Volume 到 `/data/`）。

| 表 | 用途 |
|---|---|
| `conversation_states` | 每个对话的分类、处理步骤、等待状态、附加数据 |
| `webhook_events` | 已处理的 Front event ID，防止重复处理 |

---

## 飞书交互卡片

Bobby 收到的飞书通知是可点击的交互卡片，点击后 POST 到 `/webhook/feishu/card`。

| 卡片类型 | 触发场景 | 按钮 |
|---|---|---|
| `general` | 需人工跟进（账号/账单/教育版等） | 已转告 / 已解决 |
| `security` | 安全紧急事件 | 已转安全团队 / 已解决 |
| `reply_needed` | AI 草稿需 Bobby 确认 | 通过发送 / 我来改 |
| `classify` | 分类置信度 < 75% | 4 个分类选项按钮 |

Bobby 点击后，卡片自动更新为"已处理"状态，防止重复操作。

---

## 本地启动

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入必填项
uvicorn main:app --reload --port 8000
```

本地测试 webhook 用 ngrok：

```bash
ngrok http 8000
# 把 https://xxxx.ngrok.io/webhook/front 填入 Front Rule
```

---

## Railway 部署

1. 新建项目，连接 GitHub 仓库
2. 添加 Volume，挂载到 `/data`
3. 在 Variables 中填入所有 `.env` 变量
4. 部署完成后，把 Railway 域名 + `/webhook/front` 填入 Front Rule

---

## 新增邮件分类

1. 在 `skills/` 下新建 `<类别名>.md`，参考现有文件格式
2. 在 `skills/classify.md` 的分类表中添加新类别
3. 无需改代码，无需重新部署（Railway 会在下次 push 时自动更新）

## 修改回复模板

直接编辑对应的 `skills/<类别>.md`，搜索 `⚠️ 需确认` 找到需要确认的地方。
