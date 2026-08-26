"""Pytest configuration and shared fixtures for the Composio App Research Pipeline tests."""

from hypothesis import settings

# Set default Hypothesis settings for all property-based tests:
# minimum 100 iterations per property as specified in the design document.
settings.register_profile("default", max_examples=100)
settings.register_profile("ci", max_examples=200)
settings.load_profile("default")
