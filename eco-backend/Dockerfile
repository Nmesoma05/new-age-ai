# syntax=docker/dockerfile:1.7
# API image. Same image runs the web API, migrations (`alembic upgrade head`) and jobs (`python -m scripts.…`).
# Base images: pin by digest in CI (Renovate/Dependabot keeps them current). Python 3.13 = the version tested.
FROM python:3.13-slim-bookworm AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt requirements-prod.txt ./
RUN pip wheel --wheel-dir /wheels -r requirements.txt -r requirements-prod.txt

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 LOG_FORMAT=json
# postgresql-client-16 (from the PostgreSQL project's apt repo; Debian's is v15, which can't dump a v16 server)
# for the backup and restore-drill jobs. Build tools are removed again afterwards.
# hadolint ignore=DL3008
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-16 \
 && apt-get purge -y curl gnupg && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-index /wheels/* && rm -rf /wheels
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app scripts ./scripts
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=4s --start-period=20s \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status != 200)"]
# sh -c so WEB_CONCURRENCY expands; `exec` keeps uvicorn as PID 1 for clean shutdown on SIGTERM.
# --no-proxy-headers: the client IP is resolved by app/core/clientip.py from TRUSTED_PROXIES, in one place only.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --no-proxy-headers --no-server-header --timeout-graceful-shutdown 25"]
