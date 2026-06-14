FROM debian:bookworm-slim

ARG CODEX_VERSION=0.137.0
ARG GH_VERSION=2.93.0
ARG TARGETARCH

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/forge
ENV XDG_CONFIG_HOME=/home/forge/.config
ENV CODEX_HOME=/home/forge/.codex
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        gosu \
        nodejs \
        npm \
        openssh-client \
        passwd \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH}" in \
        amd64) gh_arch="amd64" ;; \
        arm64) gh_arch="arm64" ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl --fail --location --silent --show-error \
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${gh_arch}.tar.gz" \
        --output /tmp/gh.tgz \
    && tar -xzf /tmp/gh.tgz -C /tmp \
    && install "/tmp/gh_${GH_VERSION}_linux_${gh_arch}/bin/gh" /usr/local/bin/gh \
    && rm -rf /tmp/gh.tgz "/tmp/gh_${GH_VERSION}_linux_${gh_arch}"

RUN npm install --global "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

RUN groupadd --gid 1000 forge \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/forge --shell /bin/bash forge \
    && mkdir -p /home/forge/.config

COPY docker/entrypoint.sh /usr/local/bin/forge-entrypoint
RUN chmod 0755 /usr/local/bin/forge-entrypoint

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/forge-entrypoint"]
CMD ["/bin/bash"]
