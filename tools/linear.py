import httpx
from config import settings

LINEAR_API_URL = "https://api.linear.app/graphql"
HEADERS = {
    "Authorization": settings.linear_api_key,
    "Content-Type": "application/json",
}


async def create_ticket(title: str, body: str) -> tuple[str, str] | tuple[None, None]:
    query = """
    mutation CreateIssue($title: String!, $description: String!, $teamId: String!, $projectId: String) {
        issueCreate(input: {
            title: $title,
            description: $description,
            teamId: $teamId,
            projectId: $projectId
        }) {
            success
            issue { id url identifier }
        }
    }
    """
    variables = {
        "title": title,
        "description": body,
        "teamId": settings.linear_team_id,
        "projectId": settings.linear_cus_project_id or None,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(LINEAR_API_URL, headers=HEADERS, json={"query": query, "variables": variables})
        r.raise_for_status()
        data = r.json()
        issue = data.get("data", {}).get("issueCreate", {}).get("issue")
        if issue:
            return issue.get("url"), issue.get("identifier")
    return None, None
