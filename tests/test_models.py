"""Tests for data models including JSON round-trip and field validation invariants."""

import json
import sys

sys.path.insert(0, "src")

import pytest

from composio_research.models import (
    AccessDistribution,
    AccessModel,
    ApiCoverage,
    ApiSurface,
    ApiType,
    AppRecord,
    AuthDistribution,
    AuthMethod,
    BlockerCategory,
    BlockerRank,
    BuildabilityVerdict,
    Discrepancy,
    InterventionEntry,
    Observation,
    PassMetrics,
    PatternAnalysis,
    ResearchStatus,
    VerificationMetrics,
)


# ============================================================================
# Enum Tests
# ============================================================================


class TestEnums:
    """Tests for all enum definitions."""

    def test_auth_method_values(self):
        assert AuthMethod.OAUTH2 == "oauth2"
        assert AuthMethod.API_KEY == "api_key"
        assert AuthMethod.BASIC == "basic"
        assert AuthMethod.TOKEN == "token"
        assert AuthMethod.OTHER == "other"
        assert len(AuthMethod) == 5

    def test_access_model_values(self):
        assert AccessModel.SELF_SERVE == "self_serve"
        assert AccessModel.GATED == "gated"
        assert len(AccessModel) == 2

    def test_api_type_values(self):
        assert ApiType.REST == "rest"
        assert ApiType.GRAPHQL == "graphql"
        assert ApiType.BOTH == "both"
        assert ApiType.NONE == "none"
        assert len(ApiType) == 4

    def test_api_coverage_values(self):
        assert ApiCoverage.FULL == "full"
        assert ApiCoverage.PARTIAL == "partial"
        assert ApiCoverage.MINIMAL == "minimal"
        assert len(ApiCoverage) == 3

    def test_buildability_verdict_values(self):
        assert BuildabilityVerdict.READY == "ready"
        assert BuildabilityVerdict.FEASIBLE == "feasible"
        assert BuildabilityVerdict.BLOCKED == "blocked"
        assert len(BuildabilityVerdict) == 3

    def test_blocker_category_values(self):
        assert BlockerCategory.NO_PUBLIC_API == "no_public_api"
        assert BlockerCategory.INSUFFICIENT_COVERAGE == "insufficient_coverage"
        assert BlockerCategory.RESTRICTIVE_AUTH == "restrictive_auth"
        assert BlockerCategory.RATE_LIMITS == "rate_limits"
        assert BlockerCategory.MISSING_DOCUMENTATION == "missing_documentation"
        assert len(BlockerCategory) == 5

    def test_research_status_values(self):
        assert ResearchStatus.COMPLETE == "complete"
        assert ResearchStatus.PARTIAL == "partial"
        assert ResearchStatus.FAILED == "failed"
        assert ResearchStatus.UNRESEARCHABLE == "unresearchable"
        assert len(ResearchStatus) == 4

    def test_enums_are_str_subclass(self):
        """All enums should be usable as strings for JSON serialization."""
        assert isinstance(AuthMethod.OAUTH2, str)
        assert isinstance(AccessModel.SELF_SERVE, str)
        assert isinstance(ApiType.REST, str)
        assert isinstance(ApiCoverage.FULL, str)
        assert isinstance(BuildabilityVerdict.READY, str)
        assert isinstance(BlockerCategory.NO_PUBLIC_API, str)
        assert isinstance(ResearchStatus.COMPLETE, str)


# ============================================================================
# ApiSurface Tests
# ============================================================================


class TestApiSurface:
    """Tests for ApiSurface dataclass."""

    def test_round_trip_all_fields(self):
        surface = ApiSurface(
            has_public_api=True,
            api_type=ApiType.REST,
            coverage=ApiCoverage.FULL,
            has_mcp_support=True,
            evidence_url="https://example.com/api",
        )
        assert ApiSurface.from_dict(surface.to_dict()) == surface

    def test_round_trip_none_fields(self):
        surface = ApiSurface(
            has_public_api=False,
            api_type=None,
            coverage=None,
            has_mcp_support=False,
            evidence_url=None,
        )
        assert ApiSurface.from_dict(surface.to_dict()) == surface

    def test_to_dict_serializes_enums_as_strings(self):
        surface = ApiSurface(
            has_public_api=True,
            api_type=ApiType.GRAPHQL,
            coverage=ApiCoverage.PARTIAL,
            has_mcp_support=False,
            evidence_url=None,
        )
        d = surface.to_dict()
        assert d["api_type"] == "graphql"
        assert d["coverage"] == "partial"

    def test_json_serializable(self):
        surface = ApiSurface(
            has_public_api=True,
            api_type=ApiType.BOTH,
            coverage=ApiCoverage.MINIMAL,
            has_mcp_support=True,
            evidence_url="https://docs.example.com",
        )
        json_str = json.dumps(surface.to_dict())
        assert json.loads(json_str) == surface.to_dict()


# ============================================================================
# AppRecord Tests
# ============================================================================


class TestAppRecord:
    """Tests for AppRecord dataclass."""

    def _make_complete_record(self) -> AppRecord:
        return AppRecord(
            app_name="Salesforce",
            category="CRM & Sales",
            description="Enterprise CRM platform with extensive API",
            auth_methods=[AuthMethod.OAUTH2],
            access_model=AccessModel.SELF_SERVE,
            api_surface=ApiSurface(
                has_public_api=True,
                api_type=ApiType.REST,
                coverage=ApiCoverage.FULL,
                has_mcp_support=True,
                evidence_url="https://developer.salesforce.com",
            ),
            buildability_verdict=BuildabilityVerdict.READY,
            primary_blocker=None,
            evidence_urls={"auth": "https://example.com/auth"},
            research_status=ResearchStatus.COMPLETE,
            missing_fields=[],
            failure_reason=None,
            failure_category=None,
        )

    def _make_failed_record(self) -> AppRecord:
        return AppRecord(
            app_name="ClosedApp",
            category="Finance & Fintech",
            description="App that could not be researched",
            auth_methods=[],
            access_model=AccessModel.GATED,
            api_surface=ApiSurface(
                has_public_api=False,
                api_type=None,
                coverage=None,
                has_mcp_support=False,
                evidence_url=None,
            ),
            buildability_verdict=BuildabilityVerdict.BLOCKED,
            primary_blocker=BlockerCategory.NO_PUBLIC_API,
            evidence_urls={},
            research_status=ResearchStatus.FAILED,
            missing_fields=["auth_methods", "api_surface"],
            failure_reason="Network timeout after 3 retries",
            failure_category="timeout",
        )

    def test_round_trip_complete_record(self):
        record = self._make_complete_record()
        assert AppRecord.from_dict(record.to_dict()) == record

    def test_round_trip_failed_record(self):
        record = self._make_failed_record()
        assert AppRecord.from_dict(record.to_dict()) == record

    def test_round_trip_multiple_auth_methods(self):
        record = self._make_complete_record()
        record.auth_methods = [AuthMethod.OAUTH2, AuthMethod.API_KEY, AuthMethod.TOKEN]
        assert AppRecord.from_dict(record.to_dict()) == record

    def test_to_dict_serializes_nested_api_surface(self):
        record = self._make_complete_record()
        d = record.to_dict()
        assert isinstance(d["api_surface"], dict)
        assert d["api_surface"]["api_type"] == "rest"

    def test_to_dict_enum_as_string(self):
        record = self._make_complete_record()
        d = record.to_dict()
        assert d["access_model"] == "self_serve"
        assert d["buildability_verdict"] == "ready"
        assert d["research_status"] == "complete"
        assert d["auth_methods"] == ["oauth2"]

    def test_to_dict_none_blocker(self):
        record = self._make_complete_record()
        d = record.to_dict()
        assert d["primary_blocker"] is None

    def test_to_dict_present_blocker(self):
        record = self._make_failed_record()
        d = record.to_dict()
        assert d["primary_blocker"] == "no_public_api"

    def test_json_independently_parseable(self):
        """Each AppRecord JSON should be parseable without other files (Req 9.7)."""
        record = self._make_complete_record()
        json_str = json.dumps(record.to_dict())
        parsed = json.loads(json_str)
        restored = AppRecord.from_dict(parsed)
        assert restored == record


# ============================================================================
# PatternAnalysis Tests
# ============================================================================


class TestPatternAnalysis:
    """Tests for pattern analysis dataclasses."""

    def test_auth_distribution_round_trip(self):
        ad = AuthDistribution(
            per_category={"CRM & Sales": {"oauth2": 7, "api_key": 3}},
            overall={"oauth2": 40, "api_key": 30, "token": 20, "basic": 10},
            dominant_per_category={"CRM & Sales": "oauth2"},
        )
        assert AuthDistribution.from_dict(ad.to_dict()) == ad

    def test_access_distribution_round_trip(self):
        ad = AccessDistribution(
            per_category={"CRM & Sales": {"self_serve": 7, "gated": 3}},
            category_classification={"CRM & Sales": "majority_self_serve"},
        )
        assert AccessDistribution.from_dict(ad.to_dict()) == ad

    def test_blocker_rank_round_trip(self):
        br = BlockerRank(blocker="no_public_api", count=15, rank=1)
        assert BlockerRank.from_dict(br.to_dict()) == br

    def test_observation_round_trip(self):
        obs = Observation(
            title="OAuth2 dominates CRM",
            description="7 of 10 CRM apps use OAuth2",
            supporting_data="70% of CRM & Sales category",
            opportunity="Build OAuth2 connector template for CRM apps",
        )
        assert Observation.from_dict(obs.to_dict()) == obs

    def test_full_pattern_analysis_round_trip(self):
        pa = PatternAnalysis(
            auth_distribution=AuthDistribution(
                per_category={"CRM & Sales": {"oauth2": 7}},
                overall={"oauth2": 40},
                dominant_per_category={"CRM & Sales": "oauth2"},
            ),
            access_distribution=AccessDistribution(
                per_category={"CRM & Sales": {"self_serve": 6, "gated": 4}},
                category_classification={"CRM & Sales": "majority_self_serve"},
            ),
            blocker_rankings=[
                BlockerRank(blocker="no_public_api", count=15, rank=1),
                BlockerRank(blocker="rate_limits", count=10, rank=2),
            ],
            easy_win_apps=["Salesforce", "HubSpot"],
            outreach_required_apps=["ClosedApp"],
            observations=[
                Observation(
                    title="Obs1", description="d1", supporting_data="s1", opportunity="o1"
                ),
                Observation(
                    title="Obs2", description="d2", supporting_data="s2", opportunity="o2"
                ),
                Observation(
                    title="Obs3", description="d3", supporting_data="s3", opportunity="o3"
                ),
            ],
        )
        assert PatternAnalysis.from_dict(pa.to_dict()) == pa

    def test_pattern_analysis_json_serializable(self):
        pa = PatternAnalysis(
            auth_distribution=AuthDistribution(
                per_category={}, overall={}, dominant_per_category={}
            ),
            access_distribution=AccessDistribution(
                per_category={}, category_classification={}
            ),
            blocker_rankings=[],
            easy_win_apps=[],
            outreach_required_apps=[],
            observations=[],
        )
        json_str = json.dumps(pa.to_dict())
        assert json.loads(json_str) == pa.to_dict()


# ============================================================================
# Verification Model Tests
# ============================================================================


class TestVerificationModels:
    """Tests for verification-related dataclasses."""

    def test_discrepancy_round_trip(self):
        d = Discrepancy(
            app_name="TestApp",
            field_name="auth_methods",
            original_value="basic",
            corrected_value="oauth2",
            resolution_status="resolved",
            evidence_urls_checked=["https://example.com/docs"],
            reason="Found updated OAuth2 documentation",
        )
        assert Discrepancy.from_dict(d.to_dict()) == d

    def test_discrepancy_with_none_fields(self):
        d = Discrepancy(
            app_name="TestApp",
            field_name="api_surface",
            original_value="rest",
            corrected_value=None,
            resolution_status="unresolved",
            evidence_urls_checked=["https://example.com/api"],
            reason=None,
        )
        assert Discrepancy.from_dict(d.to_dict()) == d

    def test_pass_metrics_round_trip(self):
        pm = PassMetrics(
            pass_number=1,
            accuracy_percentage=85.5,
            total_data_points=500,
            confirmed_points=427,
            discrepancies_found=73,
            corrections_applied=50,
        )
        assert PassMetrics.from_dict(pm.to_dict()) == pm

    def test_verification_metrics_round_trip(self):
        vm = VerificationMetrics(
            passes_completed=3,
            per_pass_metrics=[
                PassMetrics(
                    pass_number=1,
                    accuracy_percentage=70.0,
                    total_data_points=100,
                    confirmed_points=70,
                    discrepancies_found=30,
                    corrections_applied=20,
                ),
                PassMetrics(
                    pass_number=2,
                    accuracy_percentage=85.0,
                    total_data_points=100,
                    confirmed_points=85,
                    discrepancies_found=15,
                    corrections_applied=10,
                ),
                PassMetrics(
                    pass_number=3,
                    accuracy_percentage=92.0,
                    total_data_points=100,
                    confirmed_points=92,
                    discrepancies_found=8,
                    corrections_applied=5,
                ),
            ],
            discrepancy_log=[
                Discrepancy(
                    app_name="App1",
                    field_name="auth_methods",
                    original_value="basic",
                    corrected_value="oauth2",
                    resolution_status="resolved",
                    evidence_urls_checked=["https://example.com"],
                    reason="Updated docs",
                ),
            ],
            overall_accuracy=92.0,
            requires_manual_review=False,
        )
        assert VerificationMetrics.from_dict(vm.to_dict()) == vm

    def test_verification_metrics_manual_review_flag(self):
        vm = VerificationMetrics(
            passes_completed=2,
            per_pass_metrics=[
                PassMetrics(
                    pass_number=1,
                    accuracy_percentage=60.0,
                    total_data_points=100,
                    confirmed_points=60,
                    discrepancies_found=40,
                    corrections_applied=10,
                ),
            ],
            discrepancy_log=[],
            overall_accuracy=60.0,
            requires_manual_review=True,
        )
        d = vm.to_dict()
        assert d["requires_manual_review"] is True
        assert VerificationMetrics.from_dict(d) == vm


# ============================================================================
# InterventionEntry Tests
# ============================================================================


class TestInterventionEntry:
    """Tests for InterventionEntry dataclass."""

    def test_round_trip_with_data_point(self):
        ie = InterventionEntry(
            app_name="SomeApp",
            pipeline_stage="researcher",
            reason="API documentation requires authenticated access",
            timestamp="2024-01-15T10:30:00Z",
            data_point="api_surface",
        )
        assert InterventionEntry.from_dict(ie.to_dict()) == ie

    def test_round_trip_without_data_point(self):
        ie = InterventionEntry(
            app_name="OtherApp",
            pipeline_stage="verifier",
            reason="URL inaccessible",
            timestamp="2024-01-15T11:00:00Z",
            data_point=None,
        )
        assert InterventionEntry.from_dict(ie.to_dict()) == ie

    def test_json_serializable(self):
        ie = InterventionEntry(
            app_name="App",
            pipeline_stage="pattern_analyzer",
            reason="Invalid input",
            timestamp="2024-06-01T00:00:00Z",
            data_point=None,
        )
        json_str = json.dumps(ie.to_dict())
        assert json.loads(json_str) == ie.to_dict()


# ============================================================================
# Property-Based Tests (Hypothesis)
# ============================================================================


from hypothesis import given, strategies as st

from composio_research.config import CATEGORIES


# -- Hypothesis Strategies for Data Models --

# Strategy for generating valid ApiSurface instances
api_surface_strategy = st.builds(
    ApiSurface,
    has_public_api=st.booleans(),
    api_type=st.one_of(st.none(), st.sampled_from(ApiType)),
    coverage=st.one_of(st.none(), st.sampled_from(ApiCoverage)),
    has_mcp_support=st.booleans(),
    evidence_url=st.one_of(
        st.none(),
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
            min_size=1,
            max_size=100,
        ).map(lambda s: f"https://{s}"),
    ),
)

# Strategy for generating valid AppRecord instances covering all statuses,
# verdicts, and optional field combinations.
app_record_strategy = st.builds(
    AppRecord,
    app_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=1,
        max_size=50,
    ),
    category=st.sampled_from(CATEGORIES),
    description=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "P")),
        min_size=1,
        max_size=120,
    ),
    auth_methods=st.lists(st.sampled_from(AuthMethod), min_size=0, max_size=5),
    access_model=st.sampled_from(AccessModel),
    api_surface=api_surface_strategy,
    buildability_verdict=st.sampled_from(BuildabilityVerdict),
    primary_blocker=st.one_of(st.none(), st.sampled_from(BlockerCategory)),
    evidence_urls=st.dictionaries(
        keys=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=30,
        ),
        values=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
            min_size=1,
            max_size=100,
        ).map(lambda s: f"https://{s}"),
        max_size=5,
    ),
    research_status=st.sampled_from(ResearchStatus),
    missing_fields=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=30,
        ),
        max_size=5,
    ),
    failure_reason=st.one_of(
        st.none(),
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "P")),
            min_size=1,
            max_size=200,
        ),
    ),
    failure_category=st.one_of(
        st.none(),
        st.sampled_from(
            ["network_error", "timeout", "access_restriction", "parsing_failure", "agent_error"]
        ),
    ),
)


class TestAppRecordJsonRoundTrip:
    """Property-based tests for AppRecord JSON round-trip.

    Feature: composio-app-research-pipeline, Property 6: App record JSON round-trip

    Validates: Requirements 1.7, 8.6, 9.1, 9.7
    """

    @given(record=app_record_strategy)
    def test_round_trip_preserves_all_fields(self, record: AppRecord):
        """For any valid AppRecord, serializing to dict and deserializing back
        produces an equivalent AppRecord with all fields preserved.

        **Validates: Requirements 1.7**
        """
        restored = AppRecord.from_dict(record.to_dict())
        assert restored == record

    @given(record=app_record_strategy)
    def test_to_dict_produces_valid_json(self, record: AppRecord):
        """For any valid AppRecord, to_dict() output is JSON-serializable
        without errors.

        **Validates: Requirements 9.1**
        """
        d = record.to_dict()
        json_str = json.dumps(d)
        assert isinstance(json_str, str)
        assert len(json_str) > 0

    @given(record=app_record_strategy)
    def test_json_dumps_loads_round_trip(self, record: AppRecord):
        """For any valid AppRecord, serializing to JSON string and parsing back
        produces a dict that can be deserialized to an equivalent AppRecord.
        This ensures the JSON is independently parseable (Req 9.7).

        **Validates: Requirements 9.7**
        """
        d = record.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        restored = AppRecord.from_dict(parsed)
        assert restored == record

    @given(record=app_record_strategy)
    def test_no_fields_omitted_in_serialization(self, record: AppRecord):
        """For any valid AppRecord, the serialized dict contains all expected
        top-level keys — no fields are silently dropped.

        **Validates: Requirements 8.6**
        """
        d = record.to_dict()
        expected_keys = {
            "app_name",
            "category",
            "description",
            "auth_methods",
            "access_model",
            "api_surface",
            "buildability_verdict",
            "primary_blocker",
            "evidence_urls",
            "research_status",
            "missing_fields",
            "failure_reason",
            "failure_category",
        }
        assert set(d.keys()) == expected_keys

    @given(record=app_record_strategy)
    def test_api_surface_nested_round_trip(self, record: AppRecord):
        """For any valid AppRecord, the nested ApiSurface also round-trips
        correctly through JSON serialization.

        **Validates: Requirements 9.1**
        """
        d = record.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        restored = AppRecord.from_dict(parsed)
        assert restored.api_surface == record.api_surface


# ============================================================================
# Property 9: Conditional Field Population Invariants
# Feature: composio-app-research-pipeline, Property 9: Conditional field population invariants
# ============================================================================

from hypothesis import given
from hypothesis import strategies as st


# ============================================================================
# Hypothesis Strategies for Property 9
# ============================================================================

# Shared strategies for common fields
_app_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    min_size=1,
    max_size=50,
)
_category_st = st.sampled_from(
    [
        "CRM & Sales",
        "Support & Helpdesk",
        "Communications & Messaging",
        "Marketing/Ads/Email/Social",
        "Ecommerce",
        "Data/SEO/Scraping",
        "Developer/Infra/Data",
        "Productivity & PM",
        "Finance & Fintech",
        "AI/Research/Media",
    ]
)
_description_st = st.text(min_size=1, max_size=120)
_auth_methods_st = st.lists(st.sampled_from(list(AuthMethod)), min_size=1, max_size=5)
_evidence_urls_st = st.dictionaries(
    keys=st.text(min_size=1, max_size=30),
    values=st.text(min_size=1, max_size=100),
    min_size=0,
    max_size=5,
)
_missing_fields_st = st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5)

# Strategy for ApiSurface with NO public API (api_type and coverage can be None)
_no_public_api_surface_st = st.builds(
    ApiSurface,
    has_public_api=st.just(False),
    api_type=st.none(),
    coverage=st.none(),
    has_mcp_support=st.booleans(),
    evidence_url=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
)

# Strategy for ApiSurface WITH public API (api_type and coverage MUST be non-None)
_public_api_surface_st = st.builds(
    ApiSurface,
    has_public_api=st.just(True),
    api_type=st.sampled_from(list(ApiType)),
    coverage=st.sampled_from(list(ApiCoverage)),
    has_mcp_support=st.booleans(),
    evidence_url=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
)

# Combined ApiSurface strategy (either with or without public API)
_any_api_surface_st = st.one_of(_no_public_api_surface_st, _public_api_surface_st)

# Failure category values matching error handling design
_failure_category_st = st.sampled_from(
    ["network_error", "timeout", "access_restriction", "parsing_failure", "agent_error"]
)


class TestProperty9ConditionalFields:
    """Property 9: Conditional field population invariants.

    Feature: composio-app-research-pipeline, Property 9: Conditional field population invariants

    Verifies three invariants:
    (a) if buildability_verdict is not READY, primary_blocker is non-None
    (b) if api_surface.has_public_api is True, api_type and coverage are non-None
    (c) if research_status is FAILED or UNRESEARCHABLE, failure_reason and failure_category are non-None

    Validates: Requirements 1.5, 1.6, 8.1
    """

    @given(
        app_name=_app_name_st,
        category=_category_st,
        description=_description_st,
        auth_methods=_auth_methods_st,
        access_model=st.sampled_from(list(AccessModel)),
        api_surface=_any_api_surface_st,
        buildability_verdict=st.sampled_from(
            [BuildabilityVerdict.FEASIBLE, BuildabilityVerdict.BLOCKED]
        ),
        primary_blocker=st.sampled_from(list(BlockerCategory)),
        evidence_urls=_evidence_urls_st,
        research_status=st.sampled_from(list(ResearchStatus)),
        missing_fields=_missing_fields_st,
    )
    def test_property9_blocker_present_when_not_ready(
        self,
        app_name,
        category,
        description,
        auth_methods,
        access_model,
        api_surface,
        buildability_verdict,
        primary_blocker,
        evidence_urls,
        research_status,
        missing_fields,
    ):
        """Property 9a: When buildability_verdict is FEASIBLE or BLOCKED,
        primary_blocker MUST be non-None.

        Validates: Requirements 1.5, 1.6, 8.1

        Generates AppRecords with non-READY verdicts ensuring primary_blocker
        is always provided, then verifies the invariant holds through round-trip.
        """
        # Determine failure fields based on research_status
        if research_status in (ResearchStatus.FAILED, ResearchStatus.UNRESEARCHABLE):
            failure_reason = "Test failure reason"
            failure_category = "network_error"
        else:
            failure_reason = None
            failure_category = None

        record = AppRecord(
            app_name=app_name,
            category=category,
            description=description,
            auth_methods=auth_methods,
            access_model=access_model,
            api_surface=api_surface,
            buildability_verdict=buildability_verdict,
            primary_blocker=primary_blocker,
            evidence_urls=evidence_urls,
            research_status=research_status,
            missing_fields=missing_fields,
            failure_reason=failure_reason,
            failure_category=failure_category,
        )

        # Invariant (a): non-READY verdict requires non-None primary_blocker
        assert record.buildability_verdict != BuildabilityVerdict.READY
        assert record.primary_blocker is not None

        # Verify invariant holds after round-trip serialization
        restored = AppRecord.from_dict(record.to_dict())
        assert restored.buildability_verdict != BuildabilityVerdict.READY
        assert restored.primary_blocker is not None

    @given(
        app_name=_app_name_st,
        category=_category_st,
        description=_description_st,
        auth_methods=_auth_methods_st,
        access_model=st.sampled_from(list(AccessModel)),
        api_type=st.sampled_from(list(ApiType)),
        coverage=st.sampled_from(list(ApiCoverage)),
        has_mcp_support=st.booleans(),
        evidence_url=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        buildability_verdict=st.sampled_from(list(BuildabilityVerdict)),
        primary_blocker=st.one_of(st.none(), st.sampled_from(list(BlockerCategory))),
        evidence_urls=_evidence_urls_st,
        research_status=st.sampled_from(list(ResearchStatus)),
        missing_fields=_missing_fields_st,
    )
    def test_property9_api_fields_present_when_public_api(
        self,
        app_name,
        category,
        description,
        auth_methods,
        access_model,
        api_type,
        coverage,
        has_mcp_support,
        evidence_url,
        buildability_verdict,
        primary_blocker,
        evidence_urls,
        research_status,
        missing_fields,
    ):
        """Property 9b: When api_surface.has_public_api is True,
        api_type and coverage MUST be non-None.

        Validates: Requirements 1.5, 1.6, 8.1

        Generates AppRecords with has_public_api=True ensuring api_type and
        coverage are always populated, then verifies invariant through round-trip.
        """
        # Build ApiSurface with has_public_api=True and non-None api_type/coverage
        api_surface = ApiSurface(
            has_public_api=True,
            api_type=api_type,
            coverage=coverage,
            has_mcp_support=has_mcp_support,
            evidence_url=evidence_url,
        )

        # Ensure blocker is present when verdict is not READY
        if buildability_verdict != BuildabilityVerdict.READY and primary_blocker is None:
            primary_blocker = BlockerCategory.NO_PUBLIC_API

        # Determine failure fields based on research_status
        if research_status in (ResearchStatus.FAILED, ResearchStatus.UNRESEARCHABLE):
            failure_reason = "Test failure reason"
            failure_category = "network_error"
        else:
            failure_reason = None
            failure_category = None

        record = AppRecord(
            app_name=app_name,
            category=category,
            description=description,
            auth_methods=auth_methods,
            access_model=access_model,
            api_surface=api_surface,
            buildability_verdict=buildability_verdict,
            primary_blocker=primary_blocker,
            evidence_urls=evidence_urls,
            research_status=research_status,
            missing_fields=missing_fields,
            failure_reason=failure_reason,
            failure_category=failure_category,
        )

        # Invariant (b): public API requires non-None api_type and coverage
        assert record.api_surface.has_public_api is True
        assert record.api_surface.api_type is not None
        assert record.api_surface.coverage is not None

        # Verify invariant holds after round-trip serialization
        restored = AppRecord.from_dict(record.to_dict())
        assert restored.api_surface.has_public_api is True
        assert restored.api_surface.api_type is not None
        assert restored.api_surface.coverage is not None

    @given(
        app_name=_app_name_st,
        category=_category_st,
        description=_description_st,
        auth_methods=_auth_methods_st,
        access_model=st.sampled_from(list(AccessModel)),
        api_surface=_any_api_surface_st,
        buildability_verdict=st.sampled_from(list(BuildabilityVerdict)),
        primary_blocker=st.one_of(st.none(), st.sampled_from(list(BlockerCategory))),
        evidence_urls=_evidence_urls_st,
        research_status=st.sampled_from(
            [ResearchStatus.FAILED, ResearchStatus.UNRESEARCHABLE]
        ),
        missing_fields=_missing_fields_st,
        failure_reason=st.text(min_size=1, max_size=200),
        failure_category=_failure_category_st,
    )
    def test_property9_failure_fields_present_when_failed(
        self,
        app_name,
        category,
        description,
        auth_methods,
        access_model,
        api_surface,
        buildability_verdict,
        primary_blocker,
        evidence_urls,
        research_status,
        missing_fields,
        failure_reason,
        failure_category,
    ):
        """Property 9c: When research_status is FAILED or UNRESEARCHABLE,
        failure_reason and failure_category MUST be non-None.

        Validates: Requirements 1.5, 1.6, 8.1

        Generates AppRecords with FAILED/UNRESEARCHABLE status ensuring failure
        fields are always populated, then verifies invariant through round-trip.
        """
        # Ensure blocker is present when verdict is not READY
        if buildability_verdict != BuildabilityVerdict.READY and primary_blocker is None:
            primary_blocker = BlockerCategory.NO_PUBLIC_API

        record = AppRecord(
            app_name=app_name,
            category=category,
            description=description,
            auth_methods=auth_methods,
            access_model=access_model,
            api_surface=api_surface,
            buildability_verdict=buildability_verdict,
            primary_blocker=primary_blocker,
            evidence_urls=evidence_urls,
            research_status=research_status,
            missing_fields=missing_fields,
            failure_reason=failure_reason,
            failure_category=failure_category,
        )

        # Invariant (c): FAILED/UNRESEARCHABLE requires non-None failure fields
        assert record.research_status in (
            ResearchStatus.FAILED,
            ResearchStatus.UNRESEARCHABLE,
        )
        assert record.failure_reason is not None
        assert record.failure_category is not None

        # Verify invariant holds after round-trip serialization
        restored = AppRecord.from_dict(record.to_dict())
        assert restored.research_status in (
            ResearchStatus.FAILED,
            ResearchStatus.UNRESEARCHABLE,
        )
        assert restored.failure_reason is not None
        assert restored.failure_category is not None
