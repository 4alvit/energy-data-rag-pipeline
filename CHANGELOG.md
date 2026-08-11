# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-10

### Added
- Initial RAG pipeline for Victron Energy documentation
- Document ingestion for PDF manuals, forum HTML, and JSON
- Smart chunking with MarkdownHeaderTextSplitter and RecursiveCharacterTextSplitter
- pgvector storage with metadata filtering (product, section, page)
- FastAPI query endpoint with source citations
- LangChain retrieval with configurable LLM providers (Ollama, OpenAI, Anthropic)
- Docker Compose stack (PostgreSQL + pgvector + API)
- CI pipeline with Ruff, Pylint, pytest, and coverage
- Release workflow with automated GitHub releases

### Changed
- Fixed CI badge URL in README (was pointing to wrong org)

[0.1.0]: https://github.com/4alvit/energy-data-rag-pipeline/releases/tag/v0.1.0