# Headless Free Claude Code server - an Anthropic-compatible proxy that
# routes coding-agent traffic to free-tier providers (NVIDIA NIM, OpenRouter,
# LM Studio, Ollama, ...).
#
# Upstream has no PyPI package and no release tags, so the install URL is
# pinned to a commit and archive hash in requirements.txt. Runtime versions
# start from that commit's uv.lock with targeted advisory fixes recorded in
# requirements.in; the build backend is separately hash-locked.
# Admin UI (model/provider config) is served on the same port as the proxy.

FROM python:3.14-slim@sha256:0741d101873c12ab927e6f8653feb8862b9bd58771177acb1b885b95141f91b4

ARG FCC_REF=9b334dedfec842a4ad340a95f6332ac5acf2bb7f

LABEL org.opencontainers.image.source="https://github.com/Alishahryar1/free-claude-code"
LABEL org.opencontainers.image.description="Free Claude Code proxy server (headless)"

COPY requirements.txt requirements-build.txt /tmp/fcc-dependencies/
RUN grep -F "/archive/${FCC_REF}.tar.gz" /tmp/fcc-dependencies/requirements.txt > /dev/null && \
    pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/fcc-dependencies/requirements-build.txt && \
    pip install --no-cache-dir --only-binary=:all: --no-binary=free-claude-code --no-build-isolation --require-hashes -r /tmp/fcc-dependencies/requirements.txt

ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8082 \
    FCC_OPEN_BROWSER=false \
    MESSAGING_PLATFORM=none

RUN useradd --create-home --uid 1000 fcc
# Pre-create the config dir so volume provision (named or bind) inherits
# fcc ownership instead of root:root.
RUN mkdir -p /home/fcc/.fcc && chown fcc:fcc /home/fcc/.fcc
USER fcc
WORKDIR /home/fcc

# The Admin UI persists provider keys and model mapping to ~/.fcc/.env;
# keep it in a volume so configuration survives container replacement.
VOLUME ["/home/fcc/.fcc"]

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import socket; s = socket.create_connection(('localhost', 8082), timeout=4); s.close()"]

CMD ["fcc-server"]
