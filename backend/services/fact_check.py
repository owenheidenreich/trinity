"""
Trinity Fact Check Service

Verifies claims by searching for supporting and contradicting evidence.
Uses the existing web search infrastructure (Brave Search API).
"""

import logging

from .search import SearchResponse, format_search_context, search_web

logger = logging.getLogger(__name__)


def fact_check(claim: str) -> str:
    """
    Verify a claim by searching for evidence.

    Performs two searches: one for the claim directly, one questioning it.
    Returns formatted evidence for the agent to evaluate.

    Args:
        claim: The claim to verify

    Returns:
        Formatted evidence string
    """
    if not claim.strip():
        return "No claim provided to verify."

    # Search for supporting evidence
    supporting = search_web(claim, count=3, timeout=10)

    # Search for contradicting / verification evidence
    verification = search_web(f"is it true that {claim}", count=3, timeout=10)

    return format_fact_check(claim, supporting, verification)


def format_fact_check(
    claim: str,
    supporting: SearchResponse,
    verification: SearchResponse,
) -> str:
    """Format fact check results as readable evidence."""
    lines = [f"Fact check for: \"{claim}\"", ""]

    # Supporting evidence
    lines.append("**Evidence found:**")
    if supporting.results:
        for i, r in enumerate(supporting.results, 1):
            lines.append(f"{i}. {r.title}")
            lines.append(f"   {r.snippet}")
            lines.append(f"   Source: {r.url}")
            lines.append("")
    elif supporting.error:
        lines.append(f"  Search error: {supporting.error}")
        lines.append("")
    else:
        lines.append("  No results found.")
        lines.append("")

    # Verification evidence
    lines.append("**Verification search:**")
    if verification.results:
        for i, r in enumerate(verification.results, 1):
            lines.append(f"{i}. {r.title}")
            lines.append(f"   {r.snippet}")
            lines.append(f"   Source: {r.url}")
            lines.append("")
    elif verification.error:
        lines.append(f"  Search error: {verification.error}")
        lines.append("")
    else:
        lines.append("  No results found.")
        lines.append("")

    lines.append("Based on this evidence, assess whether the claim is supported, contradicted, or uncertain.")

    return "\n".join(lines)
