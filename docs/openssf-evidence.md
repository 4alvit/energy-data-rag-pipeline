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

## Criteria still requiring verification

Before submitting or updating the questionnaire, verify the actual project-specific record: responses to bug and enhancement reports, vulnerability reports in every supported channel, release-note history, unresolved scanner findings, dependency status and required review settings. The primary maintainer must personally confirm knowledge of secure design and common implementation vulnerabilities. A confirmation about another repository does not establish these answers here.

Assess transport encryption, credential storage and privilege limits against the implementation and deployment documented in [SECURITY.md](../SECURITY.md). Do not mark a requirement satisfied solely because a policy says it should be. Record justified non-applicability only where the actual architecture supports it. No paid certification, blanket compliance guarantee or third-party audit is claimed.
