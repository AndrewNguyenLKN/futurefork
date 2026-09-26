import pytest

from pocketcart import create_app
from support import Client


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "guard: behavior that already holds on the unchanged candidates (regression guard)"
    )


@pytest.fixture
def client() -> Client:
    return Client(create_app())
