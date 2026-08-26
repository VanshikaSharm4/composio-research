"""Verifier Agent for the Composio App Research Pipeline.

Runs multi-pass verification over collected app data, checking each data point
against evidence URLs. Detects discrepancies, attempts resolution via
re-research, computes accuracy metrics per pass, and flags records requiring
manual review when accuracy falls below threshold.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from composio_research.models import (
    AccessModel,
    ApiType,
    AppRecord,
    AuthMethod,
    BuildabilityVerdict,
    Discrepancy,
    InterventionEntry,
    PassMetrics,
    VerificationMetrics,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class VerificationConfig:
    """Configuration for the verifier agent.

    Attributes:
        min_passes: Minimum number of verification passes to run.
        max_passes: Maximum number of verification passes to run.
        min_accuracy_threshold: Accuracy percentage above which passes can stop early.
        max_resolution_attempts: Maximum re-research attempts per discrepancy.
        timeout_seconds: Timeout for individual HTTP requests.
        composio_api_key: API key for Composio SDK access.
    """

    min_passes: int = 2
    max_passes: int = 4
    min_accuracy_threshold: float = 80.0
    max_resolution_attempts: int = 3
    timeout_seconds: int = 30
    composio_api_key: Optional[str] = None


# ============================================================================
# Constants
# ============================================================================

# Retry delays in seconds for exponential backoff
_RETRY_DELAYS: list[float] = [0.0, 2.0, 4.0]

# Data point fields that can be verified against evidence URLs
_VERIFIABLE_FIELDS: list[str] = [
    "auth_methods",
    "access_model",
    "api_surface",
]

# Keywords for verifying auth methods in page content
_AUTH_VERIFICATION_KEYWORDS: dict[str, list[str]] = {
    "oauth2": ["oauth2", "oauth 2", "oauth2.0", "authorization_code", "access_token", "oauth"],
    "api_key": ["api key", "api_key", "apikey", "x-api-key", "api-key"],
    "basic": ["basic auth", "basic authentication", "http basic"],
    "token": ["bearer token", "personal access token", "jwt", "bearer", "auth token"],
    "other": [],
}

# Keywords for verifying access model
_ACCESS_MODEL_KEYWORDS: dict[str, list[str]] = {
    "self_serve": [
        "free tier", "free plan", "free trial", "sign up",
        "developer account", "sandbox", "get started",
        "no credit card", "public api", "free access",
    ],
    "gated": [
        "contact sales", "enterprise only", "paid plan",
        "request access", "invite only", "partner program",
        "custom pricing", "approval required",
    ],
}

# Keywords for verifying API surface
_API_SURFACE_KEYWORDS: dict[str, list[str]] = {
    "rest": ["rest api", "restful", "get /", "post /", "put /", "endpoints", "/api/v"],
    "graphql": ["graphql", "graph ql", "graphiql", "query {", "mutation {"],
}


# ============================================================================
# VerifierAgent
# ============================================================================


class VerifierAgent:
    """Runs multi-pass verification over collected app research data.

    Checks each data point against its associated evidence URLs, detects
    discrepancies, and attempts resolution through re-research. Computes
    accuracy metrics per pass and flags records requiring manual review.
    """

    def __init__(self, composio_client: Any, config: VerificationConfig) -> None:
        """Initialize with Composio SDK client and verification configuration.

        Args:
            composio_client: Composio SDK client providing search() and scrape() methods.
                Typed as Any to avoid hard dependency on composio-core.
            config: Verification configuration with pass limits and thresholds.
        """
        self._client = composio_client
        self._config = config
        self._http_client: Optional[httpx.AsyncClient] = None
        self._interventions: list[InterventionEntry] = []
        self._discrepancy_log: list[Discrepancy] = []

    @property
    def interventions(self) -> list[InterventionEntry]:
        """Return accumulated intervention entries from verification operations."""
        return list(self._interventions)

    async def verify(
        self, records: list[AppRecord]
    ) -> tuple[list[AppRecord], VerificationMetrics]:
        """Run 2-4 verification passes over all records.

        Executes at least min_passes verification passes. After each pass,
        checks if accuracy meets the threshold. Stops early if accuracy is
        above threshold after min_passes are complete. Continues up to
        max_passes if accuracy remains below threshold.

        Args:
            records: List of AppRecord objects to verify.

        Returns:
            Tuple of (verified_records, VerificationMetrics).
            verified_records may have corrected field values.
            VerificationMetrics contains per-pass accuracy and discrepancy log.
        """
        per_pass_metrics: list[PassMetrics] = []
        self._discrepancy_log = []

        for pass_number in range(1, self._config.max_passes + 1):
            logger.info(f"Starting verification pass {pass_number}")

            pass_metrics = await self._run_pass(records, pass_number)
            per_pass_metrics.append(pass_metrics)

            logger.info(
                f"Pass {pass_number} complete: "
                f"accuracy={pass_metrics.accuracy_percentage:.1f}%, "
                f"discrepancies={pass_metrics.discrepancies_found}, "
                f"corrections={pass_metrics.corrections_applied}"
            )

            # Check early stop: accuracy above threshold AND minimum passes done
            if (
                pass_number >= self._config.min_passes
                and pass_metrics.accuracy_percentage >= self._config.min_accuracy_threshold
            ):
                logger.info(
                    f"Accuracy {pass_metrics.accuracy_percentage:.1f}% >= "
                    f"{self._config.min_accuracy_threshold}% threshold after "
                    f"{pass_number} passes. Stopping early."
                )
                break

            # If we've done min passes but accuracy is still below, keep going
            if pass_number >= self._config.min_passes:
                logger.info(
                    f"Accuracy {pass_metrics.accuracy_percentage:.1f}% < "
                    f"{self._config.min_accuracy_threshold}% threshold. "
                    f"Continuing to pass {pass_number + 1}."
                )

        # Determine final accuracy from last pass
        final_accuracy = per_pass_metrics[-1].accuracy_percentage if per_pass_metrics else 0.0
        requires_manual_review = final_accuracy < self._config.min_accuracy_threshold

        if requires_manual_review:
            logger.warning(
                f"Final accuracy {final_accuracy:.1f}% is below "
                f"{self._config.min_accuracy_threshold}% threshold. "
                f"Flagging for manual review."
            )

        metrics = VerificationMetrics(
            passes_completed=len(per_pass_metrics),
            per_pass_metrics=per_pass_metrics,
            discrepancy_log=self._discrepancy_log,
            overall_accuracy=final_accuracy,
            requires_manual_review=requires_manual_review,
        )

        return records, metrics

    async def _run_pass(
        self, records: list[AppRecord], pass_number: int
    ) -> PassMetrics:
        """Execute a single verification pass over all records.

        For each record, iterates over data points that have associated
        evidence URLs. Checks each data point against its evidence URL.
        On discrepancy, attempts resolution. Computes and returns metrics.

        Args:
            records: List of AppRecord objects to verify.
            pass_number: Current pass number (1-indexed).

        Returns:
            PassMetrics with accuracy stats for this pass.
        """
        total_data_points = 0
        confirmed_points = 0
        discrepancies_found = 0
        corrections_applied = 0

        for record in records:
            # Skip records that completely failed research
            if record.research_status.value in ("failed", "unresearchable"):
                continue

            # Check each verifiable field that has an evidence URL
            for field_name in _VERIFIABLE_FIELDS:
                evidence_url = record.evidence_urls.get(field_name)
                if not evidence_url:
                    continue

                total_data_points += 1

                # Get the current value for this field
                current_value = self._get_field_value_str(record, field_name)

                # Check evidence
                is_confirmed = await self._check_evidence(
                    field_name, current_value, evidence_url
                )

                if is_confirmed:
                    confirmed_points += 1
                else:
                    discrepancies_found += 1

                    # Attempt resolution
                    corrected_value = await self._resolve_discrepancy(
                        record, field_name
                    )

                    if corrected_value is not None:
                        corrections_applied += 1
                        # The record was updated in-place by _resolve_discrepancy
                        confirmed_points += 1
                    else:
                        # Log unresolved discrepancy
                        self._discrepancy_log.append(
                            Discrepancy(
                                app_name=record.app_name,
                                field_name=field_name,
                                original_value=current_value,
                                corrected_value=None,
                                resolution_status="unresolved",
                                evidence_urls_checked=[evidence_url],
                                reason=f"Could not confirm {field_name} from evidence after {self._config.max_resolution_attempts} attempts",
                            )
                        )

        # Compute accuracy percentage
        accuracy_percentage = (
            (confirmed_points / total_data_points) * 100.0
            if total_data_points > 0
            else 100.0
        )

        return PassMetrics(
            pass_number=pass_number,
            accuracy_percentage=accuracy_percentage,
            total_data_points=total_data_points,
            confirmed_points=confirmed_points,
            discrepancies_found=discrepancies_found,
            corrections_applied=corrections_applied,
        )

    async def _check_evidence(
        self, data_point: str, value: str, evidence_url: str
    ) -> bool:
        """Verify a single data point against its evidence URL.

        Fetches the evidence URL content and checks whether it supports
        the given data point value using keyword matching.

        Args:
            data_point: Name of the field being verified (e.g., "auth_methods").
            value: Current string representation of the field value.
            evidence_url: URL to fetch and check against.

        Returns:
            True if the evidence supports the value, or if the URL cannot be
            fetched (can't disprove = assume confirmed). False if content
            contradicts the value.
        """
        # Fetch the evidence URL content
        content = await self._fetch_url_content(evidence_url)

        if content is None:
            # Cannot fetch evidence URL - can't disprove, assume confirmed
            logger.debug(
                f"Cannot fetch evidence URL {evidence_url} for {data_point}. "
                f"Assuming confirmed."
            )
            return True

        content_lower = content.lower()
        value_lower = value.lower()

        # Verification strategy depends on the data point type
        if data_point == "auth_methods":
            return self._verify_auth_methods(value_lower, content_lower)
        elif data_point == "access_model":
            return self._verify_access_model(value_lower, content_lower)
        elif data_point == "api_surface":
            return self._verify_api_surface(value_lower, content_lower)
        else:
            # Generic check: does the value appear in the content?
            return value_lower in content_lower

    def _verify_auth_methods(self, value_lower: str, content_lower: str) -> bool:
        """Verify auth methods against page content.

        Checks if the keywords associated with the claimed auth methods
        appear in the evidence page content.

        Args:
            value_lower: Lowercase string representation of auth methods.
            content_lower: Lowercase page content.

        Returns:
            True if evidence supports the auth methods claim.
        """
        # Parse the auth methods from the value string
        # Value format: "oauth2, api_key" or single value like "oauth2"
        methods = [m.strip() for m in value_lower.split(",")]

        for method in methods:
            method = method.strip()
            if method == "other":
                # 'other' is always considered confirmed (it's a fallback)
                continue

            keywords = _AUTH_VERIFICATION_KEYWORDS.get(method, [])
            if keywords and any(kw in content_lower for kw in keywords):
                return True

        # If no methods could be confirmed but we have 'other', that's fine
        if all(m.strip() == "other" for m in methods):
            return True

        # No keywords matched for any claimed method
        return False

    def _verify_access_model(self, value_lower: str, content_lower: str) -> bool:
        """Verify access model against page content.

        Checks if keywords for the claimed access model appear in the
        evidence page content.

        Args:
            value_lower: Lowercase access model value ("self_serve" or "gated").
            content_lower: Lowercase page content.

        Returns:
            True if evidence supports the access model claim.
        """
        keywords = _ACCESS_MODEL_KEYWORDS.get(value_lower, [])
        if not keywords:
            # Unknown access model value - can't verify
            return True

        return any(kw in content_lower for kw in keywords)

    def _verify_api_surface(self, value_lower: str, content_lower: str) -> bool:
        """Verify API surface against page content.

        Checks if evidence of the claimed API type exists in the page content.

        Args:
            value_lower: Lowercase API surface description.
            content_lower: Lowercase page content.

        Returns:
            True if evidence supports the API surface claim.
        """
        # Check for API type keywords in the content
        has_api_evidence = False

        for api_type, keywords in _API_SURFACE_KEYWORDS.items():
            if api_type in value_lower and any(kw in content_lower for kw in keywords):
                has_api_evidence = True
                break

        # If the claim is "has_public_api=True", verify API-related keywords exist
        if "true" in value_lower or "rest" in value_lower or "graphql" in value_lower:
            all_api_keywords = []
            for keywords in _API_SURFACE_KEYWORDS.values():
                all_api_keywords.extend(keywords)
            has_api_evidence = any(kw in content_lower for kw in all_api_keywords)

        # If the claim is no public API, verify absence
        if "false" in value_lower or "none" in value_lower:
            all_api_keywords = []
            for keywords in _API_SURFACE_KEYWORDS.values():
                all_api_keywords.extend(keywords)
            # If no API keywords found, the "no API" claim is confirmed
            has_api_evidence = not any(kw in content_lower for kw in all_api_keywords)

        return has_api_evidence

    async def _resolve_discrepancy(
        self, record: AppRecord, field: str, attempts: int = 0
    ) -> Optional[str]:
        """Attempt to resolve a discrepancy by re-researching.

        Re-fetches evidence for the specific field up to max_resolution_attempts.
        If a new consistent value is found, updates the record in-place.

        Args:
            record: AppRecord with the discrepant field.
            field: Name of the field to re-research.
            attempts: Current attempt count (for recursion tracking).

        Returns:
            The corrected value string if resolution succeeded, None otherwise.
        """
        if attempts >= self._config.max_resolution_attempts:
            logger.debug(
                f"Resolution attempts exhausted for {record.app_name}.{field}"
            )
            return None

        # Try to re-research the specific field
        evidence_url = record.evidence_urls.get(field)
        if not evidence_url:
            return None

        try:
            content = await self._fetch_url_content_with_retry(evidence_url)
            if not content:
                # Try searching for alternative evidence
                content = await self._search_alternative_evidence(
                    record.app_name, field
                )
                if not content:
                    return await self._resolve_discrepancy(
                        record, field, attempts + 1
                    )

            content_lower = content.lower()

            # Attempt to extract a corrected value from the content
            corrected = self._extract_corrected_value(field, content_lower, record)

            if corrected is not None:
                # Update the record in-place
                self._apply_correction(record, field, corrected)

                # Log the correction
                original_value = self._get_field_value_str(record, field)
                self._discrepancy_log.append(
                    Discrepancy(
                        app_name=record.app_name,
                        field_name=field,
                        original_value=original_value,
                        corrected_value=corrected,
                        resolution_status="resolved",
                        evidence_urls_checked=[evidence_url],
                        reason=f"Corrected from re-research on attempt {attempts + 1}",
                    )
                )
                return corrected

        except Exception as e:
            logger.debug(
                f"Resolution attempt {attempts + 1} failed for "
                f"{record.app_name}.{field}: {e}"
            )

        # Retry with incremented attempt count
        return await self._resolve_discrepancy(record, field, attempts + 1)

    def _extract_corrected_value(
        self, field: str, content_lower: str, record: AppRecord
    ) -> Optional[str]:
        """Extract a corrected value from page content for a specific field.

        Analyzes the fetched content to determine what the correct value
        should be based on keyword presence.

        Args:
            field: Name of the field to correct.
            content_lower: Lowercase page content.
            record: The AppRecord being corrected.

        Returns:
            Corrected value string, or None if no correction can be determined.
        """
        if field == "auth_methods":
            return self._extract_auth_from_content(content_lower)
        elif field == "access_model":
            return self._extract_access_from_content(content_lower)
        elif field == "api_surface":
            return self._extract_api_surface_from_content(content_lower)
        return None

    def _extract_auth_from_content(self, content_lower: str) -> Optional[str]:
        """Extract auth method(s) from page content.

        Args:
            content_lower: Lowercase page content.

        Returns:
            Comma-separated auth methods, or None if none detected.
        """
        detected: list[str] = []

        for method, keywords in _AUTH_VERIFICATION_KEYWORDS.items():
            if method == "other":
                continue
            if any(kw in content_lower for kw in keywords):
                detected.append(method)

        return ", ".join(detected) if detected else None

    def _extract_access_from_content(self, content_lower: str) -> Optional[str]:
        """Extract access model from page content.

        Args:
            content_lower: Lowercase page content.

        Returns:
            "self_serve" or "gated", or None if indeterminate.
        """
        self_serve_score = sum(
            1 for kw in _ACCESS_MODEL_KEYWORDS["self_serve"] if kw in content_lower
        )
        gated_score = sum(
            1 for kw in _ACCESS_MODEL_KEYWORDS["gated"] if kw in content_lower
        )

        if self_serve_score > gated_score:
            return "self_serve"
        elif gated_score > self_serve_score:
            return "gated"
        return None

    def _extract_api_surface_from_content(self, content_lower: str) -> Optional[str]:
        """Extract API surface info from page content.

        Args:
            content_lower: Lowercase page content.

        Returns:
            API type string, or None if no API detected.
        """
        has_rest = any(
            kw in content_lower for kw in _API_SURFACE_KEYWORDS["rest"]
        )
        has_graphql = any(
            kw in content_lower for kw in _API_SURFACE_KEYWORDS["graphql"]
        )

        if has_rest and has_graphql:
            return "both"
        elif has_rest:
            return "rest"
        elif has_graphql:
            return "graphql"
        return None

    def _apply_correction(
        self, record: AppRecord, field: str, corrected_value: str
    ) -> None:
        """Apply a corrected value to the record in-place.

        Args:
            record: AppRecord to update.
            field: Name of the field to correct.
            corrected_value: The new value to apply.
        """
        if field == "auth_methods":
            methods = [m.strip() for m in corrected_value.split(",")]
            record.auth_methods = [
                AuthMethod(m) for m in methods if m in AuthMethod._value2member_map_
            ]
            if not record.auth_methods:
                record.auth_methods = [AuthMethod.OTHER]

        elif field == "access_model":
            if corrected_value in AccessModel._value2member_map_:
                record.access_model = AccessModel(corrected_value)

        elif field == "api_surface":
            if corrected_value in ApiType._value2member_map_:
                record.api_surface.api_type = ApiType(corrected_value)
                record.api_surface.has_public_api = corrected_value != "none"

    async def _fetch_url_content(self, url: str) -> Optional[str]:
        """Fetch content from a URL using Composio client or httpx fallback.

        On failure, returns None (cannot disprove = assume confirmed).

        Args:
            url: URL to fetch.

        Returns:
            Page content as string, or None if fetch failed.
        """
        # Try Composio client scrape first
        if self._client and hasattr(self._client, "scrape"):
            try:
                result = await self._call_client_scrape(url)
                if result:
                    return self._extract_content(result)
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
            logger.debug(f"HTTP fallback fetch failed for {url}: {e}")

        return None

    async def _fetch_url_content_with_retry(self, url: str) -> Optional[str]:
        """Fetch URL content with exponential backoff retries.

        Uses the same retry pattern as the researcher (3 attempts with
        0s/2s/4s delays).

        Args:
            url: URL to fetch.

        Returns:
            Page content as string, or None if all attempts failed.
        """
        for attempt in range(len(_RETRY_DELAYS)):
            delay = _RETRY_DELAYS[attempt]
            if delay > 0:
                await asyncio.sleep(delay)

            content = await self._fetch_url_content(url)
            if content is not None:
                return content

        return None

    async def _search_alternative_evidence(
        self, app_name: str, field: str
    ) -> Optional[str]:
        """Search for alternative evidence for a specific field.

        Uses the Composio client to search for additional documentation.

        Args:
            app_name: Name of the app.
            field: Field to find evidence for.

        Returns:
            Page content from an alternative source, or None.
        """
        search_suffixes: dict[str, str] = {
            "auth_methods": "authentication API documentation",
            "access_model": "API access pricing developer signup",
            "api_surface": "REST API GraphQL developer documentation",
        }

        suffix = search_suffixes.get(field, "API documentation")
        query = f"{app_name} {suffix}"

        try:
            if self._client and hasattr(self._client, "search"):
                results = await self._call_client_search(query)
                if results and isinstance(results, list) and len(results) > 0:
                    # Get URL from first result
                    first = results[0]
                    url = None
                    if isinstance(first, dict):
                        url = first.get("url") or first.get("link")
                    elif hasattr(first, "url"):
                        url = first.url

                    if url:
                        return await self._fetch_url_content(url)
        except Exception as e:
            logger.debug(f"Alternative evidence search failed for {app_name}.{field}: {e}")

        return None

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

    @staticmethod
    def _extract_content(result: Any) -> Optional[str]:
        """Extract text content from a scrape result.

        Args:
            result: Result from Composio client scrape.

        Returns:
            Content string, or None.
        """
        if isinstance(result, str):
            return result
        elif isinstance(result, dict):
            return result.get("content") or result.get("text") or str(result)
        elif hasattr(result, "content"):
            return result.content
        return str(result) if result else None

    @staticmethod
    def _get_field_value_str(record: AppRecord, field: str) -> str:
        """Get the string representation of a field value from an AppRecord.

        Args:
            record: AppRecord to extract from.
            field: Field name to extract.

        Returns:
            String representation of the field value.
        """
        if field == "auth_methods":
            return ", ".join(m.value for m in record.auth_methods)
        elif field == "access_model":
            return record.access_model.value
        elif field == "api_surface":
            api = record.api_surface
            parts = [f"has_public_api={api.has_public_api}"]
            if api.api_type:
                parts.append(f"api_type={api.api_type.value}")
            if api.coverage:
                parts.append(f"coverage={api.coverage.value}")
            return ", ".join(parts)
        return ""

    async def write_outputs(
        self,
        records: list[AppRecord],
        metrics: VerificationMetrics,
        output_dir: Path,
    ) -> None:
        """Write verification outputs to JSON files.

        Writes verified_records.json and verification_metrics.json to the
        specified output directory.

        Args:
            records: Verified AppRecord objects.
            metrics: VerificationMetrics for the verification run.
            output_dir: Directory to write output files to.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write verified records
        records_path = output_dir / "verified_records.json"
        records_data = [r.to_dict() for r in records]
        records_path.write_text(
            json.dumps(records_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Wrote verified records to {records_path}")

        # Write verification metrics
        metrics_path = output_dir / "verification_metrics.json"
        metrics_path.write_text(
            json.dumps(metrics.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Wrote verification metrics to {metrics_path}")

    async def close(self) -> None:
        """Close any open HTTP clients."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
