"""
Trinity Web Search Service

Provides web search capabilities for the agentic pipeline.
Uses Brave Search API when available.
"""

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

# API Key from environment
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")


@dataclass
class SearchResult:
    """A single search result"""

    title: str
    url: str
    snippet: str


@dataclass
class SearchResponse:
    """Response from web search"""

    query: str
    results: List[SearchResult]
    error: Optional[str] = None


def search_web(query: str, count: int = 5, timeout: int = 10) -> SearchResponse:
    """
    Search the web using Brave Search API.

    Args:
        query: The search query
        count: Number of results (max 10)
        timeout: Request timeout in seconds

    Returns:
        SearchResponse with results or error
    """
    if not BRAVE_SEARCH_API_KEY:
        logger.warning("Web search not configured - BRAVE_SEARCH_API_KEY not set")
        return SearchResponse(query=query, results=[], error="Web search not configured")

    if not query.strip():
        return SearchResponse(query=query, results=[], error="Empty query")

    count = min(count, 10)  # Cap at 10

    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_SEARCH_API_KEY},
            params={"q": query, "count": count, "safesearch": "moderate"},
            timeout=timeout,
        )

        if response.status_code != 200:
            logger.error(f"Brave Search API error: {response.status_code}")
            return SearchResponse(
                query=query, results=[], error=f"Search API returned status {response.status_code}"
            )

        search_data = response.json()
        web_results = search_data.get("web", {}).get("results", [])

        results = []
        for r in web_results[:count]:
            results.append(
                SearchResult(
                    title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("description", "")
                )
            )

        logger.info(f"🔍 Web search: '{query}' returned {len(results)} results")

        return SearchResponse(query=query, results=results)

    except requests.Timeout:
        logger.warning(f"Search timeout for query: {query}")
        return SearchResponse(query=query, results=[], error="Search timed out")
    except Exception as e:
        logger.error(f"Search error: {e}")
        return SearchResponse(query=query, results=[], error=str(e))


def format_search_context(search_response: SearchResponse) -> str:
    """
    Format search results as context for the LLM.

    Args:
        search_response: Results from search_web()

    Returns:
        Formatted string to include in prompt
    """
    if search_response.error or not search_response.results:
        return ""

    lines = [f"Web search results for '{search_response.query}':"]
    lines.append("")

    for i, result in enumerate(search_response.results, 1):
        lines.append(f"{i}. **{result.title}**")
        lines.append(f"   {result.snippet}")
        lines.append(f"   Source: {result.url}")
        lines.append("")

    return "\n".join(lines)


def is_search_available() -> bool:
    """Check if web search is configured"""
    return bool(BRAVE_SEARCH_API_KEY)


# === TESTING ===

if __name__ == "__main__":
    print("=" * 60)
    print("Web Search Service Test")
    print("=" * 60)

    if not is_search_available():
        print("❌ BRAVE_SEARCH_API_KEY not set - search unavailable")
    else:
        print("✅ Search API configured")

        test_query = "current bitcoin price"
        print(f"\nSearching for: '{test_query}'")

        result = search_web(test_query, count=3)

        if result.error:
            print(f"❌ Error: {result.error}")
        else:
            print(f"✅ Found {len(result.results)} results:")
            for r in result.results:
                print(f"  - {r.title}")

            print("\n--- Formatted context ---")
            print(format_search_context(result))
