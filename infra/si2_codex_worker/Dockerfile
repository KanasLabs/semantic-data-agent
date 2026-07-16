FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.144.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && npm install --global "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /bin/bash codex-worker

ENV CODEX_HOME=/tmp/codex-home

USER 10001:10001
WORKDIR /workspace

ENTRYPOINT ["codex"]
