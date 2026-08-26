"""Composio App Research Pipeline.

Automated research pipeline that analyzes 100 apps across 10 categories
for Composio's AI tooling platform. The pipeline has four stages:
Researcher, Verifier, Pattern Analyzer, and HTML Generator.
"""

__version__ = "0.1.0"

from composio_research.coverage import (  # noqa: F401
    CategoryCoverage,
    CoverageSummary,
    CoverageValidator,
)
