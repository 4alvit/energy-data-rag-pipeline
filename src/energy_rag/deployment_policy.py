"""Enforce the optional local/offline deployment profile at owned call sites."""

import ipaddress
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

_TRUE = {"1", "true", "yes", "on"}


def _is_loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def validate_environment() -> None:
    """Reject routes that could take a local SDK call outside this profile."""
    for name, value in os.environ.items():
        if name.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"} and value:
            raise ValueError("Strict local profile requires HTTP(S)/ALL proxy variables unset")
        if (
            name.upper() in {"LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"}
            and value.lower() in _TRUE
        ):
            raise ValueError("Strict local profile requires external LangSmith tracing disabled")
    if os.environ.get("HF_HUB_OFFLINE", "").lower() not in _TRUE:
        raise ValueError("Set HF_HUB_OFFLINE=1 before starting the strict local profile")
    constants = sys.modules.get("huggingface_hub.constants")
    if constants is not None and not constants.HF_HUB_OFFLINE:
        raise ValueError("Restart with HF_HUB_OFFLINE=1 before importing HuggingFace")


def local_model_options(model: str, enabled: bool) -> dict:
    """Only load a pre-staged local model directory in the strict profile."""
    if not enabled:
        return {}
    validate_environment()
    if not Path(model).is_dir():
        raise ValueError("Strict local profile requires an existing local model directory")
    return {"local_files_only": True}


def validate_llm(provider: str, url: str, enabled: bool) -> None:
    """The profile supports Ollama on loopback; other SDK TLS stays out of scope."""
    if not enabled:
        return
    validate_environment()
    parsed = urlsplit(url)
    has_url_options = any((parsed.username, parsed.password, parsed.query, parsed.fragment))
    if (
        provider != "ollama"
        or parsed.scheme != "http"
        or not _is_loopback(parsed.hostname)
        or has_url_options
    ):
        raise ValueError(
            "Strict local profile requires Ollama HTTP on loopback without URL credentials"
        )


def database_options(url: str, enabled: bool) -> dict:
    """Prevent asyncpg's opportunistic TLS from selecting an unchecked context."""
    if not enabled:
        return {}
    validate_environment()
    parsed = urlsplit(url)
    if (
        parsed.scheme != "postgresql+asyncpg"
        or not _is_loopback(parsed.hostname)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Strict local profile requires loopback asyncpg without URL query overrides"
        )
    return {"connect_args": {"ssl": False}}


def validate_settings(config) -> None:
    """Fail at startup, then recheck immediately before each relevant client."""
    if not config.strict_local_profile:
        return
    validate_environment()
    validate_llm(config.llm_provider, config.ollama_base_url, True)
    database_options(config.database_url, True)
    local_model_options(config.embedding_model, True)
    if config.enable_rerank:
        local_model_options(config.rerank_model, True)
    if not _is_loopback(config.api_host):
        raise ValueError("Strict local profile requires API_HOST to be a loopback address")
