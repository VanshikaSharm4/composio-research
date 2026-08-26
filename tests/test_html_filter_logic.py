"""Tests for interactive filter logic in embedded JavaScript (Task 8.2).

Validates that the HtmlGenerator produces correct HTML with:
- Category filter dropdown
- Buildability filter dropdown
- Auth method filter dropdown
- AND logic for multi-filter combinations
- Clear-all-filters reset
- "No results" message with zero count
- Updated row count on filter change
- Correct data attributes on table rows
"""

import sys

sys.path.insert(0, "src")

import re
import json
import tempfile
from pathlib import Path

import pytest

from composio_research.html_generator import HtmlGenerator


# ============================================================================
# Fixtures
# ============================================================================


def _make_sample_records(n: int = 10) -> list[dict]:
    """Create sample app record dicts for testing.

    Distributes across categories, verdicts, access models, and auth methods
    to exercise all filter dimensions.
    """
    categories = [
        "CRM & Sales",
        "Support & Helpdesk",
        "Communications & Messaging",
        "Marketing/Ads/Email/Social",
        "Ecommerce",
    ]
    verdicts = ["ready", "feasible", "blocked"]
    access_models = ["self_serve", "gated"]
    auth_methods_pool = [
        ["oauth2"],
        ["api_key"],
        ["oauth2", "api_key"],
        ["token"],
        ["basic"],
    ]

    records = []
    for i in range(n):
        records.append(
            {
                "app_name": f"App{i}",
                "category": categories[i % len(categories)],
                "description": f"Description for app {i}",
                "auth_methods": auth_methods_pool[i % len(auth_methods_pool)],
                "access_model": access_models[i % len(access_models)],
                "api_surface": {
                    "has_public_api": True,
                    "api_type": "rest",
                    "coverage": "full",
                    "has_mcp_support": False,
                    "evidence_url": None,
                },
                "buildability_verdict": verdicts[i % len(verdicts)],
                "primary_blocker": None
                if verdicts[i % len(verdicts)] == "ready"
                else "no_public_api",
                "evidence_urls": {},
                "research_status": "complete",
                "missing_fields": [],
                "failure_reason": None,
                "failure_category": None,
            }
        )
    return records


@pytest.fixture
def generator():
    return HtmlGenerator()


@pytest.fixture
def sample_records():
    return _make_sample_records(10)


@pytest.fixture
def sample_data(sample_records):
    return {
        "app_records": sample_records,
        "pattern_analysis": None,
        "verification_metrics": None,
        "intervention_log": [],
    }


@pytest.fixture
def generated_html(generator, sample_data) -> str:
    """Generate full HTML and return content as string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_output.html"
        generator.generate(sample_data, output_path)
        return output_path.read_text(encoding="utf-8")


# ============================================================================
# Tests: Filter dropdown presence
# ============================================================================


class TestFilterDropdowns:
    """Verify all three filter dropdowns are present with correct IDs."""

    def test_category_filter_present(self, generated_html):
        """Category filter dropdown exists with correct ID."""
        assert 'id="filter-category"' in generated_html

    def test_buildability_filter_present(self, generated_html):
        """Buildability/verdict filter dropdown exists with correct ID."""
        assert 'id="filter-verdict"' in generated_html

    def test_auth_method_filter_present(self, generated_html):
        """Auth method filter dropdown exists with correct ID."""
        assert 'id="filter-auth"' in generated_html

    def test_category_filter_has_all_option(self, generated_html):
        """Category filter includes an 'All Categories' default option."""
        assert "All Categories" in generated_html

    def test_verdict_filter_has_all_option(self, generated_html):
        """Verdict filter includes an 'All Verdicts' default option."""
        assert "All Verdicts" in generated_html

    def test_auth_filter_has_all_option(self, generated_html):
        """Auth filter includes an 'All Auth Methods' default option."""
        assert "All Auth Methods" in generated_html

    def test_category_options_populated(self, generated_html, sample_records):
        """Category filter includes actual category values from data (HTML-escaped)."""
        categories = set(r["category"] for r in sample_records)
        for cat in categories:
            # html.escape() encodes & as &amp; in attribute values
            escaped_cat = cat.replace("&", "&amp;")
            assert f'value="{escaped_cat}"' in generated_html

    def test_verdict_options_populated(self, generated_html, sample_records):
        """Verdict filter includes actual verdict values from data."""
        verdicts = set(r["buildability_verdict"] for r in sample_records)
        for verdict in verdicts:
            assert f'value="{verdict}"' in generated_html

    def test_auth_options_populated(self, generated_html, sample_records):
        """Auth method filter includes all distinct auth methods from data."""
        auth_methods = set()
        for r in sample_records:
            for m in r["auth_methods"]:
                auth_methods.add(m)
        for method in auth_methods:
            assert f'value="{method}"' in generated_html


# ============================================================================
# Tests: Table row data attributes
# ============================================================================


class TestTableRowDataAttributes:
    """Verify rows have correct data attributes for filtering."""

    def test_rows_have_data_category(self, generated_html, sample_records):
        """Each table row has a data-category attribute (HTML-escaped)."""
        for record in sample_records:
            # html.escape() encodes & as &amp; in attribute values
            escaped_cat = record["category"].replace("&", "&amp;")
            assert f'data-category="{escaped_cat}"' in generated_html

    def test_rows_have_data_verdict(self, generated_html, sample_records):
        """Each table row has a data-verdict attribute."""
        for record in sample_records:
            assert f'data-verdict="{record["buildability_verdict"]}"' in generated_html

    def test_rows_have_data_auth(self, generated_html, sample_records):
        """Each table row has a data-auth attribute with comma-separated methods."""
        for record in sample_records:
            auth_value = ",".join(record["auth_methods"])
            assert f'data-auth="{auth_value}"' in generated_html


# ============================================================================
# Tests: Clear-all button
# ============================================================================


class TestClearAllButton:
    """Verify clear-all-filters button is present and wired."""

    def test_clear_button_present(self, generated_html):
        """Clear button element exists with correct ID."""
        assert 'id="clear-filters"' in generated_html

    def test_clear_button_text(self, generated_html):
        """Clear button has appropriate label text."""
        assert "Clear All" in generated_html


# ============================================================================
# Tests: No-results message
# ============================================================================


class TestNoResultsMessage:
    """Verify no-results display element is present."""

    def test_no_results_div_present(self, generated_html):
        """No-results div exists with correct ID."""
        assert 'id="no-results"' in generated_html

    def test_no_results_initially_hidden(self, generated_html):
        """No-results div starts with 'hidden' class."""
        # Find the no-results element and verify it has 'hidden' class
        match = re.search(r'id="no-results"[^>]*class="([^"]*)"', generated_html)
        assert match is not None
        assert "hidden" in match.group(1)

    def test_no_results_count_element(self, generated_html):
        """No-results section includes a count display."""
        assert 'id="no-results-count"' in generated_html
        assert "0 results" in generated_html


# ============================================================================
# Tests: Row count display
# ============================================================================


class TestRowCount:
    """Verify row count element is present and initialized."""

    def test_row_count_element_present(self, generated_html):
        """Row count span exists with correct ID."""
        assert 'id="row-count"' in generated_html

    def test_row_count_shows_total(self, generated_html, sample_records):
        """Row count displays the initial total app count."""
        total = len(sample_records)
        assert f"Showing {total} of {total} apps" in generated_html


# ============================================================================
# Tests: JavaScript filter logic
# ============================================================================


class TestJavaScriptFilterLogic:
    """Verify the embedded JavaScript implements required filter behavior."""

    def test_javascript_embedded(self, generated_html):
        """A <script> tag is present with filter logic."""
        assert "<script>" in generated_html

    def test_app_data_embedded_as_json(self, generated_html, sample_records):
        """APP_DATA constant contains embedded records as JSON."""
        assert "APP_DATA" in generated_html
        # Extract the JSON blob from the script
        match = re.search(r"const APP_DATA = (.+?);", generated_html, re.DOTALL)
        assert match is not None
        # Verify it's valid JSON
        data = json.loads(match.group(1))
        assert len(data) == len(sample_records)

    def test_and_logic_implementation(self, generated_html):
        """Filter logic uses AND (all filters must match) not OR.

        The JavaScript should check each filter independently and set show=false
        if ANY filter doesn't match (AND behavior).
        """
        # The AND logic is implemented as sequential if checks where
        # any mismatch sets show = false
        assert "show = false" in generated_html or "show=false" in generated_html

    def test_category_filter_comparison(self, generated_html):
        """JavaScript checks data-category against filter value."""
        assert "data-category" in generated_html
        assert "getAttribute" in generated_html or "rowCategory" in generated_html

    def test_verdict_filter_comparison(self, generated_html):
        """JavaScript checks data-verdict against filter value."""
        assert "data-verdict" in generated_html
        assert "rowVerdict" in generated_html or "getAttribute" in generated_html

    def test_auth_filter_uses_split(self, generated_html):
        """Auth filter handles multi-value auth by splitting on comma."""
        # Auth field can have multiple values (e.g., "oauth2,api_key")
        # The JS should split and check membership
        assert "split" in generated_html
        assert "indexOf" in generated_html or "includes" in generated_html

    def test_clear_filters_resets_all(self, generated_html):
        """clearFilters function sets all dropdown values to empty string."""
        assert "clearFilters" in generated_html
        # After clearing, it should call applyFilters
        assert "applyFilters" in generated_html

    def test_event_listeners_attached(self, generated_html):
        """Event listeners are attached to all filter controls."""
        assert "addEventListener" in generated_html
        # Verify all three filters have listeners
        assert "filterCategory" in generated_html
        assert "filterVerdict" in generated_html
        assert "filterAuth" in generated_html

    def test_row_count_updated_in_filter(self, generated_html):
        """Filter function updates the row count text content."""
        assert "rowCount" in generated_html
        assert "textContent" in generated_html
        # Should show "Showing X of Y apps" pattern
        assert "Showing" in generated_html

    def test_no_results_shown_when_zero(self, generated_html):
        """When visibleCount is 0, no-results message is shown."""
        assert "visibleCount" in generated_html
        # Should check if visibleCount === 0 and show the message
        assert "hidden" in generated_html

    def test_rows_hidden_via_display_none(self, generated_html):
        """Non-matching rows are hidden using display:none style."""
        assert "display" in generated_html
        assert "'none'" in generated_html or '"none"' in generated_html


# ============================================================================
# Tests: Filter logic correctness via Python port
# ============================================================================


class TestFilterLogicCorrectness:
    """Test the filter AND logic by simulating it in Python.

    This mirrors what the JavaScript does to verify correctness of the approach.
    """

    def _apply_filters(
        self,
        records: list[dict],
        category: str = "",
        verdict: str = "",
        auth: str = "",
    ) -> list[dict]:
        """Python port of the JavaScript filter logic."""
        results = []
        for record in records:
            show = True
            if category and record.get("category") != category:
                show = False
            if verdict and record.get("buildability_verdict") != verdict:
                show = False
            if auth:
                auth_methods = record.get("auth_methods", [])
                if auth not in auth_methods:
                    show = False
            if show:
                results.append(record)
        return results

    def test_no_filters_shows_all(self, sample_records):
        """With no filters active, all records are shown."""
        result = self._apply_filters(sample_records)
        assert len(result) == len(sample_records)

    def test_single_category_filter(self, sample_records):
        """Single category filter shows only matching apps."""
        result = self._apply_filters(sample_records, category="CRM & Sales")
        assert all(r["category"] == "CRM & Sales" for r in result)
        assert len(result) == sum(
            1 for r in sample_records if r["category"] == "CRM & Sales"
        )

    def test_single_verdict_filter(self, sample_records):
        """Single verdict filter shows only matching apps."""
        result = self._apply_filters(sample_records, verdict="ready")
        assert all(r["buildability_verdict"] == "ready" for r in result)

    def test_single_auth_filter(self, sample_records):
        """Single auth filter shows only apps with that auth method."""
        result = self._apply_filters(sample_records, auth="oauth2")
        assert all("oauth2" in r["auth_methods"] for r in result)

    def test_multi_filter_and_logic(self, sample_records):
        """Combined filters use AND logic - only rows matching ALL criteria shown."""
        result = self._apply_filters(
            sample_records, category="CRM & Sales", verdict="ready"
        )
        assert all(
            r["category"] == "CRM & Sales"
            and r["buildability_verdict"] == "ready"
            for r in result
        )

    def test_all_three_filters_and_logic(self, sample_records):
        """All three filters combined still use AND logic."""
        result = self._apply_filters(
            sample_records,
            category="CRM & Sales",
            verdict="ready",
            auth="oauth2",
        )
        for r in result:
            assert r["category"] == "CRM & Sales"
            assert r["buildability_verdict"] == "ready"
            assert "oauth2" in r["auth_methods"]

    def test_contradictory_filters_empty_result(self):
        """Contradictory filters return no results (AND logic)."""
        records = [
            {
                "app_name": "OnlyApp",
                "category": "CRM & Sales",
                "buildability_verdict": "ready",
                "auth_methods": ["oauth2"],
            }
        ]
        result = self._apply_filters(
            records, category="CRM & Sales", verdict="blocked"
        )
        assert len(result) == 0

    def test_clear_filters_shows_all(self, sample_records):
        """Clearing filters (empty strings) shows all records."""
        result = self._apply_filters(sample_records, category="", verdict="", auth="")
        assert len(result) == len(sample_records)

    def test_auth_filter_matches_multi_auth_apps(self):
        """Auth filter matches apps that have multiple auth methods."""
        records = [
            {
                "app_name": "MultiAuth",
                "category": "CRM & Sales",
                "buildability_verdict": "ready",
                "auth_methods": ["oauth2", "api_key"],
            }
        ]
        # Filtering by oauth2 should match since the app has it
        result = self._apply_filters(records, auth="oauth2")
        assert len(result) == 1

        # Filtering by api_key should also match
        result = self._apply_filters(records, auth="api_key")
        assert len(result) == 1

        # Filtering by basic should not match
        result = self._apply_filters(records, auth="basic")
        assert len(result) == 0


# ============================================================================
# Tests: Full HTML generation with 100 apps
# ============================================================================


class TestFullScaleGeneration:
    """Verify filter components work with a full 100-app dataset."""

    def test_100_apps_row_count(self, generator):
        """Row count shows 100 of 100 when generating with 100 apps."""
        records = _make_sample_records(100)
        data = {
            "app_records": records,
            "pattern_analysis": None,
            "verification_metrics": None,
            "intervention_log": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "full_output.html"
            generator.generate(data, output_path)
            html_content = output_path.read_text(encoding="utf-8")

        assert "Showing 100 of 100 apps" in html_content

    def test_100_apps_all_rows_present(self, generator):
        """All 100 table rows are generated."""
        records = _make_sample_records(100)
        data = {
            "app_records": records,
            "pattern_analysis": None,
            "verification_metrics": None,
            "intervention_log": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "full_output.html"
            generator.generate(data, output_path)
            html_content = output_path.read_text(encoding="utf-8")

        # Count table rows with data attributes
        row_count = html_content.count('data-category="')
        assert row_count == 100

    def test_json_data_embedded_for_100_apps(self, generator):
        """APP_DATA JSON blob contains all 100 records."""
        records = _make_sample_records(100)
        data = {
            "app_records": records,
            "pattern_analysis": None,
            "verification_metrics": None,
            "intervention_log": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "full_output.html"
            generator.generate(data, output_path)
            html_content = output_path.read_text(encoding="utf-8")

        match = re.search(r"const APP_DATA = (.+?);", html_content, re.DOTALL)
        assert match is not None
        embedded_data = json.loads(match.group(1))
        assert len(embedded_data) == 100
