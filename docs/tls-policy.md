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

## MCP API and corpus-download HTTPS

The MCP RagApiClient and the Victron content downloader use owned stdlib TLS
contexts. They preserve default CA/hostname checks, environment proxy routing,
redirect handling and request timeouts. The verified origin chain is checked
before the HTTP request or query payload. Plain HTTP remains available for the
existing local API deployment; this policy does not add TLS to an HTTP URL.

Run `scripts/fetch_victron_content.py` in the installed project environment
(`uv run --locked python scripts/fetch_victron_content.py ...`). The deployment
helper calls this script, so activate that same environment before using its
`--with-manuals` option. The downloader now needs the shared package and its
cryptography dependency, rather than a bare system Python.

This change does not configure the separate Requests forum loader, optional
LLM/embedding provider SDKs, database transport or external ingress. Stdlib
HTTP-proxy routing and NO_PROXY bypass are preserved. An actually selected
HTTPS-scheme proxy is rejected before any connection, CONNECT or proxy
credentials: stdlib urllib cannot provide TLS to that proxy. Use a supported
HTTP proxy (the HTTPS origin remains verified) or bypass it explicitly.
HTTP/1.1 ALPN and default redirects are preserved by the per-call opener.
These remain separate assessment paths, not a whole-project OpenSSF
key-length attestation.
