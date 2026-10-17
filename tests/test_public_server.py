"""Public demo boundary tests; no production diagnostics changes."""
import pytest
from amd.server import allowed_origins


def test_local_origins_remain_available(monkeypatch):
    monkeypatch.delenv("REFINERY_PUBLIC_ORIGIN", raising=False)
    assert allowed_origins(8765) == {"http://127.0.0.1:8765", "http://localhost:8765"}


def test_public_origin_is_explicit_and_exact(monkeypatch):
    monkeypatch.setenv("REFINERY_PUBLIC_ORIGIN", "https://demo.example.org")
    origins = allowed_origins(8765)
    assert "https://demo.example.org" in origins
    assert "https://attacker.example.org" not in origins
    assert "*" not in origins


@pytest.mark.parametrize("value", ["*", "http://demo.example.org", "https://demo.example.org/", "https://demo.example.org/path", "https://user:password@demo.example.org", "https://demo.example.org?x=1", "https://demo.example.org#fragment"])
def test_invalid_public_origin_fails_closed(monkeypatch, value):
    monkeypatch.setenv("REFINERY_PUBLIC_ORIGIN", value)
    with pytest.raises(ValueError):
        allowed_origins(8765)
