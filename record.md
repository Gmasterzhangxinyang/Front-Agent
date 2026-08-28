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
- [fix] politely remind existing-invoice customers to update Billing Info in the portal for future invoices before offering an optional supplementary Credit Note (skills/billing.md, tests/test_skills.py, README.md, CLAUDE.md)
- [fix] state that LangGenius is a non-PRC entity and cannot issue Mainland China tax invoices, including VAT special invoices, while retaining commercial Invoice guidance (skills/billing.md, skills/classify.md, tests/test_skills.py)

## 2026-07-22
- [fix] 将 Front 客户草稿和回复中的 Markdown 安全转换为 HTML，使粗体、列表和链接正确渲染（tools/front.py, requirements.txt, tests/test_runtime_boundaries.py）

## 2026-08-04
- [feat] 新增 Premium 独立咨询话术：说明其基于 Community Edition、主要用于 AWS 一键部署 POC，对大规模生产等场景推荐 Enterprise，并支持普通客户询问国家/地区与日本客户销售转交同意询问（skills/purchase.md, skills/classify.md, sop.md, docs/skill-test-cases.md, tests/test_skills.py）
- [fix] 修复 Front 内部转发回复被误判为客户新来信并重复生成草稿：根据 author/from/recipients 排除 Dify 内部消息、修正对话角色、忽略未发送草稿，并允许真实外部来信修复被污染的 sender_email（agent/message_identity.py, webhooks/front_webhook.py, agent/orchestrator.py, tools/state.py, tests/test_internal_forward_loop.py, CLAUDE.md）
- [feat] 新增 Premium 双/多 AZ Active-Active 自定义架构专用话术：明确其不符合 AWS Marketplace 标准一键部署、工程难度和潜在问题无法预估且不建议采用，并为日本客户加入 Enterprise 日本销售对接同意询问及脱敏回归案例（skills/technical.md, skills/purchase.md, skills/classify.md, sop.md, docs/skill-test-cases.md, tests/test_skills.py）
- [fix] 完善草稿采纳统计：识别 Front 内部转发线程中的真实人工回复，将评论、工单等工作流处理和等待中会话从“未发送”中分离，持续重算历史 `not_sent`，排除内部测试会话，并将原样采用率限定为已检测到回复的草稿（services/draft_adoption.py, tools/front.py, routes/ops.py, routes/static/ops.html, tests/test_draft_adoption.py）

## 2026-08-05
- [docs] 在不修改总览 SVG 的前提下，新增 ①–⑧ 八张独立架构拆解图及索引文档，逐阶段展开事件入口、可信落盘、上下文、分类路由、两层策略、安全执行、外部副作用、结果持久化与恢复，并保留每张图的 GraphViz 源文件（README.md, docs/current-system-architecture.md, docs/current-system-architecture-details.md, docs/architecture-details/*.dot, docs/assets/architecture-details/*.svg）
- [docs] 将当前系统架构重绘为 A–E 五条横向泳道：顶部固定 ①–⑧ 实时主链，模块明细按阶段编号对照，安全执行、失败恢复、数据运营和系统边界分别成行；提供 4000px PNG、可无限缩放的 SVG、GraphViz 源文件，默认折叠高密度 Mermaid 明细图，并从 README 提供直达入口（README.md, docs/current-system-architecture.md, docs/current-system-architecture.dot, docs/assets/front-agent-current-architecture.svg, docs/assets/front-agent-current-architecture-preview.png）

## 2026-08-10
- [feat] 教育版账号封禁或停用来信统一创建指定英文 Front 草稿，新增确定性识别、固定路由、分类规则与回归测试，且不自动发送或转交（agent/classification.py, agent/orchestrator.py, agent/routing.py, skills/classify.md, skills/education.md, tests/test_routing.py, tests/test_skills.py）
- [fix] 明确教育版申请被拒绝仍走原有正常审核流程，仅账号级封禁或停用使用统一草稿，并增加防混淆回归测试（skills/education.md, tests/test_routing.py, tests/test_skills.py）
- [fix] 将统一封禁草稿规则扩展到所有明确的账号封禁/停用来信（不限于教育版），保持教育版申请被拒绝走正常审核流程，并增加通用封禁与功能 disabled 误判保护测试（agent/classification.py, agent/orchestrator.py, agent/routing.py, skills/account.md, skills/classify.md, skills/education.md, tests/test_routing.py, tests/test_skills.py）
- [ops] 复核并规范化 30 个账号封禁会话：14 个旧草稿原位替换为指定模板；2 个重复会话因 Front Token 缺少 drafts:delete 权限无法删除多余草稿，已将两份内容均统一为指定模板；未发送客户邮件

## 2026-08-11
- [ops] 将本轮发现的 2 个未发送错误草稿原位更新为指定统一模板；重新草拟产生的重复项因 Front Token 缺少 `drafts:delete` 权限无法删除，已确保每个会话的两份草稿内容均与模板完全一致，未发送客户邮件
- [deploy] 将账号封禁主题+正文确定性识别修复部署至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-e378dff-FxLelz`，健康检查通过
- [ops] 补处理主题为普通营销邮件、仅正文写明 `account is banned` 的历史会话 `cnv_1jay8gm3`，创建统一模板草稿并保存 `account/account_suspended/draft_created` 状态；随后按主题+正文扫描近期 100 个会话，33 个明确封禁候选均已有完全一致的模板草稿或已发送模板，无其他缺口
- [fix] 封禁确定性识别同时读取 Front 邮件主题与正文，修正英文 `suspension` 名词词形并补充“误封/被误封”措辞，覆盖正文仅提供证明材料但主题明确写明账号封禁的来信（agent/classification.py, agent/orchestrator.py, webhooks/front_webhook.py, tasks/scheduler.py, tests/test_routing.py, tests/test_runtime_boundaries.py）
- [feat] 统一 SaaS 客户邮件语言与署名：始终先提供完整英文版并使用 `Best regards, Dify Support Team`；非英文来信在英文版后追加对应语言参考译文；账号封禁固定英文正文保持不变，并按相同规则添加英文署名及对应译文（agent/orchestrator.py, agent/tool_registry.py, sop.md, skills/*.md, tests/test_runtime_boundaries.py, tests/test_skills.py）

## 2026-08-12
- [fix] 每次外部客户来信（新会话或已有会话回复）都按标准化发件人直接从 Front 联系人会话列表与本地状态合并加载最多 5 个其他会话的主题、已发送正文、处理状态和既有 Linear 信息；无本地状态的旧会话也会纳入、草稿不计入上下文。同一用户跨会话继续封禁申诉时，在路由前阻止重复模板和重复工单，互加内部链接并转为人工复核（tools/front.py, agent/orchestrator.py, tools/state.py, skills/classify.md, skills/account.md, skills/education.md, sop.md, tests/test_runtime_boundaries.py, tests/test_skills.py）
- [ops] 将同一学生邮箱的 `cnv_1jb3qg63`、`cnv_1jbeqntn`、`cnv_1jber66z` 三个封禁申诉会话内部互链，以 `cnv_1jb3qg63` 和既有 `CUS-1513` 为主记录，并将最新会话设为 `manual_review`；未发送客户邮件或新建工单
- [deploy] 将全局同发件人多会话上下文、封禁跨会话去重及 SaaS 英文优先署名规则部署至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-e378dff-multicontext-KOHaeU`；实际 Front 联系人会话发现、启动日志、8080 监听与 `/health` 均验证通过，旧发布目录保留用于回滚
- [feat] 新增受 Ops 登录保护的账号封禁统一分析页：复核 2026-08-07 至 08-11 的 35 个 Front 会话并合并为 30 个独立事件，逐项展示用户所述情况、类型、可观察关联线索、分析判断、模板实际发送/仅草稿状态及模板后同线程或跨线程回复；支持事件/会话双视图、筛选、Front 直达和 CSV 导出，并通过 183 项完整测试（routes/ops.py, routes/static/ops.html, routes/static/account_ban_analysis.html, tests/test_ops_auth.py）
- [deploy] 将受 Ops 登录保护的账号封禁统一分析页发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-e378dff-ban-analysis-DeNKJT`；`/health` 返回正常，未登录访问分析页正确 303 跳转至 `/ops/login`
- [fix] 按 Elsie 对 `cnv_1jb49t97` 的审核意见收紧中国大陆税务/VAT 发票回复：仅描述 LangGenius, Inc. 的实际开票能力，不从实体属性自行推导税法结论，不替客户机构判断报销可接受性，并主动请客户提供额外材料的具体要求；同时在 `front_create_draft` 执行前加入专用硬校验，阻止旧式绝对因果、直接报销指示或缺少有限下一步的草稿，真实会话回放验证旧文案被拦截，完整测试 185 项通过（skills/billing.md, agent/tool_registry.py, sop.md, tests/test_skills.py, tests/test_runtime_boundaries.py）
- [deploy] 将 Elsie 审核后的中国大陆税务/VAT 发票回复规则与草稿硬校验发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-e378dff-vat-policy-yPt9gI`；启动导入、调度器日志与 `/health` 均验证正常
- [fix] SaaS 客户邮件正文不再手写 `Best regards, Dify Support Team` 或其他落款，英文版及非英文参考译文均保持无署名；Front 草稿与备用直发接口统一启用已配置的默认签名，并在运行时拒绝模型生成的手写落款，完整测试 186 项通过（agent/orchestrator.py, agent/tool_registry.py, tools/front.py, skills/*.md, sop.md, tests/test_runtime_boundaries.py, tests/test_skills.py）
- [deploy] 将 Front 默认签名与正文禁用手写落款规则发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-39bcfc8-default-signature-veqTkN`；发布前导入检查、进程切换及 `/health` 均验证正常
- [fix] 精简同发件人跨会话关联评论：当前会话仅保留主记录、额外关联会话（如有）、已有 Linear 链接及未重复建草稿状态；历史会话仅保留新会话链接和去重状态，不再复制发件人、处理状态、历史列表、说明段落或邮件正文（agent/orchestrator.py, skills/account.md, skills/education.md, sop.md, tests/test_runtime_boundaries.py, tests/test_skills.py）
- [deploy] 将跨会话关联短评论规则发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-5a2899e-concise-links-WzUS3O`；完整测试 186 项、发布前导入检查、进程切换及 `/health` 均验证正常
- [feat] 新增受 Ops 登录保护的动态系统流向页 `/ops/system-flow`：用 6 步主线直观展示 Front 来信、安全落盘、完整上下文、分类、规则校验和安全执行，再分流至 Front 草稿、Linear 工单或内部处理并保存状态；失败重试独立成回路。页面每 8 秒读取真实 SQLite 遥测、动态闪动最近活动并提供 Front 会话直达，点击节点只展开三条关键说明，避免复杂技术拓扑；完整测试 188 项通过（routes/ops.py, routes/static/system_flow.html, routes/static/ops.html, tests/test_ops_auth.py, tests/test_ops_data_quality.py, README.md）
- [deploy] 将动态系统流向页发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-3a663cd-system-flow-HjKkzJ`；发布前导入和真实数据库遥测检查、进程切换、`/health`、未登录重定向/API 401、使用现有 Ops 凭据登录后的 HTML 与 48 条实时活动加载均验证正常
- [refactor] 将动态系统流向页从文字卡片重构为全屏原生 Canvas 神经网络渲染：深色空间与扫描线背景、带鼠标视差的动态神经元场、发光核心与旋转轨道、沿主链/输出分支/失败回路传播的实时脉冲、事件驱动的核心点亮及高科技 HUD；主画面只保留极少节点名，说明与真实会话活动仅在点击核心后以浮动面板显示，不依赖外部渲染库（routes/static/system_flow.html, tests/test_ops_auth.py）
- [deploy] 将神经网络 Canvas 动态流向页发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-4d8caf6-neural-flow-QUrfgx`；JavaScript 解析、完整 188 项回归、发布资源解析、进程切换、`/health`、Ops 认证后的 21 KB Canvas 页面与 48 条实时活动数据加载均验证正常
- [refactor] 将神经网络流向页改成单封邮件的具象旅程演示：发光信封沿带箭头的路径逐站移动、停留并同步说明系统动作，固定展示接收/理解/决策约束/输出记忆四个阶段与图形化节点；可切换普通回复到 Front 草稿、技术问题到 Linear、敏感事项内部转交、失败进入自动重试四条路径并重新播放，同时保留真实遥测与节点详情（routes/static/system_flow.html, tests/test_ops_auth.py）
- [deploy] 将单封邮件具象旅程动画发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-a65ea1a-email-journey-Nj9b3s`；JavaScript 语法、完整 188 项回归、发布文件哈希、应用导入、进程切换与 `/health` 均验证正常，使用现有 Ops 凭据确认线上页面包含发光信封旅程并成功读取 48 条实时活动
- [fix] 将单邮件旅程从自动循环改为默认暂停的逐步演示：每次点击醒目的“下一步”仅播放一段节点间动画，停稳后显示本步说明；支持上一步、从头播放、可选自动播放、左右方向键及四种分支场景，并为缺少 Canvas `roundRect` 的浏览器增加兼容绘制，避免整幅动画因单个 API 不可用而中断（routes/static/system_flow.html, tests/test_ops_auth.py）
- [deploy] 将单邮件逐步演示页发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-75105c2-step-by-step-3YWUYO`；JavaScript 语法、完整 188 项回归、发布文件哈希、应用导入、进程切换、启动日志与 `/health` 均正常，使用现有 Ops 凭据确认线上逐步/上一步/自动播放控件及兼容绘制代码均已加载，并成功读取 48 条实时活动
- [refactor] 将逐步邮件旅程升级为 Agent Deep View：每一步在路径下方展开真实内部结构，包含 Front 可信入口与附件边界、WebhookInbox 持久状态机、当前会话/同发件人近 30 天最多 5 个其他会话/最近 300 状态检索 Top 4 的三层 Memory、16 个一级分类与 49 个子类型矩阵及当前命中项、GPT-5.5 Agent 与动态 Skill/全局硬约束、19 个白名单工具及当前调用链、Front 草稿/Linear/内部转交输出、ConversationState/ConversationAction 回流和失败恢复；四个演示场景使用具体分类与子类型，Canvas 路径缩至上半区并为低高度窗口提供可滚动详细面板（routes/static/system_flow.html, tests/test_ops_auth.py）
- [deploy] 将 Agent Deep View 发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-2810807-agent-deep-view-KNGVKr`；页面常量解析精确确认 16 类/49 子类型/19 工具，无头 Canvas/DOM 运行检查实际连续走通入口、持久化、Memory 和分类点亮，完整 188 项回归、发布哈希、应用导入、进程切换、启动日志和 `/health` 均正常；使用现有 Ops 凭据确认线上深度视图全部标志与 48 条实时活动成功加载
- [refactor] 将 Agent Deep View 重构为客户演示级邮件处理故事板：采用克制的暖白/黑/绿色视觉体系、8 步信封进度轨、4 条真实业务分支和逐步控制；以独立图形场景展开可信入口、持久队列、三层 Memory、16 类/49 子类型、GPT‑5.5 Agent 与 Skill/Policy/Context、19 个白名单工具、安全输出、状态回流及失败恢复，并接入实时遥测。使用真实 Chromium 对桌面端 4×8 共 32 个画面与 390px 移动端逐屏复核，修复分类矩阵截断，确认无横向溢出、无控制台错误；JavaScript 语法与完整 188 项回归通过（routes/static/system_flow.html, tests/test_ops_auth.py）
- [deploy] 将客户演示级邮件处理故事板发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-3d390cb-customer-demo-aNAHzV`；发布资源哈希、应用导入、进程切换、本机与公网 `/health` 均正常。使用真实 Ops 登录在生产环境验证页面 200、4 个场景、逐步交互、Agent 画面、48 条实时活动与 11 个安全动作，浏览器控制台零错误且无横向溢出；旧发布目录保留用于回滚

## 2026-08-13
- [fix] 将面向 Dify 的具体 B2B 产品、API、模型供应商、推理基础设施和技术集成提案归为 partnership，并在 spam 自动归档前加入确定性保护，避免商业合作邮件因免费试用或会议邀请被误关（agent/classification.py, agent/orchestrator.py, agent/routing.py, skills/classify.md, skills/partnership.md, skills/spam.md, tests/test_routing.py, tests/test_skills.py, README.md）
- [deploy] 将技术集成 partnership 防误归档修复发布至本地生产 screen `front-agent-v2`，运行目录 `/tmp/front-agent-release-b592afa-partnership-9nlu88`；发布目录导入、路由与 Skill 测试、进程切换、启动日志和 `/health` 均验证正常，现有 Front 会话未自动重开或发送邮件

## 2026-08-18
- [fix] 对学校邮箱失效后的模糊 trial/订阅取消请求先确认是否为教育版；仅在确认教育版后说明到期不自动续订，避免误走身份验证流程（agent/classification.py, agent/orchestrator.py, skills/classify.md, skills/education.md, tests/test_routing.py, tests/test_skills.py）

## 2026-08-18
- [fix] 新增教育版订阅后仅显示 200 message credits 的标准回复：说明额度从每月 5,000 调整为总计 200 且不按月重置、其余 Professional 权益不变、可配置自有模型 API Key，并明确不得提及 8 月 10 日（agent/classification.py, skills/classify.md, skills/education.md, tests/test_routing.py, tests/test_skills.py）

## 2026-08-26
- [feat] 将只读 Dify DB Gateway 收敛为 Front-Agent 的账单辅助查询工具：查询对象强制绑定当前 Front 发件人，使用固定 SQL 从 prod 映射账号/Tenant 后仅读取 billing 的订阅、额度和删除记录；模型不能传入邮箱、SQL 或数据库，结果仅作内部证据且不授权退款、取消或额度变更。新增 MCP/SSE、PostgreSQL CSV 页脚和信任边界测试，并通过真实不存在邮箱的只读冒烟验证（tools/dify_billing.py, agent/tool_registry.py, agent/orchestrator.py, config.py, skills/account.md, skills/billing.md, tests/test_dify_db_tool.py, README.md）
- [deploy] 将只读 Billing 查询工具发布至 `front-agent-v2`，运行目录 `/tmp/front-agent-release-billing-YkUoZW`；仅叠加 Billing 集成相关文件，11 组回归、编译、依赖、发布目录导入、本机与公网健康检查均通过，线上工具和 Token 加载成功，并通过工具注册层完成不存在邮箱的真实只读查询；未发送 Front 回复或写入 Dify 数据库。
- [ops] 对 `cnv_1jfq9a6z` 只读核验 Professional 订阅和当前周期用量：确认 paid bucket 为 5,000/5,000、页面 200/200 来自旧 Sandbox trial bucket，并按模型汇总 5,000 credits；将已有错误“已转交”草稿原位更新为核查结果和用量明细，会话仍仅 1 份 shared draft，未发送客户邮件。

## 2026-08-28
- [fix] 为 Linear 客服工单增加保守的近似重复检测：同一发件人 24 小时内的疑似候选交由 LLM 判断，仅高置信同一请求才复用已有工单；增加同发件人并发锁、跨会话内部备注与重开逻辑，并补齐回归测试（agent/tool_registry.py, tools/state.py, tools/linear.py, tests/test_linear_ticket_deduplication.py, README.md, docs/runtime-boundaries.md, docs/current-system-architecture.md）
- [ops] 将 `msg_2yuu2zrv` 所在会话 `cnv_1jgip0bf` 的已有 shared draft 原位更新为请求客户提供脱敏后的 Chatflow DSL（YAML）和完整复现步骤；保留原收件人与主题，未发送客户邮件，且未创建第二份草稿。
- [fix] 补齐日文 `教育認証` 主题入口及“メッセージクレジット是否按月付与”的确定性识别，使其优先命中 `education/credit_allowance_200`，并增加客户原文回归用例（agent/classification.py, tests/test_routing.py）。
- [deploy] 将此前遗漏上线的教育版 200-credit 政策及日文识别修复发布至 `front-agent-v2`，运行目录 `/tmp/front-agent-release-education-lohOSA`；仅叠加教育分类、编排与 Skill 文件，路由、Skill、webhook、内部转发、草稿、编译、依赖、发布目录原文断言、文件哈希、应用导入、进程、调度器和本机 `/health` 均验证正常，旧 Billing release 保留用于回滚。
- [ops] 将 `cnv_1jcufihn` 的唯一 shared draft `msg_2yu2wz4r` 原位改为教育版额度政策的英日双语说明：每月 5,000 已调整为总计 200 且不按月重置，其他 Professional 权益不变、用完可配置自有模型 API Key；状态从 `education/no_discount + forwarded_keep_open` 修正为 `education/credit_allowance_200 + draft_created`，草稿仍未发送。
- [ops] 将 `cnv_1jg4tb8b` 的唯一 shared draft `msg_2ytwl84b` 原位更新为英中双语说明：MCP 服务更新和删除异常已修复，请客户重新尝试，若仍报错则提供最新错误信息或截图；收件人保持 `leon@jiemasoft.com`，草稿未发送。
- [feat] 新增工作日 12 小时未回复兜底提醒：每 15 分钟限量核对客户最新邮件，真实外发回复或其后的 Bobby 本人 Front 评论视为已接手，草稿与 API 机器人评论不计；逾期后通过飞书应用私聊 Bobby 并附 Front 直达链接，按客户消息幂等且发送失败可重试（services/unanswered_reminders.py, tasks/scheduler.py, tools/feishu.py, config.py, tests/test_unanswered_reminders.py, README.md, CLAUDE.md, .env.example）。
- [deploy] 将工作日 12 小时未回复个人提醒发布至 `front-agent-v2`，运行目录 `/tmp/front-agent-release-sla-sWvYBA`；仅叠加 SLA 扫描、调度器、飞书与配置文件，261 个两天前的旧状态写入一次性上线基线以防历史洪泛。专项 13 项及完整回归、编译、依赖、发布哈希、应用导入、调度器、本机和公网健康检查均通过；首轮 10 个候选正确识别 5 个关闭、2 个 Bobby 已评论和 3 个逾期未回复，3 条带 Front 链接的飞书个人提醒均发送成功并完成幂等记录，未向客户发送邮件。
- [fix] 将 12 小时提醒的候选范围修正为“Support inbox 内全部 open 会话”与“任意 inbox 中 assigned to Bobby 的 open 会话”的去重并集，不再扫描其他 inbox 中未指派给 Bobby 的会话；首次错误扫描发送的 3 条提醒均来自 Marketing/Security 且未指派，已明确告知忽略（services/unanswered_reminders.py, tests/test_unanswered_reminders.py, README.md, CLAUDE.md）。
- [deploy] 将修正后的提醒范围发布至 `front-agent-v2`，运行目录 `/tmp/front-agent-release-sla-scope-bjkPKq`；首轮 Front 搜索确认 Support 9、assigned to Bobby 0、并集 9，实际检查 7 个新活动会话，5 个逾期提醒通过飞书私聊成功发送、2 个已有客户回复，错误数为 0；服务进程、发布哈希与本机健康检查正常，未向客户发送邮件。
- [fix] 将 12 小时提醒增加固定启用边界：仅 2026-08-28 00:00（中国时间）及之后收到的客户邮件参与计时，之前的历史积压永久忽略；修正测试时间戳为显式 UTC 并增加上线前消息不发送、写入终态的边界回归。此前误发的 5 条历史 Support 提醒已明确告知忽略（services/unanswered_reminders.py, tests/test_unanswered_reminders.py, README.md, CLAUDE.md）。
- [deploy] 将“仅从今天开始计时”的版本发布至 `front-agent-v2`，运行目录 `/tmp/front-agent-release-sla-today-JZO7n7`；16 项专项测试、编译、依赖、发布哈希和导入通过，首轮线上任务只执行 Support 与 Bobby-assigned 两条搜索且没有飞书发送请求，本机健康检查正常。
- [docs] 重构 README 和系统架构入口：以交互式概览、完整架构、①–⑧ 阶段图、运行边界和 Ops 动态故事板形成分层导航；同步当前 16 类/52 子类型/20 工具、只读 Dify Billing、Linear 语义去重与工作日 12 小时提醒。两份 Archify JSON/HTML 均通过 showcase 9/9、0 error、0 warning 原子交付，规格/产物 SHA-256 分别为 `26cb65a…/8f4beee…` 与 `ab92fe6…/c76cd89…`（README.md, docs/current-system-architecture.md, docs/current-system-architecture-details.md, docs/runtime-boundaries.md, docs/front-support*.architecture.json, docs/front-support*-architecture.html, routes/static/system_flow.html, routes/static/ops.html, tests/test_ops_auth.py）。
- [verify] 全部 12 个离线测试脚本、Python 编译、依赖检查、Ops 内联 JavaScript 语法、本地 Markdown 链接、敏感信息模式和 `git diff --check` 通过；Archify 多尺寸截图流程因宿主 Chromium 缺少 `libatk-1.0.so.0` 未完成，未提交失败回执，也未虚报视觉通过。
