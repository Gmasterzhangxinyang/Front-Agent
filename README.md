# Dify Email Automation

## 本地启动

### 1. 安装依赖
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
cp .env.example .env
```
编辑 `.env`，填入以下必填项：
- `FRONT_API_TOKEN` — Front 后台 Settings → API → Token
- `OPENAI_API_KEY` — OpenAI API key
- `LINEAR_API_KEY` — Linear Settings → API → Personal API keys
- `LINEAR_TEAM_ID` — Linear 团队 ID（URL 中可找到）
- `LINEAR_CUS_PROJECT_ID` — CUS 项目 ID
- `FEISHU_WEBHOOK_BOBBY` — 飞书机器人 webhook URL
- `FRONT_TEAMMATE_XIAXI` — 徐小茜在 Front 的 teammate ID
- `FRONT_TEAMMATE_ZHAOHQ` — 赵晗青在 Front 的 teammate ID
- `ZHAOHQ_EMAIL` — 赵晗青邮箱
- `ZHAOYAWEN_EMAIL` — 赵雅雯邮箱

**如何查 Front Teammate ID：**
Front 后台 → Settings → Teammates → 点击某人 → URL 中的 `alt_xxx` 即为 ID

### 3. 启动服务
```bash
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

服务启动后访问 http://localhost:8000/health 确认正常。

### 4. 本地测试 webhook（用 ngrok）
```bash
ngrok http 8000
```
把 ngrok 给的 URL（如 `https://xxxx.ngrok.io/webhook/front`）填入 Front Rule 的 webhook 地址。

---

## Railway 部署

1. 在 Railway 新建项目，连接此 GitHub 仓库
2. 在 Railway 的 Variables 中填入所有 `.env` 里的变量
3. 部署完成后，把 Railway 给的域名 + `/webhook/front` 填入 Front Rule

---

## 文件结构说明

```
skills/          ← 邮件处理规则（markdown），修改规则只需改这里
tools/           ← API 工具函数（Front/Linear/飞书）
agent/           ← GPT-4o orchestrator 主逻辑
webhooks/        ← Front webhook 接收
tasks/           ← 10天自动关闭定时任务
```

## 新增邮件类别

1. 在 `skills/` 下新建 `<类别名>.md`，参考现有文件格式
2. 在 `skills/classify.md` 的分类表中添加新类别
3. 无需改代码

## 模板修改

所有回复模板在对应的 `skills/<类别>.md` 文件中，搜索 `⚠️ 需确认` 找到需要你确认的地方。
