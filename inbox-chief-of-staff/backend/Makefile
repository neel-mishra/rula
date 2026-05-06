.PHONY: dev test lint typecheck migrate db-up db-down

dev:
	uv run uvicorn app.main:app --reload --port 8000

# Start only the databases (typical local dev — run the API with `make dev`)
db-up:
	docker compose up -d db db-test

db-down:
	docker compose down

test:
	DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/inbox_chief_test \
	  uv run pytest tests/ -v

test-one:
	DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/inbox_chief_test \
	  uv run pytest $(TEST) -v

lint:
	uv run ruff check app/ tests/

typecheck:
	uv run mypy app/

migrate:
	uv run alembic upgrade head

migrate-new:
	uv run alembic revision --autogenerate -m "$(MSG)"

format:
	uv run ruff format app/ tests/
