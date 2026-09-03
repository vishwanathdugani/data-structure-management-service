"""Fixtures available to every test in the project."""

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    """An unauthenticated API client. The service has no authentication story yet."""
    return APIClient()
