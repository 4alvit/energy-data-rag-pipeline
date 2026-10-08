"""Exercise the real MCP and corpus requests with disposable TLS peers."""

import importlib.util
import socket
import ssl
from pathlib import Path
from urllib.error import URLError

import pytest
from test_tls_policy import CHAIN_CASES, calibrate, chains, clean_environment, peer, proxy

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
