# OpenSSF Best Practices evidence

This is an evidence index for the OpenSSF Best Practices Passing self-assessment. It is not an assertion that a badge has been awarded or that every criterion is satisfied. The public badge service is the authority for an awarded status.

## Project and participation

Document ingestion and retrieval-augmented generation for energy documentation using pgvector, LangChain and FastAPI.

The project is developed publicly in [Git](https://github.com/4alvit/energy-data-rag-pipeline) under the [MIT license](../LICENSE). Its source, issue tracker and pull requests are available without a paid account. [Contribution instructions](../CONTRIBUTING.md) describe reporting, changes, coding conventions, tests and review. The [security policy](../SECURITY.md) provides a confidential vulnerability-reporting path, support scope, response targets and deployment boundaries.

## User and interface documentation

- [`README.md`](../README.md)
- [`docs/architecture.md`](../docs/architecture.md)
- [`docs/api-reference.md`](../docs/api-reference.md)
- [`docs/configuration.md`](../docs/configuration.md)
- [`docs/local-ci.md`](../docs/local-ci.md)
- [`RELEASING.md`](../RELEASING.md)

## Source, testing and analysis

- [`src/energy_rag`](../src/energy_rag)
- [`sql`](../sql)

- [Test suite](../tests) and [CI workflows](../.github/workflows)
- [Local CI entry point](../scripts/ci.sh)
- [CodeQL analysis](../.github/workflows/codeql.yml)
- [Dependency update configuration](../.github/dependabot.yml)

The local gate runs locked dependencies, Ruff, formatting, Pylint and the test/database harness. See `docs/local-ci.md` for PostgreSQL/pgvector prerequisites. Use fixture documents and mocked model calls where specified; external model access, downloaded corpora and physical deployment are separate checks.

CI results are evidence for the tested revision and environment, not proof of safe production or hardware operation. Check the current default-branch runs and unresolved security findings before answering the analysis criteria. Fuzzing, coverage completeness and independent penetration testing must be supported by actual runs; ordinary unit tests must not be presented as those activities.

## Changes and releases

Follow `RELEASING.md` and `docs/release-and-images.md`. Document database/schema migrations, model/index compatibility, deployment steps and security fixes in published release notes. The [release policy](../.release-policy.json) records automation behavior. A new release must identify its source revision and explain notable changes; security fixes must identify relevant advisories when known.

## Assessment evidence and limits

The maintainer personally confirmed secure-design and common-vulnerability
knowledge for this project, with no external reports during the preceding
12 months. The 2026-10-14 GitHub history review found no ordinary issues or
public vulnerability advisories; private vulnerability reporting is enabled.
These are dated historical checks and do not replace future report handling.

The source-bound `v0.2.12-rc.1` report records a successful 60-second `citations`
fuzz campaign at `ec37f2187e7fe7c696b0dbd1f81ce4578902133e`:
[run 38489038609](https://github.com/4alvit/energy-data-rag-pipeline/actions/runs/38489038609).
That campaign predates the new forum TLS and local/offline profile changes.
The profile/TLS regressions validate those changes separately; neither result
establishes exhaustive source coverage or an independent security audit.

The [TLS profile](tls-policy.md) separates owned checked HTTPS from optional
provider SDKs. Complete exact-key enforcement is claimed only for its supported
local/offline configuration, not every compatibility configuration.
[Governance](../GOVERNANCE.md), [conduct](../CODE_OF_CONDUCT.md) and
[roadmap](../ROADMAP.md) document participation. No backup maintainer or tested
one-week access recovery process exists; Silver continuity remains unmet.
The public dynamic badge is authoritative for the awarded level.


### Release-note structure

Source release notes use ATX headings: `## [version]`, `### Upgrade`, and
`### Security`. A heading at the same or a higher level ends its section.
Setext (underlined) headings within the selected release are rejected because
this deliberately limited parser does not implement all CommonMark structure.
Fenced examples and HTML comments cannot supply the required guidance; normal
blank-separated thematic breaks remain supported. The published release body
preserves the original source text after validation.
