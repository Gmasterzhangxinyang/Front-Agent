import asyncio
import logging

import httpx
from config import settings

LINEAR_API_URL = "https://api.linear.app/graphql"
HEADERS = {
    "Authorization": settings.linear_api_key,
    "Content-Type": "application/json",
}
LINEAR_TIMEOUT = httpx.Timeout(30.0, connect=8.0, read=20.0, write=10.0, pool=5.0)
LINEAR_TRANSIENT_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
LINEAR_TRANSIENT_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.NetworkError,
)


async def _linear_request(payload: dict, retries: int = 5) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=LINEAR_TIMEOUT) as client:
                response = await client.post(LINEAR_API_URL, headers=HEADERS, json=payload)
            if response.status_code not in LINEAR_TRANSIENT_STATUSES or attempt == retries:
                return response
            logging.warning(
                "Linear API transient status %s (%s/%s): %s",
                response.status_code,
                attempt,
                retries,
                response.text[:500],
            )
        except LINEAR_TRANSIENT_EXCEPTIONS as exc:
            last_error = exc
            if attempt == retries:
                raise
            logging.warning("Linear API transient error (%s/%s): %r", attempt, retries, exc)

        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

    assert last_error is not None
    raise last_error


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
    r = await _linear_request({"query": query, "variables": variables})
    r.raise_for_status()
    data = r.json()
    issue = data.get("data", {}).get("issueCreate", {}).get("issue")
    if issue:
        return issue.get("url"), issue.get("identifier")
    return None, None
