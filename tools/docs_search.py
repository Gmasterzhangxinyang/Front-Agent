import httpx
import re
from bs4 import BeautifulSoup

DOCS_BASE = "https://docs.dify.ai"


async def search_docs(query: str, max_results: int = 3) -> list[dict]:
    """Search Dify docs by fetching sitemap and matching query keywords."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{DOCS_BASE}/sitemap.xml")
            if r.status_code != 200:
                return []

            # Extract all doc URLs (exclude API reference)
            urls = re.findall(r'<loc>(https://docs\.dify\.ai/en/[^<]+)</loc>', r.text)
            urls = [u for u in urls if "api-reference" not in u]

            # Simple keyword matching
            query_lower = query.lower()
            keywords = query_lower.split()

            scored_urls = []
            for url in urls:
                url_lower = url.lower()
                score = sum(1 for kw in keywords if kw in url_lower)
                if score > 0:
                    scored_urls.append((score, url))

            scored_urls.sort(reverse=True, key=lambda x: x[0])
            top_urls = [url for _, url in scored_urls[:max_results]]

            # Fetch content from top matching pages
            results = []
            for url in top_urls:
                content = await _fetch_page_content(client, url)
                if content:
                    results.append({
                        "url": url,
                        "title": url.split("/")[-1].replace("-", " ").title(),
                        "content": content[:800],
                    })

            return results
    except Exception:
        return []


async def _fetch_page_content(client: httpx.AsyncClient, url: str) -> str:
    """Fetch and extract text content from a docs page."""
    try:
        r = await client.get(url)
        if r.status_code != 200:
            return ""

        soup = BeautifulSoup(r.text, "html.parser")

        # Remove script/style tags
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        return text
    except Exception:
        return ""
