"""LLM integration module using Google Gemini for intelligent content analysis.

Analyzes scraped documentation content to extract structured app research data
including authentication methods, API surface, access model, buildability verdict,
and concise descriptions.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash"

EXTRACTION_PROMPT = """You are an expert API analyst. Given the following documentation content for the app "{app_name}" in the "{category}" category, extract the following structured information.

DOCUMENTATION CONTENT:
---
{content}
---

Analyze the above and respond with ONLY a valid JSON object (no markdown fences, no explanation) with these exact keys:

{{
  "description": "A concise 1-sentence description of what this app does (max 120 characters)",
  "auth_methods": ["list of auth methods used. Valid values: oauth2, api_key, basic, token, other"],
  "access_model": "self_serve or gated (self_serve = free tier/trial/developer account available; gated = paid plan/contact sales/partner required)",
  "api_type": "rest, graphql, both, or none",
  "api_coverage": "full (comprehensive docs, many endpoints), partial (some endpoints documented), or minimal (very limited)",
  "has_mcp_support": false,
  "buildability_verdict": "ready (public API + good coverage + self-serve), feasible (has API but some barrier), or blocked (no usable API)",
  "primary_blocker": "no_public_api, insufficient_coverage, restrictive_auth, rate_limits, missing_documentation, or null if verdict is ready",
  "evidence_summary": "Brief 1-sentence explanation of your verdict"
}}

Rules:
- Only include auth methods you can CONFIRM from the documentation
- If you cannot determine something, use conservative defaults (gated, other, minimal)
- Never fabricate information not present in the documentation
- has_mcp_support should be true ONLY if MCP/Model Context Protocol is explicitly mentioned
- For buildability: ready = all green flags, feasible = has API but barriers, blocked = no viable path"""


def create_gemini_client(api_key: Optional[str] = None):
    """Create a Gemini client instance.

    Args:
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.

    Returns:
        google.genai.Client instance, or None if unavailable.
    """
    try:
        from google import genai

        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            logger.warning("No GEMINI_API_KEY found.")
            return None

        return genai.Client(api_key=key)
    except ImportError:
        logger.warning("google-genai package not installed.")
        return None


def analyze_app_documentation(
    app_name: str,
    category: str,
    content: str,
    gemini_client=None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Use Gemini to analyze scraped documentation and extract structured data.

    Args:
        app_name: Name of the app being researched.
        category: Category the app belongs to.
        content: Markdown content of the scraped documentation.
        gemini_client: Pre-created Gemini client (creates one if None).
        model: Gemini model to use.

    Returns:
        Dict with extracted fields (description, auth_methods, access_model, etc.).

    Raises:
        RuntimeError: If LLM call fails or returns unparseable response.
    """
    if gemini_client is None:
        gemini_client = create_gemini_client()
        if gemini_client is None:
            raise RuntimeError("Cannot create Gemini client. Check API key.")

    # Truncate content to avoid token limits (keep first ~15k chars)
    truncated_content = content[:15000] if len(content) > 15000 else content

    prompt = EXTRACTION_PROMPT.format(
        app_name=app_name,
        category=category,
        content=truncated_content,
    )

    try:
        response = gemini_client.models.generate_content(
            model=model,
            contents=prompt,
        )
        raw_text = response.text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines).strip()

        parsed = json.loads(raw_text)
        return _validate_extraction(parsed, app_name)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response for {app_name}: {e}")
        logger.debug(f"Raw response: {raw_text[:500]}")
        raise RuntimeError(f"Gemini returned invalid JSON for {app_name}: {e}")
    except Exception as e:
        logger.error(f"Gemini API call failed for {app_name}: {e}")
        raise RuntimeError(f"Gemini API error for {app_name}: {e}")


def _validate_extraction(data: dict, app_name: str) -> dict:
    """Validate and normalize the LLM extraction output.

    Ensures all expected fields are present with valid values.
    """
    valid_auth = {"oauth2", "api_key", "basic", "token", "other"}
    valid_access = {"self_serve", "gated"}
    valid_api_type = {"rest", "graphql", "both", "none"}
    valid_coverage = {"full", "partial", "minimal"}
    valid_verdict = {"ready", "feasible", "blocked"}
    valid_blockers = {
        "no_public_api", "insufficient_coverage", "restrictive_auth",
        "rate_limits", "missing_documentation", None,
    }

    # Normalize auth_methods
    auth = data.get("auth_methods", ["other"])
    if isinstance(auth, str):
        auth = [auth]
    auth = [a for a in auth if a in valid_auth] or ["other"]

    # Normalize other fields
    access = data.get("access_model", "gated")
    if access not in valid_access:
        access = "gated"

    api_type = data.get("api_type", "none")
    if api_type not in valid_api_type:
        api_type = "none"

    coverage = data.get("api_coverage", "minimal")
    if coverage not in valid_coverage:
        coverage = "minimal"

    verdict = data.get("buildability_verdict", "blocked")
    if verdict not in valid_verdict:
        verdict = "blocked"

    blocker = data.get("primary_blocker")
    if blocker not in valid_blockers:
        blocker = "missing_documentation" if verdict != "ready" else None

    # Ensure blocker is present when not ready
    if verdict != "ready" and blocker is None:
        blocker = "missing_documentation"

    description = data.get("description", f"{app_name} - API research pending")
    if len(description) > 120:
        description = description[:117] + "..."

    return {
        "description": description,
        "auth_methods": auth,
        "access_model": access,
        "api_type": api_type,
        "api_coverage": coverage,
        "has_mcp_support": bool(data.get("has_mcp_support", False)),
        "buildability_verdict": verdict,
        "primary_blocker": blocker,
        "evidence_summary": data.get("evidence_summary", ""),
    }
