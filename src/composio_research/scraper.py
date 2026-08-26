"""Web scraping module using Composio + Apify RAG Web Browser.

Provides a reusable scraper that fetches documentation pages as markdown
via the Composio SDK's Apify integration.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env for API keys
load_dotenv()

# Defaults from the working scraper pattern
DEFAULT_USER_ID = "research-agent"
DEFAULT_CONNECTED_ACCOUNT_ID = "ca_LaDPL7VQZ5DK"
DEFAULT_TOOLKIT_VERSION = "20260707_00"


def create_composio_instance(api_key: Optional[str] = None):
    """Create a Composio SDK instance."""
    try:
        from composio import Composio

        key = api_key or os.getenv("COMPOSIO_API_KEY")
        if not key:
            logger.warning("No COMPOSIO_API_KEY found.")
            return None

        return Composio(
            api_key=key,
            toolkit_versions={"apify": DEFAULT_TOOLKIT_VERSION},
        )
    except ImportError:
        logger.warning("composio package not installed.")
        return None


def scrape_url(
    url: str,
    composio_instance=None,
    user_id: str = DEFAULT_USER_ID,
    connected_account_id: str = DEFAULT_CONNECTED_ACCOUNT_ID,
) -> dict:
    """Scrape a URL and return structured content via Composio + Apify."""
    if composio_instance is None:
        composio_instance = create_composio_instance()
        if composio_instance is None:
            raise RuntimeError("Cannot create Composio instance. Check API key.")

    result = composio_instance.tools.execute(
        "APIFY_RUN_ACTOR_SYNC_GET_DATASET_ITEMS",
        arguments={
            "actorId": "apify/rag-web-browser",
            "input": {
                "query": url,
                "maxResults": 1,
                "outputFormats": ["markdown"],
            },
            "waitForFinish": 60,
            "limit": 1,
            "format": "json",
        },
        connected_account_id=connected_account_id,
        user_id=user_id,
        version=DEFAULT_TOOLKIT_VERSION,
    )

    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected result type: {type(result)}")

    if not result.get("successful"):
        raise RuntimeError(result.get("error", "Apify request failed"))

    data = result.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected data type: {type(data)}")

    items = data.get("items", [])
    if not items:
        raise RuntimeError(f"Apify returned no items for URL: {url}")

    item = items[0]
    metadata = item.get("metadata", {})

    return {
        "title": metadata.get("title", ""),
        "url": metadata.get("url") or metadata.get("canonicalUrl") or item.get("url", url),
        "description": metadata.get("description", ""),
        "content": item.get("markdown", "") or item.get("text", ""),
    }


def search_and_scrape(
    query: str,
    composio_instance=None,
    user_id: str = DEFAULT_USER_ID,
    connected_account_id: str = DEFAULT_CONNECTED_ACCOUNT_ID,
) -> dict:
    """Search for a query and scrape the top result via Composio + Apify."""
    if composio_instance is None:
        composio_instance = create_composio_instance()
        if composio_instance is None:
            raise RuntimeError("Cannot create Composio instance. Check API key.")

    result = composio_instance.tools.execute(
        "APIFY_RUN_ACTOR_SYNC_GET_DATASET_ITEMS",
        arguments={
            "actorId": "apify/rag-web-browser",
            "input": {
                "query": query,
                "maxResults": 1,
                "outputFormats": ["markdown"],
            },
            "waitForFinish": 60,
            "limit": 1,
            "format": "json",
        },
        connected_account_id=connected_account_id,
        user_id=user_id,
        version=DEFAULT_TOOLKIT_VERSION,
    )

    if not isinstance(result, dict) or not result.get("successful"):
        error = result.get("error", "Search failed") if isinstance(result, dict) else "Unexpected response"
        raise RuntimeError(error)

    data = result.get("data", {})
    items = data.get("items", [])

    if not items:
        return {"title": "", "url": "", "description": "", "content": ""}

    item = items[0]
    metadata = item.get("metadata", {})

    return {
        "title": metadata.get("title", ""),
        "url": metadata.get("url") or metadata.get("canonicalUrl") or item.get("url", ""),
        "description": metadata.get("description", ""),
        "content": item.get("markdown", "") or item.get("text", ""),
    }
