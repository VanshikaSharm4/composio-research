"""Researcher Agent for the Composio App Research Pipeline.

Researches individual apps using Composio+Apify for web scraping and
Google Gemini for intelligent content analysis.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from composio_research.app_list import AppInput
from composio_research.models import (
    AccessModel,
    ApiCoverage,
    ApiSurface,
    ApiType,
    AppRecord,
    AuthMethod,
    BlockerCategory,
    BuildabilityVerdict,
    InterventionEntry,
    ResearchStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class ResearchConfig:
    """Configuration for the researcher agent."""

    max_retries: int = 3
    timeout_seconds: int = 120
    concurrency_limit: int = 2
    composio_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"


_RETRY_DELAYS: list[float] = [0.0, 5.0, 10.0]


class ResearcherAgent:
    """Researches apps using Composio+Apify scraping and Gemini LLM analysis.
    
    Strategy: Use Apify RAG Web Browser with a targeted search query like
    "{app_name} API documentation authentication REST" to find the most 
    relevant developer docs page, then analyze with Gemini.
    """

    def __init__(self, composio_client: Any, config: ResearchConfig) -> None:
        self._config = config
        self._composio_instance = None
        self._gemini_client = None
        self._interventions: list[InterventionEntry] = []

    @property
    def interventions(self) -> list[InterventionEntry]:
        return list(self._interventions)

    def _get_composio(self):
        if self._composio_instance is None:
            from composio_research.scraper import create_composio_instance
            self._composio_instance = create_composio_instance(self._config.composio_api_key)
        return self._composio_instance

    def _get_gemini(self):
        if self._gemini_client is None:
            from composio_research.llm import create_gemini_client
            self._gemini_client = create_gemini_client(self._config.gemini_api_key)
        return self._gemini_client

    async def research_app(self, app_name: str, category: str) -> AppRecord:
        """Research a single app using scraping + LLM analysis."""
        from composio_research.scraper import scrape_url
        from composio_research.llm import analyze_app_documentation

        composio = self._get_composio()
        if composio is None:
            return self._make_failed_record(
                app_name, category, "Composio SDK not available", "agent_error"
            )

        gemini = self._get_gemini()
        if gemini is None:
            return self._make_failed_record(
                app_name, category, "Gemini client not available", "agent_error"
            )

        evidence_urls: dict[str, str] = {}

        # Strategy: scrape the app's official API docs URL directly
        # The Apify RAG browser handles finding the right page from a URL/query
        search_query = f"https://{app_name.split()[0].lower()}.com/docs/api"
        
        # Try the direct developer docs URL first
        content = ""
        doc_url = ""

        # Attempt 1: Direct developer URL
        try:
            result = await asyncio.to_thread(
                scrape_url, 
                f"https://developer.{app_name.split()[0].lower()}.com",
                composio_instance=composio,
            )
            if result.get("content") and len(result["content"]) > 200:
                content = result["content"]
                doc_url = result.get("url", "")
        except Exception as e:
            logger.debug(f"Direct developer URL failed for {app_name}: {e}")

        # Attempt 2: Try {app}/docs/api pattern
        if not content:
            try:
                result = await asyncio.to_thread(
                    scrape_url,
                    f"https://{app_name.split()[0].lower()}.com/docs/api",
                    composio_instance=composio,
                )
                if result.get("content") and len(result["content"]) > 200:
                    content = result["content"]
                    doc_url = result.get("url", "")
            except Exception as e:
                logger.debug(f"Docs/api URL failed for {app_name}: {e}")

        # Attempt 3: Search query via Apify (most reliable)
        if not content:
            try:
                from composio_research.scraper import search_and_scrape
                query = f"{app_name} API documentation developer authentication REST endpoints"
                result = await asyncio.to_thread(
                    search_and_scrape, query, composio_instance=composio,
                )
                if result.get("content") and len(result["content"]) > 200:
                    content = result["content"]
                    doc_url = result.get("url", "")
            except Exception as e:
                logger.debug(f"Search scrape failed for {app_name}: {e}")

        if doc_url:
            evidence_urls["docs_url"] = doc_url

        # If no content at all, mark as failed
        if not content or len(content) < 50:
            return self._make_failed_record(
                app_name, category,
                f"Could not find documentation for {app_name}",
                "network_error",
            )

        logger.info(f"Scraped {app_name}: {len(content)} chars from {doc_url}")

        # Analyze with Gemini
        try:
            analysis = await asyncio.to_thread(
                analyze_app_documentation,
                app_name, category, content,
                gemini_client=gemini,
                model=self._config.gemini_model,
            )
        except Exception as e:
            logger.error(f"LLM analysis failed for {app_name}: {e}")
            return self._make_failed_record(
                app_name, category, f"LLM analysis failed: {e}", "agent_error"
            )

        # Build AppRecord from analysis
        auth_methods = [AuthMethod(m) for m in analysis["auth_methods"]]
        access_model = AccessModel(analysis["access_model"])

        api_type_val = analysis["api_type"]
        has_public_api = api_type_val != "none"
        api_type = ApiType(api_type_val) if has_public_api else None
        coverage = ApiCoverage(analysis["api_coverage"]) if has_public_api else None

        api_surface = ApiSurface(
            has_public_api=has_public_api,
            api_type=api_type,
            coverage=coverage,
            has_mcp_support=analysis["has_mcp_support"],
            evidence_url=doc_url or None,
        )

        verdict = BuildabilityVerdict(analysis["buildability_verdict"])
        blocker = BlockerCategory(analysis["primary_blocker"]) if analysis["primary_blocker"] else None

        return AppRecord(
            app_name=app_name,
            category=category,
            description=analysis["description"][:120],
            auth_methods=auth_methods,
            access_model=access_model,
            api_surface=api_surface,
            buildability_verdict=verdict,
            primary_blocker=blocker,
            evidence_urls=evidence_urls,
            research_status=ResearchStatus.COMPLETE,
            missing_fields=[],
            failure_reason=None,
            failure_category=None,
        )

    async def research_batch(self, apps: list[AppInput]) -> list[AppRecord]:
        """Research all apps with concurrency control. Never raises."""
        semaphore = asyncio.Semaphore(self._config.concurrency_limit)

        async def _research_one(app: AppInput) -> AppRecord:
            async with semaphore:
                return await self._safe_research(app)

        tasks = [_research_one(app) for app in apps]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _safe_research(self, app: AppInput) -> AppRecord:
        """Research with retry logic. Never raises."""
        last_error: Optional[Exception] = None

        for attempt in range(self._config.max_retries):
            delay = _RETRY_DELAYS[attempt] if attempt < len(_RETRY_DELAYS) else 10.0
            if delay > 0:
                await asyncio.sleep(delay)

            try:
                record = await asyncio.wait_for(
                    self.research_app(app.app_name, app.category),
                    timeout=float(self._config.timeout_seconds),
                )
                # If we got a complete record, return immediately
                if record.research_status == ResearchStatus.COMPLETE:
                    return record
                # If failed, try again
                if record.research_status == ResearchStatus.FAILED and attempt < self._config.max_retries - 1:
                    last_error = RuntimeError(record.failure_reason or "Unknown")
                    continue
                return record
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(f"Attempt {attempt+1} timed out for {app.app_name}")
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt+1} failed for {app.app_name}: {e}")

        # All retries exhausted
        error_msg = str(last_error) if last_error else "Unknown error"
        self._interventions.append(
            InterventionEntry(
                app_name=app.app_name,
                pipeline_stage="researcher",
                reason=f"Failed after {self._config.max_retries} retries: {error_msg[:200]}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                data_point=None,
            )
        )
        return self._make_failed_record(
            app.app_name, app.category, error_msg[:500], self._categorize_error(last_error)
        )

    def _make_failed_record(self, app_name: str, category: str, reason: str, failure_cat: str) -> AppRecord:
        return AppRecord(
            app_name=app_name,
            category=category,
            description=f"{app_name} - research failed",
            auth_methods=[AuthMethod.OTHER],
            access_model=AccessModel.GATED,
            api_surface=ApiSurface(
                has_public_api=False, api_type=None, coverage=None,
                has_mcp_support=False, evidence_url=None,
            ),
            buildability_verdict=BuildabilityVerdict.BLOCKED,
            primary_blocker=BlockerCategory.MISSING_DOCUMENTATION,
            evidence_urls={},
            research_status=ResearchStatus.FAILED,
            missing_fields=["auth_methods", "access_model", "api_surface"],
            failure_reason=reason,
            failure_category=failure_cat,
        )

    @staticmethod
    def _categorize_error(error: Optional[Exception]) -> str:
        if error is None:
            return "agent_error"
        if isinstance(error, asyncio.TimeoutError):
            return "timeout"
        err_str = str(error).lower()
        if "network" in err_str or "connection" in err_str:
            return "network_error"
        if "access" in err_str or "401" in err_str or "403" in err_str:
            return "access_restriction"
        if "json" in err_str or "parse" in err_str:
            return "parsing_failure"
        return "agent_error"

    async def close(self) -> None:
        pass
