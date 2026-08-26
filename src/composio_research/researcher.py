"""Researcher Agent for the Composio App Research Pipeline.

Researches individual apps using Composio SDK tools for web search and scraping.
Collects authentication methods, API surface assessments, access model
determinations, and buildability verdicts. Handles retries with exponential
backoff and graceful failure marking.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

import httpx

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

T = TypeVar("T")


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class ResearchConfig:
    """Configuration for the researcher agent.

    Attributes:
        max_retries: Maximum retry attempts for external requests.
        timeout_seconds: Timeout for individual HTTP requests.
        concurrency_limit: Maximum concurrent research operations.
        composio_api_key: API key for Composio SDK access.
    """

    max_retries: int = 3
    timeout_seconds: int = 30
    concurrency_limit: int = 5
    composio_api_key: Optional[str] = None


# ============================================================================
# Constants
# ============================================================================

# Retry delays in seconds for exponential backoff
_RETRY_DELAYS: list[float] = [0.0, 2.0, 4.0]

# Keywords indicating different auth methods
_OAUTH2_KEYWORDS: list[str] = [
    "oauth2", "oauth 2", "oauth2.0", "authorization_code",
    "client_credentials", "access_token", "refresh_token",
    "authorize endpoint", "/oauth/", "oauth flow",
]
_API_KEY_KEYWORDS: list[str] = [
    "api key", "api_key", "apikey", "x-api-key",
    "api-key", "api token", "secret key",
]
_BASIC_AUTH_KEYWORDS: list[str] = [
    "basic auth", "basic authentication", "http basic",
    "username and password", "username/password",
]
_TOKEN_KEYWORDS: list[str] = [
    "bearer token", "personal access token", "pat",
    "jwt", "json web token", "auth token",
    "bearer", "authorization: bearer",
]

# Keywords for API type detection
_REST_KEYWORDS: list[str] = [
    "rest api", "restful", "rest endpoint",
    "/api/v", "api/v1", "api/v2",
    "get /", "post /", "put /", "delete /", "patch /",
    "http methods", "endpoints",
]
_GRAPHQL_KEYWORDS: list[str] = [
    "graphql", "graph ql", "graphiql", "apollo",
    "query {", "mutation {", "subscription {",
    "/graphql", "schema.graphql",
]

# Keywords for MCP support detection
_MCP_KEYWORDS: list[str] = [
    "mcp", "model context protocol", "mcp server",
    "mcp tool", "composio", "agent toolkit",
]

# Keywords for access model detection
_SELF_SERVE_KEYWORDS: list[str] = [
    "free tier", "free plan", "free trial", "sign up free",
    "get started free", "developer account", "sandbox",
    "free api", "no credit card", "try for free",
    "open api", "public api", "free access",
    "developer portal", "api playground",
]
_GATED_KEYWORDS: list[str] = [
    "contact sales", "enterprise only", "paid plan",
    "request access", "invite only", "partner program",
    "custom pricing", "talk to sales", "schedule demo",
    "apply for access", "waitlist", "approval required",
]

# Required fields for completeness checking
_REQUIRED_FIELDS: list[str] = [
    "description",
    "auth_methods",
    "access_model",
    "api_surface",
    "buildability_verdict",
]


# ============================================================================
# ResearcherAgent
# ============================================================================


class ResearcherAgent:
    """Researches individual apps using Composio SDK tools.

    Uses web search and scraping via the Composio SDK client to collect
    structured data about each app's authentication methods, API surface,
    access model, and buildability as an agent toolkit.
    """

    def __init__(self, composio_client: Any, config: ResearchConfig) -> None:
        """Initialize with Composio SDK client and research configuration.

        Args:
            composio_client: Composio SDK client providing search() and scrape() methods.
                Typed as Any to avoid hard dependency on composio-core.
            config: Research configuration with retry and concurrency settings.
        """
        self._client = composio_client
        self._config = config
        self._http_client: Optional[httpx.AsyncClient] = None
        self._interventions: list[InterventionEntry] = []

    @property
    def interventions(self) -> list[InterventionEntry]:
        """Return accumulated intervention entries from research operations."""
        return list(self._interventions)

    async def research_app(self, app_name: str, category: str) -> AppRecord:
        """Research a single app and return structured record.

        Searches for the app's API documentation, then collects auth method,
        API surface, and access model information. Synthesizes findings into
        a buildability verdict.

        Args:
            app_name: Display name of the application.
            category: Category the app belongs to.

        Returns:
            AppRecord with research results. Status will be COMPLETE, PARTIAL,
            or FAILED depending on how much data could be collected.
        """
        evidence_urls: dict[str, str] = {}
        missing_fields: list[str] = []

        # Step 1: Find API documentation URL
        docs_url: Optional[str] = None
        try:
            docs_url = await self._find_docs_url(app_name)
            if docs_url:
                evidence_urls["docs_url"] = docs_url
        except Exception as e:
            logger.warning(f"Failed to find docs URL for {app_name}: {e}")

        # Step 2: Collect auth methods
        auth_methods: Optional[list[AuthMethod]] = None
        try:
            auth_methods = await self._collect_auth_method(app_name, docs_url or "")
            if auth_methods and docs_url:
                evidence_urls["auth_methods"] = docs_url
        except Exception as e:
            logger.warning(f"Failed to collect auth methods for {app_name}: {e}")

        if not auth_methods:
            missing_fields.append("auth_methods")

        # Step 3: Assess API surface
        api_surface: Optional[ApiSurface] = None
        try:
            api_surface = await self._assess_api_surface(app_name, docs_url or "")
            if api_surface and api_surface.evidence_url:
                evidence_urls["api_surface"] = api_surface.evidence_url
        except Exception as e:
            logger.warning(f"Failed to assess API surface for {app_name}: {e}")

        if not api_surface:
            missing_fields.append("api_surface")

        # Step 4: Assess access model
        access_model: Optional[AccessModel] = None
        try:
            access_model = await self._assess_access_model(app_name, docs_url or "")
            if access_model and docs_url:
                evidence_urls["access_model"] = docs_url
        except Exception as e:
            logger.warning(f"Failed to assess access model for {app_name}: {e}")

        if not access_model:
            missing_fields.append("access_model")

        # Step 5: Generate description
        description = await self._generate_description(app_name, category)

        # Step 6: Determine buildability
        final_auth = auth_methods or [AuthMethod.OTHER]
        final_api_surface = api_surface or ApiSurface(
            has_public_api=False,
            api_type=None,
            coverage=None,
            has_mcp_support=False,
            evidence_url=None,
        )
        final_access = access_model or AccessModel.GATED

        verdict, blocker = self._determine_buildability(
            final_auth, final_api_surface, final_access
        )

        # Determine research status
        if not missing_fields:
            research_status = ResearchStatus.COMPLETE
        elif len(missing_fields) <= len(_REQUIRED_FIELDS) * 0.2:
            # 80%+ fields populated → PARTIAL but acceptable
            research_status = ResearchStatus.PARTIAL
        else:
            research_status = ResearchStatus.PARTIAL

        return AppRecord(
            app_name=app_name,
            category=category,
            description=description[:120],
            auth_methods=final_auth,
            access_model=final_access,
            api_surface=final_api_surface,
            buildability_verdict=verdict,
            primary_blocker=blocker,
            evidence_urls=evidence_urls,
            research_status=research_status,
            missing_fields=missing_fields,
            failure_reason=None,
            failure_category=None,
        )

    async def research_batch(self, apps: list[AppInput]) -> list[AppRecord]:
        """Research all apps with concurrency control and graceful failure handling.

        Uses an asyncio Semaphore to limit concurrent research operations.
        Never raises—always returns an AppRecord for each app input.

        Args:
            apps: List of AppInput specifications to research.

        Returns:
            List of AppRecord results (one per input app, same order).
        """
        semaphore = asyncio.Semaphore(self._config.concurrency_limit)
        results: list[AppRecord] = []

        async def _research_with_semaphore(app: AppInput) -> AppRecord:
            async with semaphore:
                return await self._safe_research(app)

        tasks = [_research_with_semaphore(app) for app in apps]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _safe_research(self, app: AppInput) -> AppRecord:
        """Research a single app with full error handling.

        Wraps research_app with retry logic and failure marking.
        Never raises—always returns an AppRecord.
        """
        try:
            record = await self._with_retry(
                lambda: self.research_app(app.app_name, app.category),
                operation_name=f"research_{app.app_name}",
            )
            return record
        except Exception as e:
            # Total failure after all retries
            failure_category = self._categorize_error(e)
            error_msg = str(e) if str(e) else type(e).__name__
            logger.error(
                f"Research failed for {app.app_name} after all retries: {error_msg}"
            )
            # Log intervention
            self._interventions.append(
                InterventionEntry(
                    app_name=app.app_name,
                    pipeline_stage="researcher",
                    reason=f"Research failed: {failure_category} - {error_msg[:200]}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    data_point=None,
                )
            )
            return AppRecord(
                app_name=app.app_name,
                category=app.category,
                description=f"{app.app_name} - research failed",
                auth_methods=[AuthMethod.OTHER],
                access_model=AccessModel.GATED,
                api_surface=ApiSurface(
                    has_public_api=False,
                    api_type=None,
                    coverage=None,
                    has_mcp_support=False,
                    evidence_url=None,
                ),
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.MISSING_DOCUMENTATION,
                evidence_urls={},
                research_status=ResearchStatus.FAILED,
                missing_fields=list(_REQUIRED_FIELDS),
                failure_reason=error_msg[:500],
                failure_category=failure_category,
            )

    async def _with_retry(
        self,
        operation: Callable[..., Any],
        operation_name: str = "operation",
    ) -> Any:
        """Execute an async operation with exponential backoff retry logic.

        Attempt 1: immediate, timeout 30s
        Attempt 2: 2s delay, timeout 30s
        Attempt 3: 4s delay, timeout 30s

        Args:
            operation: Async callable to execute.
            operation_name: Name for logging purposes.

        Returns:
            Result of the operation.

        Raises:
            The last exception encountered if all retries are exhausted.
        """
        last_exception: Optional[Exception] = None

        for attempt in range(self._config.max_retries):
            delay = _RETRY_DELAYS[attempt] if attempt < len(_RETRY_DELAYS) else 4.0

            if delay > 0:
                await asyncio.sleep(delay)

            try:
                result = await asyncio.wait_for(
                    operation(),
                    timeout=float(self._config.timeout_seconds),
                )
                return result
            except asyncio.TimeoutError as e:
                last_exception = e
                logger.warning(
                    f"Attempt {attempt + 1}/{self._config.max_retries} "
                    f"for {operation_name} timed out after {self._config.timeout_seconds}s"
                )
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Attempt {attempt + 1}/{self._config.max_retries} "
                    f"for {operation_name} failed: {e}"
                )

        # All retries exhausted
        raise last_exception or RuntimeError(
            f"All {self._config.max_retries} retries exhausted for {operation_name}"
        )

    async def _find_docs_url(self, app_name: str) -> Optional[str]:
        """Search for the app's API documentation URL.

        Uses Composio SDK search to find the developer/API documentation page.

        Args:
            app_name: Name of the app to search for.

        Returns:
            URL of the API documentation, or None if not found.
        """
        query = f"{app_name} API documentation developer"
        try:
            if self._client and hasattr(self._client, "search"):
                results = await self._call_client_search(query)
                if results:
                    return self._extract_best_url(results, app_name)
        except Exception as e:
            logger.debug(f"Composio search failed for {app_name}: {e}")

        # Fallback: try direct HTTP search
        return await self._fallback_search(app_name)

    async def _call_client_search(self, query: str) -> Any:
        """Call the Composio SDK client's search method.

        Handles both sync and async client interfaces.

        Args:
            query: Search query string.

        Returns:
            Search results from the Composio client.
        """
        if asyncio.iscoroutinefunction(getattr(self._client, "search", None)):
            return await self._client.search(query)
        else:
            return self._client.search(query)

    async def _call_client_scrape(self, url: str) -> Any:
        """Call the Composio SDK client's scrape method.

        Handles both sync and async client interfaces.

        Args:
            url: URL to scrape.

        Returns:
            Scraped content from the Composio client.
        """
        if asyncio.iscoroutinefunction(getattr(self._client, "scrape", None)):
            return await self._client.scrape(url)
        else:
            return self._client.scrape(url)

    async def _fallback_search(self, app_name: str) -> Optional[str]:
        """Attempt to find API docs URL via direct HTTP requests.

        Tries common API documentation URL patterns.

        Args:
            app_name: Name of the app.

        Returns:
            URL of the API documentation, or None if not found.
        """
        normalized = app_name.lower().replace(" ", "").replace(".", "")
        common_patterns = [
            f"https://developer.{normalized}.com",
            f"https://developers.{normalized}.com",
            f"https://api.{normalized}.com",
            f"https://{normalized}.com/api",
            f"https://docs.{normalized}.com",
        ]

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._config.timeout_seconds),
                follow_redirects=True,
            )

        for url in common_patterns:
            try:
                response = await self._http_client.head(url)
                if response.status_code < 400:
                    return str(response.url)
            except (httpx.HTTPError, httpx.TimeoutException):
                continue

        return None

    def _extract_best_url(self, results: Any, app_name: str) -> Optional[str]:
        """Extract the most relevant documentation URL from search results.

        Args:
            results: Search results (list of dicts or objects with url/link fields).
            app_name: App name for relevance matching.

        Returns:
            Best matching URL or None.
        """
        if not results:
            return None

        # Handle list of dicts
        if isinstance(results, list):
            for result in results:
                url = None
                if isinstance(result, dict):
                    url = result.get("url") or result.get("link") or result.get("href")
                elif hasattr(result, "url"):
                    url = result.url
                elif hasattr(result, "link"):
                    url = result.link

                if url and isinstance(url, str):
                    # Prefer developer/API documentation URLs
                    lower_url = url.lower()
                    if any(
                        kw in lower_url
                        for kw in ["developer", "api", "docs", "documentation"]
                    ):
                        return url

            # Return first URL if no developer docs found
            first = results[0]
            if isinstance(first, dict):
                return first.get("url") or first.get("link")
            elif hasattr(first, "url"):
                return first.url

        # Handle single result
        if isinstance(results, dict):
            return results.get("url") or results.get("link")

        return None

    async def _collect_auth_method(
        self, app_name: str, docs_url: str
    ) -> list[AuthMethod]:
        """Determine authentication method(s) from API documentation.

        Searches documentation content for indicators of different auth methods:
        OAuth2, API key, Basic auth, and token-based auth.

        Args:
            app_name: Name of the app.
            docs_url: URL of the API documentation.

        Returns:
            List of detected authentication methods. Returns [OTHER] if none detected.
        """
        content = await self._get_page_content(app_name, docs_url, "authentication")
        if not content:
            return [AuthMethod.OTHER]

        content_lower = content.lower()
        detected: list[AuthMethod] = []

        if any(kw in content_lower for kw in _OAUTH2_KEYWORDS):
            detected.append(AuthMethod.OAUTH2)

        if any(kw in content_lower for kw in _API_KEY_KEYWORDS):
            detected.append(AuthMethod.API_KEY)

        if any(kw in content_lower for kw in _BASIC_AUTH_KEYWORDS):
            detected.append(AuthMethod.BASIC)

        if any(kw in content_lower for kw in _TOKEN_KEYWORDS):
            detected.append(AuthMethod.TOKEN)

        return detected if detected else [AuthMethod.OTHER]

    async def _assess_api_surface(
        self, app_name: str, docs_url: str
    ) -> ApiSurface:
        """Assess API coverage, type, and MCP availability.

        Examines documentation to determine what kind of API is available,
        how comprehensive the coverage is, and whether MCP support exists.

        Args:
            app_name: Name of the app.
            docs_url: URL of the API documentation.

        Returns:
            ApiSurface assessment of the app's public API capabilities.
        """
        content = await self._get_page_content(app_name, docs_url, "api")
        if not content:
            return ApiSurface(
                has_public_api=False,
                api_type=None,
                coverage=None,
                has_mcp_support=False,
                evidence_url=docs_url or None,
            )

        content_lower = content.lower()

        # Detect API type
        has_rest = any(kw in content_lower for kw in _REST_KEYWORDS)
        has_graphql = any(kw in content_lower for kw in _GRAPHQL_KEYWORDS)

        if has_rest and has_graphql:
            api_type = ApiType.BOTH
        elif has_graphql:
            api_type = ApiType.GRAPHQL
        elif has_rest:
            api_type = ApiType.REST
        else:
            api_type = None

        has_public_api = api_type is not None

        # Assess coverage breadth
        coverage: Optional[ApiCoverage] = None
        if has_public_api:
            coverage = self._assess_coverage_level(content_lower)

        # Check MCP support
        has_mcp = any(kw in content_lower for kw in _MCP_KEYWORDS)

        return ApiSurface(
            has_public_api=has_public_api,
            api_type=api_type,
            coverage=coverage,
            has_mcp_support=has_mcp,
            evidence_url=docs_url or None,
        )

    async def _assess_access_model(
        self, app_name: str, docs_url: str
    ) -> AccessModel:
        """Determine if API access is self-serve or gated.

        Looks for indicators of free/trial access vs paid/partner-only access.

        Args:
            app_name: Name of the app.
            docs_url: URL of the API documentation.

        Returns:
            AccessModel indicating self-serve or gated access.
        """
        content = await self._get_page_content(app_name, docs_url, "pricing signup")
        if not content:
            # Default to gated when we can't determine (never fabricate)
            return AccessModel.GATED

        content_lower = content.lower()

        self_serve_score = sum(
            1 for kw in _SELF_SERVE_KEYWORDS if kw in content_lower
        )
        gated_score = sum(1 for kw in _GATED_KEYWORDS if kw in content_lower)

        if self_serve_score > gated_score:
            return AccessModel.SELF_SERVE
        elif gated_score > 0:
            return AccessModel.GATED
        else:
            # If no strong signal either way, default to gated (conservative)
            return AccessModel.GATED

    def _determine_buildability(
        self,
        auth_methods: list[AuthMethod],
        api_surface: ApiSurface,
        access_model: AccessModel,
    ) -> tuple[BuildabilityVerdict, Optional[BlockerCategory]]:
        """Synthesize auth, API, and access findings into buildability verdict.

        Classification logic:
        - READY: has public API (REST/GraphQL/BOTH), sufficient coverage
          (FULL/PARTIAL), self-serve access
        - FEASIBLE: has API but gaps (minimal coverage, gated access, or
          restrictive auth)
        - BLOCKED: no public API, or critical barriers

        Args:
            auth_methods: Detected authentication methods.
            api_surface: Assessed API surface capabilities.
            access_model: Determined access model.

        Returns:
            Tuple of (BuildabilityVerdict, Optional[BlockerCategory]).
            BlockerCategory is None only when verdict is READY.
        """
        # BLOCKED: No public API at all
        if not api_surface.has_public_api:
            return BuildabilityVerdict.BLOCKED, BlockerCategory.NO_PUBLIC_API

        # Check for sufficient API type
        has_usable_api = api_surface.api_type in (
            ApiType.REST,
            ApiType.GRAPHQL,
            ApiType.BOTH,
        )

        if not has_usable_api:
            return BuildabilityVerdict.BLOCKED, BlockerCategory.NO_PUBLIC_API

        # Check coverage
        has_sufficient_coverage = api_surface.coverage in (
            ApiCoverage.FULL,
            ApiCoverage.PARTIAL,
        )

        # READY: full criteria met
        if has_sufficient_coverage and access_model == AccessModel.SELF_SERVE:
            return BuildabilityVerdict.READY, None

        # FEASIBLE with specific blocker identification
        if not has_sufficient_coverage:
            return (
                BuildabilityVerdict.FEASIBLE,
                BlockerCategory.INSUFFICIENT_COVERAGE,
            )

        if access_model == AccessModel.GATED:
            return BuildabilityVerdict.FEASIBLE, BlockerCategory.RESTRICTIVE_AUTH

        # Check for restrictive auth only (unusual but possible)
        if auth_methods == [AuthMethod.OTHER]:
            return BuildabilityVerdict.FEASIBLE, BlockerCategory.RESTRICTIVE_AUTH

        # Default feasible with documentation gaps
        return BuildabilityVerdict.FEASIBLE, BlockerCategory.MISSING_DOCUMENTATION

    async def _get_page_content(
        self, app_name: str, docs_url: str, search_suffix: str
    ) -> Optional[str]:
        """Get page content via Composio scraping or fallback search.

        Tries to scrape the docs URL first. If that fails or no URL is provided,
        searches for relevant content.

        Args:
            app_name: Name of the app.
            docs_url: Base documentation URL.
            search_suffix: Additional search terms for topic focus.

        Returns:
            Page content as string, or None if unavailable.
        """
        # Try scraping the docs URL directly
        if docs_url:
            try:
                content = await self._scrape_url(docs_url)
                if content:
                    return content
            except Exception as e:
                logger.debug(f"Scrape failed for {docs_url}: {e}")

        # Fallback: search for specific content
        query = f"{app_name} {search_suffix}"
        try:
            if self._client and hasattr(self._client, "search"):
                results = await self._call_client_search(query)
                if results:
                    url = self._extract_best_url(results, app_name)
                    if url:
                        content = await self._scrape_url(url)
                        if content:
                            return content
        except Exception as e:
            logger.debug(f"Search+scrape fallback failed for {app_name}: {e}")

        return None

    async def _scrape_url(self, url: str) -> Optional[str]:
        """Scrape content from a URL using Composio client or httpx fallback.

        Args:
            url: URL to scrape.

        Returns:
            Page content as string, or None if scraping failed.
        """
        # Try Composio client scrape first
        if self._client and hasattr(self._client, "scrape"):
            try:
                result = await self._call_client_scrape(url)
                if result:
                    if isinstance(result, str):
                        return result
                    elif isinstance(result, dict):
                        return result.get("content") or result.get("text") or str(result)
                    elif hasattr(result, "content"):
                        return result.content
                    return str(result)
            except Exception as e:
                logger.debug(f"Composio scrape failed for {url}: {e}")

        # Fallback: httpx GET
        try:
            if self._http_client is None:
                self._http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(self._config.timeout_seconds),
                    follow_redirects=True,
                )
            response = await self._http_client.get(url)
            if response.status_code < 400:
                return response.text[:50000]  # Limit content size
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.debug(f"HTTP fallback scrape failed for {url}: {e}")

        return None

    def _assess_coverage_level(self, content_lower: str) -> ApiCoverage:
        """Assess API coverage level from documentation content.

        Heuristic based on documentation breadth indicators.

        Args:
            content_lower: Lowercase page content.

        Returns:
            ApiCoverage assessment.
        """
        # Count endpoint-like patterns as coverage indicator
        endpoint_indicators = [
            "get /", "post /", "put /", "delete /", "patch /",
            "endpoint", "resource", "method",
        ]
        indicator_count = sum(
            content_lower.count(indicator) for indicator in endpoint_indicators
        )

        # Presence of comprehensive documentation markers
        comprehensive_markers = [
            "reference", "all endpoints", "complete api",
            "api reference", "full documentation",
        ]
        has_comprehensive = any(m in content_lower for m in comprehensive_markers)

        if has_comprehensive or indicator_count >= 20:
            return ApiCoverage.FULL
        elif indicator_count >= 5:
            return ApiCoverage.PARTIAL
        else:
            return ApiCoverage.MINIMAL

    async def _generate_description(self, app_name: str, category: str) -> str:
        """Generate a brief description for the app.

        Args:
            app_name: Name of the app.
            category: Category the app belongs to.

        Returns:
            Description string, max 120 characters.
        """
        # Use search to find a description
        try:
            if self._client and hasattr(self._client, "search"):
                results = await self._call_client_search(f"{app_name} description")
                if results and isinstance(results, list) and len(results) > 0:
                    first = results[0]
                    snippet = None
                    if isinstance(first, dict):
                        snippet = first.get("snippet") or first.get("description")
                    elif hasattr(first, "snippet"):
                        snippet = first.snippet
                    if snippet and isinstance(snippet, str):
                        return snippet[:120]
        except Exception:
            pass

        # Fallback: generate a basic description from name and category
        return f"{app_name} - {category} application"[:120]

    @staticmethod
    def _categorize_error(error: Exception) -> str:
        """Categorize an exception into a failure category.

        Args:
            error: The exception that occurred.

        Returns:
            Failure category string matching design spec categories.
        """
        if isinstance(error, asyncio.TimeoutError):
            return "timeout"
        elif isinstance(error, httpx.TimeoutException):
            return "timeout"
        elif isinstance(error, (httpx.ConnectError, httpx.NetworkError, OSError)):
            return "network_error"
        elif isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            if status in (401, 403):
                return "access_restriction"
            return "network_error"
        elif isinstance(error, (ValueError, KeyError, TypeError)):
            return "parsing_failure"
        else:
            return "agent_error"

    async def close(self) -> None:
        """Close any open HTTP clients."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
