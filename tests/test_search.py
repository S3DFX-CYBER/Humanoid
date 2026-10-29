"""Tests for the URL safety guard in front of the web fetcher."""

import socket

import httpx
import pytest

from providers.search import is_safe_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1:8000/health",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "not-a-url",
        "",
    ],
)
def test_unsafe_targets_are_rejected(url):
    assert is_safe_url(url) is False


def test_public_https_target_is_allowed():
    try:
        socket.getaddrinfo("en.wikipedia.org", None)
    except OSError:
        pytest.skip("DNS is unavailable in this environment")

    url = "https://en.wikipedia.org/wiki/Transformer_(deep_learning)"
    assert is_safe_url(url) is True


def test_blocked_port_is_rejected():
    assert is_safe_url("http://example.com:6379/") is False


class _FakeResponse:
    def __init__(self, url: str, location: str | None = None):
        self.url = httpx.URL(url)
        self.headers = {"location": location} if location else {}
        self.encoding = "utf-8"

    @property
    def is_redirect(self) -> bool:
        return "location" in self.headers

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self):
        yield b"<html><body>should never be read</body></html>"


class _FakeStream:
    def __init__(self, response: _FakeResponse):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *exc_info):
        return False


class _FakeClient:
    """Redirects every request to a loopback address."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def stream(self, method, url):
        return _FakeStream(_FakeResponse(url, location="http://127.0.0.1/secret"))


async def test_redirect_to_private_address_is_refused(monkeypatch):
    from providers import search

    monkeypatch.setattr(search.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(search, "is_safe_url", lambda url: True)

    text = await search.fetch_and_extract_text("https://example.org/a")

    assert text == ""
