# Composio App Research Pipeline

Automated research pipeline that analyzes **100 apps across 10 categories** for integration into [Composio's](https://composio.dev) AI tooling platform. The pipeline assesses each app's authentication methods, API surface, access model, and buildability as an agent toolkit.

## Pipeline Architecture

```
┌──────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌────────────────┐
│  Researcher  │───▶│   Verifier   │───▶│ Pattern Analyzer│───▶│ HTML Generator │
│    Agent     │    │    Agent     │    │                 │    │                │
└──────────────┘    └──────────────┘    └─────────────────┘    └────────────────┘
       │                   │                     │                      │
       ▼                   ▼                     ▼                      ▼
 app_records.json   verified_records.json  pattern_analysis.json  deliverable.html
                    verification_metrics.json
```

**Stage 1 — Researcher Agent**: Researches each app using Composio SDK tools (web search, scraping) to collect auth methods, API surface, access model, and buildability verdict.

**Stage 2 — Verifier Agent**: Runs 2–4 verification passes, checking each data point against evidence URLs. Flags records requiring manual review if accuracy falls below 80%.

**Stage 3 — Pattern Analyzer**: Pure computation over verified records — auth distributions, access model breakdowns, blocker rankings, easy-win classification, and data-backed observations.

**Stage 4 — HTML Generator**: Produces a single-file HTML deliverable with dark-mode styling, interactive filters, and all data embedded inline (works offline via `file://`).

## Categories (10 × 10 apps = 100 total)

| Category | Example Apps |
|----------|-------------|
| CRM & Sales | Salesforce, HubSpot, Pipedrive |
| Support & Helpdesk | Zendesk, Freshdesk, Intercom |
| Communications & Messaging | Slack, Teams, Discord |
| Marketing/Ads/Email/Social | Mailchimp, Google Ads, Hootsuite |
| Ecommerce | Shopify, Stripe, WooCommerce |
| Data/SEO/Scraping | Ahrefs, SEMrush, Apify |
| Developer/Infra/Data | GitHub, GitLab, Datadog |
| Productivity & PM | Notion, Asana, Linear |
| Finance & Fintech | Stripe Billing, QuickBooks, Plaid |
| AI/Research/Media | OpenAI, Anthropic, ElevenLabs |

## Quick Start

### Prerequisites

- Python 3.11+
- (Optional) Composio API key for SDK-powered research

### Install

```bash
# Clone and install with dev dependencies
pip install -e ".[dev]"
```

### Run the Pipeline

```bash
# Basic run
python -m composio_research --output-dir ./output

# With API key
export COMPOSIO_API_KEY=sk-your-key
python -m composio_research --output-dir ./output --verbose

# See all options
python -m composio_research --help
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output-dir` | `./output` | Directory for all pipeline outputs |
| `--max-retries` | `3` | Max retry attempts per request |
| `--timeout` | `30` | HTTP request timeout (seconds) |
| `--concurrency` | `5` | Max concurrent research operations |
| `--llm-model` | `gpt-4o` | LLM model for research agents |
| `--composio-api-key` | env var | Composio SDK API key |
| `--resume` | off | Resume from last checkpoint |
| `--verbose` / `-v` | off | Enable DEBUG logging |

### Resume an Interrupted Run

```bash
python -m composio_research --output-dir ./output --resume
```

The pipeline writes a `.checkpoint` file after each stage, so it can resume from where it left off.

## Output Files

After a successful run, `output/` contains:

| File | Format | Description |
|------|--------|-------------|
| `app_records.json` | JSON array | Raw research data for all 100 apps |
| `verified_records.json` | JSON array | Records after multi-pass verification |
| `verification_metrics.json` | JSON object | Per-pass accuracy, discrepancy log |
| `pattern_analysis.json` | JSON object | Auth/access distributions, blocker rankings, observations |
| `intervention_log.json` | JSON array | Points where automation needed human input |
| `deliverable.html` | HTML | Self-contained interactive report |
| `.checkpoint` | text | Last completed stage name |

Each JSON file is independently parseable — no cross-file dependencies.

## Running Tests

```bash
# Full suite (339 tests, ~60s)
PYTHONPATH=src pytest tests/ -v

# Quick run (skip property-based tests)
PYTHONPATH=src pytest tests/ -v -k "not Property"

# Specific modules
PYTHONPATH=src pytest tests/test_integration.py -v
PYTHONPATH=src pytest tests/test_models.py -v
PYTHONPATH=src pytest tests/test_researcher.py -v

# With coverage
PYTHONPATH=src pytest tests/ --cov=composio_research --cov-report=term-missing
```

### Test Breakdown

| File | Tests | Coverage |
|------|-------|----------|
| `test_models.py` | 42 | Data models, JSON round-trip, Properties 6 & 9 |
| `test_researcher.py` | 52 | Auth detection, API assessment, retry logic |
| `test_pattern_analyzer.py` | 48 | Distributions, rankings, Properties 1–4 |
| `test_html_generator.py` | 44 | HTML structure, badges, no external requests |
| `test_html_filter_logic.py` | 42 | Filter dropdowns, AND logic, Property 5 |
| `test_verifier.py` | 37 | Evidence checking, multi-pass, Property 7 |
| `test_coordinator.py` | 35 | Stage order, checkpoints, error handling |
| `test_coverage.py` | 31 | Category validation, Properties 8 & 10 |
| `test_integration.py` | 8 | End-to-end with mocked services |

### Property-Based Tests (Hypothesis)

10 properties validated with 100+ examples each:

1. **Auth distribution sums** — overall counts = total auth assignments
2. **Access distribution partitions** — self_serve + gated = category total
3. **Blocker rankings sorted** — non-increasing frequency order
4. **Easy-win deterministic** — classification iff all criteria met
5. **Filter intersection** — combined filter = intersection of individual filters
6. **JSON round-trip** — serialize → deserialize preserves all fields
7. **Verification metrics** — accuracy = confirmed/total × 100
8. **Category coverage** — 10 categories × 10 apps = 100 total
9. **Conditional fields** — non-READY → blocker present, FAILED → reason present
10. **Partial threshold** — counted as success iff ≥ 80% fields populated

## Project Structure

```
src/composio_research/
├── __init__.py              # Package init, version
├── __main__.py              # CLI entry point
├── app_list.py              # 100 apps (10 per category)
├── config.py                # PipelineConfig, CATEGORIES
├── coordinator.py           # Pipeline orchestration, checkpointing
├── coverage.py              # Category coverage validation
├── html_generator.py        # Self-contained HTML deliverable
├── models.py                # Enums, dataclasses, serialization
├── pattern_analyzer.py      # Cross-app pattern computation
├── researcher.py            # Composio SDK research agent
└── verifier.py              # Multi-pass verification agent

tests/
├── conftest.py              # Hypothesis settings (100 min examples)
├── test_coordinator.py
├── test_coverage.py
├── test_html_filter_logic.py
├── test_html_generator.py
├── test_integration.py
├── test_models.py
├── test_pattern_analyzer.py
├── test_researcher.py
└── test_verifier.py
```

## Data Models

Each researched app is captured as an `AppRecord` with:

- **app_name** / **category** / **description** (max 120 chars)
- **auth_methods** — `[oauth2, api_key, basic, token, other]`
- **access_model** — `self_serve` | `gated`
- **api_surface** — has_public_api, api_type (REST/GraphQL/Both/None), coverage (full/partial/minimal), MCP support
- **buildability_verdict** — `ready` | `feasible` | `blocked`
- **primary_blocker** — no_public_api, insufficient_coverage, restrictive_auth, rate_limits, missing_documentation
- **evidence_urls** — field → URL mapping for verification
- **research_status** — complete, partial, failed, unresearchable

## Key Design Decisions

- **No data fabrication**: If a field can't be determined, it's marked as missing — never invented.
- **Conservative defaults**: Unknown access → gated, unknown auth → other.
- **Graceful failure**: Every app always gets a record, even on total research failure.
- **Self-contained output**: The HTML deliverable has zero external dependencies.
- **Checkpointing**: Pipeline resumes from last completed stage, not from scratch.
- **Verification loop**: 2–4 passes until accuracy ≥ 80% or max passes reached.

