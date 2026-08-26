"""CLI entry point for the Composio App Research Pipeline.

Usage:
    python -m composio_research [--output-dir PATH] [--max-retries N] [--timeout N]
                                [--concurrency N] [--llm-model MODEL]
                                [--composio-api-key KEY] [--resume]

Runs the full pipeline: Researcher -> Verifier -> Pattern Analyzer -> HTML Generator.
Outputs JSON intermediate files and a self-contained HTML deliverable.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from composio_research.app_list import APP_LIST
from composio_research.config import PipelineConfig
from composio_research.coordinator import PipelineCoordinator
from composio_research.html_generator import HtmlGenerator
from composio_research.pattern_analyzer import PatternAnalyzer
from composio_research.researcher import ResearchConfig, ResearcherAgent
from composio_research.verifier import VerificationConfig, VerifierAgent


# ============================================================================
# Composio SDK Client Factory
# ============================================================================


def create_composio_client(api_key: Optional[str] = None) -> Any:
    """Create a Composio SDK client if available, otherwise return None.

    Args:
        api_key: Optional API key for Composio. Falls back to COMPOSIO_API_KEY
            environment variable if not provided.

    Returns:
        ComposioClient instance if composio-core is installed, otherwise None.
        When None, agents will use httpx fallback for web requests.
    """
    try:
        from composio import ComposioClient  # type: ignore[import-untyped]

        return ComposioClient(api_key=api_key)
    except ImportError:
        # Composio SDK not installed; agents will use httpx fallback
        return None
    except Exception:
        # SDK installed but initialization failed (e.g., missing key)
        return None


# ============================================================================
# CLI Argument Parsing
# ============================================================================


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI entry point.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="composio_research",
        description=(
            "Composio App Research Pipeline - Automated research and analysis "
            "of 100 apps across 10 categories for AI tooling integration."
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Directory where all pipeline outputs are written (default: ./output)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retry attempts for external requests (default: 3)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds for individual HTTP requests (default: 30)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Maximum concurrent requests during batch operations (default: 5)",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default="gpt-4o",
        help="LLM model identifier for research agents (default: gpt-4o)",
    )
    parser.add_argument(
        "--composio-api-key",
        type=str,
        default=None,
        help=(
            "API key for Composio SDK access. "
            "Falls back to COMPOSIO_API_KEY environment variable."
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Resume from the last checkpoint instead of starting fresh",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose (DEBUG) logging output",
    )

    return parser


# ============================================================================
# Pipeline Setup and Execution
# ============================================================================


def create_pipeline_config(args: argparse.Namespace) -> PipelineConfig:
    """Create a PipelineConfig from parsed CLI arguments.

    Args:
        args: Parsed argparse namespace.

    Returns:
        Configured PipelineConfig instance.
    """
    api_key = args.composio_api_key or os.environ.get("COMPOSIO_API_KEY")

    return PipelineConfig(
        output_dir=Path(args.output_dir),
        max_retries=args.max_retries,
        request_timeout_seconds=args.timeout,
        concurrency_limit=args.concurrency,
        llm_model=args.llm_model,
        composio_api_key=api_key,
    )


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the pipeline.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )


async def run_pipeline(args: argparse.Namespace) -> int:
    """Set up and execute the full research pipeline.

    Creates all agent instances, wires them to the coordinator,
    and runs the pipeline to completion.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code: 0 for success, 1 for partial completion, 2 for failure.
    """
    config = create_pipeline_config(args)
    output_dir = config.output_dir

    # Resolve the Composio SDK client
    composio_client = create_composio_client(config.composio_api_key)
    if composio_client is None:
        logging.getLogger(__name__).warning(
            "Composio SDK not available. Agents will use httpx fallback."
        )

    # Create agent instances with appropriate configs
    gemini_api_key = os.environ.get("GEMINI_API_KEY")

    research_config = ResearchConfig(
        max_retries=config.max_retries,
        timeout_seconds=config.request_timeout_seconds,
        concurrency_limit=config.concurrency_limit,
        composio_api_key=config.composio_api_key,
        gemini_api_key=gemini_api_key,
        gemini_model=config.llm_model,
    )
    researcher = ResearcherAgent(composio_client, research_config)

    verification_config = VerificationConfig(
        min_passes=config.min_verification_passes,
        max_passes=config.max_verification_passes,
        min_accuracy_threshold=config.min_accuracy_threshold,
        max_resolution_attempts=config.max_retries,
        timeout_seconds=config.request_timeout_seconds,
        composio_api_key=config.composio_api_key,
    )
    verifier = VerifierAgent(composio_client, verification_config)

    pattern_analyzer = PatternAnalyzer()
    html_generator = HtmlGenerator()

    # Create coordinator and wire agents
    coordinator = PipelineCoordinator(
        app_list=APP_LIST,
        output_dir=output_dir,
        config=config,
    )
    coordinator.set_agents(
        researcher=researcher,
        verifier=verifier,
        pattern_analyzer=pattern_analyzer,
        html_generator=html_generator,
    )

    # Handle resume: if --resume is NOT set and output dir exists with checkpoint,
    # remove the checkpoint to force a fresh run
    if not args.resume:
        checkpoint_file = output_dir / ".checkpoint"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

    # Execute the pipeline
    logger = logging.getLogger(__name__)
    logger.info("Starting Composio App Research Pipeline")
    logger.info("Output directory: %s", output_dir)
    logger.info("Processing %d apps across %d categories", len(APP_LIST), 10)

    result = await coordinator.run()

    # Print summary
    print("\n" + "=" * 60)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Status: {result.status}")
    print(f"Output directory: {result.output_dir}")
    print(f"Stages completed: {', '.join(result.stages_completed) or 'none'}")
    print(f"Apps processed: {result.total_apps_processed}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  - {error}")

    # List output files
    output_files = []
    for stage_result in result.stage_results:
        output_files.extend(stage_result.output_files)
    if output_files:
        print(f"\nOutput files ({len(output_files)}):")
        for f in output_files:
            print(f"  - {f}")

    print("=" * 60)

    # Return exit code based on status
    if result.status == "completed":
        return 0
    elif result.status == "partial":
        return 1
    else:
        return 2


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> None:
    """Parse arguments and run the pipeline."""
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    exit_code = asyncio.run(run_pipeline(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
