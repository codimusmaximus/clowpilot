FROM python:3.12-slim

WORKDIR /app

RUN pip install uv
ENV UV_PYTHON=/usr/local/bin/python

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Pre-download the model into the image so first request isn't slow.
RUN .venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8001

CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
