import httpx

GITHUB_API = "https://api.github.com/search/issues"
REPO = "langgenius/dify"


async def search_issues(query: str, max_results: int = 5) -> list[dict]:
    params = {
        "q": f"{query} repo:{REPO}",
        "per_page": max_results,
        "sort": "relevance",
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(GITHUB_API, params=params, headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
        return [
            {
                "number": i["number"],
                "title": i["title"],
                "state": i["state"],
                "url": i["html_url"],
                "type": "PR" if "pull_request" in i else "Issue",
                "body_preview": (i.get("body") or "")[:300],
            }
            for i in items
        ]
