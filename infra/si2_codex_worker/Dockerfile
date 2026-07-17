ARG BASE_IMAGE=node:22-bookworm-slim
FROM ${BASE_IMAGE}

ARG CODEX_VERSION=0.144.1
ARG DEBIAN_MIRROR_HOST=deb.debian.org
ARG NPM_REGISTRY=https://registry.npmjs.org

RUN sed -i "s|deb.debian.org|${DEBIAN_MIRROR_HOST}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && npm install --global "@openai/codex@${CODEX_VERSION}" --registry="${NPM_REGISTRY}" \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /bin/bash codex-worker

COPY worker-entrypoint.sh /tmp/worker-entrypoint.sh

RUN install -m 0755 /tmp/worker-entrypoint.sh /usr/local/bin/si2-codex-worker \
    && rm /tmp/worker-entrypoint.sh

ENV CODEX_HOME=/tmp/codex-home
ENV HOME=/tmp/home

USER 10001:10001
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/si2-codex-worker"]
