# Contributing

Document ingestion and retrieval-augmented generation for energy documentation using pgvector, LangChain and FastAPI.

## Questions, bugs and proposals

Use [GitHub Issues](https://github.com/4alvit/energy-data-rag-pipeline/issues) for questions, bug reports and feature proposals. Search existing issues first. Describe the affected version/commit, expected and actual behavior, minimal reproduction and relevant environment. Remove tokens, private endpoints, household identifiers and personal data from examples. Security vulnerabilities use the confidential process in [SECURITY.md](SECURITY.md).

Anyone may propose a change through a pull request. Discuss compatibility or architectural changes in an issue before a large implementation. Maintainers aim to acknowledge actionable reports within 14 days; security reports follow the security policy. No paid support or response-time guarantee is implied.

## Development and validation

Clone the repository, create a branch from `main`, and use the Python version and dependencies declared by the project and CI. Run from the repository root:

```sh
uv sync --locked --all-extras
bash scripts/ci.sh lint
bash scripts/ci.sh test
```

The local gate runs locked dependencies, Ruff, formatting, Pylint and the test/database harness. See `docs/local-ci.md` for PostgreSQL/pgvector prerequisites. Use fixture documents and mocked model calls where specified; external model access, downloaded corpora and physical deployment are separate checks.

For a bug fix, add a regression test that fails before the fix and passes afterward. For new functionality, test normal behavior, invalid input and relevant authorization/error paths. Preserve existing checks; do not lower coverage gates or ignore findings merely to obtain a green build. Python code follows the configured formatter/linter where present and normal PEP 8 conventions otherwise. Keep shell, YAML and generated examples compatible with their declared tools.

## Review and compatibility

Keep pull requests focused and explain the problem, resulting behavior, compatibility impact and exact validation performed. Update the user-facing documentation when changing configuration, interfaces or operational behavior. Call out tests not run and their prerequisites. Maintainers review changes through GitHub pull requests and required CI; automated review is supplemental. Contributions are provided under the repository's [MIT license](LICENSE); a contributor must have the right to submit the work.

Follow `RELEASING.md` and `docs/release-and-images.md`. Document database/schema migrations, model/index compatibility, deployment steps and security fixes in published release notes.

## Source and interfaces

- [`src/energy_rag`](src/energy_rag)
- [`sql`](sql)
- [`README.md`](README.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/api-reference.md`](docs/api-reference.md)
- [`docs/configuration.md`](docs/configuration.md)
- [`docs/local-ci.md`](docs/local-ci.md)
- [`RELEASING.md`](RELEASING.md)

See the [OpenSSF evidence index](docs/openssf-evidence.md) for the current assessment scope and outstanding verification.
