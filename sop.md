# Front 邮件自动化 SOP

## 基本规则
- 回复语言：英文版本必须完整并放在最前；非英文来信在英文版后注明“下方附对应语言版本供参考”，再附对应语言译文；英文来信不重复第二语言
- 署名：所有语言版本均使用英文署名 `Best regards, Dify Support Team`，不得翻译团队名或使用非英文署名（AI自动回复需标注 AI generated）
- 固定模板：英文固定正文保持逐字不变；非英文来信仍须在英文版及英文署名后，追加对应语言参考译文，并统一使用英文署名
- 处理完成后：Front conversation 需要 resolve
- 付费用户识别：检查邮件 footer 是否含 `Current Plan: professional` 或 `Current Plan: team`
- 发件邮箱与账号邮箱不一致时：先让用户确认账号邮箱
- 附件/截图（含非英文）：AI 需要查看并处理所有附件内容
- 跨会话上下文：每次收到外部客户邮件（包括已有会话回复和新 Front 会话），必须按同一标准化发件邮箱读取其他近期 Front 会话的已发送往来、状态和已有 Linear 链接；即使旧会话没有本地自动化状态也要读取。换主题或新 conversation ID 不视为全新案例，必须先理清多会话上下文，不得重复草稿、重复建单或作出矛盾回复
- 分类不确定时：发通用回复给用户，同时飞书通知 Bobby 人工判断
- 飞书通知方式：Webhook 私信 Bobby（后续自动化稳定后改为直接通知对应人）
- 用户 10 天未回复：自动 resolve conversation
- 用户情绪激动 / 投诉 / 威胁曝光：舒缓用户情绪，立即飞书通知 Bobby
- 律师函 / 法律威胁：立即总结问题飞书通知 Bobby，Bobby 联系法务处理
- 判断为超级大客户（知名大公司等）：飞书通知 Bobby 特别关注
- 官方文档：https://docs.dify.ai
- Roadmap：工作空间内点击个人头像可查看

---

## 邮件分类与处理流程

### 1. 技术类 / Bug 类

包含：功能咨询、操作问题、bug 报告、API 限额/key 管理、服务宕机/无法访问、数据隐私咨询

**判断是否为付费用户（Team / Pro）：**

- **是付费用户（Team / Pro）：**
  - 引导用户通过 Settings → Support → Contact Us 提交工单
  - 提醒用户提交时不要删除邮件底部的订阅验证信息
  - 模板参考：
    > Dear Valued Customer,
    > Thank you for your inquiry. Priority technical support via "Contact Us" is available only for Dify Cloud Pro and Team subscribers. Please submit your request through Settings → Support → Contact Us in your dashboard. When submitting the ticket, please do not remove the subscription verification details, as they are required for us to confirm your account status.
    > Best regards, Dify Support Team

- **不是付费用户（Sandbox/Free）：**
  - 若用户在问如何操作 / 如何定制工作流：根据官方文档给出建议，告知优先技术支持仅对付费用户开放，引导升级
  - 若用户在评估技术可行性并有购买意向：根据官方文档说明（只有 100% 确定能做到才可以说能做到）
  - 引导免费用户查阅 docs.dify.ai 或在 GitHub 提交 issue：github.com/langgenius/dify/issues

- **Premium 用户（自部署授权）：**
  - AI 直接尝试回答用户问题，不走工单系统
  - 若 AI 无法解决，人工介入处理

- **自部署用户（非 Premium，无授权）：**
  - 引导用户查阅官方文档或在 GitHub 社区提问/提交 issue

**数据隐私咨询：**
- 用户问 Dify 是否会泄露数据或用于训练：明确回答否，Dify 不会这样做
- 若涉及严重数据安全问题（影响 Dify 数据）：转 Security 流程（见第 7 条）

**服务宕机 / 无法访问：**
- 告知用户正在排查，建立 Linear 工单（CUS 项目），飞书通知 Bobby

---

### 2. 账户类

#### 2a. 收不到验证码 / 无法登录
1. 自动回复用户：正在处理，请稍候
2. 飞书通知 Bobby，总结用户邮箱
3. Bobby 联系李敏查原因
4. 若是 STA 问题：邮件通知用户检查垃圾箱等操作
5. 若账号在黑名单：飞书联系李敏评估是否拉出黑名单，确认后邮件回复用户已操作完毕

#### 2b. 用户要求删除账号
1. 验证用户身份：让用户用原邮箱发送一封确认邮件，或提供证明该邮箱属于本人的材料
2. 确认后：
   - 建立 Linear 工单（CUS 项目）：账号邮箱、原因、用户说明摘要
   - 飞书通知张苑晴
3. 张苑晴确认后：邮件回复用户"已收到，已转交相关团队"
4. 张苑晴确认处理完毕后：邮件回复用户已处理完毕，resolve conversation
5. **若用户同时提及退款：** 见「5a. 退款请求」流程

#### 2c. 用户要求转移账号（邮箱失效等）
1. 验证用户身份：让用户用原邮箱发送确认邮件，或提供证明
2. 确认后：
   - 建立 Linear 工单（CUS 项目）：原邮箱、转移后邮箱、原因摘要
   - 飞书通知张苑晴
3. 张苑晴确认后：邮件回复用户"已收到，已转交相关团队"
4. 张苑晴确认处理完毕后：邮件回复用户已处理完毕，resolve conversation

#### 2d. 账号可正常登录，需要更换绑定邮箱
- 邮件引导用户通过产品内正常流程自行操作

#### 2e. 账号异常（额度错误、计划变更等）
1. 建立 Linear 工单（CUS 项目）：用户邮箱、问题描述、时间
2. 飞书通知张苑晴
3. 张苑晴确认后：邮件回复用户"已收到，已转交相关团队"
4. 张苑晴确认处理完毕后：邮件回复用户已处理完毕，resolve conversation

#### 2f. 账号被盗 / 恶意登录
1. 建立 Linear 工单（CUS 项目）：用户邮箱、问题描述、时间
2. 飞书通知 Bobby
3. 后续按账号异常流程处理

#### 2g. 用户想合并两个账号
- 目前无此功能，建立 Linear 工单（CUS 项目）记录需求，飞书通知 Bobby

---

### 3. 购买 / 询价

- **企业版咨询：** 转发至 business@dify.ai 处理
- **Premium 版本咨询：** 说明 Premium 是基于 Community Edition、主要面向 AWS 一键部署 POC 的商业化部署选项。如果用于大规模生产、高并发、多团队协作、企业级安全与权限管理，或对稳定性要求较高，建议 Enterprise。有 Enterprise 意向时请用户提供国家或地区；明显日本客户可直接询问是否同意转交并对接日本销售团队
- **Premium 双/多 AZ Active-Active 自定义架构：** 明确该架构不同于 AWS Marketplace 的标准一键部署，无法预估具体实施的工程难度和潜在问题，因此不建议采用；不要给出环境变量、实施步骤或额外的授权/支持承诺。明显日本客户推荐 Enterprise 后询问是否同意对接日本销售团队
- **Pro / Team 版本咨询：** 引导用户查看 pricing 页面，根据官方文档介绍各计划区别
- **Reseller / 代理商咨询：** Front 中将 conversation forward 给赵晗青

---

### 4. 教育版

教育版：100% 折扣，有效期一年，到期后可重新申请

#### 4a. 教育版申请被拒绝 / 申请流程
1. 邮件回复用户：请提供学校全名（英文）及学校邮箱域名（必须是学校邮箱，个人邮箱如 Gmail 不可用）
2. 收到用户回复后，判断学校类型：
   - **高等教育（大学/学院及以上，经政府认证）：**
     - 建立 Linear 工单（CUS 项目）：学校全名（英文）、邮箱域名、AI 判断结果
     - 飞书通知张苑晴
     - 张苑晴确认没问题：邮件回复用户"已收到，已转交相关团队"
     - 张苑晴确认有问题：邮件告知用户原因，或请用户提供更多信息
     - 张苑晴确认处理完毕后：邮件回复用户已处理完毕，resolve conversation
   - **K12 学校或未经政府认证的学校：**
     - 邮件回复用户：说明原因，告知无法申请教育版，resolve conversation
   - **用户提供个人邮箱（非学校邮箱）：**
     - 邮件告知用户必须使用学校邮箱域名，无法以个人邮箱申请

#### 4b. 教育版认证成功但无法获得折扣
- 引导用户：进入 Bill → 选择 Pro 版 → 选择年付 → 折扣券会自动显示
- 若未看到 edu 标识：说明教育版认证未成功，回到 4a 流程处理

---

### 5. 账单 / 退款

#### 5a. 退款请求（含重复扣款）
1. 让用户提供：邮箱账号、上次扣款时间、扣款原因、Workspace ID
2. 在 Front 中将 conversation assign 给徐小茜，并附上以上信息摘要
3. 若为重复扣款：在摘要中特别注明"重复扣款"
4. 徐小茜确认无问题后：邮件回复用户已退款，5-10 个工作日内到账
5. 若有问题需再次核验：邮件告知用户需要补充信息

#### 5b. 降级套餐 / 取消订阅
- 引导用户自行操作：Bill → Manage Bill → 更改计划

#### 5c. Invoice 相关
- 告知用户可在 Bill → Manage Bill 中自行修改地址
- 中国大陆税务发票 / 增值税发票请求：只描述实际开票能力——`LangGenius, Inc. is not a PRC-registered invoicing entity and does not issue invoices through the PRC tax administration system.` 不要用“非中国实体，因此……”自行概括税法因果
- 明确现有 invoice 与 receipt 是我们可提供的正式商业账单文件，但是否可报销由客户所在机构的报销政策决定；不得直接要求客户“拿现有文件去报销”或暗示一定会被接受
- 主动提供有限下一步：请客户提供机构要求的其他 billing information 或 supporting documentation 的具体清单，我们再核实能够提供什么；不得承诺一定能出具额外文件

#### 5d. 其他账单问题
1. 总结问题，建立 Linear 工单（CUS 项目）
2. 飞书通知张苑晴
3. 张苑晴回复后：邮件告知用户

---

### 6. 市场合作 / Marketplace / Plugin 合作 / 代理商

- Front 中将 conversation forward 给赵晗青，并 cc 赵雅雯
- 包含：plugin 合作、marketplace 合作、reseller/代理商咨询、plugin 下架申请

**注：** plugin bug 报告属于技术类（见第 1 条），不走此流程

---

### 7. Security 相关

- 转到 security inbox
- 若为紧急 security 问题（影响 Dify 数据安全）：建立工单，飞书通知杨永乐
- 数据隐私一般咨询（用户问是否泄露/训练）：见技术类处理

---

### 8. 广告 / 推销类

- 判断为推销邮件：直接 resolve，无需回复

---

### 9. 用户催促 / 重复发邮件

- 判断邮件类别：
  - 若涉及合作或影响正常使用：加急建立 Linear 工单，飞书通知 Bobby
  - 其他情况：按原类别正常处理，回复用户正在跟进

---

### 10. 律师函 / 法律威胁

1. 立即总结问题，飞书通知 Bobby
2. Bobby 联系法务处理
3. 回复用户已收到，正在处理

---

### 11. 数据导出请求

- 官方文档中无数据导出功能
- 若用户非常紧急：飞书通知 Bobby，人工评估处理方式

---

### 12. Roadmap / 功能上线时间咨询

- 引导用户：工作空间内点击个人头像可查看 Roadmap

---

### 13. 分类不确定

- 发通用回复给用户：
  > We've received your email and will get back to you shortly. Thank you for your patience.
- 飞书通知 Bobby 人工判断分类

---

## 关键联系人

| 姓名 | 负责事项 | 联系方式 |
|------|----------|----------|
| 李敏 | 账号验证、黑名单查询 | 飞书私信 Bobby → Bobby 转达 |
| 张苑晴 | 账号操作（删除/转移/异常）、教育版、账单其他 | 飞书私信 + Linear |
| 徐小茜 | 退款处理 | Front assign |
| 赵晗青 | 市场合作/plugin/代理商 | Front forward + cc 赵雅雯 |
| 杨永乐 | 紧急安全问题 | 飞书私信 |
| Bobby | 人工兜底、李敏流程中转、法律/大客户特别关注 | 飞书通知接收 |
