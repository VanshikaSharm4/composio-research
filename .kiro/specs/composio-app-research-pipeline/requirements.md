# Requirements Document

## Introduction

This feature delivers an automated research pipeline and a single-file HTML deliverable that analyzes 100 specific apps across 10 categories for Composio, an AI tooling platform that turns apps into tools for AI agents. The pipeline researches each app's authentication methods, API surface, self-serve access, and buildability as an agent toolkit. The HTML deliverable presents all findings, patterns, agent workflow documentation, and verification results in an interactive, modern interface.

## Glossary

- **Research_Pipeline**: The automated agent or script system that researches apps and captures structured data about each one
- **HTML_Deliverable**: A single self-contained HTML file presenting all research findings, patterns, and verification results
- **App_Record**: The structured data captured for a single app including category, auth method, access model, API surface, and buildability verdict
- **Auth_Method**: The authentication mechanism an app uses for API access (OAuth2, API key, Basic, token, or other)
- **Access_Model**: Whether a developer can get API credentials via self-serve (free/trial) or requires gated access (paid plan, admin approval, or partnership)
- **API_Surface**: The documented public API capabilities including REST/GraphQL endpoints, breadth of coverage, and existing MCP support
- **Buildability_Verdict**: An assessment of whether the app could be an agent toolkit today, including the main blocker if not
- **Evidence_URL**: A documentation URL backing each data point in an App_Record
- **Verification_Loop**: A process that runs multiple passes over research data to check and improve accuracy
- **Pattern_Analysis**: Cross-app analysis identifying trends in auth methods, access models, blockers, and strategic opportunities
- **Composio_SDK**: The Composio software development kit used to build agent toolkits
- **MCP**: Model Context Protocol, a standard for connecting AI models to external tools
- **Category**: One of 10 predefined groupings of apps (CRM & Sales, Support & Helpdesk, Communications & Messaging, Marketing/Ads/Email/Social, Ecommerce, Data/SEO/Scraping, Developer/Infra/Data, Productivity & PM, Finance & Fintech, AI/Research/Media)

## Requirements

### Requirement 1: App Data Collection

**User Story:** As a product operations researcher, I want the pipeline to automatically research each of the 100 specified apps, so that I have structured data for analysis without manual research.

#### Acceptance Criteria

1. WHEN the Research_Pipeline is executed, THE Research_Pipeline SHALL collect an App_Record for each of the 100 specified apps across 10 categories (10 apps per category).
2. THE App_Record SHALL contain: category, a description of no more than 120 characters, Auth_Method, Access_Model, API_Surface assessment, Buildability_Verdict, and at least one Evidence_URL per data point.
3. WHEN collecting Auth_Method, THE Research_Pipeline SHALL classify each app into one or more of: OAuth2, API key, Basic, token, or other.
4. WHEN assessing Access_Model, THE Research_Pipeline SHALL classify each app as either self-serve (free or trial credentials available) or gated (paid plan, admin approval, or partnership required).
5. WHEN assessing API_Surface, THE Research_Pipeline SHALL document whether public REST or GraphQL APIs exist, classify API coverage as full (all core features exposed), partial (some features exposed), or minimal (few endpoints available), and whether existing MCP support is available.
6. WHEN determining Buildability_Verdict, THE Research_Pipeline SHALL assign one of: ready (public API with auth, sufficient coverage, no major blockers), feasible (API exists but has gaps or limitations), or blocked (no public API or critical barriers), and identify the primary blocker category (no public API, insufficient coverage, restrictive auth, rate limits, or missing documentation) if the verdict is not ready.
7. IF the Research_Pipeline cannot determine a required data point for an App_Record after exhausting available sources, THEN THE Research_Pipeline SHALL mark that field as "unknown" and record the reason data could not be obtained.

### Requirement 2: Research Pipeline Automation

**User Story:** As a product operations researcher, I want the research process to be automated using AI tooling, so that 100 apps can be researched efficiently and repeatably.

#### Acceptance Criteria

1. THE Research_Pipeline SHALL use an automated approach (agent, script, or pipeline) to collect app data, processing at least 90 of the 100 apps without manual intervention.
2. WHEN a data source is accessible via Composio_SDK or MCP, THE Research_Pipeline SHALL use Composio_SDK or MCP for that data collection step rather than an alternative method.
3. WHEN human intervention is required during research, THE Research_Pipeline SHALL log the specific app name, the data point that could not be automated, and the reason intervention was needed.
4. THE Research_Pipeline SHALL produce a structured JSON output containing all 100 App_Records.
5. IF the Research_Pipeline does not receive a response from a data source within 30 seconds per request, THEN THE Research_Pipeline SHALL retry up to 3 times before recording the failure reason and marking the app as requiring manual research.
6. WHEN executed multiple times with the same input app list, THE Research_Pipeline SHALL follow the same research steps and produce the same output structure for each app.

### Requirement 3: Verification and Accuracy

**User Story:** As a product operations researcher, I want verification loops that check and improve data accuracy, so that the research findings are trustworthy and auditable.

#### Acceptance Criteria

1. THE Research_Pipeline SHALL execute at least two and at most four verification passes over the collected data.
2. WHEN a verification pass is executed, THE Research_Pipeline SHALL compare each data point against its associated Evidence_URLs and flag a discrepancy when the collected value contradicts or is not supported by the content at the source URL.
3. THE Research_Pipeline SHALL record accuracy metrics for each verification pass, expressed as the percentage of data points confirmed by their Evidence_URLs, showing progression from pass 1 to pass 2.
4. WHEN a discrepancy is found during verification, THE Research_Pipeline SHALL attempt to resolve it by re-researching the specific data point, up to a maximum of 3 resolution attempts per data point.
5. IF a data point cannot be verified after all resolution attempts are exhausted, THEN THE Research_Pipeline SHALL mark it as unverified and document the reason, including which Evidence_URLs were checked and why confirmation failed.
6. IF the final verification pass yields an accuracy rate below 80%, THEN THE Research_Pipeline SHALL flag the overall research output as requiring manual review.

### Requirement 4: Pattern Analysis

**User Story:** As a product operations researcher, I want cross-app pattern analysis, so that I can identify strategic opportunities and trends for Composio's platform.

#### Acceptance Criteria

1. WHEN all App_Records are collected, THE Research_Pipeline SHALL produce a frequency distribution of each Auth_Method across all 10 categories, identifying the Auth_Method with the highest count per category and overall.
2. WHEN all App_Records are collected, THE Research_Pipeline SHALL produce a count of self-serve versus gated apps per category and classify each category as majority self-serve (more than 50% self-serve) or majority gated (50% or more gated).
3. WHEN all App_Records are collected, THE Research_Pipeline SHALL rank all distinct blockers from Buildability_Verdicts by frequency and report at least the top 5 most frequently occurring blockers with their occurrence counts.
4. WHEN all App_Records are collected, THE Research_Pipeline SHALL classify each app as either "easy-win" (self-serve Access_Model, documented REST or GraphQL API exists, and Buildability_Verdict indicates the app could function as an agent toolkit today) or "requires outreach" (all other apps).
5. WHEN all App_Records are collected, THE Research_Pipeline SHALL produce at minimum 3 data-backed observations, where each observation references specific App_Record counts or percentages and identifies an actionable opportunity for expanding Composio's app ecosystem.

### Requirement 5: HTML Deliverable Structure

**User Story:** As a stakeholder reviewing the research, I want a single self-contained HTML file that presents all findings in a modern, interactive interface, so that I can review and explore the data without additional setup.

#### Acceptance Criteria

1. THE HTML_Deliverable SHALL be a single self-contained HTML file with all CSS, JavaScript, and data embedded inline, with no external resource requests, and a total file size not exceeding 15 MB.
2. THE HTML_Deliverable SHALL use a dark-mode color scheme (dark background with light foreground text) styled with Tailwind CSS.
3. THE HTML_Deliverable SHALL display an executive summary section containing between 300 and 500 words.
4. THE HTML_Deliverable SHALL be deployable as a static page without a build step or server-side processing.
5. THE HTML_Deliverable SHALL render in modern browsers (Chrome, Firefox, Safari, Edge latest versions) with all sections visible, no layout overflow or overlap, and all interactive elements responsive to user input.
6. THE HTML_Deliverable SHALL be fully functional when opened via the file:// protocol without a network connection.

### Requirement 6: HTML Interactive Data Table

**User Story:** As a stakeholder reviewing the research, I want an interactive filterable table of all 100 apps, so that I can explore the data by category, buildability, or auth type.

#### Acceptance Criteria

1. THE HTML_Deliverable SHALL display all 100 apps in a table with columns for: App Name, Category, Buildability_Verdict, Access_Model, Auth_Method, and a summary description.
2. WHEN a user selects a category filter, THE HTML_Deliverable SHALL display only apps belonging to that category.
3. WHEN a user selects a buildability filter, THE HTML_Deliverable SHALL display only apps matching that buildability status.
4. WHEN a user selects an Auth_Method filter, THE HTML_Deliverable SHALL display only apps using that authentication method.
5. THE HTML_Deliverable SHALL display visually distinct status badges for each Buildability_Verdict value and each Access_Model value, where each unique value maps to a consistent, distinguishable badge style.
6. WHEN multiple filters are applied, THE HTML_Deliverable SHALL display only apps matching all selected filter criteria simultaneously (AND logic).
7. IF no apps match the active filter criteria, THEN THE HTML_Deliverable SHALL display a message indicating that no apps match the current filters and show a count of zero results.
8. WHEN a user clears all filters, THE HTML_Deliverable SHALL display all 100 apps in the table.

### Requirement 7: HTML Deliverable Content Sections

**User Story:** As a stakeholder reviewing the research, I want dedicated sections for agent architecture and verification audit results, so that I can understand and trust the research methodology.

#### Acceptance Criteria

1. THE HTML_Deliverable SHALL include an agent architecture section that lists each stage of the Research_Pipeline workflow in execution order, showing the stage name and its input/output relationship to adjacent stages.
2. THE HTML_Deliverable SHALL include a verification/audit section displaying accuracy check results from each pass, including at minimum the accuracy percentage and the number of corrections applied per pass.
3. THE HTML_Deliverable SHALL display Pattern_Analysis results including auth distribution, access model distribution, and blocker frequency, each presented as labeled counts or percentages that sum to 100% for distribution categories.
4. THE HTML_Deliverable SHALL include a section documenting which pipeline stages required human intervention during research, stating the stage name and the reason intervention was needed.
5. WHEN verification data is displayed, THE HTML_Deliverable SHALL show the numeric accuracy score for pass 1 and pass 2 in sequential order so that improvement or regression is visible.
6. IF verification data for a pass is unavailable, THEN THE HTML_Deliverable SHALL display an indication that results for that pass are not available rather than omitting the pass entry.
7. THE HTML_Deliverable SHALL render each content section under a distinct heading so that a stakeholder can navigate directly to agent architecture, verification/audit, pattern analysis, or human intervention sections.

### Requirement 8: Data Integrity and Honesty

**User Story:** As a product operations researcher, I want the system to honestly report failures and limitations, so that the research is credible and transparent about its constraints.

#### Acceptance Criteria

1. IF the Research_Pipeline fails to research an app, THEN THE Research_Pipeline SHALL record the failure with a categorized reason (e.g., network error, timeout, access restriction, parsing failure, or agent error) rather than fabricating data.
2. IF an app requires gated access (login, paid subscription, or invite-only), THEN THE Research_Pipeline SHALL document gated access as the correct finding without attempting to bypass restrictions.
3. THE Research_Pipeline SHALL not require paid accounts or authenticated sessions to complete research; documenting gated access is a valid finding.
4. WHEN the Research_Pipeline encounters an agent error (tool invocation failure, LLM refusal, or unrecoverable exception), THE Research_Pipeline SHALL log the error type, affected app, and processing step in the output so the failure is traceable to a specific point in the pipeline.
5. THE HTML_Deliverable SHALL include a transparency section listing: (a) apps that failed research with their failure category, (b) apps where data could not be independently confirmed from a second source, and (c) any pipeline-level limitations affecting the batch run.
6. IF the Research_Pipeline retrieves no data for a research field on an app that was otherwise accessible, THEN THE Research_Pipeline SHALL record the field as "not found" rather than omitting it or substituting assumed values.

### Requirement 9: Pipeline Output Format

**User Story:** As a developer building the HTML deliverable, I want the pipeline to produce structured, well-defined output, so that the data can be reliably consumed by the HTML generation step.

#### Acceptance Criteria

1. THE Research_Pipeline SHALL output all App_Records in a JSON file where each record contains the fields defined in Requirement 1 (category, description, Auth_Method, Access_Model, API_Surface, Buildability_Verdict, and Evidence_URLs).
2. THE Research_Pipeline SHALL output Pattern_Analysis results in a JSON file containing auth distribution counts, access model distribution counts, blocker frequency counts, and categorized easy-win versus outreach-required app lists.
3. THE Research_Pipeline SHALL output verification metrics in a JSON file containing: the number of verification passes completed, per-pass accuracy percentage (0–100), and a discrepancy log where each entry identifies the app name, field name, original value, corrected value, and resolution status.
4. THE Research_Pipeline SHALL output a human intervention log in a JSON file where each entry contains: the app name, the pipeline stage at which intervention was needed, the reason intervention was required, and a timestamp.
5. WHEN the Research_Pipeline completes execution, THE Research_Pipeline SHALL produce a single output directory containing one dedicated file per output type (app records, pattern analysis, verification metrics, and intervention log).
6. IF the Research_Pipeline fails to write any output file, THEN THE Research_Pipeline SHALL report which file could not be written and the reason for the failure without silently omitting the file.
7. THE Research_Pipeline SHALL produce output files that are valid, parseable JSON; each file SHALL be independently parseable without requiring content from other output files.

### Requirement 10: App Coverage Completeness

**User Story:** As a product operations researcher, I want to ensure all 100 specified apps are covered, so that the deliverable is comprehensive across all 10 categories.

#### Acceptance Criteria

1. THE Research_Pipeline SHALL process exactly 10 apps per category for all 10 categories (100 apps total).
2. THE Research_Pipeline SHALL cover the following categories: CRM & Sales, Support & Helpdesk, Communications & Messaging, Marketing/Ads/Email/Social, Ecommerce, Data/SEO/Scraping, Developer/Infra/Data, Productivity & PM, Finance & Fintech, AI/Research/Media.
3. IF any app from the specified list cannot be found or no longer exists after checking the app's official website and primary documentation source, THEN THE Research_Pipeline SHALL mark the app as unresearchable in the output, include the app name, its assigned category, and the reason it could not be researched.
4. WHEN execution is complete, THE Research_Pipeline SHALL report per-category counts and the total number of successfully researched apps versus the target of 100, where an app is considered successfully researched when all required data fields defined by the research schema have been populated.
5. THE HTML_Deliverable SHALL display a coverage summary showing the count of successfully researched apps out of 100, a per-category breakdown of researched versus target (10 per category), and a list of any apps marked as unresearchable with their reasons.
6. IF an app exists but required data fields cannot be populated after exhausting available sources, THEN THE Research_Pipeline SHALL mark the app as partially researched, record which fields are missing, and include the app in the successfully researched count only if at least 80% of required fields are populated.
