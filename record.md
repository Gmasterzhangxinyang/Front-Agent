## 2026-05-06 (session 10)
- [fix] 点击按钮后卡片跳回原状（PR merge）：重复回调不再返回 `{"code": 0}`，而是始终返回正确的卡片状态（forwarded/resolved card），飞书用响应体更新 UI 而不是用缓存的旧状态覆盖

## 2026-05-06 (session 9)
- [fix] 点击按钮后卡片跳回原状（最终修复）：用数据库 `WebhookEvent` 表的主键唯一约束做 event_id 去重，第一次插入成功则处理，第二次插入冲突则直接返回。跨进程有效，彻底解决飞书双回调问题

## 2026-05-06 (session 8)
- [fix] 点击"已转告"后卡片跳回原状（真正根因）：AI 调用 `feishu_notify_bobby` 时未传 `conversation_id`，导致新卡片按钮没有绑定 conversation，点击时绕过去重检查并覆盖了已更新的卡片。将 `conversation_id` 加入 `feishu_notify_bobby` 的 `required` 字段强制 AI 填写

## 2026-05-06 (session 7)
- [fix] 点击按钮后卡片跳回原状（根本修复）：`feishu_notify_bobby` 的 `conversation_id` 加入 required，AI 必须填写，新卡片按钮能正确绑定 conversation，点击去重逻辑才能生效
- [fix] 只处理 schema 2.0 回调，丢弃旧格式回调，消除飞书双回调

## 2026-05-06 (session 6)
- [fix] 点击"已转告"/"已解决"后卡片跳回原状：在 `webhooks/feishu_card.py` 中加入 per-conversation asyncio.Lock，将 check-and-set 操作串行化，彻底消除飞书双回调的 race condition

## 2026-05-06 (session 5)
- [feat] 所有 Linear 工单自动注入发件人邮箱和邮件原文：在 `agent/orchestrator.py` 的 `_run_agent_loop` 中自动填充 `sender_email` 和 `original_message`，无需 AI 填参数，覆盖所有 skill（education/billing/account/technical）
- [feat] Bobby 手动分类后创建的工单同样注入：`webhooks/feishu_card.py` 的 `_run_agent_with_classification` 从 state 取 sender_email，从消息历史取最新用户消息，传给 `_run_agent_loop`
- [fix] Linear 教育版工单 AI 评估字段写占位符问题：在 `skills/education.md` 中明确要求填入实际值，不得使用占位符文本

## 2026-05-06 (session 4)
- [fix] Linear 教育版工单描述格式：将 `skills/education.md` 中的工单描述从逗号连排改为分行 Markdown 格式（学校全名、邮箱域名、AI 评估各占一行）

## 2026-05-06 (session 3)
- [feat] Linear 工单末尾自动附加发件人邮箱和邮件原文：在 `agent/tool_registry.py` 的 `linear_create_ticket` schema 加入可选参数 `sender_email` 和 `original_message`，执行时拼接到工单 body 末尾（空两行 + 分隔线）

## 2026-05-06 (session 2)
- [fix] 飞书卡片 Linear URL 重复显示：移除 `agent/tool_registry.py` 中对消息文本的 regex 提取，不再将 URL 单独作为 `linear_url` 参数传给 `notify_bobby`，URL 只在消息正文中出现一次
- [fix] 点击"已转告"后按钮不消失：在 `webhooks/feishu_card.py` 中加入 `_check_and_set_forwarded()` 原子性去重，防止飞书双回调导致第二次回调覆盖卡片更新

## 2026-05-06
- [fix] 飞书卡片点击后出现两张卡片问题：在 `agent/orchestrator.py` 的 `_run_agent_loop` 中加入去重逻辑，同一 conversation_id 在同一次 agent 运行中 `feishu_notify_bobby` 只执行一次
- [fix] 点击"已解决"触发两次问题：在 `webhooks/feishu_card.py` 中加入 `_check_and_set_resolved()` 原子性检查，防止 Feishu 双回调导致生成两份结案草稿
- [refactor] 重写 `CLAUDE.md`，加入架构说明、强制 record.md 更新规则、环境变量列表
- [fix] `skills/education.md` 中 feishu_notify_bobby 的消息模板，明确要求使用 linear_create_ticket 返回的真实 URL，不得使用占位符
