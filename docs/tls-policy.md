# TLS certificate key policy

Owned TLS contexts retain CA and hostname verification and inspect the actual
verified chain, including its selected trust anchor, before application data.
RSA moduli must contain at least 2048 significant bits; EC keys need at least
224 bits; DSA requires p >= 2048 and q >= 224. Ed25519 and Ed448 are accepted.
Unknown algorithms or runtimes without an accessible verified chain fail closed.
OpenSSL security level 2 alone can accept a 2047-bit RSA modulus.

CPython 3.11 and 3.12 use the private `_sslobj.get_verified_chain` interface;
newer CPython versions may expose the public equivalent. This runtime contract
is tested rather than inferred from the Python version. Alternative Python
implementations are not implicitly supported.

The public-key decoder uses cryptography except on Intel macOS, where the
native Security framework reads key metadata without changing trust decisions.
The Intel backend accepts RSA and EC only. No system trust store is modified.

The TLS policy and Darwin metadata decoder are adapted from the MIT-licensed
victron-venus/inverter-dashboard implementation, copyright 2026 victron-venus.
The project MIT license also applies to these adaptations. This policy does
not establish the strength of inbound TLS terminators or unrelated transports.

## MCP API, corpus-download and forum HTTPS

The MCP RagApiClient, Victron content downloader and forum loader use owned stdlib TLS
contexts. They preserve default CA/hostname checks, environment proxy routing,
redirect handling and request timeouts. The verified origin chain is checked
before the HTTP request or query payload. Forum ingestion accepts only HTTP(S)
URLs, including redirect targets; local files, FTP and data URLs are rejected.
Plain HTTP remains available for the
existing local API deployment; this policy does not add TLS to an HTTP URL.

Run `scripts/fetch_victron_content.py` in the installed project environment
(`uv run --locked python scripts/fetch_victron_content.py ...`). The deployment
helper calls this script, so activate that same environment before using its
`--with-manuals` option. The downloader now needs the shared package and its
cryptography dependency, rather than a bare system Python.

The compatibility profile does not configure optional LLM/embedding provider
SDKs, database transport or external ingress. Stdlib
HTTP-proxy routing and NO_PROXY bypass are preserved. An actually selected
HTTPS-scheme proxy is rejected before any connection, CONNECT or proxy
credentials: stdlib urllib cannot provide TLS to that proxy. Use a supported
HTTP proxy (the HTTPS origin remains verified) or bypass it explicitly.
HTTP/1.1 ALPN and default redirects are preserved by the per-call opener.
Use the following enforced profile when all application TLS must use this
verified-chain policy.


## Local/offline deployment profile

`STRICT_LOCAL_PROFILE=true` is an optional, enforced deployment profile for a
single trusted host running the RAG API, PostgreSQL and Ollama. It keeps full
local ingestion, vector search and generation functionality while eliminating
unmanaged SDK TLS. The compatibility profile remains the default and still
supports remote providers and normal model downloads; those SDK connections
are not covered by the exact verified-chain checks above.

Prepare embedding and optional reranker model directories through a separately
reviewed distribution process, verify their provenance, and install dependencies
before starting. A missing model fails instead of downloading it. The following
variables must be exported in the process environment (Hub reads its offline
flag at import time; putting only that flag in `.env` is insufficient):

```sh
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export HF_HUB_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export LANGCHAIN_TRACING=false LANGCHAIN_TRACING_V2=false LANGSMITH_TRACING=false
export STRICT_LOCAL_PROFILE=true
export API_HOST=127.0.0.1
export EMBEDDING_MODEL=/absolute/path/to/verified-local-embedding-model
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://127.0.0.1:11434
# Set DATABASE_URL privately to a loopback postgresql+asyncpg URL with no query.
# Keep credentials out of shell history and public reports.
uv run --locked energy-rag-api
```

If reranking is enabled, set `RERANK_MODEL` to its verified local model directory.
Both model constructors receive `local_files_only=True`. Startup rejects an
online Hub already imported into the process, proxy variables, external tracing,
remote/provider SDK endpoints, non-local API bindings and database URL query
options. The three database creation paths explicitly set `ssl=False` on
loopback, preventing asyncpg opportunistic TLS from selecting a different
unchecked context. No certificate or trust verification is disabled on an
actual TLS connection: local PostgreSQL and Ollama use plaintext within the
trusted host boundary; forum/corpus/API HTTPS retains verified TLS.

The trusted local Ollama and PostgreSQL services, host routing, model artifacts
and other users with host access are part of this profile's trust boundary.
This is not an egress sandbox: for example, the local Ollama service must not
redirect its client to an untrusted remote endpoint. Never use this profile to
claim encrypted traffic across machines, or expose its plaintext loopback
services through an unreviewed forwarder. External ingress, proxies and release
transport have separate responsibilities. The release helper's verified
GitHub CLI/Go configuration is described in [RELEASE_TLS_PROFILE.md](RELEASE_TLS_PROFILE.md).

`tests/unit/test_deployment_policy.py` checks startup rejection and the actual
embedding/reranker/database factory wiring; `tests/unit/test_urllib_tls.py`
performs real TLS handshakes against synthetic strong and weak certificate
chains before checking received application bytes. These tests establish the
profile and owned HTTPS behavior, not a complete model or third-party SDK audit.
