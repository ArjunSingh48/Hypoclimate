"""Tests never touch the internet: any real network call fails loudly instead of hanging."""
import pytest

from backend import geoadmin


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **k):
        raise RuntimeError(f"network call in a test: {a[:1]}")
    monkeypatch.setattr(geoadmin._session, "get", blocked)
