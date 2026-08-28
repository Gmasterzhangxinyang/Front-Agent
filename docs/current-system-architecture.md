# Front-Agent 系统架构

> 当前事实来源：`refactor/stable-agent-v2` 的运行代码、Skill、测试与运维配置。交互式图是当前总览；2026-08-05 的 GraphViz 泳道图保留为历史快照。

## 推荐阅读顺序

| 入口 | 内容 | 适合场景 |
|---|---|---|
| [交互式概览](front-support-architecture.html) | 12 个核心组件、主链、安全边界、恢复与 SLA | 5 分钟快速理解 |
| [交互式完整架构](front-support-full-architecture.html) | 可信入口、Memory、16/52 分类、20 个工具、外部集成、Ops | 设计评审与故障定位 |
| [①–⑧ 阶段拆解](current-system-architecture-details.md) | 每个处理阶段的输入、判断、状态和异常路径 | 深入代码流程 |
| `/ops/system-flow` | 一封邮件的 8 步动态故事板与实时遥测 | 线上演示 |
| [运行安全边界](runtime-boundaries.md) | 配置、信任、重试、at-least-once 与部署核对 | 上线与审计 |

## 一眼看懂

```text
Front Rule Webhook
  → 签名与消息身份校验
  → webhook_inbox 持久化与租约
  → 线程 / 附件 / 同发件人历史 / Case Memory
  → 16 类、52 子类型分类
  → Python 确定性路由 或 类别 Skill
  → 20 个白名单工具的 Schema、可信重绑与幂等门
  → Front / Linear / Feishu / 只读 Dify Billing
  → conversation state + action log + retry/dead letter
```

## 五个系统平面

| 平面 | 职责 | 关键模块 |
|---|---|---|
| 可信接入 | 验签、事件身份、外部入站识别、Support inbox 边界 | `webhooks/front_webhook.py`, `agent/message_identity.py` |
| 决策编排 | 构建上下文、分类、确定性路由、Skill 与多轮状态 | `agent/orchestrator.py`, `agent/classification.py`, `agent/routing.py`, `skills/` |
| 安全执行 | 工具 Schema、可信参数重绑、收件人保护、动作去重 | `agent/tool_registry.py`, `tools/` |
| 状态恢复 | Durable inbox、15 分钟租约、有界重试、dead letter、优雅停机 | `services/webhook_inbox.py`, `tasks/scheduler.py`, `tools/state.py` |
| 运营观测 | 优先队列、报告、草稿采纳、数据覆盖、SLA 与个人提醒 | `routes/ops.py`, `services/draft_adoption.py`, `services/unanswered_reminders.py` |

## 主请求生命周期

| 阶段 | 成功路径 | 失败或拒绝路径 |
|---|---|---|
| ① Event ingress | 校验 `X-Front-Signature`，派生稳定 event ID | 401 / 400 / deterministic ignore |
| ② Durable intake | 先提交 `webhook_inbox`，再按会话锁和全局容量 claim | DB 失败返回 503；过期 lease 可回收 |
| ③ Context | 读取完整线程、原始发件人、附件、状态和相关历史 | 附件越界被跳过；正文仍可处理 |
| ④ Classification | 输出 category、sub-type、evidence、flags | 非法输出归一化；confidence 不参与阈值路由 |
| ⑤ Policy | 确定性 Python 规则优先，否则加载单一 Skill | 不足信息创建澄清草稿或进入 waiting state |
| ⑥ Safe execution | Schema 校验、conversation ID 与 sender 重绑、动作去重 | 未知/非法工具被拒绝；失败不伪装成功 |
| ⑦ External effects | 创建草稿、移动/转交、建 Linear、发 Feishu、只读 Billing | 客户邮件不自动发送；不确定副作用保留复核 |
| ⑧ Commit/recovery | 保存 state/action，标记 processed 并清理 payload | 1/5/15/60/180 分钟重试，第 6 次 dead letter |

## 关键横切边界

### 客户与数据安全

- 客户回复默认只创建 Front draft；没有直接客户发送工具。
- `conversation_id`、原始客户邮箱和草稿收件人来自可信运行时，而不是模型参数。
- `dify_lookup_billing` 只能对当前可信 Front 发件人执行固定只读查询，模型不能传 SQL、邮箱或数据库。
- 附件只允许精确配置的 Front HTTPS 主机，并受数量、字节与文本长度限制。

### 幂等与副作用

- `webhook_events` 对成功或确定性忽略的 Front event 去重。
- `conversation_actions` 以工具专用 action key 抑制重复成功写入。
- Linear 先做精确消息去重，再对同发件人 24 小时内最多 5 个候选执行保守语义复核；只有高置信重复才复用。
- 系统保证 at-least-once 处理，不宣称外部 API exactly-once。

### 工作日 12 小时响应提醒

- 范围是所有 open Support 会话与所有 assigned to Bobby 的 open 会话之并集。
- 仅 2026-08-28 00:00（中国时间）及之后收到的客户邮件参与计时；历史积压永久忽略。
- 最新客户邮件超过 12 个自然小时，且之后没有真实外发回复、也没有 Bobby 本人评论时，私聊飞书并附 Front 链接。
- 草稿和 API 机器人评论不算人工响应；每条客户消息最多提醒一次。

## 后台任务

| 任务 | 周期 |
|---|---|
| Durable webhook recovery | 每分钟 |
| Ops metadata refresh | 每 15 分钟，最多 20 条，60 秒上限 |
| Reply SLA scan | 工作日每 15 分钟，单轮最多 10 条 |
| Ops reports | 启动时及每 3 小时 |
| Sybil digest | 每天 10:00 |
| Stale conversation close | 每天，按既有 10 天规则 |

## 保证与限制

| 已保证 | 明确限制 |
|---|---|
| 已认证事件先持久化再处理 | 外部写入成功、本地提交前崩溃仍可能重复 |
| 单进程同会话串行、全局 webhook 并发受限 | 进程内锁与 Ops session 不跨多实例 |
| 非 spam 默认保持 open，客户回复 draft-first | SQLite 是单机状态，不是多节点协调数据库 |
| 错误保持可见并进入 retry/dead letter | 没有 provider idempotency 或 reconciliation 时不保证 exactly-once |

## 图与源文件

| 产物 | 可维护源 | 校验 |
|---|---|---|
| [交互式概览 HTML](front-support-architecture.html) | [overview JSON](front-support.architecture.json) | Archify showcase 9/9，0 error，0 warning |
| [交互式完整 HTML](front-support-full-architecture.html) | [full JSON](front-support-full.architecture.json) | Archify showcase 9/9，0 error，0 warning |
| [历史泳道 SVG](assets/front-agent-current-architecture.svg) / [PNG](assets/front-agent-current-architecture-preview.png) | [GraphViz DOT](current-system-architecture.dot) | 2026-08-05 代码快照，仅作历史细节参考 |

若图、README 与代码不一致，以受测试覆盖的运行代码和 Skill 为准，并在同一次变更中同步更新图规格与文档。
