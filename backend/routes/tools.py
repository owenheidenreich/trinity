"""
Tools endpoints — web search, browse, document upload/query, transcript cleaning.
Routes: /tools/*
"""

import json
import re
import time
from datetime import datetime

import requests as requests_lib
from flask import Blueprint, jsonify, request

from config import (
    BRAVE_SEARCH_API_KEY,
    MAX_WEB_SCRAPE_CHARS,
    MAX_WEB_SCRAPE_CHARS_CAP,
    MODEL_NAME,
    OLLAMA_HOST,
    OLLAMA_TIMEOUT_TOOLS,
    SEARCH_SUMMARIZE_CHARS_PER_SOURCE,
    SEARCH_SUMMARIZE_MAX_SOURCES,
    WEB_FETCH_TIMEOUT,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_TIMEOUT,
    http_session,
    logger,
)
from middleware import rate_limit
from routes.shared import (
    FuturesTimeoutError,
    MAX_DOCUMENT_SIZE,
    _document_store_lock,
    _io_executor,
    cleanup_document_store,
    document_store,
)
from services import check_ollama_connection
from validation import is_safe_url

tools_bp = Blueprint("tools", __name__)


def call_ollama_for_tools(prompt, temperature=0.3):
    """Helper function to call Ollama API for tools."""
    try:
        response = http_session.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            },
            timeout=OLLAMA_TIMEOUT_TOOLS,
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        raise


@tools_bp.route("/tools/search", methods=["POST"])
@rate_limit
def web_search():
    """Search the web using Brave Search API."""
    try:
        if not BRAVE_SEARCH_API_KEY:
            return jsonify({"error": "Web search not configured. Set BRAVE_SEARCH_API_KEY environment variable.", "results": []}), 503

        data = request.json or {}
        query = data.get("query", "").strip()
        count = min(int(data.get("count", 5)), WEB_SEARCH_MAX_RESULTS)

        if not query:
            return jsonify({"error": "No search query provided", "results": []}), 400

        response = http_session.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_SEARCH_API_KEY},
            params={"q": query, "count": count, "safesearch": "moderate"},
            timeout=WEB_SEARCH_TIMEOUT,
        )

        if response.status_code != 200:
            logger.error(f"Brave Search API error: {response.status_code}")
            return jsonify({"error": f"Search API returned status {response.status_code}", "results": []}), 502

        search_data = response.json()
        web_results = search_data.get("web", {}).get("results", [])

        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
            for r in web_results[:count]
        ]

        logger.info(f"🔍 Web search: '{query}' returned {len(results)} results")
        return jsonify({"query": query, "results": results})

    except requests_lib.Timeout:
        return jsonify({"error": "Search request timed out", "results": []}), 504
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return jsonify({"error": str(e), "results": []}), 500


@tools_bp.route("/tools/browse", methods=["POST"])
@rate_limit
def browse_url():
    """Fetch and extract text content from a URL (non-blocking via ThreadPoolExecutor)."""
    try:
        data = request.json or {}
        url = data.get("url", "").strip()
        max_length = min(int(data.get("max_length", MAX_WEB_SCRAPE_CHARS)), MAX_WEB_SCRAPE_CHARS_CAP)

        if not url:
            return jsonify({"error": "No URL provided"}), 400

        if not url.startswith(("http://", "https://")):
            return jsonify({"error": "URL must start with http:// or https://"}), 400

        is_safe, error_msg = is_safe_url(url)
        if not is_safe:
            logger.warning(f"🚨 SSRF blocked: {url} - {error_msg}")
            return jsonify({"error": error_msg, "url": url}), 403

        def _fetch_and_parse(target_url, target_max_length):
            resp = http_session.get(
                target_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; TrinityBot/1.0; +https://dubya.ai)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                timeout=WEB_FETCH_TIMEOUT,
                allow_redirects=True,
            )

            if resp.status_code != 200:
                return {"error": f"Failed to fetch URL: status {resp.status_code}", "url": target_url, "status": resp.status_code}

            content_type = resp.headers.get("Content-Type", "")

            if "application/json" in content_type:
                try:
                    json_content = resp.json()
                    content = json.dumps(json_content, indent=2)[:target_max_length]
                    return {"url": target_url, "title": "JSON Response", "content": content, "content_type": "application/json"}
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            for element in soup(["script", "style", "head", "meta", "link", "noscript", "iframe"]):
                element.decompose()
            clean = soup.get_text(separator=" ", strip=True)
            clean = re.sub(r"\s+", " ", clean).strip()[:target_max_length]
            return {"url": target_url, "title": title, "content": clean, "content_type": "text/html"}

        future = _io_executor.submit(_fetch_and_parse, url, max_length)
        try:
            result = future.result(timeout=20)
        except FuturesTimeoutError:
            future.cancel()
            return jsonify({"error": "Request timed out", "url": url}), 504

        if "error" in result and "content" not in result:
            status = result.pop("status", 502)
            return jsonify(result), status

        logger.info(f"🌐 Browsed URL: {url} - {len(result.get('content', ''))} chars extracted")
        return jsonify(result)

    except requests_lib.Timeout:
        return jsonify({"error": "Request timed out", "url": url}), 504
    except Exception as e:
        logger.error(f"Browse error: {e}")
        return jsonify({"error": str(e), "url": url}), 500


@tools_bp.route("/tools/search-and-summarize", methods=["POST"])
@rate_limit
def search_and_summarize():
    """Combined: Search web, fetch top results, and return context for LLM."""
    try:
        if not BRAVE_SEARCH_API_KEY:
            return jsonify({"error": "Web search not configured", "context": "", "sources": []}), 503

        data = request.json or {}
        query = data.get("query", "").strip()
        num_results = min(int(data.get("num_results", 3)), SEARCH_SUMMARIZE_MAX_SOURCES)

        if not query:
            return jsonify({"error": "No search query provided"}), 400

        search_response = http_session.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_SEARCH_API_KEY},
            params={"q": query, "count": num_results + 2, "safesearch": "moderate"},
            timeout=WEB_SEARCH_TIMEOUT,
        )

        if search_response.status_code != 200:
            return jsonify({"error": "Search failed", "context": "", "sources": []}), 502

        search_data = search_response.json()
        web_results = search_data.get("web", {}).get("results", [])[:num_results]

        from bs4 import BeautifulSoup
        sources = []
        context_parts = [f"Web search results for: {query}\n"]

        for i, result in enumerate(web_results, 1):
            title = result.get("title", "Untitled")
            url = result.get("url", "")
            snippet = result.get("description", "")
            sources.append({"title": title, "url": url})

            try:
                page_response = http_session.get(
                    url, headers={"User-Agent": "Mozilla/5.0 (compatible; TrinityBot/1.0)"}, timeout=8, allow_redirects=True,
                )
                if page_response.status_code == 200:
                    soup = BeautifulSoup(page_response.text, "html.parser")
                    for element in soup(["script", "style", "head", "meta", "noscript"]):
                        element.decompose()
                    clean = soup.get_text(separator=" ", strip=True)
                    clean = re.sub(r"\s+", " ", clean).strip()[:SEARCH_SUMMARIZE_CHARS_PER_SOURCE]
                    context_parts.append(f"\n[Source {i}: {title}]\n{clean}\n")
                else:
                    context_parts.append(f"\n[Source {i}: {title}]\n{snippet}\n")
            except (requests_lib.RequestException, ValueError, AttributeError) as e:
                logger.debug(f"Failed to fetch source {i}: {e}")
                context_parts.append(f"\n[Source {i}: {title}]\n{snippet}\n")

        context = "\n".join(context_parts)
        logger.info(f"🔍 Search+summarize: '{query}' - {len(sources)} sources, {len(context)} chars")
        return jsonify({"query": query, "context": context, "sources": sources})

    except Exception as e:
        logger.error(f"Search and summarize error: {e}")
        return jsonify({"error": str(e), "context": "", "sources": []}), 500


@tools_bp.route("/tools/documents/upload", methods=["POST"])
@rate_limit
def upload_document():
    """Upload a document for querying."""
    try:
        data = request.json
        content = data.get("content", "")
        filename = data.get("filename", "uploaded_document.txt")
        session_id = data.get("sessionId", str(time.time()))

        if not content:
            return jsonify({"error": "No content provided"}), 400

        if len(content) > MAX_DOCUMENT_SIZE:
            return jsonify({
                "error": f"Document too large (max {MAX_DOCUMENT_SIZE // 1_000_000}MB)",
                "received": len(content),
                "max_allowed": MAX_DOCUMENT_SIZE,
            }), 413

        cleanup_document_store()

        with _document_store_lock:
            document_store[session_id] = {
                "content": content,
                "filename": filename,
                "uploaded_at": datetime.now(tz=None).isoformat(),
                "uploaded_at_ts": time.time(),
            }

        logger.info(f"📄 Document uploaded: {filename} ({len(content)} chars)")
        return jsonify({"success": True, "sessionId": session_id, "filename": filename, "documentLength": len(content)})

    except Exception as e:
        logger.error(f"❌ Document upload error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@tools_bp.route("/tools/documents/query", methods=["POST"])
def query_document():
    """Query an uploaded document using Ollama."""
    try:
        data = request.json
        session_id = data.get("sessionId", "")
        query = data.get("query", "")

        if not query:
            return jsonify({"error": "No query provided"}), 400

        with _document_store_lock:
            if not session_id or session_id not in document_store:
                return jsonify({"error": "No document found. Please upload first."}), 400
            doc = document_store[session_id].copy()

        doc_content = doc["content"][:30000]
        prompt = f"""You are a helpful document analysis assistant.
Answer based ONLY on this document. If not found, say so.

=== DOCUMENT ({doc['filename']}) ===
{doc_content}
=== END DOCUMENT ===

Question: {query}
Answer:"""

        answer = call_ollama_for_tools(prompt, temperature=0.3)
        logger.info(f'📄 Document query: "{query[:50]}..."')
        return jsonify({"answer": answer, "documentUsed": doc["filename"], "model": MODEL_NAME})

    except Exception as e:
        logger.error(f"❌ Document query error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@tools_bp.route("/tools/transcript/clean", methods=["POST"])
def clean_transcript():
    """Clean and polish a transcript."""
    try:
        data = request.json
        raw_text = data.get("text", "")

        if not raw_text:
            return jsonify({"error": "No text provided"}), 400

        prompt = f"""You are a professional transcript editor. Clean this transcript:
1. Fix grammar, spelling, punctuation
2. Remove filler words (um, uh, like) unless meaningful
3. Fix run-on sentences
4. Preserve speaker labels if present
5. Maintain original meaning and tone

Return ONLY the cleaned transcript.

=== RAW TRANSCRIPT ===
{raw_text}
=== END ===

Cleaned transcript:"""

        cleaned = call_ollama_for_tools(prompt, temperature=0.3)
        logger.info(f"🎙️ Transcript cleaned: {len(raw_text)} -> {len(cleaned)} chars")
        return jsonify({"cleanedText": cleaned, "originalLength": len(raw_text), "cleanedLength": len(cleaned), "model": MODEL_NAME})

    except Exception as e:
        logger.error(f"❌ Transcript error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@tools_bp.route("/tools/status")
def tools_status():
    """Check status of all AI tools."""
    ollama_ok = check_ollama_connection()
    return jsonify({
        "ollama_connected": ollama_ok,
        "model": MODEL_NAME,
        "tools": {
            "chatWithDocuments": {"available": ollama_ok},
            "transcriptCleaner": {"available": ollama_ok},
        },
        "activeDocumentSessions": len(document_store),
    })
