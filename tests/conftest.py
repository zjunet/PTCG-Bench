"""
Pytest configuration and shared fixtures for PTCG tests.

This module provides common fixtures and test utilities used across
all test modules.
"""

import pytest

# ============================================================================
# Fixtures
# ============================================================================

# Note: Player and State fixtures require complex setup (deck, agent).
# For unit tests, we use minimal mock objects.
# Integration tests should use real game environment setup.


# ============================================================================
# Markers

# ============================================================================
# Markers
# ============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")


# ============================================================================
# Test Helpers
# ============================================================================


class TestUtils:
    """Utility class with helper methods for tests."""

    @staticmethod
    def assert_valid_action_encoding(encoding) -> None:
        """Assert that an action encoding is valid."""
        import numpy as np

        assert isinstance(encoding, np.ndarray), "Encoding must be numpy array"
        assert len(encoding) == 38, f"Encoding length should be 38, got {len(encoding)}"
        assert encoding.dtype == np.int8, f"Encoding dtype should be int8, got {encoding.dtype}"

    @staticmethod
    def assert_valid_observation(obs: dict) -> None:
        """Assert that an observation dict is valid."""
        assert "meta_info" in obs, "Observation missing 'meta_info'"
        assert "cards" in obs, "Observation missing 'cards'"
        assert len(obs["meta_info"]) == 16, (
            f"meta_info should have 16 elements, got {len(obs['meta_info'])}"
        )


@pytest.fixture
def test_utils() -> TestUtils:
    """Provide test utility methods."""
    return TestUtils()
