"""Pipeline Coordinator for the Composio App Research Pipeline.

Top-level orchestrator that manages stage execution in sequence:
Researcher -> Verifier -> Pattern Analyzer -> HTML Generator.
Handles error recovery, checkpointing (resume from last successful stage),
and intervention logging.
"""

from __future__ import annotations

import json
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol

from composio_research.config import PipelineConfig
from composio_research.models import (
    AppRecord,
    InterventionEntry,
    PatternAnalysis,
    VerificationMetrics,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Pipeline Stage Enum
# ============================================================================


class PipelineStage(str, Enum):
    """The four sequential stages of the research pipeline."""

    RESEARCHER = "researcher"
    VERIFIER = "verifier"
    PATTERN_ANALYZER = "pattern_analyzer"
    HTML_GENERATOR = "html_generator"


# Stage execution order
STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.RESEARCHER,
    PipelineStage.VERIFIER,
    PipelineStage.PATTERN_ANALYZER,
    PipelineStage.HTML_GENERATOR,
]


# ============================================================================
# Result Dataclasses
# ============================================================================


@dataclass
class StageResult:
    """Result from executing a single pipeline stage.

    Attributes:
        stage: The pipeline stage that was executed.
        success: Whether the stage completed without fatal errors.
        output_files: List of output file paths written by this stage.
        error: Error message if the stage failed.
        error_traceback: Full traceback string if an exception occurred.
    """

    stage: PipelineStage
    success: bool
    output_files: list[str] = field(default_factory=list)
    error: Optional[str] = None
    error_traceback: Optional[str] = None


@dataclass
class PipelineResult:
    """Overall result from running the full pipeline.

    Attributes:
        status: Final status - "completed", "partial", or "failed".
        output_dir: Path to the output directory containing all files.
        stages_completed: List of stages that completed successfully.
        stage_results: Results for each stage that was attempted.
        errors: List of error messages from failed stages.
        total_apps_processed: Number of apps that were processed.
    """

    status: str  # "completed", "partial", "failed"
    output_dir: Path
    stages_completed: list[str] = field(default_factory=list)
    stage_results: list[StageResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_apps_processed: int = 0


# ============================================================================
# Stage Agent Protocols
# ============================================================================


class ResearcherProtocol(Protocol):
    """Protocol for the researcher agent."""

    async def research_batch(self, apps: list[Any]) -> list[AppRecord]: ...


class VerifierProtocol(Protocol):
    """Protocol for the verifier agent."""

    async def verify(self, records: list[AppRecord]) -> tuple[list[AppRecord], VerificationMetrics]: ...


class PatternAnalyzerProtocol(Protocol):
    """Protocol for the pattern analyzer."""

    def analyze(self, records: list[AppRecord]) -> PatternAnalysis: ...


class HtmlGeneratorProtocol(Protocol):
    """Protocol for the HTML generator."""

    def generate(self, data: dict[str, Any], output_path: Path) -> None: ...


# ============================================================================
# Pipeline Coordinator
# ============================================================================

CHECKPOINT_FILENAME = ".checkpoint"
INTERVENTION_LOG_FILENAME = "intervention_log.json"


class PipelineCoordinator:
    """Top-level orchestrator for the Composio App Research Pipeline.

    Manages sequential execution of four stages (researcher, verifier,
    pattern_analyzer, html_generator) with checkpointing, error handling,
    and intervention logging.
    """

    def __init__(
        self,
        app_list: list[Any],
        output_dir: Path,
        config: PipelineConfig,
    ) -> None:
        """Initialize the pipeline coordinator.

        Args:
            app_list: List of AppInput instances defining the 100 apps to research.
            output_dir: Directory where all pipeline outputs are written.
            config: Pipeline configuration with retry, timeout, and other settings.
        """
        self.app_list = app_list
        self.output_dir = output_dir
        self.config = config
        self.intervention_log: list[InterventionEntry] = []

        # Stage agent references (set externally or via set_agents)
        self._researcher: Optional[ResearcherProtocol] = None
        self._verifier: Optional[VerifierProtocol] = None
        self._pattern_analyzer: Optional[PatternAnalyzerProtocol] = None
        self._html_generator: Optional[HtmlGeneratorProtocol] = None

        # In-memory state for passing data between stages
        self._app_records: list[AppRecord] = []
        self._verified_records: list[AppRecord] = []
        self._verification_metrics: Optional[VerificationMetrics] = None
        self._pattern_analysis: Optional[PatternAnalysis] = None

    def set_agents(
        self,
        researcher: Optional[ResearcherProtocol] = None,
        verifier: Optional[VerifierProtocol] = None,
        pattern_analyzer: Optional[PatternAnalyzerProtocol] = None,
        html_generator: Optional[HtmlGeneratorProtocol] = None,
    ) -> None:
        """Set the agent instances used by each pipeline stage.

        Args:
            researcher: Agent for app research stage.
            verifier: Agent for verification stage.
            pattern_analyzer: Analyzer for pattern computation stage.
            html_generator: Generator for HTML output stage.
        """
        if researcher is not None:
            self._researcher = researcher
        if verifier is not None:
            self._verifier = verifier
        if pattern_analyzer is not None:
            self._pattern_analyzer = pattern_analyzer
        if html_generator is not None:
            self._html_generator = html_generator

    async def run(self) -> PipelineResult:
        """Execute all pipeline stages in sequence.

        Creates the output directory if it doesn't exist, checks for a
        checkpoint to resume from, and executes stages in order. On each
        stage completion, writes a checkpoint marker file.

        Returns:
            PipelineResult with overall status and any errors.
        """
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Check for checkpoint to determine resume point
        checkpoint = self.get_checkpoint()
        start_index = 0
        if checkpoint is not None:
            try:
                completed_stage = PipelineStage(checkpoint)
                completed_index = STAGE_ORDER.index(completed_stage)
                start_index = completed_index + 1
                logger.info(
                    "Resuming from checkpoint: last completed stage is '%s'",
                    checkpoint,
                )
            except (ValueError, KeyError):
                logger.warning(
                    "Invalid checkpoint value '%s', starting from beginning.",
                    checkpoint,
                )
                start_index = 0

        result = PipelineResult(
            status="failed",
            output_dir=self.output_dir,
        )

        # If resuming, load intermediate state from existing files
        if start_index > 0:
            self._load_intermediate_state(start_index)

        # Execute stages in sequence from start_index
        for stage in STAGE_ORDER[start_index:]:
            stage_result = await self.run_stage(stage)
            result.stage_results.append(stage_result)

            if stage_result.success:
                result.stages_completed.append(stage.value)
                self._write_checkpoint(stage)
            else:
                if stage_result.error:
                    result.errors.append(
                        f"Stage '{stage.value}' failed: {stage_result.error}"
                    )
                # Stop pipeline on stage failure
                break

        # Write intervention log
        self._write_intervention_log()

        # Determine overall status
        if len(result.stages_completed) == len(STAGE_ORDER):
            result.status = "completed"
        elif len(result.stages_completed) > 0:
            result.status = "partial"
        else:
            result.status = "failed"

        result.total_apps_processed = len(self._app_records)

        return result

    async def run_stage(self, stage: PipelineStage) -> StageResult:
        """Execute a single pipeline stage with error handling.

        Calls the appropriate agent/analyzer for the stage, writes output
        JSON to the output directory, and logs interventions on errors.

        Args:
            stage: The pipeline stage to execute.

        Returns:
            StageResult with success status and output file paths.
        """
        logger.info("Starting stage: %s", stage.value)

        try:
            if stage == PipelineStage.RESEARCHER:
                return await self._run_researcher_stage()
            elif stage == PipelineStage.VERIFIER:
                return await self._run_verifier_stage()
            elif stage == PipelineStage.PATTERN_ANALYZER:
                return await self._run_pattern_analyzer_stage()
            elif stage == PipelineStage.HTML_GENERATOR:
                return await self._run_html_generator_stage()
            else:
                return StageResult(
                    stage=stage,
                    success=False,
                    error=f"Unknown stage: {stage.value}",
                )
        except Exception as exc:
            tb = traceback.format_exc()
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error("Stage '%s' failed: %s", stage.value, error_msg)

            # Log intervention
            self._log_intervention(
                app_name="N/A",
                pipeline_stage=stage.value,
                reason=error_msg,
                data_point=None,
            )

            return StageResult(
                stage=stage,
                success=False,
                error=error_msg,
                error_traceback=tb,
            )

    def get_checkpoint(self) -> Optional[str]:
        """Return the last successfully completed stage name for resume.

        Reads the .checkpoint file in the output directory.

        Returns:
            Stage name string, or None if no checkpoint exists.
        """
        checkpoint_path = self.output_dir / CHECKPOINT_FILENAME
        if checkpoint_path.exists():
            content = checkpoint_path.read_text().strip()
            if content:
                return content
        return None

    # ========================================================================
    # Private: Stage Execution Methods
    # ========================================================================

    async def _run_researcher_stage(self) -> StageResult:
        """Execute the researcher stage."""
        if self._researcher is None:
            return StageResult(
                stage=PipelineStage.RESEARCHER,
                success=False,
                error="Researcher agent not configured. Use set_agents() to provide one.",
            )

        self._app_records = await self._researcher.research_batch(self.app_list)

        # Write output
        output_path = self.output_dir / "app_records.json"
        self._write_json(
            output_path,
            [record.to_dict() for record in self._app_records],
        )

        logger.info(
            "Researcher stage complete: %d app records written.",
            len(self._app_records),
        )
        return StageResult(
            stage=PipelineStage.RESEARCHER,
            success=True,
            output_files=[str(output_path)],
        )

    async def _run_verifier_stage(self) -> StageResult:
        """Execute the verifier stage."""
        if self._verifier is None:
            return StageResult(
                stage=PipelineStage.VERIFIER,
                success=False,
                error="Verifier agent not configured. Use set_agents() to provide one.",
            )

        if not self._app_records:
            return StageResult(
                stage=PipelineStage.VERIFIER,
                success=False,
                error="No app records available. Researcher stage must run first.",
            )

        self._verified_records, self._verification_metrics = (
            await self._verifier.verify(self._app_records)
        )

        # Write verified records
        verified_path = self.output_dir / "verified_records.json"
        self._write_json(
            verified_path,
            [record.to_dict() for record in self._verified_records],
        )

        # Write verification metrics
        metrics_path = self.output_dir / "verification_metrics.json"
        self._write_json(metrics_path, self._verification_metrics.to_dict())

        logger.info(
            "Verifier stage complete: %d verified records, overall accuracy %.1f%%.",
            len(self._verified_records),
            self._verification_metrics.overall_accuracy,
        )
        return StageResult(
            stage=PipelineStage.VERIFIER,
            success=True,
            output_files=[str(verified_path), str(metrics_path)],
        )

    async def _run_pattern_analyzer_stage(self) -> StageResult:
        """Execute the pattern analyzer stage."""
        if self._pattern_analyzer is None:
            return StageResult(
                stage=PipelineStage.PATTERN_ANALYZER,
                success=False,
                error="Pattern analyzer not configured. Use set_agents() to provide one.",
            )

        records = self._verified_records if self._verified_records else self._app_records
        if not records:
            return StageResult(
                stage=PipelineStage.PATTERN_ANALYZER,
                success=False,
                error="No records available. Research or verification stage must run first.",
            )

        self._pattern_analysis = self._pattern_analyzer.analyze(records)

        # Write output
        output_path = self.output_dir / "pattern_analysis.json"
        self._write_json(output_path, self._pattern_analysis.to_dict())

        logger.info("Pattern analyzer stage complete.")
        return StageResult(
            stage=PipelineStage.PATTERN_ANALYZER,
            success=True,
            output_files=[str(output_path)],
        )

    async def _run_html_generator_stage(self) -> StageResult:
        """Execute the HTML generator stage."""
        if self._html_generator is None:
            return StageResult(
                stage=PipelineStage.HTML_GENERATOR,
                success=False,
                error="HTML generator not configured. Use set_agents() to provide one.",
            )

        records = self._verified_records if self._verified_records else self._app_records
        if not records:
            return StageResult(
                stage=PipelineStage.HTML_GENERATOR,
                success=False,
                error="No records available for HTML generation.",
            )

        output_path = self.output_dir / "deliverable.html"

        # Assemble all data for the HTML generator
        html_data: dict[str, Any] = {
            "app_records": [r.to_dict() for r in records],
            "pattern_analysis": (
                self._pattern_analysis.to_dict()
                if self._pattern_analysis is not None
                else None
            ),
            "verification_metrics": (
                self._verification_metrics.to_dict()
                if self._verification_metrics is not None
                else None
            ),
            "intervention_log": [e.to_dict() for e in self.intervention_log],
        }

        self._html_generator.generate(html_data, output_path)

        logger.info("HTML generator stage complete: %s", output_path)
        return StageResult(
            stage=PipelineStage.HTML_GENERATOR,
            success=True,
            output_files=[str(output_path)],
        )

    # ========================================================================
    # Private: Checkpointing
    # ========================================================================

    def _write_checkpoint(self, stage: PipelineStage) -> None:
        """Write the checkpoint file with the last completed stage name."""
        checkpoint_path = self.output_dir / CHECKPOINT_FILENAME
        try:
            checkpoint_path.write_text(stage.value)
            logger.debug("Checkpoint written: %s", stage.value)
        except OSError as exc:
            logger.warning("Failed to write checkpoint: %s", exc)

    # ========================================================================
    # Private: Intervention Logging
    # ========================================================================

    def _log_intervention(
        self,
        app_name: str,
        pipeline_stage: str,
        reason: str,
        data_point: Optional[str],
    ) -> None:
        """Record an intervention entry."""
        entry = InterventionEntry(
            app_name=app_name,
            pipeline_stage=pipeline_stage,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            data_point=data_point,
        )
        self.intervention_log.append(entry)

    def _write_intervention_log(self) -> None:
        """Write the intervention log JSON to the output directory."""
        log_path = self.output_dir / INTERVENTION_LOG_FILENAME
        try:
            self._write_json(
                log_path,
                [entry.to_dict() for entry in self.intervention_log],
            )
            logger.debug("Intervention log written with %d entries.", len(self.intervention_log))
        except OSError as exc:
            logger.error("Failed to write intervention log: %s", exc)

    # ========================================================================
    # Private: JSON I/O Helpers
    # ========================================================================

    def _write_json(self, path: Path, data: Any) -> None:
        """Write data as formatted JSON to the given path.

        Args:
            path: Output file path.
            data: JSON-serializable data.

        Raises:
            OSError: If the file cannot be written.
        """
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except OSError as exc:
            logger.error("Failed to write JSON to %s: %s", path, exc)
            self._log_intervention(
                app_name="N/A",
                pipeline_stage="coordinator",
                reason=f"Failed to write file '{path.name}': {exc}",
                data_point=None,
            )
            raise

    def _load_intermediate_state(self, start_index: int) -> None:
        """Load intermediate state from previously written JSON files.

        Used when resuming from a checkpoint to restore in-memory data
        that prior stages would have produced.

        Args:
            start_index: Index into STAGE_ORDER indicating where to resume.
        """
        # If resuming past researcher, load app_records
        if start_index > 0:
            app_records_path = self.output_dir / "app_records.json"
            if app_records_path.exists():
                try:
                    raw = json.loads(app_records_path.read_text())
                    self._app_records = [AppRecord.from_dict(r) for r in raw]
                    logger.info("Loaded %d app records from checkpoint.", len(self._app_records))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning("Failed to load app_records.json: %s", exc)

        # If resuming past verifier, load verified records and metrics
        if start_index > 1:
            verified_path = self.output_dir / "verified_records.json"
            if verified_path.exists():
                try:
                    raw = json.loads(verified_path.read_text())
                    self._verified_records = [AppRecord.from_dict(r) for r in raw]
                    logger.info("Loaded %d verified records from checkpoint.", len(self._verified_records))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning("Failed to load verified_records.json: %s", exc)

            metrics_path = self.output_dir / "verification_metrics.json"
            if metrics_path.exists():
                try:
                    raw = json.loads(metrics_path.read_text())
                    self._verification_metrics = VerificationMetrics.from_dict(raw)
                    logger.info("Loaded verification metrics from checkpoint.")
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning("Failed to load verification_metrics.json: %s", exc)

        # If resuming past pattern analyzer, load pattern analysis
        if start_index > 2:
            pattern_path = self.output_dir / "pattern_analysis.json"
            if pattern_path.exists():
                try:
                    raw = json.loads(pattern_path.read_text())
                    self._pattern_analysis = PatternAnalysis.from_dict(raw)
                    logger.info("Loaded pattern analysis from checkpoint.")
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning("Failed to load pattern_analysis.json: %s", exc)

        # Load existing intervention log if present
        log_path = self.output_dir / INTERVENTION_LOG_FILENAME
        if log_path.exists():
            try:
                raw = json.loads(log_path.read_text())
                self.intervention_log = [InterventionEntry.from_dict(e) for e in raw]
                logger.info("Loaded %d intervention log entries.", len(self.intervention_log))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Failed to load intervention log: %s", exc)
