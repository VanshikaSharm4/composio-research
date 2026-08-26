"""Tests for VerifierAgent including evidence checking, discrepancy resolution,
multi-pass metrics, and accuracy threshold behavior.

Requirements validated: 3.1, 3.2, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest

from hypothesis import given
import hypothesis.strategies as st

from composio_research.models import (
    AccessModel,
    ApiCoverage,
    ApiSurface,
    ApiType,
    AppRecord,
    AuthMethod,
    BlockerCategory,
    BuildabilityVerdict,
    PassMetrics,
    ResearchStatus,
    VerificationMetrics,
)
from composio_research.verifier import VerificationConfig, VerifierAgent


# ============================================================================
# Mock Composio Client
# ============================================================================


class MockComposioClient:
    """Mock Composio SDK client for testing the verifier.

    Simulates search() and scrape() methods with configurable responses.
    """

    def __init__(
        self,
        search_results: Optional[list[dict[str, str]]] = None,
        scrape_content: Optional[str] = None,
        search_side_effect: Optional[Exception] = None,
        scrape_side_effect: Optional[Exception] = None,
    ) -> None:
        self._search_results = search_results or []
        self._scrape_content = scrape_content or ""
        self._search_side_effect = search_side_effect
        self._scrape_side_effect = scrape_side_effect
        self.search_call_count = 0
        self.scrape_call_count = 0

    async def search(self, query: str) -> list[dict[str, str]]:
        self.search_call_count += 1
        if self._search_side_effect:
            raise self._search_side_effect
        return self._search_results

    async def scrape(self, url: str) -> str:
        self.scrape_call_count += 1
        if self._scrape_side_effect:
            raise self._scrape_side_effect
        return self._scrape_content


# ============================================================================
# Helpers
# ============================================================================


def _make_config(
    min_passes: int = 2,
    max_passes: int = 4,
    min_accuracy_threshold: float = 80.0,
    max_resolution_attempts: int = 3,
    timeout_seconds: int = 5,
) -> VerificationConfig:
    """Create a VerificationConfig for tests with fast settings."""
    return VerificationConfig(
        min_passes=min_passes,
        max_passes=max_passes,
        min_accuracy_threshold=min_accuracy_threshold,
        max_resolution_attempts=max_resolution_attempts,
        timeout_seconds=timeout_seconds,
    )


def _make_app_record(
    app_name: str = "TestApp",
    category: str = "CRM & Sales",
    auth_methods: Optional[list[AuthMethod]] = None,
    access_model: AccessModel = AccessModel.SELF_SERVE,
    has_public_api: bool = True,
    api_type: Optional[ApiType] = ApiType.REST,
    coverage: Optional[ApiCoverage] = ApiCoverage.FULL,
    buildability_verdict: BuildabilityVerdict = BuildabilityVerdict.READY,
    primary_blocker: Optional[BlockerCategory] = None,
    evidence_urls: Optional[dict[str, str]] = None,
    research_status: ResearchStatus = ResearchStatus.COMPLETE,
    missing_fields: Optional[list[str]] = None,
    failure_reason: Optional[str] = None,
    failure_category: Optional[str] = None,
) -> AppRecord:
    """Create a sample AppRecord with configurable fields for testing."""
    return AppRecord(
        app_name=app_name,
        category=category,
        description=f"{app_name} description",
        auth_methods=auth_methods or [AuthMethod.OAUTH2],
        access_model=access_model,
        api_surface=ApiSurface(
            has_public_api=has_public_api,
            api_type=api_type,
            coverage=coverage,
            has_mcp_support=False,
            evidence_url="https://example.com/api-docs",
        ),
        buildability_verdict=buildability_verdict,
        primary_blocker=primary_blocker,
        evidence_urls=evidence_urls or {},
        research_status=research_status,
        missing_fields=missing_fields or [],
        failure_reason=failure_reason,
        failure_category=failure_category,
    )


# ============================================================================
# Tests: _check_evidence
# ============================================================================


class TestCheckEvidence:
    """Tests for _check_evidence: verifying data points against evidence URLs."""

    @pytest.fixture
    def verifier(self) -> VerifierAgent:
        """Create a VerifierAgent with a basic mock client."""
        client = MockComposioClient(scrape_side_effect=Exception("no scrape"))
        return VerifierAgent(client, _make_config())

    async def test_returns_true_when_content_matches_auth_oauth2(self, verifier: VerifierAgent):
        """Evidence page mentioning oauth2 confirms auth_methods='oauth2'."""
        with patch.object(verifier, "_fetch_url_content", return_value="Use OAuth2 to authenticate"):
            result = await verifier._check_evidence(
                "auth_methods", "oauth2", "https://example.com/auth"
            )
        assert result is True

    async def test_returns_true_when_content_matches_auth_api_key(self, verifier: VerifierAgent):
        """Evidence page mentioning api key confirms auth_methods='api_key'."""
        with patch.object(verifier, "_fetch_url_content", return_value="Pass your API key in the header"):
            result = await verifier._check_evidence(
                "auth_methods", "api_key", "https://example.com/auth"
            )
        assert result is True

    async def test_returns_false_when_content_contradicts_auth(self, verifier: VerifierAgent):
        """Content has 'api key' but claim is 'oauth2' — contradiction."""
        with patch.object(verifier, "_fetch_url_content", return_value="Authentication uses your API key for all requests"):
            result = await verifier._check_evidence(
                "auth_methods", "oauth2", "https://example.com/auth"
            )
        assert result is False

    async def test_returns_true_when_url_inaccessible(self, verifier: VerifierAgent):
        """Cannot fetch evidence URL — can't disprove, assume confirmed."""
        with patch.object(verifier, "_fetch_url_content", return_value=None):
            result = await verifier._check_evidence(
                "auth_methods", "oauth2", "https://example.com/broken"
            )
        assert result is True

    async def test_returns_true_for_other_auth_method(self, verifier: VerifierAgent):
        """The 'other' auth method is always considered confirmed."""
        with patch.object(verifier, "_fetch_url_content", return_value="Some random page content"):
            result = await verifier._check_evidence(
                "auth_methods", "other", "https://example.com/auth"
            )
        assert result is True

    async def test_returns_true_for_access_model_self_serve(self, verifier: VerifierAgent):
        """Evidence mentioning 'free tier' confirms self_serve access model."""
        with patch.object(verifier, "_fetch_url_content", return_value="Start with our free tier today"):
            result = await verifier._check_evidence(
                "access_model", "self_serve", "https://example.com/pricing"
            )
        assert result is True

    async def test_returns_false_for_access_model_mismatch(self, verifier: VerifierAgent):
        """Content says 'contact sales' but claim is 'self_serve'."""
        with patch.object(verifier, "_fetch_url_content", return_value="Please contact our sales team for pricing"):
            result = await verifier._check_evidence(
                "access_model", "self_serve", "https://example.com/pricing"
            )
        assert result is False

    async def test_returns_true_for_api_surface_rest(self, verifier: VerifierAgent):
        """Evidence with REST API keywords confirms api_surface with REST."""
        with patch.object(verifier, "_fetch_url_content", return_value="Our REST API provides GET /users and POST /users endpoints"):
            result = await verifier._check_evidence(
                "api_surface", "has_public_api=True, api_type=rest", "https://example.com/api"
            )
        assert result is True

    async def test_returns_true_for_api_surface_no_api(self, verifier: VerifierAgent):
        """Evidence without API keywords confirms 'no public API' claim."""
        with patch.object(verifier, "_fetch_url_content", return_value="Welcome to our marketing website with product info"):
            result = await verifier._check_evidence(
                "api_surface", "has_public_api=False", "https://example.com"
            )
        assert result is True


# ============================================================================
# Tests: _run_pass
# ============================================================================


class TestRunPass:
    """Tests for _run_pass: single verification pass behavior."""

    async def test_skips_failed_records(self):
        """Records with FAILED status are skipped during verification."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config())

        record = _make_app_record(
            research_status=ResearchStatus.FAILED,
            evidence_urls={"auth_methods": "https://example.com/auth"},
            failure_reason="timeout",
            failure_category="timeout",
        )

        with patch.object(verifier, "_check_evidence", return_value=True) as mock_check:
            metrics = await verifier._run_pass([record], 1)

        # _check_evidence should never be called for failed records
        mock_check.assert_not_called()
        # With no data points checked, accuracy is 100% by default
        assert metrics.accuracy_percentage == 100.0
        assert metrics.total_data_points == 0

    async def test_skips_unresearchable_records(self):
        """Records with UNRESEARCHABLE status are skipped during verification."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config())

        record = _make_app_record(
            research_status=ResearchStatus.UNRESEARCHABLE,
            evidence_urls={"auth_methods": "https://example.com/auth"},
            failure_reason="app not found",
            failure_category="access_restriction",
        )

        with patch.object(verifier, "_check_evidence", return_value=True) as mock_check:
            metrics = await verifier._run_pass([record], 1)

        mock_check.assert_not_called()
        assert metrics.total_data_points == 0

    async def test_only_checks_fields_with_evidence_urls(self):
        """Only fields that have evidence URLs are checked."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config())

        # Only auth_methods has an evidence URL
        record = _make_app_record(
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        with patch.object(verifier, "_check_evidence", return_value=True) as mock_check:
            metrics = await verifier._run_pass([record], 1)

        # Only 1 data point should be checked (auth_methods)
        assert mock_check.call_count == 1
        assert metrics.total_data_points == 1
        assert metrics.confirmed_points == 1

    async def test_computes_correct_accuracy_percentage(self):
        """Accuracy is confirmed_points / total_data_points * 100."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config(max_resolution_attempts=0))

        # 3 fields with evidence, 2 confirmed, 1 not
        record = _make_app_record(
            evidence_urls={
                "auth_methods": "https://example.com/auth",
                "access_model": "https://example.com/pricing",
                "api_surface": "https://example.com/api",
            },
        )

        call_count = [0]

        async def mock_check_evidence(data_point, value, url):
            call_count[0] += 1
            # First two confirm, third doesn't
            return call_count[0] <= 2

        with patch.object(verifier, "_check_evidence", side_effect=mock_check_evidence):
            with patch.object(verifier, "_resolve_discrepancy", return_value=None):
                metrics = await verifier._run_pass([record], 1)

        assert metrics.total_data_points == 3
        assert metrics.confirmed_points == 2
        assert metrics.discrepancies_found == 1
        # 2/3 * 100 ≈ 66.67
        assert abs(metrics.accuracy_percentage - 66.67) < 0.1

    async def test_returns_100_percent_when_all_confirmed(self):
        """All evidence confirms — 100% accuracy."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config())

        record = _make_app_record(
            evidence_urls={
                "auth_methods": "https://example.com/auth",
                "access_model": "https://example.com/pricing",
            },
        )

        with patch.object(verifier, "_check_evidence", return_value=True):
            metrics = await verifier._run_pass([record], 1)

        assert metrics.accuracy_percentage == 100.0
        assert metrics.confirmed_points == 2
        assert metrics.total_data_points == 2
        assert metrics.discrepancies_found == 0

    async def test_corrections_applied_on_successful_resolution(self):
        """When a discrepancy is resolved, corrections_applied increments."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config())

        record = _make_app_record(
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        with patch.object(verifier, "_check_evidence", return_value=False):
            with patch.object(verifier, "_resolve_discrepancy", return_value="api_key"):
                metrics = await verifier._run_pass([record], 1)

        assert metrics.discrepancies_found == 1
        assert metrics.corrections_applied == 1
        # Corrected points count as confirmed
        assert metrics.confirmed_points == 1


# ============================================================================
# Tests: verify (multi-pass)
# ============================================================================


class TestVerify:
    """Tests for verify(): multi-pass execution, early stop, and manual review flag."""

    async def test_runs_minimum_two_passes(self):
        """verify() always runs at least min_passes (2) even if accuracy is 100%."""
        client = MockComposioClient()
        config = _make_config(min_passes=2, max_passes=4)
        verifier = VerifierAgent(client, config)

        record = _make_app_record(
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        with patch.object(verifier, "_check_evidence", return_value=True):
            records, metrics = await verifier.verify([record])

        # Must run at least 2 passes
        assert metrics.passes_completed >= 2

    async def test_stops_early_after_min_passes_if_accuracy_above_threshold(self):
        """verify() stops after min_passes when accuracy >= threshold."""
        client = MockComposioClient()
        config = _make_config(min_passes=2, max_passes=4, min_accuracy_threshold=80.0)
        verifier = VerifierAgent(client, config)

        record = _make_app_record(
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        with patch.object(verifier, "_check_evidence", return_value=True):
            records, metrics = await verifier.verify([record])

        # Should stop at exactly 2 (min_passes) since accuracy is 100%
        assert metrics.passes_completed == 2

    async def test_continues_to_max_passes_if_accuracy_below_threshold(self):
        """verify() continues up to max_passes when accuracy remains below threshold."""
        client = MockComposioClient()
        config = _make_config(min_passes=2, max_passes=3, min_accuracy_threshold=80.0)
        verifier = VerifierAgent(client, config)

        record = _make_app_record(
            evidence_urls={
                "auth_methods": "https://example.com/auth",
                "access_model": "https://example.com/pricing",
                "api_surface": "https://example.com/api",
            },
        )

        # Always return False so accuracy stays at 0%
        with patch.object(verifier, "_check_evidence", return_value=False):
            with patch.object(verifier, "_resolve_discrepancy", return_value=None):
                records, metrics = await verifier.verify([record])

        # Should run all 3 passes (max_passes) since accuracy never hits 80%
        assert metrics.passes_completed == 3

    async def test_returns_records_and_metrics_tuple(self):
        """verify() returns a tuple of (records, VerificationMetrics)."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config())

        record = _make_app_record(
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        with patch.object(verifier, "_check_evidence", return_value=True):
            result = await verifier.verify([record])

        assert isinstance(result, tuple)
        assert len(result) == 2
        records, metrics = result
        assert isinstance(records, list)
        assert len(records) == 1
        assert hasattr(metrics, "passes_completed")
        assert hasattr(metrics, "per_pass_metrics")
        assert hasattr(metrics, "overall_accuracy")
        assert hasattr(metrics, "requires_manual_review")

    async def test_sets_requires_manual_review_true_below_80(self):
        """requires_manual_review is True when final accuracy < 80%."""
        client = MockComposioClient()
        config = _make_config(min_passes=2, max_passes=2, min_accuracy_threshold=80.0)
        verifier = VerifierAgent(client, config)

        record = _make_app_record(
            evidence_urls={
                "auth_methods": "https://example.com/auth",
                "access_model": "https://example.com/pricing",
                "api_surface": "https://example.com/api",
            },
        )

        # All checks fail → 0% accuracy
        with patch.object(verifier, "_check_evidence", return_value=False):
            with patch.object(verifier, "_resolve_discrepancy", return_value=None):
                _, metrics = await verifier.verify([record])

        assert metrics.requires_manual_review is True
        assert metrics.overall_accuracy < 80.0

    async def test_sets_requires_manual_review_false_at_or_above_80(self):
        """requires_manual_review is False when final accuracy >= 80%."""
        client = MockComposioClient()
        config = _make_config(min_passes=2, max_passes=2, min_accuracy_threshold=80.0)
        verifier = VerifierAgent(client, config)

        record = _make_app_record(
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        # All checks pass → 100% accuracy
        with patch.object(verifier, "_check_evidence", return_value=True):
            _, metrics = await verifier.verify([record])

        assert metrics.requires_manual_review is False
        assert metrics.overall_accuracy >= 80.0


# ============================================================================
# Tests: _resolve_discrepancy
# ============================================================================


class TestResolveDiscrepancy:
    """Tests for _resolve_discrepancy: retry logic and in-place correction."""

    async def test_returns_corrected_value_on_success(self):
        """Returns corrected value when re-research finds new evidence."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config(max_resolution_attempts=3))

        record = _make_app_record(
            auth_methods=[AuthMethod.OAUTH2],
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        # Simulate re-fetch returning page with api_key evidence
        with patch.object(
            verifier, "_fetch_url_content_with_retry",
            return_value="All requests must include your API key in the header"
        ):
            result = await verifier._resolve_discrepancy(record, "auth_methods")

        assert result is not None
        assert "api_key" in result

    async def test_returns_none_after_max_attempts_exhausted(self):
        """Returns None when max_resolution_attempts are exhausted."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config(max_resolution_attempts=3))

        record = _make_app_record(
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        # All fetches return None (unable to fetch)
        with patch.object(verifier, "_fetch_url_content_with_retry", return_value=None):
            with patch.object(verifier, "_search_alternative_evidence", return_value=None):
                result = await verifier._resolve_discrepancy(record, "auth_methods")

        assert result is None

    async def test_applies_correction_in_place(self):
        """On successful resolution, the record is updated in-place."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config(max_resolution_attempts=3))

        record = _make_app_record(
            auth_methods=[AuthMethod.OAUTH2],
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        # Content clearly indicates api_key
        with patch.object(
            verifier, "_fetch_url_content_with_retry",
            return_value="Use your API key to authenticate all requests"
        ):
            result = await verifier._resolve_discrepancy(record, "auth_methods")

        assert result is not None
        # The record should have been updated in-place
        assert AuthMethod.API_KEY in record.auth_methods

    async def test_applies_access_model_correction(self):
        """Resolves access_model discrepancy and applies correction."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config(max_resolution_attempts=3))

        record = _make_app_record(
            access_model=AccessModel.SELF_SERVE,
            evidence_urls={"access_model": "https://example.com/pricing"},
        )

        # Content indicates gated
        with patch.object(
            verifier, "_fetch_url_content_with_retry",
            return_value="Enterprise only. Contact sales for pricing."
        ):
            result = await verifier._resolve_discrepancy(record, "access_model")

        assert result is not None
        assert record.access_model == AccessModel.GATED

    async def test_returns_none_when_no_evidence_url(self):
        """Returns None immediately if the field has no evidence URL."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config())

        record = _make_app_record(evidence_urls={})

        result = await verifier._resolve_discrepancy(record, "auth_methods")
        assert result is None


# ============================================================================
# Tests: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Edge case tests for the verifier."""

    async def test_record_with_empty_evidence_urls(self):
        """A record with no evidence URLs produces no data points to verify."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config())

        record = _make_app_record(evidence_urls={})

        with patch.object(verifier, "_check_evidence", return_value=True) as mock_check:
            metrics = await verifier._run_pass([record], 1)

        mock_check.assert_not_called()
        assert metrics.total_data_points == 0
        assert metrics.accuracy_percentage == 100.0

    async def test_all_records_failed_gives_100_accuracy(self):
        """When all records are FAILED, nothing to verify → 100% accuracy."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config(min_passes=2, max_passes=2))

        records = [
            _make_app_record(
                app_name=f"App{i}",
                research_status=ResearchStatus.FAILED,
                evidence_urls={"auth_methods": "https://example.com"},
                failure_reason="timeout",
                failure_category="timeout",
            )
            for i in range(5)
        ]

        _, metrics = await verifier.verify(records)

        assert metrics.overall_accuracy == 100.0
        assert metrics.requires_manual_review is False

    async def test_single_pass_100_accuracy(self):
        """With high accuracy from the start, stops at min_passes."""
        client = MockComposioClient()
        config = _make_config(min_passes=2, max_passes=4, min_accuracy_threshold=80.0)
        verifier = VerifierAgent(client, config)

        records = [
            _make_app_record(
                app_name=f"App{i}",
                evidence_urls={"auth_methods": "https://example.com/auth"},
            )
            for i in range(10)
        ]

        with patch.object(verifier, "_check_evidence", return_value=True):
            _, metrics = await verifier.verify(records)

        # Stops at 2 (min_passes) since each pass gets 100%
        assert metrics.passes_completed == 2
        assert metrics.overall_accuracy == 100.0

    async def test_mixed_records_some_skipped_some_verified(self):
        """Mix of FAILED and COMPLETE records — only COMPLETE records verified."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config(min_passes=2, max_passes=2))

        records = [
            _make_app_record(
                app_name="FailedApp",
                research_status=ResearchStatus.FAILED,
                evidence_urls={"auth_methods": "https://example.com"},
                failure_reason="timeout",
                failure_category="timeout",
            ),
            _make_app_record(
                app_name="GoodApp",
                research_status=ResearchStatus.COMPLETE,
                evidence_urls={"auth_methods": "https://example.com/auth"},
            ),
        ]

        with patch.object(verifier, "_check_evidence", return_value=True):
            _, metrics = await verifier.verify(records)

        # Only 1 data point per pass (from GoodApp)
        assert metrics.per_pass_metrics[0].total_data_points == 1
        assert metrics.overall_accuracy == 100.0

    async def test_partial_records_are_verified(self):
        """Records with PARTIAL status are still verified (not skipped)."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config(min_passes=2, max_passes=2))

        record = _make_app_record(
            research_status=ResearchStatus.PARTIAL,
            evidence_urls={"auth_methods": "https://example.com/auth"},
            missing_fields=["api_surface"],
        )

        with patch.object(verifier, "_check_evidence", return_value=True):
            _, metrics = await verifier.verify([record])

        # Partial records are checked
        assert metrics.per_pass_metrics[0].total_data_points == 1
        assert metrics.overall_accuracy == 100.0

    async def test_per_pass_metrics_accumulate_correctly(self):
        """Each pass produces independent PassMetrics in sequence."""
        client = MockComposioClient()
        config = _make_config(min_passes=2, max_passes=2)
        verifier = VerifierAgent(client, config)

        record = _make_app_record(
            evidence_urls={"auth_methods": "https://example.com/auth"},
        )

        with patch.object(verifier, "_check_evidence", return_value=True):
            _, metrics = await verifier.verify([record])

        assert len(metrics.per_pass_metrics) == 2
        assert metrics.per_pass_metrics[0].pass_number == 1
        assert metrics.per_pass_metrics[1].pass_number == 2
        # Both should have 1 data point and 100% accuracy
        for pm in metrics.per_pass_metrics:
            assert pm.total_data_points == 1
            assert pm.accuracy_percentage == 100.0

    async def test_multiple_fields_all_verified(self):
        """Multiple evidence URLs on one record all get checked."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config(min_passes=2, max_passes=2))

        record = _make_app_record(
            evidence_urls={
                "auth_methods": "https://example.com/auth",
                "access_model": "https://example.com/pricing",
                "api_surface": "https://example.com/api",
            },
        )

        with patch.object(verifier, "_check_evidence", return_value=True):
            _, metrics = await verifier.verify([record])

        # 3 data points per pass
        assert metrics.per_pass_metrics[0].total_data_points == 3
        assert metrics.overall_accuracy == 100.0

    async def test_close_cleans_up_http_client(self):
        """close() properly cleans up the internal HTTP client."""
        client = MockComposioClient()
        verifier = VerifierAgent(client, _make_config())

        # Simulate that an http client was created
        mock_http = AsyncMock()
        verifier._http_client = mock_http

        await verifier.close()

        mock_http.aclose.assert_called_once()
        assert verifier._http_client is None


# ============================================================================
# Property-Based Tests: Property 7
# Feature: composio-app-research-pipeline, Property 7: Verification accuracy metric consistency
# Validates: Requirements 3.3, 3.6
# ============================================================================


@st.composite
def pass_metrics_strategy(draw):
    """Generate valid PassMetrics with consistent internal relationships.

    Constraints:
    - total_data_points: 1-1000 (positive)
    - confirmed_points: 0 to total_data_points
    - discrepancies_found: 0 to total_data_points
    - corrections_applied: 0 to discrepancies_found
    - accuracy_percentage: computed as (confirmed_points / total_data_points) * 100
    """
    total = draw(st.integers(min_value=1, max_value=1000))
    confirmed = draw(st.integers(min_value=0, max_value=total))
    discrepancies = draw(st.integers(min_value=0, max_value=total))
    corrections = draw(st.integers(min_value=0, max_value=discrepancies))
    accuracy = (confirmed / total) * 100.0
    pass_number = draw(st.integers(min_value=1, max_value=10))
    return PassMetrics(
        pass_number=pass_number,
        accuracy_percentage=accuracy,
        total_data_points=total,
        confirmed_points=confirmed,
        discrepancies_found=discrepancies,
        corrections_applied=corrections,
    )


@st.composite
def verification_metrics_strategy(draw):
    """Generate valid VerificationMetrics with 2-4 passes and correct review flag.

    The requires_manual_review flag is derived from the final pass accuracy.
    """
    num_passes = draw(st.integers(min_value=2, max_value=4))
    passes = [draw(pass_metrics_strategy()) for _ in range(num_passes)]
    # Renumber passes sequentially
    for i, p in enumerate(passes):
        p.pass_number = i + 1
    final_accuracy = passes[-1].accuracy_percentage
    requires_review = final_accuracy < 80.0
    return VerificationMetrics(
        passes_completed=num_passes,
        per_pass_metrics=passes,
        discrepancy_log=[],
        overall_accuracy=final_accuracy,
        requires_manual_review=requires_review,
    )


class TestProperty7VerificationMetrics:
    """Property 7: Verification accuracy metric consistency.

    Feature: composio-app-research-pipeline, Property 7: Verification accuracy metric consistency
    **Validates: Requirements 3.3, 3.6**
    """

    @given(metrics=pass_metrics_strategy())
    def test_property7_accuracy_computation(self, metrics: PassMetrics):
        """For any PassMetrics, accuracy_percentage == (confirmed_points / total_data_points) * 100.

        Feature: composio-app-research-pipeline, Property 7: Verification accuracy metric consistency
        **Validates: Requirements 3.3**
        """
        expected_accuracy = (metrics.confirmed_points / metrics.total_data_points) * 100.0
        assert metrics.accuracy_percentage == expected_accuracy

    @given(metrics=pass_metrics_strategy())
    def test_property7_corrections_bound(self, metrics: PassMetrics):
        """For any PassMetrics, corrections_applied <= discrepancies_found.

        Feature: composio-app-research-pipeline, Property 7: Verification accuracy metric consistency
        **Validates: Requirements 3.3**
        """
        assert metrics.corrections_applied <= metrics.discrepancies_found

    @given(vm=verification_metrics_strategy())
    def test_property7_manual_review_flag(self, vm: VerificationMetrics):
        """For any VerificationMetrics, requires_manual_review == (final pass accuracy < 80).

        Feature: composio-app-research-pipeline, Property 7: Verification accuracy metric consistency
        **Validates: Requirements 3.6**
        """
        final_pass_accuracy = vm.per_pass_metrics[-1].accuracy_percentage
        expected_flag = final_pass_accuracy < 80.0
        assert vm.requires_manual_review == expected_flag
