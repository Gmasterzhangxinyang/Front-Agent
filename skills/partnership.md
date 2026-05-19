# Skill: Partnership / Marketplace / Plugin / Community

## Purpose
Handle partnership inquiries, marketplace cooperation, plugin cooperation, plugin takedown requests, and community ecosystem inquiries.

## Steps

### 1. Classify the inquiry type
Determine if this is:
- **plugins_templates**: 运营插件与模板生态相关（plugin ecosystem, templates, marketplace listing）
- **japan**: 日本社区活动或业务合作
- **cn_apac**: 中国及亚太区（CN & APAC）业务线合作
- **eu**: 欧洲区（EU）业务线合作
- **partnership**: 其他 partnership/marketplace/reseller 合作

### 2. Forward based on type

#### For community types (plugins_templates / japan / cn_apac / eu):
- Call `front_forward_to_community` — creates a forward draft for Bobby to review and send

#### For partnership type:
- Call `front_forward_to_partnerships` — creates a forward draft for Bobby to review and send

**Important**: Do NOT call `front_create_draft` to reply to the user. Only create the forward draft.

## Regional Routing

| Type | Region | To | CC |
|------|--------|----|----|
| plugins_templates | — | 赵晗青 | 赵雅雯 |
| japan | 日本 | 赵雅雯 | marudan.kj@dify.ai |
| cn_apac | CN & APAC | 赵雅雯 | lushachen@dify.ai, byron@dify.ai |
| eu | EU | 赵雅雯 | xinruiliu@dify.ai |

## Bobby's Workflow
1. AI creates forward draft (no action needed from you yet)
2. You review and send the draft manually in Front
3. No automatic reply sent to the user — you decide what to tell them after sending
