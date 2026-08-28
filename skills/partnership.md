# Skill: Partnership / Marketplace / Plugin / Community

## Purpose
Handle partnership inquiries, Marketplace cooperation, plugin cooperation, plugin takedown requests, community ecosystem inquiries, and targeted B2B technology-integration proposals for Dify.

Marketplace/community external cooperation is now owned by the marketing intake address: `marketing@dify.ai`.

## Steps

### 1. Classify the inquiry type
Determine if this is:
- **plugins_templates**: 插件、模板生态、Marketplace listing、插件上架/下架/合作
- **community**: 社区活动、社区合作、生态合作
- **technology_integration**: 面向 Dify 的具体产品、API、模型供应商、推理基础设施或技术栈集成合作
- **partnership**: reseller、代理商、战略合作、外部合作、其他 marketplace/partnership inquiry

A proposal can be commercially motivated and still be a partnership when it describes a concrete fit with Dify's product or technology stack and proposes an integration, pilot, free access, or further cooperation discussion. Generic SEO, backlink, staffing, lead-generation, or unrelated mass vendor pitches remain spam.

### 2. Forward to marketing intake

For all types above:
- Call `front_forward_to_community` with `conversation_id`, a 1-2 sentence `summary`, and `region` set to `plugins_templates` when the inquiry is about Marketplace/plugins/templates.
- If the inquiry is reseller or generic partnership and you prefer the legacy tool name, `front_forward_to_partnerships` is also acceptable. It routes to the same address.

Both tools forward to `marketing@dify.ai` and include the original Front conversation content in the forwarded email body.

**Important**: Do NOT call `front_create_draft` to reply to the user. Only forward to marketing intake.

## Bobby's Workflow
1. AI forwards the original inquiry to `marketing@dify.ai`.
2. No automatic reply is sent to the user.
3. Marketing owns Marketplace/community external cooperation follow-up.
