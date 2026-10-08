# Security Policy

## Reporting a Vulnerability

Private vulnerability reporting is enabled for this repository. Use
[Report a vulnerability](https://github.com/4alvit/energy-data-rag-pipeline/security/advisories/new)
to send a confidential report to the maintainers. Follow
[GitHub's private reporting instructions](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
if you need help submitting the report.

Include the affected version or commit, steps to reproduce, expected and actual
behavior, and potential impact. Remove access tokens, credentials and personal
data from examples. Do not disclose exploit details in public issues before
coordinating with the maintainers.

## Support and response

Security fixes target the current default branch and the latest maintained release, where releases exist. Older versions are not promised backports. Maintainers aim to acknowledge private reports within 14 days, investigate and communicate status within 60 days, and coordinate disclosure with the reporter. Confirmed vulnerabilities with a practical fix receive priority over feature work; publish an advisory and release notes that identify affected versions, mitigation and the fixed version. If a fix takes longer, keep the reporter informed without exposing confidential details.

## Deployment trust boundaries

Downloaded documents, upload contents, source URLs and model outputs are untrusted. Preserve fetch/path/input limits and citation provenance. The service configuration includes local-development database defaults; replace these with private credentials and put the API/database behind trusted access controls before external exposure. Do not assume generated answers are authoritative or execute instructions embedded in retrieved documents. Protect provider keys and any non-public ingested material.

Use synthetic data for testing. Never attach live tokens, private keys, database exports or household telemetry to public CI artifacts. Report a suspected credential exposure privately and revoke the credential through its issuer. See [CONTRIBUTING.md](CONTRIBUTING.md) for validation and [the evidence index](docs/openssf-evidence.md) for assessment limits.


## Cryptographic implementation and platform policy

Use current supported Python and TLS/SSH libraries. HTTPS requests retain the
library's certificate verification; do not disable verification to work around
an endpoint error. The audited Python 3.12.14/OpenSSL 3.5.8 default TLS context
requires TLS 1.2 or later, security level 2, at least 128-bit symmetric encryption
and ephemeral key exchange. Retain those requirements on the deployed runtime.
The project delegates cryptographic primitives to FLOSS libraries; it does not
implement a cipher or a random-number generator for keys/nonces. Telemetry
sampling and retry jitter, where present, are not cryptographic operations.

Use authenticated encrypted transport whenever credentials or private data leave
a trusted isolated network. A local plaintext MQTT/HTTP option is not encrypted
by these TLS defaults. Operators must separately verify remote certificates or
SSH host-key fingerprints and replace obsolete endpoint keys. The source and
release downloads are served through GitHub HTTPS.
