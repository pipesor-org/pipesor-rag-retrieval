FROM python:3.14.8-slim@sha256:00ebdcac87ebf7fd62576d8bbe8f8f1e94198befcc4e38c4db9671e61e0dfcfe AS builder

WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip wheel --disable-pip-version-check --no-cache-dir --wheel-dir /wheels .

FROM python:3.14.8-slim@sha256:00ebdcac87ebf7fd62576d8bbe8f8f1e94198befcc4e38c4db9671e61e0dfcfe AS runtime

ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/pipesor-org/pipesor-rag-retrieval" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="0.1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 pipesor \
    && useradd --uid 10001 --gid pipesor --no-create-home --shell /usr/sbin/nologin pipesor

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels pipesor-rag-retrieval==0.1.0 \
    && rm -rf /wheels

WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["pipesor-rag-retrieval"]

