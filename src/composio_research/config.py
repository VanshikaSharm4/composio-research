"""Pipeline configuration for the Composio App Research Pipeline.

Defines PipelineConfig dataclass with all configuration fields including
output directory, retry settings, verification passes, accuracy thresholds,
API keys, LLM model selection, and concurrency limits.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


CATEGORIES: list[str] = [
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


@dataclass
class PipelineConfig:
    """Configuration for the research pipeline.

    Attributes:
        output_dir: Directory where all pipeline outputs are written.
        max_retries: Maximum retry attempts for external requests.
        request_timeout_seconds: Timeout for individual HTTP requests.
        min_verification_passes: Minimum number of verification passes to run.
        max_verification_passes: Maximum number of verification passes to run.
        min_accuracy_threshold: Minimum accuracy percentage before flagging manual review.
        composio_api_key: API key for Composio SDK access.
        llm_model: LLM model identifier for research agents.
        concurrency_limit: Maximum concurrent requests during batch operations.
    """

    output_dir: Path
    max_retries: int = 3
    request_timeout_seconds: int = 30
    min_verification_passes: int = 2
    max_verification_passes: int = 4
    min_accuracy_threshold: float = 80.0
    composio_api_key: Optional[str] = None
    llm_model: str = "gpt-4o"
    concurrency_limit: int = 5
