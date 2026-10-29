"""Tests for the URL safety guard in front of the web fetcher."""

import socket

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
