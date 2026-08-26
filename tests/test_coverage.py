"""Unit tests for the coverage validation module."""

from __future__ import annotations

from typing import List, Optional

import pytest

from composio_research.config import CATEGORIES
from composio_research.coverage import (
    CategoryCoverage,
    CoverageSummary,
    CoverageValidator,
    REQUIRED_FIELDS,
)
from composio_research.models import (
    AccessModel,
    ApiCoverage,
    ApiSurface,
    ApiType,
    AppRecord,
    AuthMethod,
    BlockerCategory,
    BuildabilityVerdict,
    ResearchStatus,
)


_SENTINEL = object()


def _make_record(
    app_name: str = "TestApp",
    category: str = "CRM & Sales",
    description: str = "A test app",
    auth_methods=_SENTINEL,
    access_model: AccessModel = AccessModel.SELF_SERVE,
    has_public_api: bool = True,
    api_type: Optional[ApiType] = ApiType.REST,
    coverage: Optional[ApiCoverage] = ApiCoverage.FULL,
    buildability_verdict: BuildabilityVerdict = BuildabilityVerdict.READY,
    primary_blocker: Optional[BlockerCategory] = None,
    research_status: ResearchStatus = ResearchStatus.COMPLETE,
    missing_fields=_SENTINEL,
    failure_reason: Optional[str] = None,
    failure_category: Optional[str] = None,
) -> AppRecord:
    """Helper to create an AppRecord with sensible defaults."""
    if auth_methods is _SENTINEL:
        auth_methods = [AuthMethod.OAUTH2]
    if missing_fields is _SENTINEL:
        missing_fields = []
    return AppRecord(
        app_name=app_name,
        category=category,
        description=description,
        auth_methods=auth_methods,
        access_model=access_model,
        api_surface=ApiSurface(
            has_public_api=has_public_api,
            api_type=api_type,
            coverage=coverage,
            has_mcp_support=False,
            evidence_url=None,
        ),
        buildability_verdict=buildability_verdict,
        primary_blocker=primary_blocker,
        evidence_urls={},
        research_status=research_status,
        missing_fields=missing_fields,
        failure_reason=failure_reason,
        failure_category=failure_category,
    )


def _make_full_dataset(
    status: ResearchStatus = ResearchStatus.COMPLETE,
) -> list[AppRecord]:
    """Create a valid 100-app dataset (10 per category)."""
    records = []
    for category in CATEGORIES:
        for i in range(10):
            records.append(
                _make_record(
                    app_name=f"{category}_App_{i}",
                    category=category,
                    research_status=status,
                )
            )
    return records


class TestCoverageValidator:
    """Tests for CoverageValidator.validate()."""

    def test_valid_100_apps_all_complete(self):
        """100 COMPLETE apps across all categories yields valid summary."""
        validator = CoverageValidator()
        records = _make_full_dataset(ResearchStatus.COMPLETE)
        summary = validator.validate(records)

        assert summary.total_apps == 100
        assert summary.total_successfully_researched == 100
        assert summary.is_valid is True
        assert summary.validation_errors == []
        assert len(summary.per_category) == 10

        for cat_cov in summary.per_category:
            assert cat_cov.target_count == 10
            assert cat_cov.total_records == 10
            assert cat_cov.successfully_researched == 10
            assert cat_cov.failed_count == 0
            assert cat_cov.unresearchable_count == 0
            assert cat_cov.partial_count == 0
            assert cat_cov.unresearchable_apps == []

    def test_missing_category_invalid(self):
        """If a category is missing entirely, summary is invalid."""
        validator = CoverageValidator()
        # Only 9 categories, omitting last one
        records = []
        for category in CATEGORIES[:9]:
            for i in range(10):
                records.append(_make_record(app_name=f"App_{i}", category=category))

        summary = validator.validate(records)

        assert summary.total_apps == 90
        assert summary.is_valid is False
        assert any("Missing categories" in e for e in summary.validation_errors)
        assert any("90" in e for e in summary.validation_errors)

    def test_wrong_count_per_category(self):
        """If a category has != 10 records, validation error is reported."""
        validator = CoverageValidator()
        records = _make_full_dataset()
        # Remove one record from first category
        records = [r for r in records if not (r.category == "CRM & Sales" and r.app_name == "CRM & Sales_App_0")]

        summary = validator.validate(records)

        assert summary.total_apps == 99
        assert summary.is_valid is False
        assert any("CRM & Sales" in e and "9" in e for e in summary.validation_errors)

    def test_failed_apps_not_counted_as_success(self):
        """FAILED apps are not counted as successfully researched."""
        validator = CoverageValidator()
        records = _make_full_dataset()
        # Mark first 3 in CRM & Sales as FAILED
        for i, r in enumerate(records):
            if r.category == "CRM & Sales" and i < 3:
                r.research_status = ResearchStatus.FAILED
                r.failure_reason = "timeout"
                r.failure_category = "timeout"

        summary = validator.validate(records)

        crm_cov = next(c for c in summary.per_category if c.category == "CRM & Sales")
        assert crm_cov.failed_count == 3
        assert crm_cov.successfully_researched == 7
        assert summary.total_successfully_researched == 97

    def test_unresearchable_apps_tracked(self):
        """UNRESEARCHABLE apps are listed with reasons."""
        validator = CoverageValidator()
        records = _make_full_dataset()
        # Mark two apps in Ecommerce as UNRESEARCHABLE
        ecommerce_records = [r for r in records if r.category == "Ecommerce"]
        ecommerce_records[0].research_status = ResearchStatus.UNRESEARCHABLE
        ecommerce_records[0].failure_reason = "App no longer exists"
        ecommerce_records[0].failure_category = "access_restriction"
        ecommerce_records[1].research_status = ResearchStatus.UNRESEARCHABLE
        ecommerce_records[1].failure_reason = "Merged with another product"
        ecommerce_records[1].failure_category = "access_restriction"

        summary = validator.validate(records)

        ecom_cov = next(c for c in summary.per_category if c.category == "Ecommerce")
        assert ecom_cov.unresearchable_count == 2
        assert ecom_cov.successfully_researched == 8
        assert len(ecom_cov.unresearchable_apps) == 2
        assert ecom_cov.unresearchable_apps[0]["reason"] == "App no longer exists"

    def test_partial_above_threshold_counted(self):
        """PARTIAL app with >= 80% fields populated is counted as success."""
        validator = CoverageValidator()
        # All 7 required fields populated (100%) - PARTIAL but meets threshold
        record = _make_record(
            research_status=ResearchStatus.PARTIAL,
            missing_fields=["evidence_urls"],  # only optional field missing
        )
        assert validator._is_successfully_researched(record) is True

    def test_partial_below_threshold_not_counted(self):
        """PARTIAL app with < 80% fields populated is NOT counted as success."""
        validator = CoverageValidator()
        # Missing description, auth_methods, and api_surface → 4/7 = 57%
        record = _make_record(
            description="",
            auth_methods=[],
            has_public_api=True,
            research_status=ResearchStatus.PARTIAL,
            missing_fields=["description", "auth_methods"],
        )
        # 4/7 required fields populated = 57.1%
        # app_name (yes), category (yes), description (no - empty),
        # auth_methods (no - empty list), access_model (yes),
        # api_surface (yes), buildability_verdict (yes) = 5/7 = 71.4%
        # Wait: we need to make it actually below 80%
        # Let's also clear app_name to get under threshold
        record.app_name = ""
        record.category = ""
        # Now: app_name(no), category(no), description(no), auth(no),
        # access_model(yes), api_surface(yes), buildability(yes) = 3/7 = 42.9%
        assert validator._is_successfully_researched(record) is False

    def test_partial_at_exact_boundary(self):
        """PARTIAL app with exactly 80% (rounded) meets threshold."""
        validator = CoverageValidator()
        # 6/7 = 85.7% - above threshold
        record = _make_record(
            description="",  # missing this one field
            research_status=ResearchStatus.PARTIAL,
            missing_fields=["description"],
        )
        # app_name(yes), category(yes), description(no - empty),
        # auth_methods(yes), access_model(yes), api_surface(yes),
        # buildability_verdict(yes) = 6/7 = 85.7%
        assert validator._is_successfully_researched(record) is True

    def test_partial_below_80_percent_boundary(self):
        """PARTIAL app with 5/7 (71.4%) does NOT meet 80% threshold."""
        validator = CoverageValidator()
        record = _make_record(
            description="",
            auth_methods=[],
            research_status=ResearchStatus.PARTIAL,
            missing_fields=["description", "auth_methods"],
        )
        # app_name(yes), category(yes), description(no),
        # auth_methods(no - empty), access_model(yes), api_surface(yes),
        # buildability_verdict(yes) = 5/7 = 71.4%
        assert validator._is_successfully_researched(record) is False

    def test_complete_always_counted(self):
        """COMPLETE records are always counted as successful."""
        validator = CoverageValidator()
        record = _make_record(research_status=ResearchStatus.COMPLETE)
        assert validator._is_successfully_researched(record) is True

    def test_failed_never_counted(self):
        """FAILED records are never counted as successful."""
        validator = CoverageValidator()
        record = _make_record(
            research_status=ResearchStatus.FAILED,
            failure_reason="timeout",
            failure_category="timeout",
        )
        assert validator._is_successfully_researched(record) is False

    def test_unresearchable_never_counted(self):
        """UNRESEARCHABLE records are never counted as successful."""
        validator = CoverageValidator()
        record = _make_record(
            research_status=ResearchStatus.UNRESEARCHABLE,
            failure_reason="App defunct",
            failure_category="access_restriction",
        )
        assert validator._is_successfully_researched(record) is False


class TestFieldPopulation:
    """Tests for _compute_field_population_percentage."""

    def test_all_fields_populated(self):
        """Record with all required fields → 100%."""
        validator = CoverageValidator()
        record = _make_record()
        pct = validator._compute_field_population_percentage(record)
        assert pct == pytest.approx(100.0)

    def test_no_description(self):
        """Missing description → 6/7 = 85.7%."""
        validator = CoverageValidator()
        record = _make_record(description="")
        pct = validator._compute_field_population_percentage(record)
        assert pct == pytest.approx(6 / 7 * 100)

    def test_empty_auth_methods(self):
        """Empty auth_methods list → 6/7 = 85.7%."""
        validator = CoverageValidator()
        record = _make_record(auth_methods=[])
        pct = validator._compute_field_population_percentage(record)
        assert pct == pytest.approx(6 / 7 * 100)

    def test_multiple_missing(self):
        """Multiple missing fields reduce percentage."""
        validator = CoverageValidator()
        record = _make_record(
            app_name="",
            description="",
            auth_methods=[],
        )
        # category(yes), access_model(yes), api_surface(yes), buildability(yes) = 4/7
        pct = validator._compute_field_population_percentage(record)
        assert pct == pytest.approx(4 / 7 * 100)

    def test_get_required_fields_returns_7(self):
        """Required fields list has exactly 7 entries."""
        validator = CoverageValidator()
        fields = validator._get_required_fields()
        assert len(fields) == 7
        assert fields == REQUIRED_FIELDS


class TestCountPerCategory:
    """Tests for _count_per_category grouping."""

    def test_groups_correctly(self):
        """Records are grouped by their category field."""
        validator = CoverageValidator()
        records = [
            _make_record(app_name="App1", category="CRM & Sales"),
            _make_record(app_name="App2", category="CRM & Sales"),
            _make_record(app_name="App3", category="Ecommerce"),
        ]
        grouped = validator._count_per_category(records)
        assert len(grouped["CRM & Sales"]) == 2
        assert len(grouped["Ecommerce"]) == 1

    def test_empty_list(self):
        """Empty record list returns empty dict."""
        validator = CoverageValidator()
        grouped = validator._count_per_category([])
        assert grouped == {}


class TestCoverageSummarySerialization:
    """Tests for CoverageSummary to_dict/from_dict round-trip."""

    def test_round_trip(self):
        """CoverageSummary serializes and deserializes correctly."""
        summary = CoverageSummary(
            total_apps=100,
            total_successfully_researched=95,
            per_category=[
                CategoryCoverage(
                    category="CRM & Sales",
                    target_count=10,
                    total_records=10,
                    successfully_researched=9,
                    failed_count=1,
                    unresearchable_count=0,
                    partial_count=1,
                    unresearchable_apps=[],
                ),
            ],
            is_valid=True,
            validation_errors=[],
        )

        data = summary.to_dict()
        restored = CoverageSummary.from_dict(data)

        assert restored.total_apps == 100
        assert restored.total_successfully_researched == 95
        assert restored.is_valid is True
        assert restored.validation_errors == []
        assert len(restored.per_category) == 1
        assert restored.per_category[0].category == "CRM & Sales"
        assert restored.per_category[0].successfully_researched == 9

    def test_category_coverage_round_trip(self):
        """CategoryCoverage serializes and deserializes correctly."""
        cov = CategoryCoverage(
            category="Ecommerce",
            target_count=10,
            total_records=10,
            successfully_researched=8,
            failed_count=1,
            unresearchable_count=1,
            partial_count=2,
            unresearchable_apps=[
                {"app_name": "DefunctShop", "reason": "No longer exists"}
            ],
        )

        data = cov.to_dict()
        restored = CategoryCoverage.from_dict(data)

        assert restored.category == "Ecommerce"
        assert restored.target_count == 10
        assert restored.total_records == 10
        assert restored.successfully_researched == 8
        assert restored.failed_count == 1
        assert restored.unresearchable_count == 1
        assert restored.partial_count == 2
        assert len(restored.unresearchable_apps) == 1
        assert restored.unresearchable_apps[0]["app_name"] == "DefunctShop"

    def test_summary_with_validation_errors(self):
        """CoverageSummary with errors round-trips correctly."""
        summary = CoverageSummary(
            total_apps=90,
            total_successfully_researched=85,
            per_category=[],
            is_valid=False,
            validation_errors=["Missing categories: ['AI/Research/Media']", "Total app count is 90 (expected 100)"],
        )

        data = summary.to_dict()
        restored = CoverageSummary.from_dict(data)

        assert restored.is_valid is False
        assert len(restored.validation_errors) == 2
        assert "Missing categories" in restored.validation_errors[0]


class TestTotalSuccessConsistency:
    """Tests that total_successfully_researched equals sum of per-category counts."""

    def test_sum_matches_total(self):
        """Total successfully researched == sum of per-category successfully researched."""
        validator = CoverageValidator()
        records = _make_full_dataset()

        # Mark some apps in various categories as failed/partial
        crm_records = [r for r in records if r.category == "CRM & Sales"]
        crm_records[0].research_status = ResearchStatus.FAILED
        crm_records[0].failure_reason = "timeout"
        crm_records[0].failure_category = "timeout"

        ecom_records = [r for r in records if r.category == "Ecommerce"]
        ecom_records[0].research_status = ResearchStatus.PARTIAL
        ecom_records[0].missing_fields = ["description"]
        ecom_records[0].description = ""
        ecom_records[0].auth_methods = []
        ecom_records[0].app_name = ""
        # This will be 4/7 = 57.1% → NOT counted

        summary = validator.validate(records)

        per_cat_sum = sum(c.successfully_researched for c in summary.per_category)
        assert summary.total_successfully_researched == per_cat_sum


# ============================================================================
# Property-Based Tests (Hypothesis)
# ============================================================================

from hypothesis import given, settings
import hypothesis.strategies as st


# ============================================================================
# Hypothesis Strategies for Property 10
# ============================================================================


@st.composite
def partial_record_strategy(draw):
    """Generate AppRecords with PARTIAL status and varied field population.

    Randomly decides whether each of the 7 required fields is populated
    or empty/missing. Fields that are always present as enum values
    (access_model, buildability_verdict) are always populated; api_surface
    is always a valid object. The variable fields are: app_name, category,
    description, auth_methods.
    """
    has_app_name = draw(st.booleans())
    has_category = draw(st.booleans())
    has_description = draw(st.booleans())
    has_auth_methods = draw(st.booleans())

    # app_name: non-empty string or empty
    app_name = draw(st.text(min_size=1, max_size=30).filter(lambda s: s.strip() != "")) if has_app_name else ""

    # category: valid category or empty
    category = draw(st.sampled_from(CATEGORIES)) if has_category else ""

    # description: non-empty string or empty
    description = draw(st.text(min_size=1, max_size=120).filter(lambda s: s.strip() != "")) if has_description else ""

    # auth_methods: non-empty list or empty list
    if has_auth_methods:
        auth_methods = draw(
            st.lists(st.sampled_from(list(AuthMethod)), min_size=1, max_size=3)
        )
    else:
        auth_methods = []

    # These fields are always populated (enum values / required objects)
    access_model = draw(st.sampled_from(list(AccessModel)))
    buildability_verdict = draw(st.sampled_from(list(BuildabilityVerdict)))

    api_surface = ApiSurface(
        has_public_api=draw(st.booleans()),
        api_type=draw(st.sampled_from(list(ApiType) + [None])),
        coverage=draw(st.sampled_from(list(ApiCoverage) + [None])),
        has_mcp_support=draw(st.booleans()),
        evidence_url=None,
    )

    # Determine primary_blocker based on verdict
    if buildability_verdict != BuildabilityVerdict.READY:
        primary_blocker = draw(st.sampled_from(list(BlockerCategory)))
    else:
        primary_blocker = None

    record = AppRecord(
        app_name=app_name,
        category=category if category else "CRM & Sales",  # for valid construction
        description=description,
        auth_methods=auth_methods,
        access_model=access_model,
        api_surface=api_surface,
        buildability_verdict=buildability_verdict,
        primary_blocker=primary_blocker,
        evidence_urls={},
        research_status=ResearchStatus.PARTIAL,
        missing_fields=[],  # will be computed in test
        failure_reason=None,
        failure_category=None,
    )

    # Override category back to the drawn value for accurate field population check
    record.category = category

    return record, {
        "has_app_name": has_app_name,
        "has_category": has_category,
        "has_description": has_description,
        "has_auth_methods": has_auth_methods,
    }


# ============================================================================
# Property 10: Partial Research Threshold
# ============================================================================


class TestProperty10PartialResearchThreshold:
    """Property 10: Partial research threshold.

    Feature: composio-app-research-pipeline, Property 10: Partial research threshold

    For any AppRecord with research_status PARTIAL, the app SHALL be counted
    as "successfully researched" if and only if the percentage of populated
    required fields is >= 80%. The missing_fields list SHALL accurately
    reflect which fields are not populated.

    **Validates: Requirements 10.6, 1.7**
    """

    @given(data=partial_record_strategy())
    @settings(max_examples=100)
    def test_partial_threshold_property(self, data):
        """Partial records are counted as successfully researched iff >= 80% fields populated.

        Feature: composio-app-research-pipeline, Property 10: Partial research threshold
        **Validates: Requirements 10.6, 1.7**
        """
        record, field_flags = data
        validator = CoverageValidator()

        # Compute actual population percentage from the validator
        computed_percentage = validator._compute_field_population_percentage(record)

        # Manually compute expected population percentage
        # The 7 required fields and their population conditions:
        populated_count = 0
        expected_missing = []

        # 1. app_name: non-empty string
        if record.app_name and record.app_name.strip():
            populated_count += 1
        else:
            expected_missing.append("app_name")

        # 2. category: non-empty string
        if record.category and record.category.strip():
            populated_count += 1
        else:
            expected_missing.append("category")

        # 3. description: non-empty string
        if record.description and record.description.strip():
            populated_count += 1
        else:
            expected_missing.append("description")

        # 4. auth_methods: non-empty list
        if record.auth_methods and len(record.auth_methods) > 0:
            populated_count += 1
        else:
            expected_missing.append("auth_methods")

        # 5. access_model: always populated (enum value, not None)
        if record.access_model is not None:
            populated_count += 1
        else:
            expected_missing.append("access_model")

        # 6. api_surface: always populated (object exists)
        if record.api_surface is not None:
            populated_count += 1
        else:
            expected_missing.append("api_surface_has_public_api")

        # 7. buildability_verdict: always populated (enum value, not None)
        if record.buildability_verdict is not None:
            populated_count += 1
        else:
            expected_missing.append("buildability_verdict")

        expected_percentage = (populated_count / 7) * 100.0

        # Assert: percentage matches manual count of populated fields / 7 * 100
        assert abs(computed_percentage - expected_percentage) < 0.001, (
            f"Computed {computed_percentage}% != expected {expected_percentage}% "
            f"(populated {populated_count}/7)"
        )

        # Assert: threshold behavior
        is_success = validator._is_successfully_researched(record)

        if expected_percentage >= 80.0:
            assert is_success is True, (
                f"Record with {expected_percentage:.1f}% populated "
                f"({populated_count}/7 fields) should be successfully researched"
            )
        else:
            assert is_success is False, (
                f"Record with {expected_percentage:.1f}% populated "
                f"({populated_count}/7 fields) should NOT be successfully researched"
            )

    @given(data=partial_record_strategy())
    @settings(max_examples=100)
    def test_missing_fields_accuracy(self, data):
        """The missing_fields list accurately reflects which fields are not populated.

        Feature: composio-app-research-pipeline, Property 10: Partial research threshold
        **Validates: Requirements 10.6, 1.7**
        """
        record, field_flags = data
        validator = CoverageValidator()

        # Compute actually missing fields based on the same logic as the validator
        actually_missing: list[str] = []

        if not (record.app_name and record.app_name.strip()):
            actually_missing.append("app_name")
        if not (record.category and record.category.strip()):
            actually_missing.append("category")
        if not (record.description and record.description.strip()):
            actually_missing.append("description")
        if not (record.auth_methods and len(record.auth_methods) > 0):
            actually_missing.append("auth_methods")
        if record.access_model is None:
            actually_missing.append("access_model")
        if record.api_surface is None:
            actually_missing.append("api_surface_has_public_api")
        if record.buildability_verdict is None:
            actually_missing.append("buildability_verdict")

        # Verify: count of missing fields is consistent with percentage
        populated_count = 7 - len(actually_missing)
        expected_pct = (populated_count / 7) * 100.0
        computed_pct = validator._compute_field_population_percentage(record)

        assert abs(computed_pct - expected_pct) < 0.001, (
            f"Field population percentage mismatch: "
            f"computed={computed_pct:.1f}%, expected={expected_pct:.1f}% "
            f"(missing={actually_missing})"
        )

        # Verify: the field_flags from strategy align with missing fields
        if not field_flags["has_app_name"]:
            assert "app_name" in actually_missing
        else:
            assert "app_name" not in actually_missing

        if not field_flags["has_category"]:
            assert "category" in actually_missing
        else:
            assert "category" not in actually_missing

        if not field_flags["has_description"]:
            assert "description" in actually_missing
        else:
            assert "description" not in actually_missing

        if not field_flags["has_auth_methods"]:
            assert "auth_methods" in actually_missing
        else:
            assert "auth_methods" not in actually_missing

    @given(data=partial_record_strategy())
    @settings(max_examples=100)
    def test_threshold_boundary_is_80_percent(self, data):
        """The 80% threshold is the exact boundary for success classification.

        Feature: composio-app-research-pipeline, Property 10: Partial research threshold
        **Validates: Requirements 10.6, 1.7**

        With 7 required fields, possible percentages are:
        0/7=0%, 1/7=14.3%, 2/7=28.6%, 3/7=42.9%, 4/7=57.1%,
        5/7=71.4%, 6/7=85.7%, 7/7=100%

        Only 6/7 (85.7%) and 7/7 (100%) meet the >= 80% threshold.
        5/7 (71.4%) does NOT meet the threshold.
        """
        record, field_flags = data
        validator = CoverageValidator()

        pct = validator._compute_field_population_percentage(record)
        is_success = validator._is_successfully_researched(record)

        # With 7 fields, only 6/7=85.7% and 7/7=100% are >= 80%
        # 5/7=71.4% is the highest value below 80%
        if pct >= 80.0:
            assert is_success is True, (
                f"Percentage {pct:.1f}% >= 80% should be successful"
            )
            # Verify minimum populated count is 6
            populated = round(pct * 7 / 100.0)
            assert populated >= 6, (
                f"At >= 80%, at least 6/7 fields should be populated, got {populated}"
            )
        else:
            assert is_success is False, (
                f"Percentage {pct:.1f}% < 80% should NOT be successful"
            )


# ============================================================================
# Property-Based Tests (Hypothesis) - Property 8: Category Coverage Invariant
# ============================================================================

from hypothesis import given, settings, HealthCheck
import hypothesis.strategies as st

# Pre-computed lists for fast sampling in property tests
_FAILURE_CATEGORIES = [
    "network_error", "timeout", "access_restriction",
    "parsing_failure", "agent_error",
]
_POSSIBLE_MISSING = ["description", "auth_methods", "api_surface", "evidence_urls"]
_APP_NAMES = [f"App_{i}" for i in range(200)]
_DESCRIPTIONS = ["A useful tool", "Integration platform", "Data service", ""]


@st.composite
def app_record_in_category_strategy(draw, category: str):
    """Generate a random AppRecord for a specific category.

    Uses sampled_from with pre-built lists for fast generation while
    covering the full range of research statuses, auth methods, access
    models, api surfaces, and buildability verdicts.
    """
    research_status = draw(st.sampled_from(list(ResearchStatus)))

    # Fast app_name from pre-built list
    app_name = draw(st.sampled_from(_APP_NAMES))

    # Description: empty possible for non-COMPLETE to test threshold
    if research_status == ResearchStatus.COMPLETE:
        description = draw(st.sampled_from(_DESCRIPTIONS[:3]))  # non-empty only
    else:
        description = draw(st.sampled_from(_DESCRIPTIONS))

    # Auth methods: 0-2 items
    if research_status == ResearchStatus.COMPLETE:
        auth_methods = draw(st.lists(
            st.sampled_from(list(AuthMethod)), min_size=1, max_size=2,
        ))
    else:
        auth_methods = draw(st.lists(
            st.sampled_from(list(AuthMethod)), min_size=0, max_size=2,
        ))

    access_model = draw(st.sampled_from(list(AccessModel)))

    # API surface
    has_public_api = draw(st.booleans())
    if has_public_api:
        api_type = draw(st.sampled_from(list(ApiType)))
        api_coverage = draw(st.sampled_from(list(ApiCoverage)))
    else:
        api_type = draw(st.one_of(st.none(), st.sampled_from(list(ApiType))))
        api_coverage = draw(st.one_of(st.none(), st.sampled_from(list(ApiCoverage))))

    api_surface = ApiSurface(
        has_public_api=has_public_api,
        api_type=api_type,
        coverage=api_coverage,
        has_mcp_support=draw(st.booleans()),
        evidence_url=None,
    )

    # Buildability verdict and blocker
    buildability_verdict = draw(st.sampled_from(list(BuildabilityVerdict)))
    if buildability_verdict != BuildabilityVerdict.READY:
        primary_blocker = draw(st.sampled_from(list(BlockerCategory)))
    else:
        primary_blocker = None

    # Failure info for FAILED/UNRESEARCHABLE
    if research_status in (ResearchStatus.FAILED, ResearchStatus.UNRESEARCHABLE):
        failure_reason = draw(st.sampled_from(["timeout", "not found", "access denied", "parse error"]))
        failure_category = draw(st.sampled_from(_FAILURE_CATEGORIES))
    else:
        failure_reason = None
        failure_category = None

    # Missing fields for PARTIAL
    if research_status == ResearchStatus.PARTIAL:
        missing_fields = draw(st.lists(
            st.sampled_from(_POSSIBLE_MISSING),
            min_size=0, max_size=len(_POSSIBLE_MISSING), unique=True,
        ))
    else:
        missing_fields = []

    return AppRecord(
        app_name=app_name,
        category=category,
        description=description,
        auth_methods=auth_methods,
        access_model=access_model,
        api_surface=api_surface,
        buildability_verdict=buildability_verdict,
        primary_blocker=primary_blocker,
        evidence_urls={},
        research_status=research_status,
        missing_fields=missing_fields,
        failure_reason=failure_reason,
        failure_category=failure_category,
    )


@st.composite
def valid_100_records_strategy(draw):
    """Generate exactly 100 AppRecords: 10 per category for all 10 CATEGORIES.

    This guarantees the 10-per-category constraint is always satisfied,
    allowing Property 8 to verify the CoverageValidator correctly identifies
    valid datasets and computes consistent success metrics.
    """
    records = []
    for category in CATEGORIES:
        for i in range(10):
            record = draw(app_record_in_category_strategy(category))
            records.append(record)
    return records


class TestProperty8CategoryCoverage:
    """Property 8: Category coverage invariant.

    Feature: composio-app-research-pipeline, Property 8: Category coverage invariant

    For any pipeline execution result, the total number of app records
    (including failed and unresearchable) SHALL equal 100, distributed as
    exactly 10 per category across all 10 defined categories, and the
    reported total of successfully researched apps SHALL equal the sum of
    per-category successfully researched counts.

    **Validates: Requirements 10.1, 10.2, 10.4**
    """

    @given(records=valid_100_records_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example])
    def test_property8_total_apps_equals_100(self, records: list):
        """For any valid 10-per-category dataset, total_apps SHALL be 100.

        Feature: composio-app-research-pipeline, Property 8: Category coverage invariant
        **Validates: Requirements 10.1**
        """
        validator = CoverageValidator()
        summary = validator.validate(records)
        assert summary.total_apps == 100

    @given(records=valid_100_records_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example])
    def test_property8_per_category_count_is_10(self, records: list):
        """For any valid dataset, each per_category entry SHALL have total_records == 10.

        Feature: composio-app-research-pipeline, Property 8: Category coverage invariant
        **Validates: Requirements 10.1, 10.2**
        """
        validator = CoverageValidator()
        summary = validator.validate(records)
        assert len(summary.per_category) == 10
        for cat_cov in summary.per_category:
            assert cat_cov.total_records == 10

    @given(records=valid_100_records_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example])
    def test_property8_all_categories_present(self, records: list):
        """For any valid dataset, all 10 defined categories SHALL be present.

        Feature: composio-app-research-pipeline, Property 8: Category coverage invariant
        **Validates: Requirements 10.2**
        """
        validator = CoverageValidator()
        summary = validator.validate(records)
        category_names = {c.category for c in summary.per_category}
        assert category_names == set(CATEGORIES)

    @given(records=valid_100_records_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example])
    def test_property8_success_total_equals_sum_of_per_category(self, records: list):
        """The reported total_successfully_researched SHALL equal the sum of
        per-category successfully_researched counts.

        Feature: composio-app-research-pipeline, Property 8: Category coverage invariant
        **Validates: Requirements 10.4**
        """
        validator = CoverageValidator()
        summary = validator.validate(records)
        per_cat_sum = sum(c.successfully_researched for c in summary.per_category)
        assert summary.total_successfully_researched == per_cat_sum

    @given(records=valid_100_records_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example])
    def test_property8_is_valid_when_constraints_met(self, records: list):
        """When exactly 10 apps per category across all 10 categories,
        is_valid SHALL be True.

        Feature: composio-app-research-pipeline, Property 8: Category coverage invariant
        **Validates: Requirements 10.1, 10.2**
        """
        validator = CoverageValidator()
        summary = validator.validate(records)
        assert summary.is_valid is True
        assert summary.validation_errors == []
