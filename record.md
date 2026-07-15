## 2026-06-02
- [fix] 批量处理过去三天未处理邮件: SEO spam归档(1封)，YouTube合作通知Bobby+回复用户(1封)，教育版取消申请通知Bobby(3封)，跳过已分配给Bobby的技术问题(1封)，忽略Flippa销售类邮件(1封)
- [fix] business category 邮件被多次处理: "done" 不应视为 reworkable，移除出 _REWORKABLE_STEPS (agent/orchestrator.py)

## 2026-06-01

## 2026-05-29
- [fix] 修复 front_webhook.py 重复路由定义导致新邮件未处理 (webhooks/front_webhook.py)
- [fix] reply_to_conversation/create_draft/forward_conversation_direct 优先使用 support/hello 邮箱，避免多 inbox 时用错 Business 地址 (tools/front.py)
- [feat] investment/partnership/community 转发改用 forward_conversation_direct 直接发送，不再建草稿 (agent/tool_registry.py, skills/partnership.md, skills/investment.md)
- [fix] handle_email 增加 reworkable 状态检查，防止同一对话被多次分类 (agent/orchestrator.py)
- [feat] 新增 business category，对企业版/销售相关邮件直接移到 Business inbox，不做 AI 处理 (skills/business.md, skills/classify.md)
- [feat] investment 转发后增加 feishu_notify_bobby 通知 Bobby (skills/investment.md)
- [fix] 添加 CLAUDIA_EMAIL 到 .env，解决投资邮件转发失败问题
- [feat] 自动回复模板增加"我们不会用用户数据训练，security 问题请联系 security@dify.ai" (agent/tool_registry.py)

## 2026-05-27
- [fix] 只处理发送到 hello@dify.ai 和 support@dify.ai 的邮件，其他收件箱忽略（webhooks/front_webhook.py, tasks/scheduler.py）

- [fix] 将教育版通知人名从"张婉清"改为"张苑晴"（skills/education.md）

## 2026-05-26
- [fix] 禁用飞书群聊中李敏 @bob小的小猫处理功能（webhooks/feishu_card.py）
- [fix] 修复飞书群消息处理：chat_type 在 message 对象里而非 event 对象（webhooks/feishu_card.py）
- [feat] 新增教育版取消订阅处理：cancel_subscription 分类 + 不自动续费说明模板（skills/education.md, skills/classify.md）
- [feat] 教育版通知改到教育版群 @sybil：新增 feishu_notify_sybil 工具，config.py/.env 配置群ID和sybil open_id（tools/feishu.py, agent/tool_registry.py, skills/education.md）

## 2026-05-20
- [feat] 社区/合作区域路由：新增 `front_forward_to_community` 工具，支持 plugins_templates/japan/cn_apac/eu 四种区域路由（agent/tool_registry.py）
- [feat] 区域路由 Skill 更新：重写 `skills/partnership.md`，支持插件模板/日本/CN&APAC/EU 四种分类和对应转发（skills/partnership.md）
- [fix] Partnership/Community 都不自动回复用户：只创建转发草稿供 Bobby 审核后手动发送（skills/partnership.md）
- [feat] 新增 Marketing 分类：新增 `front_forward_to_marketing` 工具，marketing 类邮件移动到 marketing inbox（agent/tool_registry.py, skills/classify.md, skills/marketing.md）
- [feat] Front inbox 移动功能：新增 `move_conversation_to_inbox` 函数，通过 inbox name 移动对话到指定 inbox（tools/front.py）
- [fix] 分类确认后追加 example 到 git：`_append_classify_example` 改为调用 `update_skill_file` 推送到 GitHub，持久化 Bobby 纠正的分类样本（webhooks/feishu_card.py）

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

## 2026-05-24
- [feat] 新增 investment 类别用于投资融资相关邮件，转发给 claudia@dify.ai (刘景媛)
  - 创建 skills/investment.md - 投资融资处理流程
  - 更新 skills/classify.md - 添加 investment 分类选项
  - 更新 agent/tool_registry.py - 添加 front_forward_to_investment 工具
  - 更新 agent/orchestrator.py - 低置信度时添加 investment 选项
  - 更新 config.py - 添加 claudia_email 配置项

## 2026-05-25
- [fix] CLAUDE.md 更新：Railway部署改为自托管VM (124.220.5.97:8080)，运行命令改为 `./start.sh`，PORT 默认 8080
- [fix] start.sh now loads .env with `set -a/source` before starting uvicorn, supports local (PORT defaults to 8000) and Railway (PORT from env)
- [fix] 切换 OpenAI → MiniMax：服务器在上海无法访问 OpenAI，改为使用 MiniMax OpenAI兼容API (agent/orchestrator.py, services/skill_analyzer.py, webhooks/feishu_card.py, config.py, .env)
  - MiniMax API: https://api.minimax.chat/v1, 模型: MiniMax-M2.7
  - 当 MINIMAX_API_KEY 配置时优先使用 MiniMax，否则回退 OpenAI
- [fix] category 未定义报错：`_send_feedback_comment` 调用移到分类分支内，非初始状态的对话从 existing_state 读取 category（agent/orchestrator.py）
- [fix] 附件 MIME 类型错误：非图片附件（PDF/Word等）不再传给 LLM，只处理图片类型（tools/attachments.py）
- [fix] MiniMax JSON 解析：去掉 `response_format=json_object`，添加 markdown JSON 提取兼容（agent/orchestrator.py, services/skill_analyzer.py）
- [feat] 配置公网 URL STREAMLIT_URL=http://124.220.5.97:8080，feedback 链接不再跳 localhost
- [fix] 低置信 spam/unclear 邮件直接 archive，不跑 agent loop 也不打扰 Bobby（agent/orchestrator.py）
- [fix] purchase.md 截断修复：补全 pro_team/no_promo_code/reseller 模板（skills/purchase.md）
- [fix] education.md 逻辑修复：K-12 分支补 state_set done，no_discount 补 awaiting_school_info 后续步骤（skills/education.md）
- [refactor] 自进化系统去掉 git push：update_skill_file/rollback_skill_file 只写本地文件（services/file_git.py）
- [fix] 置信度 < 0.3 才通知 Bobby（极低才打扰），其余全自动处理（agent/orchestrator.py）
- [fix] unclear 分类也直接 archive（agent/orchestrator.py）

## 2026-07-06
- [fix] 不确定分类转发 Bobby 后保持 Front 会话 open；Linear 创建成功后主动 reopen，并拦截后续 done/closed_spam 状态写入（agent/orchestrator.py, agent/tool_registry.py, tests/test_routing.py）
- [feat] 新增 recruiting 求职/招聘分类和 skill：候选人求职、实习、简历邮件创建 careers 草稿，不再走 unclear 转 Bobby（agent/classification.py, agent/routing.py, skills/classify.md, skills/recruiting.md, tests/test_routing.py, tests/test_skills.py）

## 2026-07-13
- [docs] document the approved runtime boundary hardening design (docs/superpowers/specs/2026-07-13-runtime-boundary-hardening-design.md)
- [docs] add the test-driven runtime boundary hardening implementation plan (docs/superpowers/plans/2026-07-13-runtime-boundary-hardening.md)
- [chore] ignore project-local Git worktrees used for isolated feature implementation (.gitignore)
- [fix] bind LLM tools to trusted conversation context, require explicit webhook trust, bound authenticated attachments, and return truthful handler failures without recording them as processed (agent/orchestrator.py, agent/tool_registry.py, config.py, main.py, tools/attachments.py, tools/front.py, webhooks/front_webhook.py, tests/test_runtime_boundaries.py)
- [docs] add the runtime boundary operations guide and synchronize README, repository guidance, verification, and deployment requirements (docs/runtime-boundaries.md, README.md, CLAUDE.md)
- [docs] document the Front Rule Webhook API secret source and correct automatic-retry claims to match Front's delivery behavior (.env.example, README.md, docs/runtime-boundaries.md, runtime hardening design and plan)
- [fix] handle verified Education Plan users blocked by unsupported credit cards with a final no-bypass draft and no Linear or Sybil escalation (skills/education.md, tests/test_skills.py)

## 2026-07-14
- [feat] add the approved existing-invoice Credit Note flow: first create a policy/confirmation draft, then on explicit second customer confirmation add a deduplicated Front internal comment saying the case should go to Elsie, without assignment, Ops queue, Linear ticket, or billing-provider action (skills/billing.md, skills/classify.md, agent/orchestrator.py, agent/tool_registry.py, tests/test_skills.py, tests/test_runtime_boundaries.py, README.md, CLAUDE.md)
- [docs] document the approved durable Front webhook recovery design (docs/superpowers/specs/2026-07-14-durable-webhook-recovery-design.md)
- [docs] add the test-driven durable Front webhook recovery implementation plan (docs/superpowers/plans/2026-07-14-durable-webhook-recovery.md)
- [docs] document authenticated soft dismissal for individual pending Sybil queue items (docs/superpowers/specs/2026-07-14-sybil-queue-dismissal-design.md)
- [docs] add the test-driven Sybil queue soft-dismissal implementation plan (docs/superpowers/plans/2026-07-14-sybil-queue-dismissal.md)
- [feat] add authenticated soft dismissal for individual pending Sybil queue records while retaining dismissed history and audit actions (config.py, routes/ops.py, routes/static/ops.html, tools/sybil_digest.py, tests/test_ops_sybil_dismissal.py)
- [docs] document the Ops write secret, leased digest claims, and Sybil dismissed-state semantics without committing the real secret (.env.example, README.md, CLAUDE.md, Sybil design and plan)
- [feat] persist authenticated Front webhooks before processing and retry temporary failures with leased SQLite inbox records and APScheduler (models.py, services/webhook_inbox.py, webhooks/front_webhook.py, tasks/scheduler.py, tests/test_webhook_recovery.py)
- [docs] document durable webhook recovery, retry timing, dead letters, and verification (README.md, CLAUDE.md, docs/runtime-boundaries.md)
- [fix] start webhook leases only after execution capacity, drain APScheduler jobs for up to 60 seconds, and document at-least-once external side-effect semantics (webhooks/front_webhook.py, main.py, tests/test_webhook_recovery.py, tests/test_runtime_boundaries.py, README.md, CLAUDE.md, docs/runtime-boundaries.md)
- [docs] clarify the 60-second graceful scheduler drain guarantee and residual timeout boundary (README.md, CLAUDE.md, docs/runtime-boundaries.md)
- [fix] deduplicate simultaneous Linear ticket creation across conversations for the same trusted sender and original email within 24 hours (agent/orchestrator.py, agent/tool_registry.py, tools/state.py, tests/test_linear_ticket_deduplication.py, README.md, CLAUDE.md, docs/runtime-boundaries.md)
- [feat] rebuild the Ops overview around actionable queues and truthful coverage, expose webhook recovery health, refresh draft adoption before reports, and conservatively backfill missing Front sender/summary metadata every 15 minutes (routes/ops.py, routes/static/ops.html, services/ops_metadata.py, tasks/scheduler.py, tests/test_ops_data_quality.py, tests/test_routing.py, README.md, CLAUDE.md, docs/runtime-boundaries.md)
- [fix] serialize Ops maintenance and release SQLite transactions before Front API calls so report and metadata refreshes cannot block each other or webhook writes (services/draft_adoption.py, tasks/scheduler.py, tests/test_draft_adoption.py, tests/test_routing.py, docs/runtime-boundaries.md)
- [refactor] simplify the Ops frontend into a focused workbench with four KPIs, one priority queue, system health, and data coverage; remove secondary overview clutter and compress reports (routes/static/ops.html, tests/test_ops_data_quality.py)
- [refactor] rename the user-facing Sybil queue to the education account exception queue while retaining internal API and storage identifiers (routes/static/ops.html, tests/test_ops_data_quality.py, README.md)

## 2026-07-15
- [fix] keep Linear issue metadata internal in technical-support drafts, present Contact Us as the priority-support channel for paid users, and avoid exhaustive ticket-content checklists (skills/technical.md, tests/test_skills.py)
