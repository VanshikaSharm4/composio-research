"""Data models and enums for the Composio App Research Pipeline.

Defines all structured data types including AppRecord, PatternAnalysis,
VerificationMetrics, and supporting enums for auth methods, access models,
API types, coverage levels, buildability verdicts, blocker categories,
and research statuses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================================
# Enums
# ============================================================================


class AuthMethod(str, Enum):
    """Authentication method an app uses for API access."""

    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BASIC = "basic"
    TOKEN = "token"
    OTHER = "other"


class AccessModel(str, Enum):
    """Whether API credentials are self-serve or gated."""

    SELF_SERVE = "self_serve"
    GATED = "gated"


class ApiType(str, Enum):
    """Type of public API available."""

    REST = "rest"
    GRAPHQL = "graphql"
    BOTH = "both"
    NONE = "none"


class ApiCoverage(str, Enum):
    """How much of the app's features are exposed via API."""

    FULL = "full"
    PARTIAL = "partial"
    MINIMAL = "minimal"


class BuildabilityVerdict(str, Enum):
    """Assessment of whether the app could be an agent toolkit today."""

    READY = "ready"
    FEASIBLE = "feasible"
    BLOCKED = "blocked"


class BlockerCategory(str, Enum):
    """Primary blocker preventing an app from being toolkit-ready."""

    NO_PUBLIC_API = "no_public_api"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    RESTRICTIVE_AUTH = "restrictive_auth"
    RATE_LIMITS = "rate_limits"
    MISSING_DOCUMENTATION = "missing_documentation"


class ResearchStatus(str, Enum):
    """Status of research completion for an app."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    UNRESEARCHABLE = "unresearchable"


# ============================================================================
# Dataclasses - Core App Data
# ============================================================================


@dataclass
class ApiSurface:
    """Documented public API capabilities for an app."""

    has_public_api: bool
    api_type: Optional[ApiType]
    coverage: Optional[ApiCoverage]
    has_mcp_support: bool
    evidence_url: Optional[str]

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "has_public_api": self.has_public_api,
            "api_type": self.api_type.value if self.api_type is not None else None,
            "coverage": self.coverage.value if self.coverage is not None else None,
            "has_mcp_support": self.has_mcp_support,
            "evidence_url": self.evidence_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ApiSurface:
        """Deserialize from a dictionary."""
        return cls(
            has_public_api=data["has_public_api"],
            api_type=ApiType(data["api_type"]) if data.get("api_type") is not None else None,
            coverage=ApiCoverage(data["coverage"]) if data.get("coverage") is not None else None,
            has_mcp_support=data["has_mcp_support"],
            evidence_url=data.get("evidence_url"),
        )


@dataclass
class AppRecord:
    """Structured data captured for a single researched app."""

    app_name: str
    category: str
    description: str  # max 120 chars
    auth_methods: list[AuthMethod]
    access_model: AccessModel
    api_surface: ApiSurface
    buildability_verdict: BuildabilityVerdict
    primary_blocker: Optional[BlockerCategory]
    evidence_urls: dict[str, str]  # field_name -> URL
    research_status: ResearchStatus
    missing_fields: list[str]
    failure_reason: Optional[str]
    failure_category: Optional[str]

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "app_name": self.app_name,
            "category": self.category,
            "description": self.description,
            "auth_methods": [m.value for m in self.auth_methods],
            "access_model": self.access_model.value,
            "api_surface": self.api_surface.to_dict(),
            "buildability_verdict": self.buildability_verdict.value,
            "primary_blocker": self.primary_blocker.value if self.primary_blocker is not None else None,
            "evidence_urls": self.evidence_urls,
            "research_status": self.research_status.value,
            "missing_fields": self.missing_fields,
            "failure_reason": self.failure_reason,
            "failure_category": self.failure_category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AppRecord:
        """Deserialize from a dictionary."""
        return cls(
            app_name=data["app_name"],
            category=data["category"],
            description=data["description"],
            auth_methods=[AuthMethod(m) for m in data["auth_methods"]],
            access_model=AccessModel(data["access_model"]),
            api_surface=ApiSurface.from_dict(data["api_surface"]),
            buildability_verdict=BuildabilityVerdict(data["buildability_verdict"]),
            primary_blocker=BlockerCategory(data["primary_blocker"]) if data.get("primary_blocker") is not None else None,
            evidence_urls=data["evidence_urls"],
            research_status=ResearchStatus(data["research_status"]),
            missing_fields=data["missing_fields"],
            failure_reason=data.get("failure_reason"),
            failure_category=data.get("failure_category"),
        )


# ============================================================================
# Dataclasses - Pattern Analysis
# ============================================================================


@dataclass
class AuthDistribution:
    """Frequency distribution of auth methods per category and overall."""

    per_category: dict[str, dict[str, int]]  # category -> {auth_method: count}
    overall: dict[str, int]  # auth_method -> count
    dominant_per_category: dict[str, str]  # category -> most_common_auth

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "per_category": self.per_category,
            "overall": self.overall,
            "dominant_per_category": self.dominant_per_category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AuthDistribution:
        """Deserialize from a dictionary."""
        return cls(
            per_category=data["per_category"],
            overall=data["overall"],
            dominant_per_category=data["dominant_per_category"],
        )


@dataclass
class AccessDistribution:
    """Count of self-serve vs gated per category."""

    per_category: dict[str, dict[str, int]]  # category -> {self_serve: N, gated: N}
    category_classification: dict[str, str]  # category -> "majority_self_serve" | "majority_gated"

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "per_category": self.per_category,
            "category_classification": self.category_classification,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AccessDistribution:
        """Deserialize from a dictionary."""
        return cls(
            per_category=data["per_category"],
            category_classification=data["category_classification"],
        )


@dataclass
class BlockerRank:
    """A blocker category ranked by frequency."""

    blocker: str
    count: int
    rank: int

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "blocker": self.blocker,
            "count": self.count,
            "rank": self.rank,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BlockerRank:
        """Deserialize from a dictionary."""
        return cls(
            blocker=data["blocker"],
            count=data["count"],
            rank=data["rank"],
        )


@dataclass
class Observation:
    """A data-backed observation with actionable recommendation."""

    title: str
    description: str
    supporting_data: str  # specific counts or percentages
    opportunity: str  # actionable recommendation

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "title": self.title,
            "description": self.description,
            "supporting_data": self.supporting_data,
            "opportunity": self.opportunity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Observation:
        """Deserialize from a dictionary."""
        return cls(
            title=data["title"],
            description=data["description"],
            supporting_data=data["supporting_data"],
            opportunity=data["opportunity"],
        )


@dataclass
class PatternAnalysis:
    """Cross-app analysis identifying trends and strategic opportunities."""

    auth_distribution: AuthDistribution
    access_distribution: AccessDistribution
    blocker_rankings: list[BlockerRank]  # sorted by frequency, top 5+
    easy_win_apps: list[str]
    outreach_required_apps: list[str]
    observations: list[Observation]  # minimum 3

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "auth_distribution": self.auth_distribution.to_dict(),
            "access_distribution": self.access_distribution.to_dict(),
            "blocker_rankings": [b.to_dict() for b in self.blocker_rankings],
            "easy_win_apps": self.easy_win_apps,
            "outreach_required_apps": self.outreach_required_apps,
            "observations": [o.to_dict() for o in self.observations],
        }

    @classmethod
    def from_dict(cls, data: dict) -> PatternAnalysis:
        """Deserialize from a dictionary."""
        return cls(
            auth_distribution=AuthDistribution.from_dict(data["auth_distribution"]),
            access_distribution=AccessDistribution.from_dict(data["access_distribution"]),
            blocker_rankings=[BlockerRank.from_dict(b) for b in data["blocker_rankings"]],
            easy_win_apps=data["easy_win_apps"],
            outreach_required_apps=data["outreach_required_apps"],
            observations=[Observation.from_dict(o) for o in data["observations"]],
        )


# ============================================================================
# Dataclasses - Verification
# ============================================================================


@dataclass
class Discrepancy:
    """A data point that contradicted or could not be confirmed by evidence."""

    app_name: str
    field_name: str
    original_value: str
    corrected_value: Optional[str]
    resolution_status: str  # "resolved", "unresolved", "partially_resolved"
    evidence_urls_checked: list[str]
    reason: Optional[str]

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "app_name": self.app_name,
            "field_name": self.field_name,
            "original_value": self.original_value,
            "corrected_value": self.corrected_value,
            "resolution_status": self.resolution_status,
            "evidence_urls_checked": self.evidence_urls_checked,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Discrepancy:
        """Deserialize from a dictionary."""
        return cls(
            app_name=data["app_name"],
            field_name=data["field_name"],
            original_value=data["original_value"],
            corrected_value=data.get("corrected_value"),
            resolution_status=data["resolution_status"],
            evidence_urls_checked=data["evidence_urls_checked"],
            reason=data.get("reason"),
        )


@dataclass
class PassMetrics:
    """Metrics for a single verification pass."""

    pass_number: int
    accuracy_percentage: float  # 0-100
    total_data_points: int
    confirmed_points: int
    discrepancies_found: int
    corrections_applied: int

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "pass_number": self.pass_number,
            "accuracy_percentage": self.accuracy_percentage,
            "total_data_points": self.total_data_points,
            "confirmed_points": self.confirmed_points,
            "discrepancies_found": self.discrepancies_found,
            "corrections_applied": self.corrections_applied,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PassMetrics:
        """Deserialize from a dictionary."""
        return cls(
            pass_number=data["pass_number"],
            accuracy_percentage=data["accuracy_percentage"],
            total_data_points=data["total_data_points"],
            confirmed_points=data["confirmed_points"],
            discrepancies_found=data["discrepancies_found"],
            corrections_applied=data["corrections_applied"],
        )


@dataclass
class VerificationMetrics:
    """Overall verification results across all passes."""

    passes_completed: int
    per_pass_metrics: list[PassMetrics]
    discrepancy_log: list[Discrepancy]
    overall_accuracy: float
    requires_manual_review: bool  # True if final accuracy < 80%

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "passes_completed": self.passes_completed,
            "per_pass_metrics": [p.to_dict() for p in self.per_pass_metrics],
            "discrepancy_log": [d.to_dict() for d in self.discrepancy_log],
            "overall_accuracy": self.overall_accuracy,
            "requires_manual_review": self.requires_manual_review,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VerificationMetrics:
        """Deserialize from a dictionary."""
        return cls(
            passes_completed=data["passes_completed"],
            per_pass_metrics=[PassMetrics.from_dict(p) for p in data["per_pass_metrics"]],
            discrepancy_log=[Discrepancy.from_dict(d) for d in data["discrepancy_log"]],
            overall_accuracy=data["overall_accuracy"],
            requires_manual_review=data["requires_manual_review"],
        )


# ============================================================================
# Dataclasses - Intervention Logging
# ============================================================================


@dataclass
class InterventionEntry:
    """Record of a point where automation required human intervention."""

    app_name: str
    pipeline_stage: str
    reason: str
    timestamp: str  # ISO 8601
    data_point: Optional[str]

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "app_name": self.app_name,
            "pipeline_stage": self.pipeline_stage,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "data_point": self.data_point,
        }

    @classmethod
    def from_dict(cls, data: dict) -> InterventionEntry:
        """Deserialize from a dictionary."""
        return cls(
            app_name=data["app_name"],
            pipeline_stage=data["pipeline_stage"],
            reason=data["reason"],
            timestamp=data["timestamp"],
            data_point=data.get("data_point"),
        )
