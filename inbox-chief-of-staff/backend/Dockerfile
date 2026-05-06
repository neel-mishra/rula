FROM python:3.11-slim
WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Install dependencies first (cached layer — only re-runs when pyproject.toml changes)
COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache -e ".[dev]"

# Copy source last (changes most often)
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
