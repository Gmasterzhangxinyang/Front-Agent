## 2026-05-15
- [fix] Sandbox 用户技术支持免责：明确告知 AI 回复仅供参考，付费用户享有优先技术支持（skills/technical.md）
- [fix] 教育版工单标题改为"教育版"：将 Linear 工单 title 从 "Education plan application - [school name]" 改为 "教育版 - [school name]"（skills/education.md）
- [fix] start.sh 重启死循环：加入 PID 文件锁防止多实例并发启动，添加详细日志和最终代理存在检查（start.sh）
- [feat] 分类不确定卡片重新设计：从4个按钮扩展到12个分类全覆盖，移除按钮数量限制，按钮文字改为"中文(category)"格式（agent/orchestrator.py, tools/feishu.py）
- [feat] Skill 自进化系统：Skill Analyzer + 三层架构 + skill_versions/skill_suggestions/skill_feedback/skill_examples 表 + Streamlit UI + git commit+push + 每3次更新存快照（models.py, services/, app_ui.py, routes/feedback.py, agent/orchestrator.py, railway.toml, start.sh）

## 2026-05-19
- [fix] 自进化系统部署问题修复：将 Streamlit 页面迁移到 FastAPI HTML 页面，移除 Streamlit 依赖（routes/static/feedback.html, routes/static/admin.html, routes/feedback_api.py）
- [fix] file_git.py 硬编码路径修复：移除 `/Users/bobby/Desktop/email` 硬编码，改用相对路径（services/file_git.py）
- [fix] skill_analyzer.py 重复变量修复：修复重复定义的 `prompt` 变量，并限制 prompt 大小防止 token 溢出（services/skill_analyzer.py）
- [fix] skill_version_store.py 空初始化修复：首次 increment_change_count 时自动创建版本条目（services/skill_version_store.py）
- [feat] FastAPI 反馈表单：独立的 HTML 评分表单页面（/feedback/form），Bobby 无需 Streamlit 即可评分（routes/static/feedback.html）
- [feat] FastAPI 管理后台：独立 HTML 管理页面（/feedback/api/admin），支持审批/否决建议、查看反馈日志（routes/static/admin.html）
- [refactor] 保持 Railway 部署简洁：start.sh 使用简化版（无 proxy/streamlit），$PORT 直接暴露 uvicorn

## 2026-05-07
- [feat] 教育版自动建工单：用户首封邮件已提供学校名和域名时，AI 直接判断并建工单，跳过"请提供学校信息"步骤（skills/education.md）
- [feat] 促销码处理：新增 purchase/promo_code 分类，回复"无促销码，但有免费 Sandbox 和教育折扣"（skills/classify.md, skills/purchase.md）
- [fix] Partnership 转发改为草稿：`forward_conversation` 创建草稿而非直接发送，需 Bobby 手动审核；转发内容包含摘要、发件人、conversation ID（tools/front.py, agent/tool_registry.py, skills/partnership.md, skills/purchase.md）
- [fix] create_draft 错误处理改进：分离异常处理、加超时、详细日志，修复 channel_id 获取失败导致 400 错误（tools/front.py）

## 2026-05-06 (session 11)
- [feat] 更新产品版本知识：Community/Premium/SaaS/Enterprise 版本区别，多租户、Logo、商用权限说明（purchase.md, technical.md）
- [fix] Partnership 转发修复：新增 `front_forward_to_partnerships` 工具自动从 config 读取邮箱，修复 `forward_conversation` 缺少 channel_id 导致 400 错误（tools/front.py, agent/tool_registry.py, skills/partnership.md）
- [fix] 邮件专业性改进：删除所有 `[AI generated]` 标签，改进模板语气，AI 以客服身份直接回答而非引用文档（所有 skill 文件）

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
