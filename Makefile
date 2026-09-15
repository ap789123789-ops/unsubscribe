.PHONY: setup openapi build test lint typecheck verify smoke-real-read smoke-real dev-backend dev-frontend

setup:
	cd backend && uv sync
	npm --prefix frontend install

openapi:
	cd backend && uv run python ../scripts/export_openapi.py
	npm --prefix frontend run generate:api

build: openapi
	npm --prefix frontend run build

test:
	cd backend && uv run pytest -q
	npm --prefix frontend test

lint:
	cd backend && uv run ruff format --check app tests ../scripts
	cd backend && uv run ruff check app tests ../scripts
	npm --prefix frontend run lint

typecheck:
	cd backend && uv run mypy app
	npm --prefix frontend run typecheck

verify:
	cd backend && uv lock --check
	cd backend && uv run ruff format --check app tests ../scripts
	cd backend && uv run ruff check app tests ../scripts
	cd backend && uv run mypy app
	cd backend && uv run pytest tests/unit -q
	cd backend && uv run pytest tests/api tests/integration -q
	cd backend && uv run pytest tests/evals -q
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck
	npm --prefix frontend test
	npm --prefix frontend run build
	cd backend && uv run python ../scripts/check_openapi.py
	npm --prefix frontend run test:e2e

smoke-real:
	cd backend && uv run python ../scripts/smoke_real.py

smoke-real-read:
	cd backend && uv run python ../scripts/smoke_real_read.py

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend:
	npm --prefix frontend run dev
