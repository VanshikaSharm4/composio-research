"""Tests for PipelineCoordinator including stage execution order, checkpoint
resume behavior, error handling, and intervention logging.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from composio_research.config import PipelineConfig
from composio_research.coordinator import (
    STAGE_ORDER,
    PipelineCoordinator,
    PipelineResult,
    PipelineStage,
    StageResult,
)
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
# Helper: Sample Data Factories
# ============================================================================


def make_sample_app_record(
    app_name: str = "TestApp",
    category: str = "CRM & Sales",
) -> AppRecord:
    """Create a sample AppRecord for testing."""
    return AppRecord(
        app_name=app_name,
        category=category,
        description="A test app for unit testing",
        auth_methods=[AuthMethod.OAUTH2],
        access_model=AccessModel.SELF_SERVE,
        api_surface=ApiSurface(
            has_public_api=True,
            api_type=ApiType.REST,
            coverage=ApiCoverage.FULL,
            has_mcp_support=False,
            evidence_url="https://example.com/docs",
        ),
        buildability_verdict=BuildabilityVerdict.READY,
        primary_blocker=None,
        evidence_urls={"auth_methods": "https://example.com/auth"},
        research_status=ResearchStatus.COMPLETE,
        missing_fields=[],
        failure_reason=None,
        failure_category=None,
    )


def make_sample_verification_metrics() -> VerificationMetrics:
    """Create sample VerificationMetrics for testing."""
    return VerificationMetrics(
        passes_completed=2,
        per_pass_metrics=[
            PassMetrics(
                pass_number=1,
                accuracy_percentage=85.0,
                total_data_points=100,
                confirmed_points=85,
                discrepancies_found=15,
                corrections_applied=10,
            ),
            PassMetrics(
                pass_number=2,
                accuracy_percentage=92.0,
                total_data_points=100,
                confirmed_points=92,
                discrepancies_found=8,
                corrections_applied=5,
            ),
        ],
        discrepancy_log=[
            Discrepancy(
                app_name="TestApp",
                field_name="auth_methods",
                original_value="basic",
                corrected_value="oauth2",
                resolution_status="resolved",
                evidence_urls_checked=["https://example.com/docs"],
                reason="Documentation confirms OAuth2",
            ),
        ],
        overall_accuracy=92.0,
        requires_manual_review=False,
    )


def make_sample_pattern_analysis() -> PatternAnalysis:
    """Create sample PatternAnalysis for testing."""
    return PatternAnalysis(
        auth_distribution=AuthDistribution(
            per_category={"CRM & Sales": {"oauth2": 5, "api_key": 3, "token": 2}},
            overall={"oauth2": 50, "api_key": 30, "token": 20},
            dominant_per_category={"CRM & Sales": "oauth2"},
        ),
        access_distribution=AccessDistribution(
            per_category={"CRM & Sales": {"self_serve": 7, "gated": 3}},
            category_classification={"CRM & Sales": "majority_self_serve"},
        ),
        blocker_rankings=[
            BlockerRank(blocker="no_public_api", count=15, rank=1),
            BlockerRank(blocker="insufficient_coverage", count=10, rank=2),
        ],
        easy_win_apps=["TestApp"],
        outreach_required_apps=["GatedApp"],
        observations=[
            Observation(
                title="OAuth2 Dominance",
                description="OAuth2 is the most common auth method",
                supporting_data="50 out of 100 apps use OAuth2",
                opportunity="Prioritize OAuth2 integration tooling",
            ),
            Observation(
                title="Self-serve majority",
                description="Most categories have majority self-serve access",
                supporting_data="7 of 10 categories are majority self-serve",
                opportunity="Focus on self-serve apps for fastest expansion",
            ),
            Observation(
                title="API coverage gaps",
                description="Insufficient coverage is the #2 blocker",
                supporting_data="10 apps blocked by insufficient coverage",
                opportunity="Partner with apps that have partial APIs",
            ),
        ],
    )


# ============================================================================
# Mock Agents
# ============================================================================


class MockResearcher:
    """Mock researcher agent that returns predefined AppRecords."""

    def __init__(self, records: list[AppRecord] | None = None, should_raise: bool = False):
        self.records = records or [make_sample_app_record()]
        self.should_raise = should_raise
        self.research_batch_called = False

    async def research_batch(self, apps: list[Any]) -> list[AppRecord]:
        self.research_batch_called = True
        if self.should_raise:
            raise RuntimeError("Research failed: network timeout")
        return self.records


class MockVerifier:
    """Mock verifier agent that returns (records, metrics)."""

    def __init__(
        self,
        records: list[AppRecord] | None = None,
        metrics: VerificationMetrics | None = None,
        should_raise: bool = False,
    ):
        self.records = records or [make_sample_app_record()]
        self.metrics = metrics or make_sample_verification_metrics()
        self.should_raise = should_raise
        self.verify_called = False

    async def verify(self, records: list[AppRecord]) -> tuple[list[AppRecord], VerificationMetrics]:
        self.verify_called = True
        if self.should_raise:
            raise RuntimeError("Verification failed: evidence URL inaccessible")
        return self.records, self.metrics


class MockPatternAnalyzer:
    """Mock pattern analyzer that returns PatternAnalysis."""

    def __init__(
        self,
        analysis: PatternAnalysis | None = None,
        should_raise: bool = False,
    ):
        self.analysis = analysis or make_sample_pattern_analysis()
        self.should_raise = should_raise
        self.analyze_called = False

    def analyze(self, records: list[AppRecord]) -> PatternAnalysis:
        self.analyze_called = True
        if self.should_raise:
            raise RuntimeError("Pattern analysis failed: malformed input")
        return self.analysis


class MockHtmlGenerator:
    """Mock HTML generator that writes a simple file."""

    def __init__(self, should_raise: bool = False):
        self.should_raise = should_raise
        self.generate_called = False
        self.last_output_path: Path | None = None

    def generate(self, data: dict[str, Any], output_path: Path) -> None:
        self.generate_called = True
        self.last_output_path = output_path
        if self.should_raise:
            raise RuntimeError("HTML generation failed: write error")
        output_path.write_text("<html><body>Deliverable</body></html>")


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_app_list() -> list[dict[str, str]]:
    """Simple app list for coordinator initialization."""
    return [{"app_name": "TestApp", "category": "CRM & Sales"}]


@pytest.fixture
def pipeline_config(tmp_path: Path) -> PipelineConfig:
    """Create a PipelineConfig using tmp_path as output directory."""
    return PipelineConfig(output_dir=tmp_path / "output")


@pytest.fixture
def coordinator(sample_app_list: list, pipeline_config: PipelineConfig) -> PipelineCoordinator:
    """Create a PipelineCoordinator with all mock agents configured."""
    coord = PipelineCoordinator(
        app_list=sample_app_list,
        output_dir=pipeline_config.output_dir,
        config=pipeline_config,
    )
    coord.set_agents(
        researcher=MockResearcher(),
        verifier=MockVerifier(),
        pattern_analyzer=MockPatternAnalyzer(),
        html_generator=MockHtmlGenerator(),
    )
    return coord


# ============================================================================
# Tests: Stage Execution Order
# ============================================================================


class TestStageExecutionOrder:
    """Tests verifying stages execute in the correct order."""

    def test_stage_order_constant(self):
        """STAGE_ORDER defines the four stages in the expected sequence."""
        assert STAGE_ORDER == [
            PipelineStage.RESEARCHER,
            PipelineStage.VERIFIER,
            PipelineStage.PATTERN_ANALYZER,
            PipelineStage.HTML_GENERATOR,
        ]

    @pytest.mark.asyncio
    async def test_all_stages_execute_in_order(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """All four stages execute sequentially when all agents succeed."""
        researcher = MockResearcher()
        verifier = MockVerifier()
        pattern_analyzer = MockPatternAnalyzer()
        html_generator = MockHtmlGenerator()

        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=researcher,
            verifier=verifier,
            pattern_analyzer=pattern_analyzer,
            html_generator=html_generator,
        )

        result = await coord.run()

        # All agents were called
        assert researcher.research_batch_called
        assert verifier.verify_called
        assert pattern_analyzer.analyze_called
        assert html_generator.generate_called

        # Result indicates full completion
        assert result.status == "completed"
        assert len(result.stages_completed) == 4
        assert result.stages_completed == [
            "researcher",
            "verifier",
            "pattern_analyzer",
            "html_generator",
        ]

    @pytest.mark.asyncio
    async def test_pipeline_result_is_completed_on_success(self, coordinator: PipelineCoordinator):
        """PipelineResult status is 'completed' when all stages succeed."""
        result = await coordinator.run()
        assert result.status == "completed"
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_stage_results_recorded(self, coordinator: PipelineCoordinator):
        """Each executed stage produces a StageResult in the pipeline result."""
        result = await coordinator.run()
        assert len(result.stage_results) == 4
        for stage_result in result.stage_results:
            assert stage_result.success is True
            assert stage_result.error is None


# ============================================================================
# Tests: Output Directory and File Writing
# ============================================================================


class TestOutputFiles:
    """Tests verifying output directory creation and JSON file writing."""

    @pytest.mark.asyncio
    async def test_output_directory_created(self, coordinator: PipelineCoordinator, pipeline_config: PipelineConfig):
        """Output directory is created if it doesn't exist."""
        assert not pipeline_config.output_dir.exists()
        await coordinator.run()
        assert pipeline_config.output_dir.exists()
        assert pipeline_config.output_dir.is_dir()

    @pytest.mark.asyncio
    async def test_app_records_json_written(self, coordinator: PipelineCoordinator, pipeline_config: PipelineConfig):
        """app_records.json is written by the researcher stage."""
        await coordinator.run()
        path = pipeline_config.output_dir / "app_records.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["app_name"] == "TestApp"

    @pytest.mark.asyncio
    async def test_verified_records_json_written(self, coordinator: PipelineCoordinator, pipeline_config: PipelineConfig):
        """verified_records.json is written by the verifier stage."""
        await coordinator.run()
        path = pipeline_config.output_dir / "verified_records.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_verification_metrics_json_written(self, coordinator: PipelineCoordinator, pipeline_config: PipelineConfig):
        """verification_metrics.json is written by the verifier stage."""
        await coordinator.run()
        path = pipeline_config.output_dir / "verification_metrics.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "passes_completed" in data
        assert "overall_accuracy" in data

    @pytest.mark.asyncio
    async def test_pattern_analysis_json_written(self, coordinator: PipelineCoordinator, pipeline_config: PipelineConfig):
        """pattern_analysis.json is written by the pattern analyzer stage."""
        await coordinator.run()
        path = pipeline_config.output_dir / "pattern_analysis.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "auth_distribution" in data
        assert "blocker_rankings" in data

    @pytest.mark.asyncio
    async def test_intervention_log_json_written(self, coordinator: PipelineCoordinator, pipeline_config: PipelineConfig):
        """intervention_log.json is always written, even if empty."""
        await coordinator.run()
        path = pipeline_config.output_dir / "intervention_log.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_html_deliverable_written(self, coordinator: PipelineCoordinator, pipeline_config: PipelineConfig):
        """deliverable.html is written by the HTML generator stage."""
        await coordinator.run()
        path = pipeline_config.output_dir / "deliverable.html"
        assert path.exists()
        content = path.read_text()
        assert "<html>" in content

    @pytest.mark.asyncio
    async def test_total_apps_processed_count(self, coordinator: PipelineCoordinator):
        """PipelineResult reports the number of apps processed."""
        result = await coordinator.run()
        assert result.total_apps_processed == 1  # One sample record


# ============================================================================
# Tests: Checkpoint Behavior
# ============================================================================


class TestCheckpointBehavior:
    """Tests verifying checkpoint file writing and resume from checkpoint."""

    @pytest.mark.asyncio
    async def test_checkpoint_written_after_full_run(self, coordinator: PipelineCoordinator, pipeline_config: PipelineConfig):
        """After successful run, .checkpoint file contains 'html_generator'."""
        await coordinator.run()
        checkpoint_path = pipeline_config.output_dir / ".checkpoint"
        assert checkpoint_path.exists()
        assert checkpoint_path.read_text().strip() == "html_generator"

    @pytest.mark.asyncio
    async def test_checkpoint_written_after_each_stage(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """Checkpoint is updated after each successful stage."""
        # Make verifier raise so pipeline stops after researcher
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(),
            verifier=MockVerifier(should_raise=True),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(),
        )

        await coord.run()
        checkpoint_path = pipeline_config.output_dir / ".checkpoint"
        assert checkpoint_path.exists()
        # Only researcher completed, so checkpoint is "researcher"
        assert checkpoint_path.read_text().strip() == "researcher"

    def test_get_checkpoint_returns_none_when_no_file(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """get_checkpoint() returns None when no checkpoint file exists."""
        pipeline_config.output_dir.mkdir(parents=True, exist_ok=True)
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        assert coord.get_checkpoint() is None

    def test_get_checkpoint_returns_stage_name(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """get_checkpoint() returns the stage name from checkpoint file."""
        pipeline_config.output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = pipeline_config.output_dir / ".checkpoint"
        checkpoint_path.write_text("researcher")

        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        assert coord.get_checkpoint() == "researcher"

    @pytest.mark.asyncio
    async def test_resume_from_researcher_checkpoint(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """When checkpoint is 'researcher', verifier runs next on resume."""
        # Setup: write checkpoint and app_records.json
        pipeline_config.output_dir.mkdir(parents=True, exist_ok=True)
        (pipeline_config.output_dir / ".checkpoint").write_text("researcher")

        # Write app_records.json as if researcher already ran
        sample_record = make_sample_app_record()
        (pipeline_config.output_dir / "app_records.json").write_text(
            json.dumps([sample_record.to_dict()], indent=2)
        )

        researcher = MockResearcher()
        verifier = MockVerifier()
        pattern_analyzer = MockPatternAnalyzer()
        html_generator = MockHtmlGenerator()

        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=researcher,
            verifier=verifier,
            pattern_analyzer=pattern_analyzer,
            html_generator=html_generator,
        )

        result = await coord.run()

        # Researcher should NOT have been called (skipped due to checkpoint)
        assert not researcher.research_batch_called
        # Verifier, pattern_analyzer, and html_generator should have been called
        assert verifier.verify_called
        assert pattern_analyzer.analyze_called
        assert html_generator.generate_called
        # stages_completed only tracks stages run in this execution
        assert "verifier" in result.stages_completed
        assert "pattern_analyzer" in result.stages_completed
        assert "html_generator" in result.stages_completed
        assert "researcher" not in result.stages_completed
        # No errors encountered
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_resume_from_verifier_checkpoint(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """When checkpoint is 'verifier', pattern_analyzer runs next."""
        pipeline_config.output_dir.mkdir(parents=True, exist_ok=True)
        (pipeline_config.output_dir / ".checkpoint").write_text("verifier")

        # Write required intermediate files
        sample_record = make_sample_app_record()
        (pipeline_config.output_dir / "app_records.json").write_text(
            json.dumps([sample_record.to_dict()], indent=2)
        )
        (pipeline_config.output_dir / "verified_records.json").write_text(
            json.dumps([sample_record.to_dict()], indent=2)
        )
        metrics = make_sample_verification_metrics()
        (pipeline_config.output_dir / "verification_metrics.json").write_text(
            json.dumps(metrics.to_dict(), indent=2)
        )

        researcher = MockResearcher()
        verifier = MockVerifier()
        pattern_analyzer = MockPatternAnalyzer()
        html_generator = MockHtmlGenerator()

        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=researcher,
            verifier=verifier,
            pattern_analyzer=pattern_analyzer,
            html_generator=html_generator,
        )

        result = await coord.run()

        # Only pattern_analyzer and html_generator should run
        assert not researcher.research_batch_called
        assert not verifier.verify_called
        assert pattern_analyzer.analyze_called
        assert html_generator.generate_called
        # stages_completed only tracks stages run in this execution
        assert "pattern_analyzer" in result.stages_completed
        assert "html_generator" in result.stages_completed
        assert "researcher" not in result.stages_completed
        assert "verifier" not in result.stages_completed
        # No errors encountered
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_invalid_checkpoint_restarts_from_beginning(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """Invalid checkpoint value causes pipeline to start from beginning."""
        pipeline_config.output_dir.mkdir(parents=True, exist_ok=True)
        (pipeline_config.output_dir / ".checkpoint").write_text("invalid_stage")

        researcher = MockResearcher()
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=researcher,
            verifier=MockVerifier(),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(),
        )

        result = await coord.run()
        assert researcher.research_batch_called
        assert result.status == "completed"


# ============================================================================
# Tests: Error Handling
# ============================================================================


class TestErrorHandling:
    """Tests verifying error handling and pipeline status on failures."""

    @pytest.mark.asyncio
    async def test_researcher_raises_pipeline_fails(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """When researcher raises, PipelineResult status is 'failed', error is recorded."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(should_raise=True),
            verifier=MockVerifier(),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(),
        )

        result = await coord.run()

        assert result.status == "failed"
        assert len(result.errors) == 1
        assert "researcher" in result.errors[0].lower() or "Research failed" in result.errors[0]
        assert len(result.stages_completed) == 0

    @pytest.mark.asyncio
    async def test_verifier_raises_partial_status(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """When verifier raises, status is 'partial' and researcher is in stages_completed."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(),
            verifier=MockVerifier(should_raise=True),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(),
        )

        result = await coord.run()

        assert result.status == "partial"
        assert "researcher" in result.stages_completed
        assert "verifier" not in result.stages_completed
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_pattern_analyzer_raises_partial_status(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """When pattern_analyzer raises, researcher and verifier are completed."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(),
            verifier=MockVerifier(),
            pattern_analyzer=MockPatternAnalyzer(should_raise=True),
            html_generator=MockHtmlGenerator(),
        )

        result = await coord.run()

        assert result.status == "partial"
        assert "researcher" in result.stages_completed
        assert "verifier" in result.stages_completed
        assert "pattern_analyzer" not in result.stages_completed

    @pytest.mark.asyncio
    async def test_html_generator_raises_partial_status(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """When html_generator raises, first three stages are completed."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(),
            verifier=MockVerifier(),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(should_raise=True),
        )

        result = await coord.run()

        assert result.status == "partial"
        assert "researcher" in result.stages_completed
        assert "verifier" in result.stages_completed
        assert "pattern_analyzer" in result.stages_completed
        assert "html_generator" not in result.stages_completed

    @pytest.mark.asyncio
    async def test_researcher_not_configured_returns_error(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """When researcher agent is not configured, stage returns error and pipeline stops."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        # Don't set any agents

        result = await coord.run()

        assert result.status == "failed"
        assert len(result.errors) == 1
        assert "not configured" in result.errors[0].lower() or "set_agents" in result.errors[0]

    @pytest.mark.asyncio
    async def test_verifier_not_configured_returns_error(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """When verifier agent is not configured, pipeline is partial."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(researcher=MockResearcher())
        # verifier not set

        result = await coord.run()

        assert result.status == "partial"
        assert "researcher" in result.stages_completed
        assert any("not configured" in e.lower() or "set_agents" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_pipeline_stops_on_first_failure(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """Pipeline stops executing stages after the first failure."""
        pattern_analyzer = MockPatternAnalyzer()
        html_generator = MockHtmlGenerator()

        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(should_raise=True),
            verifier=MockVerifier(),
            pattern_analyzer=pattern_analyzer,
            html_generator=html_generator,
        )

        await coord.run()

        # Subsequent stages should not have been called
        assert not pattern_analyzer.analyze_called
        assert not html_generator.generate_called

    @pytest.mark.asyncio
    async def test_stage_result_contains_error_traceback(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """StageResult includes traceback on exception."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(should_raise=True),
            verifier=MockVerifier(),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(),
        )

        result = await coord.run()

        failed_stage = result.stage_results[0]
        assert failed_stage.success is False
        assert failed_stage.error is not None
        assert "RuntimeError" in failed_stage.error
        assert failed_stage.error_traceback is not None
        assert "Traceback" in failed_stage.error_traceback


# ============================================================================
# Tests: Intervention Logging
# ============================================================================


class TestInterventionLogging:
    """Tests verifying intervention log entries on failures."""

    @pytest.mark.asyncio
    async def test_intervention_logged_on_stage_failure(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """Intervention entry is logged when a stage fails with an exception."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(should_raise=True),
            verifier=MockVerifier(),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(),
        )

        await coord.run()

        # Check intervention log was populated
        assert len(coord.intervention_log) > 0
        entry = coord.intervention_log[0]
        assert entry.pipeline_stage == "researcher"
        assert "Research failed" in entry.reason or "RuntimeError" in entry.reason
        assert entry.timestamp != ""

    @pytest.mark.asyncio
    async def test_intervention_log_json_contains_entries(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """intervention_log.json contains entries for failed operations."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(should_raise=True),
            verifier=MockVerifier(),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(),
        )

        await coord.run()

        log_path = pipeline_config.output_dir / "intervention_log.json"
        assert log_path.exists()
        data = json.loads(log_path.read_text())
        assert isinstance(data, list)
        assert len(data) > 0

        entry = data[0]
        assert "app_name" in entry
        assert "pipeline_stage" in entry
        assert "reason" in entry
        assert "timestamp" in entry

    @pytest.mark.asyncio
    async def test_intervention_entry_has_required_fields(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """Each intervention entry has app_name, pipeline_stage, reason, timestamp."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(should_raise=True),
            verifier=MockVerifier(),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(),
        )

        await coord.run()

        for entry in coord.intervention_log:
            assert entry.app_name is not None
            assert entry.pipeline_stage is not None
            assert entry.reason is not None
            assert entry.timestamp is not None

    @pytest.mark.asyncio
    async def test_no_intervention_on_success(self, coordinator: PipelineCoordinator, pipeline_config: PipelineConfig):
        """No intervention entries when all stages succeed."""
        await coordinator.run()

        log_path = pipeline_config.output_dir / "intervention_log.json"
        data = json.loads(log_path.read_text())
        assert data == []

    @pytest.mark.asyncio
    async def test_multiple_failures_multiple_interventions(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """Multiple stage failures result in corresponding intervention entries (one per failure since pipeline stops)."""
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(
            researcher=MockResearcher(should_raise=True),
            verifier=MockVerifier(),
            pattern_analyzer=MockPatternAnalyzer(),
            html_generator=MockHtmlGenerator(),
        )

        await coord.run()

        # Pipeline stops at first failure so only one intervention
        assert len(coord.intervention_log) == 1
        assert coord.intervention_log[0].pipeline_stage == "researcher"


# ============================================================================
# Tests: run_stage() Directly
# ============================================================================


class TestRunStage:
    """Tests for running individual stages via run_stage()."""

    @pytest.mark.asyncio
    async def test_run_stage_researcher_success(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """run_stage() returns successful StageResult for researcher."""
        pipeline_config.output_dir.mkdir(parents=True, exist_ok=True)
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(researcher=MockResearcher())

        result = await coord.run_stage(PipelineStage.RESEARCHER)

        assert result.success is True
        assert result.stage == PipelineStage.RESEARCHER
        assert len(result.output_files) > 0

    @pytest.mark.asyncio
    async def test_run_stage_researcher_failure(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """run_stage() returns failed StageResult when researcher raises."""
        pipeline_config.output_dir.mkdir(parents=True, exist_ok=True)
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(researcher=MockResearcher(should_raise=True))

        result = await coord.run_stage(PipelineStage.RESEARCHER)

        assert result.success is False
        assert result.error is not None
        assert "RuntimeError" in result.error

    @pytest.mark.asyncio
    async def test_run_stage_verifier_no_records(self, sample_app_list: list, pipeline_config: PipelineConfig):
        """run_stage() for verifier fails gracefully when no records exist."""
        pipeline_config.output_dir.mkdir(parents=True, exist_ok=True)
        coord = PipelineCoordinator(
            app_list=sample_app_list,
            output_dir=pipeline_config.output_dir,
            config=pipeline_config,
        )
        coord.set_agents(verifier=MockVerifier())

        result = await coord.run_stage(PipelineStage.VERIFIER)

        assert result.success is False
        assert "no app records" in result.error.lower() or "must run first" in result.error.lower()
