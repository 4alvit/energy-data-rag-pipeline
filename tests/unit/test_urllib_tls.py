"""Exercise the real MCP and corpus requests with disposable TLS peers."""

import importlib.util
import socket
import ssl
import urllib.request
from pathlib import Path
from urllib.error import URLError

import pytest
from test_tls_policy import CHAIN_CASES, calibrate, chains, clean_environment, peer, proxy

from energy_rag.ingestion.forum_loader import _normalize_forum_url, fetch_forum_url
from energy_rag.mcp_server import RagApiClient

__all__ = ["chains", "clean_environment"]


def corpus_get(url: str) -> bytes:
    script = Path(__file__).resolve().parents[2] / "scripts/fetch_victron_content.py"
    spec = importlib.util.spec_from_file_location("corpus_fetch", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._get(url, timeout=3)


@pytest.mark.parametrize("operation", ["mcp", "corpus"])
@pytest.mark.parametrize("case", [*CHAIN_CASES, "untrusted", "wrong-host"])
@pytest.mark.parametrize("version", [ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3])
def test_actual_requests_reject_before_payload(chains, monkeypatch, operation, case, version):
    chain = chains.get(case, chains["strong"])
    calibrate(chain, version)
    ca = chains["strong-ec"][2] if case == "untrusted" else chain[2]
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    with peer(chain, version, response_body=b'{"state":"42"}') as (port, observed):
        host = "127.0.0.1" if case == "wrong-host" else "localhost"
        url = f"https://{host}:{port}"

        def request():
            if operation == "mcp":
                return RagApiClient(url).query("synthetic-query")
            return corpus_get(url)

        if case.startswith("strong"):
            expected = {"state": "42"} if operation == "mcp" else b'{"state":"42"}'
            assert request() == expected
        else:
            with pytest.raises(RuntimeError if operation == "mcp" else URLError):
                request()
    assert bool(observed["application_bytes"]) == case.startswith("strong")
    if case.startswith("strong"):
        assert observed["alpn"] == "http/1.1"
    if case.startswith("strong") and operation == "mcp":
        assert b"synthetic-query" in observed["application_bytes"]


@pytest.mark.parametrize("case", ["strong", "weak-2047-root"])
def test_http_proxy_tunnel_still_checks_origin(chains, monkeypatch, case):
    chain = chains[case]
    monkeypatch.setenv("SSL_CERT_FILE", str(chain[2]))
    with (
        peer(chain, ssl.TLSVersion.TLSv1_3, response_body=b'{"state":"42"}') as (port, observed),
        proxy(port, None) as (proxy_port, requests),
    ):
        monkeypatch.setenv("HTTPS_PROXY", f"http://localhost:{proxy_port}")
        if case == "strong":
            assert RagApiClient(f"https://localhost:{port}").health() == {"state": "42"}
        else:
            with pytest.raises(RuntimeError):
                RagApiClient(f"https://localhost:{port}").health()
    assert len(requests) == 1
    assert bool(observed["application_bytes"]) == (case == "strong")


@pytest.mark.parametrize("operation", ["mcp", "corpus"])
@pytest.mark.parametrize("scheme", ["http", "https"])
def test_https_proxy_rejected_before_any_connection(monkeypatch, operation, scheme):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.1)
        monkeypatch.setenv(
            scheme.upper() + "_PROXY",
            f"https://fixture:synthetic@127.0.0.1:{listener.getsockname()[1]}",
        )
        url = f"{scheme}://localhost:1"
        with pytest.raises(ssl.SSLError, match="does not support HTTPS-scheme proxies"):
            if operation == "mcp":
                RagApiClient(url).health()
            else:
                corpus_get(url)
        with pytest.raises(TimeoutError):
            listener.accept()


@pytest.mark.parametrize("operation", ["mcp", "corpus"])
def test_https_proxy_no_proxy_bypass_stays_direct(chains, monkeypatch, operation):
    monkeypatch.setenv("HTTPS_PROXY", "https://fixture:synthetic@127.0.0.1:1")
    monkeypatch.setenv("no_proxy", "localhost")
    monkeypatch.setenv("SSL_CERT_FILE", str(chains["strong"][2]))
    with peer(chains["strong"], ssl.TLSVersion.TLSv1_3, response_body=b'{"state":"42"}') as (
        port,
        observed,
    ):
        url = f"https://localhost:{port}"
        if operation == "mcp":
            assert RagApiClient(url).health() == {"state": "42"}
        else:
            assert corpus_get(url) == b'{"state":"42"}'
    assert observed["alpn"] == "http/1.1"
    assert b"Proxy-Authorization" not in observed["application_bytes"]


@pytest.mark.parametrize("case", [*CHAIN_CASES, "untrusted", "wrong-host"])
@pytest.mark.parametrize("version", [ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3])
def test_forum_uses_verified_connection(chains, monkeypatch, case, version):
    chain = chains.get(case, chains["strong"])
    calibrate(chain, version)
    ca = chains["strong-ec"][2] if case == "untrusted" else chain[2]
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    body = b"<html><h1>Title</h1><main>test question</main></html>"
    with peer(chain, version, response_body=body) as (port, observed):
        host = "127.0.0.1" if case == "wrong-host" else "localhost"
        documents = list(
            fetch_forum_url(
                f"https://{host}:{port}/question",
                {"title": "h1", "question": "main", "answer": ".answer", "metadata": {}},
            )
        )
    assert bool(observed["application_bytes"]) == case.startswith("strong")
    assert bool(documents) == case.startswith("strong")
    if documents:
        assert "test question" in documents[0].page_content


@pytest.mark.parametrize("scheme", ["file", "data", "ftp"])
def test_forum_rejects_non_http_initial_urls(tmp_path, scheme, monkeypatch):
    def forbidden_handler(*args, **kwargs):
        pytest.fail("non-HTTP protocol handler must not run")

    monkeypatch.setattr(urllib.request.FTPHandler, "ftp_open", forbidden_handler)
    monkeypatch.setattr(urllib.request.FileHandler, "file_open", forbidden_handler)
    monkeypatch.setattr(urllib.request.DataHandler, "data_open", forbidden_handler)
    private = tmp_path / "private.html"
    private.write_text("<h1>Private</h1><main>local synthetic secret</main>")
    url = {
        "file": private.as_uri(),
        "data": "data:text/html,<main>local synthetic secret</main>",
        "ftp": "ftp://127.0.0.1:1/private.html",
    }[scheme]
    assert (
        list(
            fetch_forum_url(
                url,
                {
                    "title": "h1",
                    "question": "main",
                    "answer": ".answer",
                    "metadata": {},
                },
            )
        )
        == []
    )


@pytest.mark.parametrize(
    "target", ["file:///etc/passwd", "ftp://127.0.0.1:1/private.html", "data:text/html,secret"]
)
def test_forum_rejects_non_http_redirects(chains, monkeypatch, target):
    def forbidden_handler(*args, **kwargs):
        pytest.fail("redirect must not reach a non-HTTP protocol handler")

    monkeypatch.setattr(urllib.request.FTPHandler, "ftp_open", forbidden_handler)
    monkeypatch.setattr(urllib.request.FileHandler, "file_open", forbidden_handler)
    monkeypatch.setattr(urllib.request.DataHandler, "data_open", forbidden_handler)
    monkeypatch.setenv("SSL_CERT_FILE", str(chains["strong"][2]))
    with peer(chains["strong"], ssl.TLSVersion.TLSv1_3, redirect=target) as (port, observed):
        assert list(fetch_forum_url(f"https://localhost:{port}")) == []
    assert observed["application_bytes"]


@pytest.mark.parametrize(
    "url", ["relative/forum.html", "//example.invalid/forum", "http://[invalid"]
)
def test_forum_cleanly_rejects_missing_or_malformed_scheme(url):
    assert list(fetch_forum_url(url)) == []


@pytest.mark.parametrize("version", [ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3])
def test_forum_discards_truncated_response(chains, monkeypatch, version):
    monkeypatch.setenv("SSL_CERT_FILE", str(chains["strong"][2]))
    body = b"<h1>Title</h1><main>partial document must not be ingested</main>"
    with peer(chains["strong"], version, response_body=body, declared_length=len(body) + 100) as (
        port,
        observed,
    ):
        assert (
            list(
                fetch_forum_url(
                    f"https://localhost:{port}",
                    {
                        "title": "h1",
                        "question": "main",
                        "answer": ".answer",
                        "metadata": {},
                    },
                )
            )
            == []
        )
    assert observed["application_bytes"]


@pytest.mark.parametrize(
    "response",
    [
        b"not-an-http-status\r\nContent-Length: 0\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nX-Oversized: " + b"x" * 66000 + b"\r\n\r\n",
    ],
)
def test_forum_discards_malformed_http_response(chains, monkeypatch, response):
    monkeypatch.setenv("SSL_CERT_FILE", str(chains["strong"][2]))
    with peer(chains["strong"], ssl.TLSVersion.TLSv1_3, raw_response=response) as (port, observed):
        assert list(fetch_forum_url(f"https://localhost:{port}")) == []
    assert observed["application_bytes"]


@pytest.mark.parametrize(
    "charset,text",
    [
        ("windows-1251", "Привет"),
        ("shift_jis", "こんにちは"),
        ("iso-8859-9", "ışık"),
        ("invalid-charset", "Привет"),
    ],
)
def test_forum_preserves_http_charset(chains, monkeypatch, charset, text):
    monkeypatch.setenv("SSL_CERT_FILE", str(chains["strong"][2]))
    encoding = "utf-8" if charset == "invalid-charset" else charset
    body = f"<html><h1>Title</h1><main>{text}</main></html>".encode(encoding)
    response = (
        f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset={charset}\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    ).encode("ascii") + body
    with peer(chains["strong"], ssl.TLSVersion.TLSv1_3, raw_response=response) as (port, _):
        documents = list(
            fetch_forum_url(
                f"https://localhost:{port}",
                {
                    "title": "h1",
                    "question": "main",
                    "answer": ".answer",
                    "metadata": {},
                },
            )
        )
    assert len(documents) == 1
    assert text in documents[0].page_content


def test_forum_preserves_unicode_paths_and_queries(chains, monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", str(chains["strong"][2]))
    body = b"<h1>Title</h1><main>Unicode URL works</main>"
    with peer(chains["strong"], ssl.TLSVersion.TLSv1_3, response_body=body) as (port, observed):
        url = f"https://localhost:{port}/тема?q=б"
        documents = list(
            fetch_forum_url(
                url,
                {
                    "title": "h1",
                    "question": "main",
                    "answer": ".answer",
                    "metadata": {},
                },
            )
        )
    assert b"GET /%D1%82%D0%B5%D0%BC%D0%B0?q=%D0%B1 HTTP/1.1" in observed["application_bytes"]
    assert len(documents) == 1
    assert documents[0].metadata["source"] == url


def test_forum_normalizes_internationalized_host_without_network():
    assert (
        _normalize_forum_url("https://пример.рф/тема")
        == "https://xn--e1afmkfd.xn--p1ai/%D1%82%D0%B5%D0%BC%D0%B0"
    )
