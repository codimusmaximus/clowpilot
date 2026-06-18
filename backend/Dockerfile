FROM python:3.12-slim

# Docker CLI: the container plugin shells out to `docker` against the host socket
# (mounted in docker-compose.yml) to manage the sandbox sibling container.
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install uv
ENV UV_PYTHON=/usr/local/bin/python

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV WORKSPACE_DIR=/workspace
ENV SQLITE_DB_PATH=/data/copilot.sqlite3

EXPOSE 8000

CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
