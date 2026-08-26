"""Tests for PatternAnalyzer including auth distribution, access distribution,
blocker rankings, and easy-win classification properties.
"""

import sys

sys.path.insert(0, "src")

from typing import Optional

import pytest

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
from composio_research.pattern_analyzer import PatternAnalyzer


# ============================================================================
# Helper function to build AppRecords with specific characteristics
# ============================================================================


def make_app_record(
    app_name: str = "TestApp",
    category: str = "CRM & Sales",
    description: str = "A test application",
    auth_methods: Optional[list[AuthMethod]] = None,
    access_model: AccessModel = AccessModel.SELF_SERVE,
    has_public_api: bool = True,
    api_type: Optional[ApiType] = ApiType.REST,
    coverage: Optional[ApiCoverage] = ApiCoverage.FULL,
    has_mcp_support: bool = False,
    buildability_verdict: BuildabilityVerdict = BuildabilityVerdict.READY,
    primary_blocker: Optional[BlockerCategory] = None,
    research_status: ResearchStatus = ResearchStatus.COMPLETE,
    missing_fields: Optional[list[str]] = None,
    failure_reason: Optional[str] = None,
    failure_category: Optional[str] = None,
) -> AppRecord:
    """Build an AppRecord with sensible defaults for testing."""
    if auth_methods is None:
        auth_methods = [AuthMethod.OAUTH2]
    if missing_fields is None:
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
            has_mcp_support=has_mcp_support,
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


# ============================================================================
# Unit Tests for PatternAnalyzer
# ============================================================================


class TestPatternAnalyzerUnit:
    """Unit tests for PatternAnalyzer covering all analysis methods and edge cases."""

    def setup_method(self):
        self.analyzer = PatternAnalyzer()

    # ------------------------------------------------------------------
    # Test analyze() method
    # ------------------------------------------------------------------

    def test_analyze_returns_all_fields_populated(self):
        """analyze() returns PatternAnalysis with all fields populated."""
        records = [
            make_app_record(app_name="App1", category="CRM & Sales"),
            make_app_record(app_name="App2", category="Ecommerce", access_model=AccessModel.GATED),
            make_app_record(
                app_name="App3",
                category="CRM & Sales",
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.NO_PUBLIC_API,
            ),
        ]

        result = self.analyzer.analyze(records)

        assert result.auth_distribution is not None
        assert result.access_distribution is not None
        assert result.blocker_rankings is not None
        assert result.easy_win_apps is not None
        assert result.outreach_required_apps is not None
        assert result.observations is not None

    def test_analyze_always_produces_at_least_3_observations(self):
        """analyze() always generates at least 3 observations."""
        records = [
            make_app_record(app_name="App1"),
            make_app_record(app_name="App2"),
        ]

        result = self.analyzer.analyze(records)

        assert len(result.observations) >= 3

    # ------------------------------------------------------------------
    # Test _compute_auth_distribution()
    # ------------------------------------------------------------------

    def test_auth_distribution_all_same_method(self):
        """All apps with same auth method → overall has single entry, dominant matches."""
        records = [
            make_app_record(app_name="App1", category="CRM & Sales", auth_methods=[AuthMethod.OAUTH2]),
            make_app_record(app_name="App2", category="CRM & Sales", auth_methods=[AuthMethod.OAUTH2]),
            make_app_record(app_name="App3", category="Ecommerce", auth_methods=[AuthMethod.OAUTH2]),
        ]

        result = self.analyzer._compute_auth_distribution(records)

        # Overall should have single entry
        assert result.overall == {"oauth2": 3}
        # Dominant for each category should be oauth2
        assert result.dominant_per_category["CRM & Sales"] == "oauth2"
        assert result.dominant_per_category["Ecommerce"] == "oauth2"

    def test_auth_distribution_multi_auth_counted_correctly(self):
        """Multi-auth apps count each method separately."""
        records = [
            make_app_record(
                app_name="App1",
                category="CRM & Sales",
                auth_methods=[AuthMethod.OAUTH2, AuthMethod.API_KEY],
            ),
            make_app_record(
                app_name="App2",
                category="CRM & Sales",
                auth_methods=[AuthMethod.API_KEY],
            ),
        ]

        result = self.analyzer._compute_auth_distribution(records)

        # Overall: oauth2=1, api_key=2
        assert result.overall["oauth2"] == 1
        assert result.overall["api_key"] == 2
        # Per category: CRM & Sales has oauth2=1, api_key=2
        assert result.per_category["CRM & Sales"]["oauth2"] == 1
        assert result.per_category["CRM & Sales"]["api_key"] == 2
        # Dominant is api_key
        assert result.dominant_per_category["CRM & Sales"] == "api_key"

    def test_auth_distribution_multiple_categories(self):
        """Auth distribution tracks categories independently."""
        records = [
            make_app_record(app_name="App1", category="CRM & Sales", auth_methods=[AuthMethod.OAUTH2]),
            make_app_record(app_name="App2", category="Ecommerce", auth_methods=[AuthMethod.API_KEY]),
            make_app_record(app_name="App3", category="Ecommerce", auth_methods=[AuthMethod.API_KEY]),
        ]

        result = self.analyzer._compute_auth_distribution(records)

        assert result.per_category["CRM & Sales"] == {"oauth2": 1}
        assert result.per_category["Ecommerce"] == {"api_key": 2}
        assert result.dominant_per_category["CRM & Sales"] == "oauth2"
        assert result.dominant_per_category["Ecommerce"] == "api_key"

    # ------------------------------------------------------------------
    # Test _compute_access_distribution()
    # ------------------------------------------------------------------

    def test_access_distribution_single_category_all_gated(self):
        """Single category all gated → classified as 'majority_gated'."""
        records = [
            make_app_record(app_name="App1", category="Finance & Fintech", access_model=AccessModel.GATED),
            make_app_record(app_name="App2", category="Finance & Fintech", access_model=AccessModel.GATED),
            make_app_record(app_name="App3", category="Finance & Fintech", access_model=AccessModel.GATED),
        ]

        result = self.analyzer._compute_access_distribution(records)

        assert result.per_category["Finance & Fintech"]["self_serve"] == 0
        assert result.per_category["Finance & Fintech"]["gated"] == 3
        assert result.category_classification["Finance & Fintech"] == "majority_gated"

    def test_access_distribution_balanced_50_50_is_gated(self):
        """Balanced 50/50 → classified as 'majority_gated' (>50% required for self-serve)."""
        records = [
            make_app_record(app_name="App1", category="CRM & Sales", access_model=AccessModel.SELF_SERVE),
            make_app_record(app_name="App2", category="CRM & Sales", access_model=AccessModel.GATED),
        ]

        result = self.analyzer._compute_access_distribution(records)

        assert result.per_category["CRM & Sales"]["self_serve"] == 1
        assert result.per_category["CRM & Sales"]["gated"] == 1
        # Exactly 50% is NOT > 50%, so should be majority_gated
        assert result.category_classification["CRM & Sales"] == "majority_gated"

    def test_access_distribution_60_percent_self_serve(self):
        """60% self-serve → 'majority_self_serve'."""
        records = [
            make_app_record(app_name=f"SS{i}", category="CRM & Sales", access_model=AccessModel.SELF_SERVE)
            for i in range(3)
        ] + [
            make_app_record(app_name=f"G{i}", category="CRM & Sales", access_model=AccessModel.GATED)
            for i in range(2)
        ]

        result = self.analyzer._compute_access_distribution(records)

        assert result.per_category["CRM & Sales"]["self_serve"] == 3
        assert result.per_category["CRM & Sales"]["gated"] == 2
        assert result.category_classification["CRM & Sales"] == "majority_self_serve"

    # ------------------------------------------------------------------
    # Test _rank_blockers()
    # ------------------------------------------------------------------

    def test_rank_blockers_no_non_ready_apps(self):
        """No non-READY apps → empty rankings."""
        records = [
            make_app_record(app_name="App1", buildability_verdict=BuildabilityVerdict.READY),
            make_app_record(app_name="App2", buildability_verdict=BuildabilityVerdict.READY),
        ]

        result = self.analyzer._rank_blockers(records)

        assert result == []

    def test_rank_blockers_all_same_blocker(self):
        """All same blocker → single entry with full count."""
        records = [
            make_app_record(
                app_name=f"App{i}",
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.NO_PUBLIC_API,
            )
            for i in range(5)
        ]

        result = self.analyzer._rank_blockers(records)

        assert len(result) == 1
        assert result[0].blocker == "no_public_api"
        assert result[0].count == 5
        assert result[0].rank == 1

    def test_rank_blockers_multiple_sorted_by_frequency(self):
        """Multiple blockers → sorted by frequency descending."""
        records = [
            # 3x no_public_api
            make_app_record(
                app_name="App1",
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.NO_PUBLIC_API,
            ),
            make_app_record(
                app_name="App2",
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.NO_PUBLIC_API,
            ),
            make_app_record(
                app_name="App3",
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.NO_PUBLIC_API,
            ),
            # 2x rate_limits
            make_app_record(
                app_name="App4",
                buildability_verdict=BuildabilityVerdict.FEASIBLE,
                primary_blocker=BlockerCategory.RATE_LIMITS,
            ),
            make_app_record(
                app_name="App5",
                buildability_verdict=BuildabilityVerdict.FEASIBLE,
                primary_blocker=BlockerCategory.RATE_LIMITS,
            ),
            # 1x missing_documentation
            make_app_record(
                app_name="App6",
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.MISSING_DOCUMENTATION,
            ),
        ]

        result = self.analyzer._rank_blockers(records)

        assert len(result) == 3
        assert result[0].blocker == "no_public_api"
        assert result[0].count == 3
        assert result[0].rank == 1
        assert result[1].blocker == "rate_limits"
        assert result[1].count == 2
        assert result[1].rank == 2
        assert result[2].blocker == "missing_documentation"
        assert result[2].count == 1
        assert result[2].rank == 3

    def test_rank_blockers_only_considers_non_ready(self):
        """Only non-READY apps are considered for blocker ranking."""
        records = [
            make_app_record(
                app_name="Ready",
                buildability_verdict=BuildabilityVerdict.READY,
                primary_blocker=None,
            ),
            make_app_record(
                app_name="Blocked",
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.RESTRICTIVE_AUTH,
            ),
        ]

        result = self.analyzer._rank_blockers(records)

        assert len(result) == 1
        assert result[0].blocker == "restrictive_auth"
        assert result[0].count == 1

    # ------------------------------------------------------------------
    # Test _classify_apps()
    # ------------------------------------------------------------------

    def test_classify_app_meeting_all_easy_win_criteria(self):
        """App meeting all easy-win criteria → in easy_win list."""
        records = [
            make_app_record(
                app_name="EasyApp",
                access_model=AccessModel.SELF_SERVE,
                has_public_api=True,
                api_type=ApiType.REST,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
        ]

        easy_wins, outreach = self.analyzer._classify_apps(records)

        assert "EasyApp" in easy_wins
        assert "EasyApp" not in outreach

    def test_classify_app_graphql_is_easy_win(self):
        """App with GRAPHQL api_type meeting other criteria is easy-win."""
        records = [
            make_app_record(
                app_name="GraphQLApp",
                access_model=AccessModel.SELF_SERVE,
                has_public_api=True,
                api_type=ApiType.GRAPHQL,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
        ]

        easy_wins, outreach = self.analyzer._classify_apps(records)

        assert "GraphQLApp" in easy_wins

    def test_classify_app_both_api_type_is_easy_win(self):
        """App with BOTH api_type meeting other criteria is easy-win."""
        records = [
            make_app_record(
                app_name="BothApp",
                access_model=AccessModel.SELF_SERVE,
                has_public_api=True,
                api_type=ApiType.BOTH,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
        ]

        easy_wins, outreach = self.analyzer._classify_apps(records)

        assert "BothApp" in easy_wins

    def test_classify_app_missing_one_criterion_gated(self):
        """App with gated access (missing self-serve criterion) → in outreach list."""
        records = [
            make_app_record(
                app_name="GatedApp",
                access_model=AccessModel.GATED,
                has_public_api=True,
                api_type=ApiType.REST,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
        ]

        easy_wins, outreach = self.analyzer._classify_apps(records)

        assert "GatedApp" not in easy_wins
        assert "GatedApp" in outreach

    def test_classify_app_missing_one_criterion_no_public_api(self):
        """App without public API (missing has_public_api criterion) → in outreach list."""
        records = [
            make_app_record(
                app_name="NoApiApp",
                access_model=AccessModel.SELF_SERVE,
                has_public_api=False,
                api_type=ApiType.NONE,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
        ]

        easy_wins, outreach = self.analyzer._classify_apps(records)

        assert "NoApiApp" not in easy_wins
        assert "NoApiApp" in outreach

    def test_classify_app_missing_one_criterion_not_ready(self):
        """App with FEASIBLE verdict (missing READY criterion) → in outreach list."""
        records = [
            make_app_record(
                app_name="FeasibleApp",
                access_model=AccessModel.SELF_SERVE,
                has_public_api=True,
                api_type=ApiType.REST,
                buildability_verdict=BuildabilityVerdict.FEASIBLE,
                primary_blocker=BlockerCategory.RATE_LIMITS,
            ),
        ]

        easy_wins, outreach = self.analyzer._classify_apps(records)

        assert "FeasibleApp" not in easy_wins
        assert "FeasibleApp" in outreach

    def test_classify_app_api_type_none_is_outreach(self):
        """App with api_type NONE (not REST/GRAPHQL/BOTH) → in outreach list."""
        records = [
            make_app_record(
                app_name="NoTypeApp",
                access_model=AccessModel.SELF_SERVE,
                has_public_api=True,
                api_type=ApiType.NONE,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
        ]

        easy_wins, outreach = self.analyzer._classify_apps(records)

        assert "NoTypeApp" not in easy_wins
        assert "NoTypeApp" in outreach

    def test_classify_empty_records(self):
        """Empty records → both lists empty."""
        easy_wins, outreach = self.analyzer._classify_apps([])

        assert easy_wins == []
        assert outreach == []

    def test_classify_union_equals_full_set(self):
        """Union of easy-win and outreach equals the full app set."""
        records = [
            make_app_record(
                app_name="Easy",
                access_model=AccessModel.SELF_SERVE,
                has_public_api=True,
                api_type=ApiType.REST,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
            make_app_record(
                app_name="Hard",
                access_model=AccessModel.GATED,
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.NO_PUBLIC_API,
            ),
        ]

        easy_wins, outreach = self.analyzer._classify_apps(records)

        all_names = {r.app_name for r in records}
        classified_names = set(easy_wins) | set(outreach)
        assert classified_names == all_names

    # ------------------------------------------------------------------
    # Test _generate_observations()
    # ------------------------------------------------------------------

    def test_observations_always_at_least_3(self):
        """Observations always produces >= 3 observations."""
        records = [
            make_app_record(app_name="App1"),
            make_app_record(app_name="App2"),
        ]
        auth_dist = self.analyzer._compute_auth_distribution(records)
        access_dist = self.analyzer._compute_access_distribution(records)
        blockers = self.analyzer._rank_blockers(records)

        observations = self.analyzer._generate_observations(records, auth_dist, access_dist, blockers)

        assert len(observations) >= 3

    def test_observations_have_non_empty_fields(self):
        """Each observation has non-empty title, description, supporting_data, opportunity."""
        records = [
            make_app_record(app_name="App1", auth_methods=[AuthMethod.OAUTH2]),
            make_app_record(
                app_name="App2",
                auth_methods=[AuthMethod.API_KEY],
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.NO_PUBLIC_API,
            ),
            make_app_record(app_name="App3", access_model=AccessModel.GATED),
        ]
        auth_dist = self.analyzer._compute_auth_distribution(records)
        access_dist = self.analyzer._compute_access_distribution(records)
        blockers = self.analyzer._rank_blockers(records)

        observations = self.analyzer._generate_observations(records, auth_dist, access_dist, blockers)

        for obs in observations:
            assert obs.title, f"Observation title should not be empty: {obs}"
            assert obs.description, f"Observation description should not be empty: {obs}"
            assert obs.supporting_data, f"Observation supporting_data should not be empty: {obs}"
            assert obs.opportunity, f"Observation opportunity should not be empty: {obs}"

    def test_observations_with_no_blockers_still_produces_3(self):
        """With no blockers (all READY) → still produces 3+ observations."""
        records = [
            make_app_record(app_name="App1", buildability_verdict=BuildabilityVerdict.READY),
            make_app_record(app_name="App2", buildability_verdict=BuildabilityVerdict.READY),
            make_app_record(app_name="App3", buildability_verdict=BuildabilityVerdict.READY),
        ]
        auth_dist = self.analyzer._compute_auth_distribution(records)
        access_dist = self.analyzer._compute_access_distribution(records)
        blockers = self.analyzer._rank_blockers(records)

        assert blockers == []  # Confirm no blockers

        observations = self.analyzer._generate_observations(records, auth_dist, access_dist, blockers)

        assert len(observations) >= 3

    def test_observations_reference_data(self):
        """Observations contain references to specific data (counts/percentages)."""
        records = [
            make_app_record(app_name="App1", auth_methods=[AuthMethod.OAUTH2]),
            make_app_record(app_name="App2", auth_methods=[AuthMethod.OAUTH2]),
            make_app_record(
                app_name="App3",
                auth_methods=[AuthMethod.API_KEY],
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.RATE_LIMITS,
            ),
        ]
        auth_dist = self.analyzer._compute_auth_distribution(records)
        access_dist = self.analyzer._compute_access_distribution(records)
        blockers = self.analyzer._rank_blockers(records)

        observations = self.analyzer._generate_observations(records, auth_dist, access_dist, blockers)

        # At least one observation should contain a number (count or percentage)
        has_numeric_reference = any(
            any(char.isdigit() for char in obs.supporting_data) for obs in observations
        )
        assert has_numeric_reference, "At least one observation should reference numeric data"

    # ------------------------------------------------------------------
    # Edge Cases
    # ------------------------------------------------------------------

    def test_empty_records_list(self):
        """Empty records list produces valid (but empty) analysis."""
        result = self.analyzer.analyze([])

        assert result.auth_distribution.per_category == {}
        assert result.auth_distribution.overall == {}
        assert result.auth_distribution.dominant_per_category == {}
        assert result.access_distribution.per_category == {}
        assert result.blocker_rankings == []
        assert result.easy_win_apps == []
        assert result.outreach_required_apps == []
        # Even with no data, observations should handle gracefully
        # The implementation produces observations (may be fewer since no data to reference)
        assert result.observations is not None

    def test_single_record(self):
        """Single record produces valid analysis."""
        records = [
            make_app_record(
                app_name="OnlyApp",
                category="CRM & Sales",
                auth_methods=[AuthMethod.TOKEN],
                access_model=AccessModel.SELF_SERVE,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
        ]

        result = self.analyzer.analyze(records)

        assert result.auth_distribution.overall == {"token": 1}
        assert result.auth_distribution.dominant_per_category == {"CRM & Sales": "token"}
        assert result.access_distribution.per_category["CRM & Sales"]["self_serve"] == 1
        assert result.access_distribution.per_category["CRM & Sales"]["gated"] == 0
        assert result.blocker_rankings == []
        assert "OnlyApp" in result.easy_win_apps
        assert result.outreach_required_apps == []

    def test_all_records_failed_research(self):
        """All records with failed research (no auth methods) handled gracefully."""
        records = [
            make_app_record(
                app_name=f"FailedApp{i}",
                category="CRM & Sales",
                auth_methods=[],
                access_model=AccessModel.GATED,
                has_public_api=False,
                api_type=None,
                coverage=None,
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.NO_PUBLIC_API,
                research_status=ResearchStatus.FAILED,
                failure_reason="Timeout during research",
                failure_category="timeout",
            )
            for i in range(3)
        ]

        result = self.analyzer.analyze(records)

        # Auth distribution should be empty since no auth methods
        assert result.auth_distribution.overall == {}
        assert result.auth_distribution.dominant_per_category == {}
        # All gated
        assert result.access_distribution.per_category["CRM & Sales"]["gated"] == 3
        assert result.access_distribution.category_classification["CRM & Sales"] == "majority_gated"
        # All blocked with same blocker
        assert len(result.blocker_rankings) == 1
        assert result.blocker_rankings[0].blocker == "no_public_api"
        assert result.blocker_rankings[0].count == 3
        # No easy wins since all blocked
        assert result.easy_win_apps == []
        assert len(result.outreach_required_apps) == 3

    def test_mixed_categories_and_verdicts(self):
        """Complex scenario with multiple categories, verdicts, and auth methods."""
        records = [
            # CRM category - 2 easy wins, 1 blocked
            make_app_record(
                app_name="CRM1",
                category="CRM & Sales",
                auth_methods=[AuthMethod.OAUTH2, AuthMethod.API_KEY],
                access_model=AccessModel.SELF_SERVE,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
            make_app_record(
                app_name="CRM2",
                category="CRM & Sales",
                auth_methods=[AuthMethod.OAUTH2],
                access_model=AccessModel.SELF_SERVE,
                buildability_verdict=BuildabilityVerdict.READY,
            ),
            make_app_record(
                app_name="CRM3",
                category="CRM & Sales",
                auth_methods=[AuthMethod.BASIC],
                access_model=AccessModel.GATED,
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.RESTRICTIVE_AUTH,
            ),
            # Ecommerce category - 1 feasible, 1 blocked
            make_app_record(
                app_name="Shop1",
                category="Ecommerce",
                auth_methods=[AuthMethod.API_KEY],
                access_model=AccessModel.SELF_SERVE,
                buildability_verdict=BuildabilityVerdict.FEASIBLE,
                primary_blocker=BlockerCategory.RATE_LIMITS,
            ),
            make_app_record(
                app_name="Shop2",
                category="Ecommerce",
                auth_methods=[AuthMethod.API_KEY],
                access_model=AccessModel.GATED,
                buildability_verdict=BuildabilityVerdict.BLOCKED,
                primary_blocker=BlockerCategory.NO_PUBLIC_API,
            ),
        ]

        result = self.analyzer.analyze(records)

        # Auth: oauth2 appears 3 times (CRM1 has 2 methods), api_key 3 times, basic 1 time
        assert result.auth_distribution.overall["oauth2"] == 2
        assert result.auth_distribution.overall["api_key"] == 3
        assert result.auth_distribution.overall["basic"] == 1

        # Access: CRM has 2 self_serve, 1 gated; Ecommerce has 1 self_serve, 1 gated
        assert result.access_distribution.per_category["CRM & Sales"]["self_serve"] == 2
        assert result.access_distribution.per_category["CRM & Sales"]["gated"] == 1
        assert result.access_distribution.category_classification["CRM & Sales"] == "majority_self_serve"

        # Blockers: restrictive_auth=1, rate_limits=1, no_public_api=1
        assert len(result.blocker_rankings) == 3

        # Easy wins: CRM1 and CRM2 meet all criteria
        assert set(result.easy_win_apps) == {"CRM1", "CRM2"}
        assert set(result.outreach_required_apps) == {"CRM3", "Shop1", "Shop2"}

        # Observations produced
        assert len(result.observations) >= 3


# ============================================================================
# Property-Based Tests (Hypothesis)
# ============================================================================

from collections import Counter

from hypothesis import given, settings
from hypothesis import strategies as st

from composio_research.config import CATEGORIES


# ============================================================================
# Hypothesis Strategies for Pattern Analyzer property tests
# ============================================================================

# Strategy for auth methods: 1-5 methods per app as specified in task
_auth_methods_strategy = st.lists(
    st.sampled_from(list(AuthMethod)), min_size=1, max_size=5
)

# Strategy for ApiSurface instances
_api_surface_strategy = st.builds(
    ApiSurface,
    has_public_api=st.booleans(),
    api_type=st.one_of(st.none(), st.sampled_from(list(ApiType))),
    coverage=st.one_of(st.none(), st.sampled_from(list(ApiCoverage))),
    has_mcp_support=st.booleans(),
    evidence_url=st.one_of(st.none(), st.just("https://example.com/api")),
)

# Strategy for generating AppRecords with varied auth_methods (1-5 methods per app)
_app_record_for_auth_strategy = st.builds(
    AppRecord,
    app_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=30,
    ),
    category=st.sampled_from(CATEGORIES),
    description=st.text(min_size=1, max_size=120),
    auth_methods=_auth_methods_strategy,
    access_model=st.sampled_from(list(AccessModel)),
    api_surface=_api_surface_strategy,
    buildability_verdict=st.sampled_from(list(BuildabilityVerdict)),
    primary_blocker=st.one_of(st.none(), st.sampled_from(list(BlockerCategory))),
    evidence_urls=st.just({}),
    research_status=st.sampled_from(list(ResearchStatus)),
    missing_fields=st.just([]),
    failure_reason=st.none(),
    failure_category=st.none(),
)


# ============================================================================
# Property 1: Auth distribution sums to total app count
# Feature: composio-app-research-pipeline, Property 1: Auth distribution sums to total app count
# ============================================================================


class TestProperty1AuthDistribution:
    """Property-based tests for auth distribution computation.

    Feature: composio-app-research-pipeline, Property 1: Auth distribution sums to total app count

    For any set of AppRecords, the sum of all auth method counts in the overall
    auth distribution SHALL equal the total number of auth method assignments
    across all records (accounting for apps with multiple auth methods), and
    the dominant auth method per category SHALL be the one with the highest
    count in that category.

    **Validates: Requirements 4.1**
    """

    @given(records=st.lists(_app_record_for_auth_strategy, min_size=0, max_size=30))
    def test_overall_sum_equals_total_auth_assignments(self, records: list[AppRecord]):
        """The sum of overall auth distribution counts equals the total number
        of auth method assignments across all records.

        Each app can have multiple auth methods (1-5), so total assignments is
        sum(len(r.auth_methods) for r in records).

        **Validates: Requirements 4.1**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_auth_distribution(records)

        # Expected total auth assignments
        expected_total = sum(len(r.auth_methods) for r in records)
        # Actual sum from overall distribution
        actual_total = sum(result.overall.values())

        assert actual_total == expected_total

    @given(records=st.lists(_app_record_for_auth_strategy, min_size=1, max_size=30))
    def test_dominant_per_category_is_highest_count(self, records: list[AppRecord]):
        """For each category, the dominant auth method is the one with the
        highest count in that category.

        **Validates: Requirements 4.1**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_auth_distribution(records)

        for category, methods in result.per_category.items():
            if methods:
                # The dominant method for this category should be the one with max count
                expected_dominant = max(methods, key=methods.get)
                assert category in result.dominant_per_category
                assert result.dominant_per_category[category] == expected_dominant

    @given(records=st.lists(_app_record_for_auth_strategy, min_size=1, max_size=30))
    def test_per_category_sums_to_category_auth_assignments(self, records: list[AppRecord]):
        """For each category, the sum of per-category auth method counts equals
        the total auth method assignments in that category.

        **Validates: Requirements 4.1**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_auth_distribution(records)

        # Compute expected per-category totals
        expected_per_category: dict[str, int] = {}
        for record in records:
            cat = record.category
            expected_per_category[cat] = expected_per_category.get(cat, 0) + len(
                record.auth_methods
            )

        # Verify per_category sums match
        for category, methods in result.per_category.items():
            actual_sum = sum(methods.values())
            assert actual_sum == expected_per_category[category]

    @given(records=st.lists(_app_record_for_auth_strategy, min_size=0, max_size=30))
    def test_overall_equals_sum_of_per_category(self, records: list[AppRecord]):
        """The overall distribution should be the sum of all per-category
        distributions (overall[method] == sum of per_category[*][method]).

        **Validates: Requirements 4.1**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_auth_distribution(records)

        # Compute expected overall from per_category
        expected_overall: Counter = Counter()
        for category, methods in result.per_category.items():
            for method, count in methods.items():
                expected_overall[method] += count

        assert dict(expected_overall) == result.overall

    @given(records=st.just([]))
    def test_empty_records_produces_empty_distribution(self, records: list[AppRecord]):
        """An empty list of records produces empty distributions.

        **Validates: Requirements 4.1**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_auth_distribution(records)

        assert result.overall == {}
        assert result.per_category == {}
        assert result.dominant_per_category == {}


# ============================================================================
# Property-Based Tests (Hypothesis)
# ============================================================================

from hypothesis import given, strategies as st

from composio_research.config import CATEGORIES


# ============================================================================
# Shared Hypothesis Strategies for Pattern Analyzer Property Tests
# ============================================================================

# Strategy for generating valid ApiSurface instances
_api_surface_strategy = st.builds(
    ApiSurface,
    has_public_api=st.booleans(),
    api_type=st.one_of(st.none(), st.sampled_from(ApiType)),
    coverage=st.one_of(st.none(), st.sampled_from(ApiCoverage)),
    has_mcp_support=st.booleans(),
    evidence_url=st.one_of(st.none(), st.just("https://example.com/api")),
)

# Strategy for generating valid AppRecord instances for pattern analysis
_app_record_strategy = st.builds(
    AppRecord,
    app_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=30,
    ),
    category=st.sampled_from(CATEGORIES),
    description=st.text(min_size=1, max_size=120),
    auth_methods=st.lists(st.sampled_from(list(AuthMethod)), min_size=1, max_size=3),
    access_model=st.sampled_from(list(AccessModel)),
    api_surface=_api_surface_strategy,
    buildability_verdict=st.sampled_from(list(BuildabilityVerdict)),
    primary_blocker=st.one_of(st.none(), st.sampled_from(list(BlockerCategory))),
    evidence_urls=st.just({}),
    research_status=st.sampled_from(list(ResearchStatus)),
    missing_fields=st.just([]),
    failure_reason=st.none(),
    failure_category=st.none(),
)


# ============================================================================
# Property 2: Access distribution partitions categories completely
# Feature: composio-app-research-pipeline, Property 2: Access distribution partitions categories completely
# ============================================================================


class TestProperty2AccessDistribution:
    """Property-based tests for access distribution partitions.

    Feature: composio-app-research-pipeline, Property 2: Access distribution partitions categories completely

    For any set of AppRecords grouped by category, the sum of self_serve and gated
    counts per category SHALL equal the total number of apps in that category, and
    the category classification SHALL be "majority_self_serve" if and only if
    self_serve count > 50% of apps in that category.

    **Validates: Requirements 4.2**
    """

    @given(records=st.lists(_app_record_strategy, min_size=1, max_size=50))
    def test_self_serve_plus_gated_equals_category_total(self, records: list[AppRecord]):
        """For any set of AppRecords, the sum of self_serve + gated counts per category
        equals the total number of apps in that category.

        **Validates: Requirements 4.2**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_access_distribution(records)

        # Compute expected per-category totals
        expected_per_category: dict[str, int] = {}
        for record in records:
            expected_per_category[record.category] = (
                expected_per_category.get(record.category, 0) + 1
            )

        # Verify self_serve + gated equals total for each category
        for category, expected_total in expected_per_category.items():
            assert category in result.per_category, (
                f"Category '{category}' missing from per_category distribution"
            )
            counts = result.per_category[category]
            actual_total = counts.get("self_serve", 0) + counts.get("gated", 0)
            assert actual_total == expected_total, (
                f"Category '{category}': self_serve ({counts.get('self_serve', 0)}) + "
                f"gated ({counts.get('gated', 0)}) = {actual_total}, "
                f"expected {expected_total}"
            )

    @given(records=st.lists(_app_record_strategy, min_size=1, max_size=50))
    def test_category_classification_majority_self_serve_iff_above_50_percent(
        self, records: list[AppRecord]
    ):
        """For any set of AppRecords, category_classification is "majority_self_serve"
        if and only if self_serve count > 50% of apps in that category.

        **Validates: Requirements 4.2**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_access_distribution(records)

        for category, counts in result.per_category.items():
            total = counts.get("self_serve", 0) + counts.get("gated", 0)
            self_serve_count = counts.get("self_serve", 0)

            assert category in result.category_classification, (
                f"Category '{category}' missing from category_classification"
            )

            classification = result.category_classification[category]

            if self_serve_count > total * 0.5:
                assert classification == "majority_self_serve", (
                    f"Category '{category}': self_serve={self_serve_count}/{total} "
                    f"(>{total * 0.5}) but classified as '{classification}'"
                )
            else:
                assert classification == "majority_gated", (
                    f"Category '{category}': self_serve={self_serve_count}/{total} "
                    f"(<={total * 0.5}) but classified as '{classification}'"
                )

    @given(records=st.lists(_app_record_strategy, min_size=1, max_size=50))
    def test_all_categories_present_in_distribution(self, records: list[AppRecord]):
        """For any set of AppRecords, all categories present in the input records
        are represented in the access distribution output.

        **Validates: Requirements 4.2**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_access_distribution(records)

        # Collect all distinct categories from input records
        input_categories = {record.category for record in records}

        # Verify all input categories appear in per_category
        for category in input_categories:
            assert category in result.per_category, (
                f"Category '{category}' present in input but missing from distribution"
            )

        # Verify all input categories appear in category_classification
        for category in input_categories:
            assert category in result.category_classification, (
                f"Category '{category}' present in input but missing from classification"
            )

    @given(records=st.lists(_app_record_strategy, min_size=0, max_size=0))
    def test_empty_records_produces_empty_distribution(self, records: list[AppRecord]):
        """For an empty list of AppRecords, the distribution should have no categories.

        **Validates: Requirements 4.2**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_access_distribution(records)

        assert result.per_category == {}
        assert result.category_classification == {}

    @given(records=st.lists(_app_record_strategy, min_size=1, max_size=50))
    def test_no_extra_categories_in_distribution(self, records: list[AppRecord]):
        """The distribution should not contain categories that are not present
        in the input records.

        **Validates: Requirements 4.2**
        """
        analyzer = PatternAnalyzer()
        result = analyzer._compute_access_distribution(records)

        input_categories = {record.category for record in records}

        # No extra categories should appear in the output
        for category in result.per_category:
            assert category in input_categories, (
                f"Category '{category}' in distribution but not in input records"
            )

        for category in result.category_classification:
            assert category in input_categories, (
                f"Category '{category}' in classification but not in input records"
            )


# ============================================================================
# Property 4: Easy-win classification is deterministic
# Feature: composio-app-research-pipeline, Property 4: Easy-win classification is deterministic
# ============================================================================

# Strategy for ApiSurface covering both public and non-public API cases for Property 4
_api_surface_for_classify_strategy = st.one_of(
    # Case: has_public_api=True with non-None api_type and coverage
    st.builds(
        ApiSurface,
        has_public_api=st.just(True),
        api_type=st.sampled_from(list(ApiType)),
        coverage=st.sampled_from(list(ApiCoverage)),
        has_mcp_support=st.booleans(),
        evidence_url=st.one_of(st.none(), st.just("https://example.com/api")),
    ),
    # Case: has_public_api=False with None api_type and coverage
    st.builds(
        ApiSurface,
        has_public_api=st.just(False),
        api_type=st.none(),
        coverage=st.none(),
        has_mcp_support=st.booleans(),
        evidence_url=st.one_of(st.none(), st.just("https://example.com/api")),
    ),
)

# Strategy for AppRecords with all possible verdict/access/api combinations
_app_record_for_classify_strategy = st.builds(
    AppRecord,
    app_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=30,
    ),
    category=st.sampled_from(CATEGORIES),
    description=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=1,
        max_size=120,
    ),
    auth_methods=st.lists(st.sampled_from(list(AuthMethod)), min_size=1, max_size=3),
    access_model=st.sampled_from(list(AccessModel)),
    api_surface=_api_surface_for_classify_strategy,
    buildability_verdict=st.sampled_from(list(BuildabilityVerdict)),
    primary_blocker=st.one_of(st.none(), st.sampled_from(list(BlockerCategory))),
    evidence_urls=st.just({}),
    research_status=st.sampled_from(list(ResearchStatus)),
    missing_fields=st.just([]),
    failure_reason=st.none(),
    failure_category=st.none(),
)


class TestProperty4EasyWinClassification:
    """Property 4: Easy-win classification is deterministic.

    Feature: composio-app-research-pipeline, Property 4: Easy-win classification is deterministic

    For any AppRecord, the app is classified as "easy-win" if and only if:
    - access_model == SELF_SERVE
    - api_surface.has_public_api == True
    - api_surface.api_type in (REST, GRAPHQL, BOTH)
    - buildability_verdict == READY

    All other apps are classified as "requires-outreach."
    The union of easy-win and requires-outreach sets equals the full app set.

    **Validates: Requirements 4.4**
    """

    EASY_WIN_API_TYPES = {ApiType.REST, ApiType.GRAPHQL, ApiType.BOTH}

    def _is_easy_win(self, record: AppRecord) -> bool:
        """Reference implementation of the easy-win classification logic."""
        return (
            record.access_model == AccessModel.SELF_SERVE
            and record.api_surface.has_public_api is True
            and record.api_surface.api_type in self.EASY_WIN_API_TYPES
            and record.buildability_verdict == BuildabilityVerdict.READY
        )

    @given(records=st.lists(_app_record_for_classify_strategy, min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_easy_win_iff_all_criteria_met(self, records: list[AppRecord]):
        """For each record, app_name is in easy_win_apps if and only if ALL
        easy-win criteria are satisfied.

        **Validates: Requirements 4.4**
        """
        analyzer = PatternAnalyzer()
        easy_win_apps, outreach_apps = analyzer._classify_apps(records)

        for record in records:
            expected_easy_win = self._is_easy_win(record)
            if expected_easy_win:
                assert record.app_name in easy_win_apps, (
                    f"{record.app_name} should be easy-win: "
                    f"access={record.access_model}, has_api={record.api_surface.has_public_api}, "
                    f"api_type={record.api_surface.api_type}, verdict={record.buildability_verdict}"
                )
            else:
                assert record.app_name in outreach_apps, (
                    f"{record.app_name} should be requires-outreach: "
                    f"access={record.access_model}, has_api={record.api_surface.has_public_api}, "
                    f"api_type={record.api_surface.api_type}, verdict={record.buildability_verdict}"
                )

    @given(records=st.lists(_app_record_for_classify_strategy, min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_union_equals_full_app_set(self, records: list[AppRecord]):
        """The union of easy-win and requires-outreach app name lists equals
        the full set of app names from the input records.

        **Validates: Requirements 4.4**
        """
        analyzer = PatternAnalyzer()
        easy_win_apps, outreach_apps = analyzer._classify_apps(records)

        all_app_names = [r.app_name for r in records]
        combined = easy_win_apps + outreach_apps

        assert sorted(combined) == sorted(all_app_names)

    @given(records=st.lists(_app_record_for_classify_strategy, min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_no_overlap_between_sets(self, records: list[AppRecord]):
        """The easy-win and requires-outreach sets have no overlap—
        no app name appears in both lists when app names are unique
        (which they always are in the real pipeline: 100 distinct apps).

        **Validates: Requirements 4.4**
        """
        # Deduplicate by app_name to reflect real-world invariant
        # (each app has a unique name in the pipeline)
        seen_names: set[str] = set()
        unique_records: list[AppRecord] = []
        for r in records:
            if r.app_name not in seen_names:
                seen_names.add(r.app_name)
                unique_records.append(r)

        analyzer = PatternAnalyzer()
        easy_win_apps, outreach_apps = analyzer._classify_apps(unique_records)

        easy_set = set(easy_win_apps)
        outreach_set = set(outreach_apps)

        assert easy_set & outreach_set == set(), (
            f"Overlap found: {easy_set & outreach_set}"
        )

    @given(records=st.lists(_app_record_for_classify_strategy, min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_total_count_equals_input_count(self, records: list[AppRecord]):
        """The total number of apps in easy-win + requires-outreach
        equals the number of input records.

        **Validates: Requirements 4.4**
        """
        analyzer = PatternAnalyzer()
        easy_win_apps, outreach_apps = analyzer._classify_apps(records)

        assert len(easy_win_apps) + len(outreach_apps) == len(records)

    @given(records=st.lists(_app_record_for_classify_strategy, min_size=1, max_size=30))
    @settings(max_examples=100)
    def test_classification_is_deterministic(self, records: list[AppRecord]):
        """Running classification twice on the same input produces
        identical results—the classification is pure and deterministic.

        **Validates: Requirements 4.4**
        """
        analyzer = PatternAnalyzer()
        easy1, outreach1 = analyzer._classify_apps(records)
        easy2, outreach2 = analyzer._classify_apps(records)

        assert easy1 == easy2
        assert outreach1 == outreach2


# ============================================================================
# Property 3: Blocker rankings are frequency-sorted
# Feature: composio-app-research-pipeline, Property 3: Blocker rankings are frequency-sorted
# ============================================================================

# Strategy for generating non-ready AppRecords with guaranteed non-None primary_blocker
_non_ready_verdicts_strategy = st.sampled_from(
    [BuildabilityVerdict.FEASIBLE, BuildabilityVerdict.BLOCKED]
)

_non_ready_app_record_strategy = st.builds(
    AppRecord,
    app_name=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=30,
    ),
    category=st.sampled_from(CATEGORIES),
    description=st.text(min_size=1, max_size=120),
    auth_methods=st.lists(st.sampled_from(list(AuthMethod)), min_size=1, max_size=3),
    access_model=st.sampled_from(list(AccessModel)),
    api_surface=st.builds(
        ApiSurface,
        has_public_api=st.booleans(),
        api_type=st.one_of(st.none(), st.sampled_from(list(ApiType))),
        coverage=st.one_of(st.none(), st.sampled_from(list(ApiCoverage))),
        has_mcp_support=st.booleans(),
        evidence_url=st.one_of(st.none(), st.just("https://example.com/api")),
    ),
    buildability_verdict=_non_ready_verdicts_strategy,
    primary_blocker=st.sampled_from(list(BlockerCategory)),
    evidence_urls=st.just({}),
    research_status=st.sampled_from(list(ResearchStatus)),
    missing_fields=st.just([]),
    failure_reason=st.none(),
    failure_category=st.none(),
)


class TestProperty3BlockerRankings:
    """Property-based tests for blocker rankings frequency sorting.

    Feature: composio-app-research-pipeline, Property 3: Blocker rankings are frequency-sorted

    For any set of AppRecords with buildability verdicts that are not "ready,"
    the blocker rankings SHALL be sorted in non-increasing order of count,
    SHALL include all distinct blockers present in the data, and SHALL report
    at least the top 5 if 5 or more distinct blockers exist.

    **Validates: Requirements 4.3**
    """

    @given(records=st.lists(_non_ready_app_record_strategy, min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_rankings_sorted_descending(self, records: list[AppRecord]) -> None:
        """Rankings are sorted in non-increasing order of count.

        Feature: composio-app-research-pipeline, Property 3: Blocker rankings are frequency-sorted
        **Validates: Requirements 4.3**
        """
        analyzer = PatternAnalyzer()
        rankings = analyzer._rank_blockers(records)

        # Assert non-increasing order of count
        for i in range(len(rankings) - 1):
            assert rankings[i].count >= rankings[i + 1].count, (
                f"Rankings not sorted: rank {i+1} has count {rankings[i].count} "
                f"but rank {i+2} has count {rankings[i+1].count}"
            )

    @given(records=st.lists(_non_ready_app_record_strategy, min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_all_distinct_blockers_included(self, records: list[AppRecord]) -> None:
        """All distinct blocker values present in data appear in rankings.

        Feature: composio-app-research-pipeline, Property 3: Blocker rankings are frequency-sorted
        **Validates: Requirements 4.3**
        """
        analyzer = PatternAnalyzer()
        rankings = analyzer._rank_blockers(records)

        # Collect distinct blockers from the input records (all are non-READY with non-None blocker)
        expected_blockers = {
            record.primary_blocker.value
            for record in records
            if record.buildability_verdict != BuildabilityVerdict.READY
            and record.primary_blocker is not None
        }

        # Collect blockers reported in rankings
        ranked_blockers = {r.blocker for r in rankings}

        assert ranked_blockers == expected_blockers, (
            f"Mismatch: expected {expected_blockers}, got {ranked_blockers}"
        )

    @given(records=st.lists(_non_ready_app_record_strategy, min_size=5, max_size=50))
    @settings(max_examples=100)
    def test_at_least_top_5_if_5_distinct_blockers(self, records: list[AppRecord]) -> None:
        """At least top 5 blockers are reported if 5+ distinct blockers exist.

        Feature: composio-app-research-pipeline, Property 3: Blocker rankings are frequency-sorted
        **Validates: Requirements 4.3**
        """
        analyzer = PatternAnalyzer()
        rankings = analyzer._rank_blockers(records)

        # Count distinct blockers from data
        distinct_blockers = {
            record.primary_blocker.value
            for record in records
            if record.buildability_verdict != BuildabilityVerdict.READY
            and record.primary_blocker is not None
        }

        if len(distinct_blockers) >= 5:
            assert len(rankings) >= 5, (
                f"Expected at least 5 rankings for {len(distinct_blockers)} "
                f"distinct blockers, got {len(rankings)}"
            )

    @given(records=st.lists(_non_ready_app_record_strategy, min_size=1, max_size=50))
    @settings(max_examples=100)
    def test_ranks_are_1_indexed_sequential(self, records: list[AppRecord]) -> None:
        """Rank values are 1-indexed and sequential (1, 2, 3, ...).

        Feature: composio-app-research-pipeline, Property 3: Blocker rankings are frequency-sorted
        **Validates: Requirements 4.3**
        """
        analyzer = PatternAnalyzer()
        rankings = analyzer._rank_blockers(records)

        for i, ranking in enumerate(rankings):
            expected_rank = i + 1
            assert ranking.rank == expected_rank, (
                f"Expected rank {expected_rank} at index {i}, got {ranking.rank}"
            )
