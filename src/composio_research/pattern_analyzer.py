"""Pattern Analyzer for the Composio App Research Pipeline.

Pure computation module that analyzes verified app records to produce:
- Auth method frequency distribution (per-category and overall)
- Access model distribution (self-serve vs gated per category)
- Blocker rankings by frequency
- Easy-win vs requires-outreach app classification
- Data-backed observations with actionable recommendations
"""

from collections import Counter
from typing import Optional

from composio_research.models import (
    AccessDistribution,
    AccessModel,
    ApiType,
    AppRecord,
    AuthDistribution,
    BlockerRank,
    BuildabilityVerdict,
    Observation,
    PatternAnalysis,
)


class PatternAnalyzer:
    """Analyzes verified app records to identify cross-app patterns and strategic opportunities.

    All methods are pure computation with no I/O or external dependencies.
    """

    def analyze(self, records: list[AppRecord]) -> PatternAnalysis:
        """Compute all pattern analysis from verified records.

        Orchestrates auth distribution, access distribution, blocker rankings,
        app classification, and observation generation.

        Args:
            records: List of verified AppRecord instances to analyze.

        Returns:
            PatternAnalysis containing all computed analysis results.
        """
        auth_distribution = self._compute_auth_distribution(records)
        access_distribution = self._compute_access_distribution(records)
        blocker_rankings = self._rank_blockers(records)
        easy_win_apps, outreach_required_apps = self._classify_apps(records)
        observations = self._generate_observations(
            records, auth_distribution, access_distribution, blocker_rankings
        )

        return PatternAnalysis(
            auth_distribution=auth_distribution,
            access_distribution=access_distribution,
            blocker_rankings=blocker_rankings,
            easy_win_apps=easy_win_apps,
            outreach_required_apps=outreach_required_apps,
            observations=observations,
        )

    def _compute_auth_distribution(self, records: list[AppRecord]) -> AuthDistribution:
        """Compute frequency distribution of auth methods per category and overall.

        For each record, counts each auth method in its auth_methods list.
        Apps can have multiple auth methods, so each is counted separately.

        Args:
            records: List of AppRecord instances.

        Returns:
            AuthDistribution with per_category counts, overall counts, and
            dominant auth method per category.
        """
        per_category: dict[str, dict[str, int]] = {}
        overall: Counter[str] = Counter()

        for record in records:
            category = record.category
            if category not in per_category:
                per_category[category] = {}

            for auth_method in record.auth_methods:
                method_value = auth_method.value
                per_category[category][method_value] = (
                    per_category[category].get(method_value, 0) + 1
                )
                overall[method_value] += 1

        # Determine dominant auth method per category
        dominant_per_category: dict[str, str] = {}
        for category, methods in per_category.items():
            if methods:
                dominant_per_category[category] = max(methods, key=methods.get)  # type: ignore[arg-type]
            # If no methods recorded for a category, skip it

        return AuthDistribution(
            per_category=per_category,
            overall=dict(overall),
            dominant_per_category=dominant_per_category,
        )

    def _compute_access_distribution(self, records: list[AppRecord]) -> AccessDistribution:
        """Compute self-serve vs gated counts per category with classification.

        Classifies each category as "majority_self_serve" if more than 50% of
        apps in that category have self-serve access, otherwise "majority_gated".

        Args:
            records: List of AppRecord instances.

        Returns:
            AccessDistribution with per_category counts and category classification.
        """
        per_category: dict[str, dict[str, int]] = {}

        for record in records:
            category = record.category
            if category not in per_category:
                per_category[category] = {"self_serve": 0, "gated": 0}

            if record.access_model == AccessModel.SELF_SERVE:
                per_category[category]["self_serve"] += 1
            else:
                per_category[category]["gated"] += 1

        # Classify each category
        category_classification: dict[str, str] = {}
        for category, counts in per_category.items():
            total = counts["self_serve"] + counts["gated"]
            if total > 0 and counts["self_serve"] > total * 0.5:
                category_classification[category] = "majority_self_serve"
            else:
                category_classification[category] = "majority_gated"

        return AccessDistribution(
            per_category=per_category,
            category_classification=category_classification,
        )

    def _rank_blockers(self, records: list[AppRecord]) -> list[BlockerRank]:
        """Rank all distinct blockers by frequency for non-READY apps.

        Only considers records where buildability_verdict is FEASIBLE or BLOCKED.
        Returns all distinct blockers sorted by count descending, with 1-indexed ranks.

        Args:
            records: List of AppRecord instances.

        Returns:
            List of BlockerRank sorted by count descending. Includes at least
            top 5 if 5+ distinct blockers exist.
        """
        blocker_counter: Counter[str] = Counter()

        for record in records:
            if record.buildability_verdict != BuildabilityVerdict.READY:
                if record.primary_blocker is not None:
                    blocker_counter[record.primary_blocker.value] += 1

        # Sort by count descending
        sorted_blockers = blocker_counter.most_common()

        rankings: list[BlockerRank] = []
        for rank_idx, (blocker, count) in enumerate(sorted_blockers, start=1):
            rankings.append(BlockerRank(blocker=blocker, count=count, rank=rank_idx))

        return rankings

    def _classify_apps(self, records: list[AppRecord]) -> tuple[list[str], list[str]]:
        """Classify each app as easy-win or requires-outreach.

        Easy-win criteria (ALL must be true):
        - access_model == SELF_SERVE
        - api_surface.has_public_api == True
        - api_surface.api_type in (REST, GRAPHQL, BOTH)
        - buildability_verdict == READY

        All other apps are classified as requires-outreach.

        Args:
            records: List of AppRecord instances.

        Returns:
            Tuple of (easy_win_names, outreach_names). Union equals the full app set.
        """
        easy_win_apps: list[str] = []
        outreach_required_apps: list[str] = []

        easy_win_api_types = {ApiType.REST, ApiType.GRAPHQL, ApiType.BOTH}

        for record in records:
            is_easy_win = (
                record.access_model == AccessModel.SELF_SERVE
                and record.api_surface.has_public_api is True
                and record.api_surface.api_type in easy_win_api_types
                and record.buildability_verdict == BuildabilityVerdict.READY
            )

            if is_easy_win:
                easy_win_apps.append(record.app_name)
            else:
                outreach_required_apps.append(record.app_name)

        return easy_win_apps, outreach_required_apps

    def _generate_observations(
        self,
        records: list[AppRecord],
        auth_dist: AuthDistribution,
        access_dist: AccessDistribution,
        blockers: list[BlockerRank],
    ) -> list[Observation]:
        """Generate 3+ data-backed observations with actionable recommendations.

        Each observation references specific counts or percentages from the analysis
        and includes an actionable opportunity for Composio's platform strategy.

        Args:
            records: List of AppRecord instances.
            auth_dist: Computed auth distribution.
            access_dist: Computed access distribution.
            blockers: Ranked blocker list.

        Returns:
            List of at least 3 Observation instances.
        """
        observations: list[Observation] = []
        total_apps = len(records)

        # Observation 1: Dominant auth method
        if auth_dist.overall and total_apps > 0:
            dominant_auth = max(auth_dist.overall, key=auth_dist.overall.get)  # type: ignore[arg-type]
            dominant_count = auth_dist.overall[dominant_auth]
            # Calculate total auth assignments for percentage
            total_auth_assignments = sum(auth_dist.overall.values())
            if total_auth_assignments > 0:
                dominant_pct = round(dominant_count / total_auth_assignments * 100, 1)
            else:
                dominant_pct = 0.0

            observations.append(
                Observation(
                    title=f"{dominant_auth.replace('_', ' ').title()} dominance in authentication",
                    description=(
                        f"{dominant_auth} is the most common authentication method across "
                        f"all analyzed apps, appearing in {dominant_count} of "
                        f"{total_auth_assignments} total auth method assignments."
                    ),
                    supporting_data=(
                        f"{dominant_count}/{total_auth_assignments} auth assignments "
                        f"({dominant_pct}%) use {dominant_auth}"
                    ),
                    opportunity=(
                        f"Prioritize {dominant_auth} connector support in the Composio SDK to "
                        f"maximize compatibility with the largest segment of apps."
                    ),
                )
            )

        # Observation 2: Self-serve opportunity
        easy_win_apps, _ = self._classify_apps(records)
        easy_win_count = len(easy_win_apps)

        # Count categories with easy-win apps
        easy_win_categories: set[str] = set()
        for record in records:
            if record.app_name in easy_win_apps:
                easy_win_categories.add(record.category)

        if total_apps > 0:
            easy_win_pct = round(easy_win_count / total_apps * 100, 1)
        else:
            easy_win_pct = 0.0

        observations.append(
            Observation(
                title="Self-serve easy-win opportunity",
                description=(
                    f"{easy_win_count} apps are classified as easy-wins, requiring no "
                    f"outreach or special partnerships to integrate. These span "
                    f"{len(easy_win_categories)} categories."
                ),
                supporting_data=(
                    f"{easy_win_count}/{total_apps} apps ({easy_win_pct}%) are ready "
                    f"for immediate integration across {len(easy_win_categories)} categories"
                ),
                opportunity=(
                    "Focus initial integration efforts on easy-win apps to rapidly "
                    "expand the Composio toolkit catalog with minimal business development overhead."
                ),
            )
        )

        # Observation 3: Top blocker insight
        if blockers:
            top_blocker = blockers[0]
            blocker_label = top_blocker.blocker.replace("_", " ")

            # Count total non-ready apps
            non_ready_count = sum(
                1
                for r in records
                if r.buildability_verdict != BuildabilityVerdict.READY
            )

            if non_ready_count > 0:
                blocker_pct = round(top_blocker.count / non_ready_count * 100, 1)
            else:
                blocker_pct = 0.0

            observations.append(
                Observation(
                    title=f"Top blocker: {blocker_label}",
                    description=(
                        f"The most common barrier to buildability is '{blocker_label}', "
                        f"affecting {top_blocker.count} apps out of {non_ready_count} "
                        f"non-ready apps."
                    ),
                    supporting_data=(
                        f"{top_blocker.count}/{non_ready_count} non-ready apps "
                        f"({blocker_pct}%) blocked by {blocker_label}"
                    ),
                    opportunity=(
                        f"Develop targeted solutions or partnerships to address "
                        f"'{blocker_label}' barriers, potentially unblocking "
                        f"{top_blocker.count} apps for toolkit integration."
                    ),
                )
            )
        else:
            # Fallback if no blockers exist (all apps are READY)
            observations.append(
                Observation(
                    title="No integration blockers detected",
                    description=(
                        "All analyzed apps have a READY buildability verdict with no "
                        "identified blockers preventing toolkit integration."
                    ),
                    supporting_data=f"{total_apps}/{total_apps} apps have no blockers",
                    opportunity=(
                        "Proceed with full-scale integration across all analyzed apps "
                        "since no systematic barriers exist."
                    ),
                )
            )

        # Observation 4: Access model distribution insight
        self_serve_total = sum(
            counts.get("self_serve", 0) for counts in access_dist.per_category.values()
        )
        gated_total = sum(
            counts.get("gated", 0) for counts in access_dist.per_category.values()
        )

        # Find categories that are majority gated
        gated_categories = [
            cat
            for cat, classification in access_dist.category_classification.items()
            if classification == "majority_gated"
        ]

        if total_apps > 0:
            self_serve_pct = round(self_serve_total / total_apps * 100, 1)
        else:
            self_serve_pct = 0.0

        observations.append(
            Observation(
                title="Access model landscape",
                description=(
                    f"{self_serve_total} apps offer self-serve API access while "
                    f"{gated_total} require gated access (paid plans, partnerships, or approvals). "
                    f"{len(gated_categories)} categories are majority-gated."
                ),
                supporting_data=(
                    f"{self_serve_total}/{total_apps} apps ({self_serve_pct}%) are self-serve; "
                    f"{len(gated_categories)} categories are majority-gated"
                ),
                opportunity=(
                    "For gated-majority categories, establish partnership programs or "
                    "explore community-contributed integrations to expand coverage "
                    "without direct API access requirements."
                ),
            )
        )

        return observations
