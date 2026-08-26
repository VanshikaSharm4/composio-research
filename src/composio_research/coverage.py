"""Category coverage validation and reporting for the Composio App Research Pipeline.

Validates that the pipeline processes exactly 10 apps per category (100 total),
reports per-category counts of successfully researched apps, and implements
the partial research threshold (>= 80% required fields populated).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from composio_research.config import CATEGORIES
from composio_research.models import AppRecord, ResearchStatus


# Required fields for the 80% threshold completeness check.
# These are the 7 fields an AppRecord must have populated to be
# considered fully researched.
REQUIRED_FIELDS: list[str] = [
    "app_name",
    "category",
    "description",
    "auth_methods",
    "access_model",
    "api_surface_has_public_api",
    "buildability_verdict",
]


@dataclass
class CategoryCoverage:
    """Per-category coverage breakdown."""

    category: str
    target_count: int  # always 10
    total_records: int
    successfully_researched: int
    failed_count: int
    unresearchable_count: int
    partial_count: int
    unresearchable_apps: list[dict]  # [{app_name, reason}]

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "category": self.category,
            "target_count": self.target_count,
            "total_records": self.total_records,
            "successfully_researched": self.successfully_researched,
            "failed_count": self.failed_count,
            "unresearchable_count": self.unresearchable_count,
            "partial_count": self.partial_count,
            "unresearchable_apps": self.unresearchable_apps,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CategoryCoverage:
        """Deserialize from a dictionary."""
        return cls(
            category=data["category"],
            target_count=data["target_count"],
            total_records=data["total_records"],
            successfully_researched=data["successfully_researched"],
            failed_count=data["failed_count"],
            unresearchable_count=data["unresearchable_count"],
            partial_count=data["partial_count"],
            unresearchable_apps=data["unresearchable_apps"],
        )


@dataclass
class CoverageSummary:
    """Overall coverage summary across all categories."""

    total_apps: int  # should be 100
    total_successfully_researched: int
    per_category: list[CategoryCoverage]
    is_valid: bool  # True if 10 per category and 100 total
    validation_errors: list[str]  # any issues found

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "total_apps": self.total_apps,
            "total_successfully_researched": self.total_successfully_researched,
            "per_category": [c.to_dict() for c in self.per_category],
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CoverageSummary:
        """Deserialize from a dictionary."""
        return cls(
            total_apps=data["total_apps"],
            total_successfully_researched=data["total_successfully_researched"],
            per_category=[CategoryCoverage.from_dict(c) for c in data["per_category"]],
            is_valid=data["is_valid"],
            validation_errors=data["validation_errors"],
        )


class CoverageValidator:
    """Validates category coverage and computes research success metrics.

    Ensures exactly 10 apps per category are processed (100 total) and
    reports per-category counts of successfully researched apps using
    the 80% field population threshold for partial records.
    """

    def validate(self, records: list[AppRecord]) -> CoverageSummary:
        """Validate coverage across all records and produce a summary.

        Args:
            records: List of all AppRecords produced by the pipeline.

        Returns:
            CoverageSummary with per-category breakdowns and validation status.
        """
        validation_errors: list[str] = []
        grouped = self._count_per_category(records)

        # Check that all 10 expected categories are present
        present_categories = set(grouped.keys())
        expected_categories = set(CATEGORIES)
        missing_categories = expected_categories - present_categories
        extra_categories = present_categories - expected_categories

        if missing_categories:
            validation_errors.append(
                f"Missing categories: {sorted(missing_categories)}"
            )
        if extra_categories:
            validation_errors.append(
                f"Unexpected categories: {sorted(extra_categories)}"
            )

        # Validate count per category
        per_category_coverages: list[CategoryCoverage] = []

        for category in CATEGORIES:
            cat_records = grouped.get(category, [])
            count = len(cat_records)

            if count != 10:
                validation_errors.append(
                    f"Category '{category}' has {count} records (expected 10)"
                )

            # Compute per-status counts
            failed_count = sum(
                1 for r in cat_records if r.research_status == ResearchStatus.FAILED
            )
            unresearchable_count = sum(
                1 for r in cat_records
                if r.research_status == ResearchStatus.UNRESEARCHABLE
            )
            partial_count = sum(
                1 for r in cat_records if r.research_status == ResearchStatus.PARTIAL
            )

            # Compute successfully researched using threshold
            successfully_researched = sum(
                1 for r in cat_records if self._is_successfully_researched(r)
            )

            # Collect unresearchable app details
            unresearchable_apps = [
                {
                    "app_name": r.app_name,
                    "reason": r.failure_reason or "Unknown reason",
                }
                for r in cat_records
                if r.research_status == ResearchStatus.UNRESEARCHABLE
            ]

            per_category_coverages.append(
                CategoryCoverage(
                    category=category,
                    target_count=10,
                    total_records=count,
                    successfully_researched=successfully_researched,
                    failed_count=failed_count,
                    unresearchable_count=unresearchable_count,
                    partial_count=partial_count,
                    unresearchable_apps=unresearchable_apps,
                )
            )

        # Total validation
        total_apps = len(records)
        if total_apps != 100:
            validation_errors.append(
                f"Total app count is {total_apps} (expected 100)"
            )

        # Check category count
        if len(present_categories & expected_categories) != 10:
            validation_errors.append(
                f"Found {len(present_categories & expected_categories)} valid categories (expected 10)"
            )

        total_successfully_researched = sum(
            c.successfully_researched for c in per_category_coverages
        )

        is_valid = total_apps == 100 and all(
            c.total_records == 10 for c in per_category_coverages
        ) and not missing_categories and not extra_categories

        return CoverageSummary(
            total_apps=total_apps,
            total_successfully_researched=total_successfully_researched,
            per_category=per_category_coverages,
            is_valid=is_valid,
            validation_errors=validation_errors,
        )

    def _count_per_category(
        self, records: list[AppRecord]
    ) -> dict[str, list[AppRecord]]:
        """Group records by their category.

        Args:
            records: Flat list of AppRecords.

        Returns:
            Dictionary mapping category name to list of AppRecords in that category.
        """
        grouped: dict[str, list[AppRecord]] = {}
        for record in records:
            grouped.setdefault(record.category, []).append(record)
        return grouped

    def _is_successfully_researched(self, record: AppRecord) -> bool:
        """Determine whether a record counts as successfully researched.

        A record is considered successfully researched if:
        - research_status is COMPLETE, OR
        - research_status is PARTIAL AND >= 80% of required fields are populated.

        Records with FAILED or UNRESEARCHABLE status are never counted as
        successfully researched.

        Args:
            record: The AppRecord to evaluate.

        Returns:
            True if the record meets the success threshold.
        """
        if record.research_status == ResearchStatus.COMPLETE:
            return True
        if record.research_status == ResearchStatus.PARTIAL:
            return self._compute_field_population_percentage(record) >= 80.0
        return False

    def _get_required_fields(self) -> list[str]:
        """Return the list of required field names for completeness check.

        Returns:
            List of 7 required field identifiers.
        """
        return list(REQUIRED_FIELDS)

    def _compute_field_population_percentage(self, record: AppRecord) -> float:
        """Calculate what percentage of required fields are populated.

        Required fields (7 total):
        - app_name: non-empty string
        - category: non-empty string
        - description: non-empty string
        - auth_methods: non-empty list
        - access_model: always set (enum value)
        - api_surface_has_public_api: api_surface.has_public_api is not None
        - buildability_verdict: always set (enum value)

        Args:
            record: The AppRecord to evaluate.

        Returns:
            Percentage (0-100) of required fields that are populated.
        """
        total_fields = len(REQUIRED_FIELDS)
        populated = 0

        # app_name: non-empty string
        if record.app_name and record.app_name.strip():
            populated += 1

        # category: non-empty string
        if record.category and record.category.strip():
            populated += 1

        # description: non-empty string
        if record.description and record.description.strip():
            populated += 1

        # auth_methods: non-empty list
        if record.auth_methods and len(record.auth_methods) > 0:
            populated += 1

        # access_model: always set as it's a required enum field;
        # count as populated if it exists (it's always an enum value)
        if record.access_model is not None:
            populated += 1

        # api_surface.has_public_api: the boolean is set (not None-like)
        # Since has_public_api is a bool, it's always set (True/False),
        # so we count it as populated if api_surface exists
        if record.api_surface is not None:
            populated += 1

        # buildability_verdict: always set as it's a required enum field
        if record.buildability_verdict is not None:
            populated += 1

        return (populated / total_fields) * 100.0
