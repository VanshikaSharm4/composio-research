# Implementation Plan: Composio App Research Pipeline

## Overview

This plan implements a Python-based automated research pipeline that analyzes 100 apps across 10 categories for Composio's AI tooling platform. The pipeline has four stages (Researcher, Verifier, Pattern Analyzer, HTML Generator) coordinated by a central orchestrator. The deliverable is a single-file HTML page with interactive filtering, dark-mode Tailwind CSS, and embedded data.

## Tasks

- [x] 1. Set up project structure, dependencies, and data models
  - [x] 1.1 Create Python project structure with pyproject.toml and dependencies
    - Create directory layout: `src/composio_research/` with `__init__.py`, `coordinator.py`, `researcher.py`, `verifier.py`, `pattern_analyzer.py`, `html_generator.py`, `models.py`, `config.py`, `app_list.py`
    - Create `tests/` directory with `__init__.py`, `test_models.py`, `test_pattern_analyzer.py`, `test_verifier.py`, `test_html_generator.py`, `test_coordinator.py`, `conftest.py`
    - Add `pyproject.toml` with dependencies: `composio-core`, `httpx`, `pydantic` (or dataclasses), `jinja2`, `hypothesis` (dev), `pytest` (dev), `pytest-asyncio` (dev)
    - _Requirements: 2.1, 2.2, 9.5_

  - [x] 1.2 Implement data models and enums in models.py
    - Implement all enums: `AuthMethod`, `AccessModel`, `ApiType`, `ApiCoverage`, `BuildabilityVerdict`, `BlockerCategory`, `ResearchStatus`
    - Implement dataclasses: `ApiSurface`, `AppRecord`, `AuthDistribution`, `AccessDistribution`, `BlockerRank`, `Observation`, `PatternAnalysis`
    - Implement dataclasses: `Discrepancy`, `PassMetrics`, `VerificationMetrics`, `InterventionEntry`
    - Implement JSON serialization/deserialization for all models with round-trip fidelity
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 9.1, 9.7_

  - [x] 1.3 Implement PipelineConfig and app list in config.py and app_list.py
    - Create `PipelineConfig` dataclass with all config fields (output_dir, max_retries, request_timeout_seconds, verification passes, accuracy threshold, composio_api_key, llm_model, concurrency_limit)
    - Create `CATEGORIES` list with all 10 category strings
    - Create `AppInput` dataclass and define the full list of 100 apps (10 per category) in `app_list.py`
    - _Requirements: 10.1, 10.2_

  - [x] 1.4 Write property test for AppRecord JSON round-trip (Property 6)
    - **Property 6: App record JSON round-trip**
    - Implement Hypothesis strategy for generating valid `AppRecord` instances covering all statuses, verdicts, and optional fields
    - Verify serialization to JSON and deserialization back produces equivalent AppRecord with all fields preserved
    - **Validates: Requirements 1.7, 8.6, 9.1, 9.7**

  - [x] 1.5 Write property test for conditional field population invariants (Property 9)
    - **Property 9: Conditional field population invariants**
    - Verify: if buildability_verdict is not READY, primary_blocker is non-None
    - Verify: if api_surface.has_public_api is True, api_type and coverage are non-None
    - Verify: if research_status is FAILED or UNRESEARCHABLE, failure_reason and failure_category are non-None
    - **Validates: Requirements 1.5, 1.6, 8.1**

- [x] 2. Implement Pipeline Coordinator
  - [x] 2.1 Implement PipelineCoordinator class in coordinator.py
    - Implement `__init__` accepting app_list, output_dir, and PipelineConfig
    - Implement `run()` method orchestrating all four stages in sequence
    - Implement `run_stage()` with error handling and checkpointing (write stage output to JSON files)
    - Implement `get_checkpoint()` returning last successfully completed stage for resume
    - Implement intervention logging: write `intervention_log.json` to output directory
    - _Requirements: 2.1, 2.3, 2.6, 8.4, 9.4, 9.5, 9.6_

  - [x] 2.2 Write unit tests for PipelineCoordinator
    - Test stage execution order
    - Test checkpoint resume behavior
    - Test error handling and intervention logging
    - Test output directory creation and file writing
    - _Requirements: 2.1, 2.6, 9.5, 9.6_

- [x] 3. Implement Researcher Agent
  - [x] 3.1 Implement ResearcherAgent class in researcher.py
    - Implement `__init__` with Composio SDK client and ResearchConfig
    - Implement `research_app()` for single app research: auth method collection, API surface assessment, access model determination, buildability verdict
    - Implement `research_batch()` for processing all apps with concurrency control and graceful failure handling
    - Implement `_collect_auth_method()` using Composio search/scrape tools to find API docs and classify auth
    - Implement `_assess_api_surface()` to determine REST/GraphQL availability, coverage level, and MCP support
    - Implement `_assess_access_model()` to determine self-serve vs gated access
    - Implement `_determine_buildability()` synthesizing all findings into verdict + blocker
    - Implement retry logic with exponential backoff (3 retries, 2s/4s delays, 30s timeout)
    - On failure after retries: mark `research_status = FAILED` with reason and category
    - On partial data: mark `research_status = PARTIAL`, populate available fields, list missing
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.4, 2.5, 8.1, 8.2, 8.3, 8.6_

  - [x] 3.2 Write unit tests for ResearcherAgent
    - Mock Composio SDK responses for various app documentation patterns
    - Test auth method classification (OAuth2 page, API key docs, multiple methods)
    - Test API surface assessment (REST detection, GraphQL schema, MCP availability)
    - Test access model determination (self-serve signup, gated/paid indicators)
    - Test failure handling (timeout, network error, parsing failure)
    - Test partial research marking and missing field tracking
    - _Requirements: 1.3, 1.4, 1.5, 1.7, 2.5, 8.1_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Verifier Agent
  - [x] 5.1 Implement VerifierAgent class in verifier.py
    - Implement `__init__` with Composio SDK client and VerificationConfig
    - Implement `verify()` running 2-4 verification passes over all records
    - Implement `_run_pass()` executing a single verification pass, comparing each data point against evidence URLs
    - Implement `_check_evidence()` to fetch evidence URL and verify a data point matches content
    - Implement `_resolve_discrepancy()` to re-research a specific data point (up to 3 attempts)
    - Compute per-pass metrics: accuracy_percentage, total_data_points, confirmed_points, discrepancies_found, corrections_applied
    - Set `requires_manual_review = True` if final accuracy < 80%
    - Mark unresolvable discrepancies with reason and evidence URLs checked
    - Output `verified_records.json` and `verification_metrics.json`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 9.3_

  - [x] 5.2 Write property test for verification accuracy metric consistency (Property 7)
    - **Property 7: Verification accuracy metric consistency**
    - Verify accuracy_percentage = (confirmed_points / total_data_points) × 100
    - Verify corrections_applied <= discrepancies_found
    - Verify requires_manual_review is True iff final pass accuracy < 80
    - **Validates: Requirements 3.3, 3.6**

  - [x] 5.3 Write unit tests for VerifierAgent
    - Test evidence URL checking (matching content, contradicting content, inaccessible URL)
    - Test discrepancy resolution with retries
    - Test multi-pass execution and metric accumulation
    - Test manual review flag trigger at <80% accuracy
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6_

- [x] 6. Implement Pattern Analyzer
  - [x] 6.1 Implement PatternAnalyzer class in pattern_analyzer.py
    - Implement `analyze()` orchestrating all analysis computations
    - Implement `_compute_auth_distribution()` computing per-category and overall auth method frequencies, identifying dominant method per category
    - Implement `_compute_access_distribution()` computing self-serve vs gated counts per category, classifying each category
    - Implement `_rank_blockers()` ranking all distinct blockers by frequency, reporting top 5+
    - Implement `_classify_apps()` classifying each app as easy-win or requires-outreach based on access_model, api_surface, and buildability_verdict
    - Implement `_generate_observations()` producing 3+ data-backed observations with specific counts/percentages and actionable recommendations
    - Output `pattern_analysis.json`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 9.2_

  - [x] 6.2 Write property test for auth distribution sums (Property 1)
    - **Property 1: Auth distribution sums to total app count**
    - Generate random AppRecords with varied auth_methods
    - Verify sum of overall distribution counts equals total auth method assignments
    - Verify dominant per category is the one with highest count
    - **Validates: Requirements 4.1**

  - [x] 6.3 Write property test for access distribution partitions (Property 2)
    - **Property 2: Access distribution partitions categories completely**
    - Generate random AppRecords grouped by category
    - Verify self_serve + gated counts per category equals total apps in that category
    - Verify category_classification is majority_self_serve iff self_serve > 50%
    - **Validates: Requirements 4.2**

  - [x] 6.4 Write property test for blocker rankings (Property 3)
    - **Property 3: Blocker rankings are frequency-sorted**
    - Generate random AppRecords with non-ready verdicts and random blockers
    - Verify rankings are sorted in non-increasing order of count
    - Verify all distinct blockers present in data are included
    - Verify at least top 5 reported if 5+ distinct blockers exist
    - **Validates: Requirements 4.3**

  - [x] 6.5 Write property test for easy-win classification (Property 4)
    - **Property 4: Easy-win classification is deterministic**
    - Generate random AppRecords with varied verdict/access/api combinations
    - Verify app is easy-win iff: access_model=SELF_SERVE AND has_public_api=True AND api_type in (REST, GRAPHQL, BOTH) AND buildability_verdict=READY
    - Verify union of easy-win and requires-outreach equals full app set
    - **Validates: Requirements 4.4**

  - [x] 6.6 Write unit tests for PatternAnalyzer
    - Test observation generation produces >= 3 observations with data references
    - Test edge cases: all apps same auth method, single category all gated, no blockers
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement HTML Generator
  - [x] 8.1 Implement HtmlGenerator class in html_generator.py
    - Implement `generate()` assembling the full HTML file from all pipeline outputs
    - Implement `_render_executive_summary()` generating 300-500 word summary section
    - Implement `_render_data_table()` generating the interactive 100-app filterable table with columns: App Name, Category, Buildability_Verdict, Access_Model, Auth_Method, Description
    - Implement `_render_pattern_section()` rendering auth distribution, access distribution, blocker rankings as labeled counts/percentages
    - Implement `_render_verification_section()` rendering per-pass accuracy and corrections
    - Implement `_render_architecture_section()` listing pipeline stages in execution order with input/output relationships
    - Implement `_render_transparency_section()` listing failed apps with categories, unconfirmed data points, and pipeline limitations
    - Implement `_embed_tailwind()` embedding Tailwind CSS via CDN script tag inline
    - Implement `_embed_javascript()` embedding all research data as JSON blob in `<script>` tag with vanilla JS filtering logic
    - Apply dark-mode color scheme throughout
    - Ensure single-file output with no external requests, functional via file:// protocol
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.5, 6.7, 6.8, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.5, 10.5_

  - [x] 8.2 Implement interactive filter logic in embedded JavaScript
    - Implement category filter dropdown
    - Implement buildability filter dropdown
    - Implement auth method filter dropdown
    - Implement AND logic for multi-filter combinations
    - Implement clear-all-filters reset showing all 100 apps
    - Display "no results" message with zero count when no apps match
    - Update displayed row count on filter change
    - _Requirements: 6.2, 6.3, 6.4, 6.6, 6.7, 6.8_

  - [x] 8.3 Write property test for filter intersection correctness (Property 5)
    - **Property 5: Filter intersection correctness**
    - Port filter logic to Python for testing (or test via generated data)
    - Generate random app datasets and random filter combinations
    - Verify displayed set equals intersection of individually applied filters
    - Verify displayed row count matches intersection cardinality
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.6, 6.8**

  - [x] 8.4 Write unit tests for HtmlGenerator
    - Test HTML structure contains all required sections (executive summary, architecture, verification, transparency, pattern analysis, data table)
    - Test badge rendering for each verdict/access value produces distinct styles
    - Test file size does not exceed 15 MB with sample data
    - Test HTML is valid and contains no external resource requests
    - _Requirements: 5.1, 5.2, 5.5, 6.5, 7.7_

- [x] 9. Implement category coverage and partial research logic
  - [x] 9.1 Implement category coverage validation and reporting
    - Add validation that exactly 10 apps per category are processed (100 total)
    - Implement per-category count reporting (successfully researched vs target)
    - Implement partial research threshold: count as successfully researched if >= 80% required fields populated
    - Add coverage summary data to HTML generator input
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 9.2 Write property test for category coverage invariant (Property 8)
    - **Property 8: Category coverage invariant**
    - Generate random records constrained to 10-per-category
    - Verify total records equals 100, distributed as exactly 10 per category across all 10 categories
    - Verify reported total of successfully researched apps equals sum of per-category successfully researched counts
    - **Validates: Requirements 10.1, 10.2, 10.4**

  - [x] 9.3 Write property test for partial research threshold (Property 10)
    - **Property 10: Partial research threshold**
    - Generate AppRecords with PARTIAL status and varied field population percentages
    - Verify app counted as successfully researched iff >= 80% required fields populated
    - Verify missing_fields list accurately reflects unpopulated fields
    - **Validates: Requirements 10.6, 1.7**

- [x] 10. Integration, wiring, and end-to-end testing
  - [x] 10.1 Wire all pipeline stages together in coordinator
    - Connect ResearcherAgent output → VerifierAgent input → PatternAnalyzer input → HtmlGenerator input
    - Implement JSON file I/O between stages (app_records.json, verified_records.json, verification_metrics.json, pattern_analysis.json, intervention_log.json)
    - Implement CLI entry point (`__main__.py`) with arguments for app list, output directory, and config overrides
    - Ensure no orphaned code: all modules imported and used in the coordinator flow
    - _Requirements: 2.1, 2.4, 2.6, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 10.2 Write integration tests with mocked external services
    - Create mock Composio SDK responses and web endpoint stubs
    - Test full pipeline end-to-end producing all output files
    - Verify output JSON files are independently parseable via `json.loads()`
    - Verify pipeline resume from checkpoint produces consistent results
    - Test timeout and retry behavior with artificially slow mock responses
    - _Requirements: 2.1, 2.5, 2.6, 9.5, 9.7_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document using Hypothesis (minimum 100 iterations per property)
- Unit tests validate specific examples and edge cases
- The pipeline uses Composio SDK for research (web search, scraping) and produces all outputs as JSON intermediates
- The HTML deliverable embeds all data inline for offline file:// usage
- Error handling uses exponential backoff (3 retries) and never fabricates data

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "2.1", "3.1"] },
    { "id": 3, "tasks": ["2.2", "3.2", "5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "6.5", "6.6"] },
    { "id": 6, "tasks": ["8.1", "9.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "8.4", "9.2", "9.3"] },
    { "id": 8, "tasks": ["10.1"] },
    { "id": 9, "tasks": ["10.2"] }
  ]
}
```