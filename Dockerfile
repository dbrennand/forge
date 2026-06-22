FROM debian:bookworm-slim AS gh-builder

ARG GH_VERSION=2.93.0
ARG TARGETARCH
ARG GH_AMD64_SHA256=02d1290eba130e0b896f3709ffff22e1c75a51475ddb70476a85abc6b5807af0
ARG GH_ARM64_SHA256=c55feb33684abba57e9909737340d5b39282257c0363e1edde6785ac4a413be7

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        tar \
    && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH}" in \
        amd64) gh_arch="amd64"; gh_sha256="${GH_AMD64_SHA256}" ;; \
        arm64) gh_arch="arm64"; gh_sha256="${GH_ARM64_SHA256}" ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl --fail --location --silent --show-error \
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${gh_arch}.tar.gz" \
        --output /tmp/gh.tgz \
    && echo "${gh_sha256}  /tmp/gh.tgz" | sha256sum --check - \
    && tar -xzf /tmp/gh.tgz -C /tmp \
    && install "/tmp/gh_${GH_VERSION}_linux_${gh_arch}/bin/gh" /usr/local/bin/gh \
    && rm -rf /tmp/gh.tgz "/tmp/gh_${GH_VERSION}_linux_${gh_arch}"

FROM debian:bookworm-slim AS uv-builder

ARG UV_VERSION=0.11.21
ARG TARGETARCH
ARG UV_AMD64_SHA256=8c88519b0ef0af9801fcdee419bbb12116bd9e6b18e162ae093c932d8b264050
ARG UV_ARM64_SHA256=88e800834007cc5efd4675f166eb2a51e7e3ad19876d85fa8805a6fb5c922397

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        tar \
    && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH}" in \
        amd64) uv_dist="uv-x86_64-unknown-linux-gnu"; uv_sha256="${UV_AMD64_SHA256}" ;; \
        arm64) uv_dist="uv-aarch64-unknown-linux-gnu"; uv_sha256="${UV_ARM64_SHA256}" ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl --fail --location --silent --show-error \
        "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${uv_dist}.tar.gz" \
        --output /tmp/uv.tgz \
    && echo "${uv_sha256}  /tmp/uv.tgz" | sha256sum --check - \
    && tar -xzf /tmp/uv.tgz -C /tmp \
    && install "/tmp/${uv_dist}/uv" /usr/local/bin/uv \
    && install "/tmp/${uv_dist}/uvx" /usr/local/bin/uvx \
    && rm -rf /tmp/uv.tgz "/tmp/${uv_dist}"

FROM debian:bookworm-slim AS gitleaks-builder

ARG GITLEAKS_VERSION=8.30.1
ARG TARGETARCH
ARG GITLEAKS_AMD64_SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
ARG GITLEAKS_ARM64_SHA256=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        tar \
    && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH}" in \
        amd64) gitleaks_arch="x64"; gitleaks_sha256="${GITLEAKS_AMD64_SHA256}" ;; \
        arm64) gitleaks_arch="arm64"; gitleaks_sha256="${GITLEAKS_ARM64_SHA256}" ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl --fail --location --silent --show-error \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${gitleaks_arch}.tar.gz" \
        --output /tmp/gitleaks.tgz \
    && echo "${gitleaks_sha256}  /tmp/gitleaks.tgz" | sha256sum --check - \
    && tar -xzf /tmp/gitleaks.tgz -C /tmp \
    && install /tmp/gitleaks /usr/local/bin/gitleaks \
    && rm -rf /tmp/gitleaks.tgz /tmp/gitleaks

FROM debian:bookworm-slim AS codex-builder

ARG CODEX_VERSION=0.137.0

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install --global "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

FROM debian:bookworm-slim

ARG AI_GUARDIAN_VERSION=1.11.1

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/forge
ENV XDG_CONFIG_HOME=/home/forge/.config
ENV CODEX_HOME=/home/forge/.codex
ENV PYTHONUNBUFFERED=1
ENV UV_TOOL_BIN_DIR=/usr/local/bin
ENV UV_TOOL_DIR=/opt/uv/tools
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bash \
        bubblewrap \
        ca-certificates \
        curl \
        git \
        gosu \
        nodejs \
        openssh-client \
        passwd \
        ripgrep \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=gh-builder /usr/local/bin/gh /usr/local/bin/gh
COPY --from=uv-builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=uv-builder /usr/local/bin/uvx /usr/local/bin/uvx
COPY --from=gitleaks-builder /usr/local/bin/gitleaks /usr/local/bin/gitleaks
COPY --from=codex-builder /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -sf ../lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex

RUN mkdir -p "${UV_TOOL_DIR}" "${UV_PYTHON_INSTALL_DIR}" \
    && uv tool install --python 3.13 "ai-guardian==${AI_GUARDIAN_VERSION}"

RUN groupadd --gid 1000 forge \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/forge --shell /bin/bash forge \
    && mkdir -p /home/forge/.config

COPY docker/entrypoint.sh /usr/local/bin/forge-entrypoint
RUN chmod 0755 /usr/local/bin/forge-entrypoint

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/forge-entrypoint"]
CMD ["/bin/bash"]
