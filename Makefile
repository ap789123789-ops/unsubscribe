.PHONY: setup openapi build test dev-backend dev-frontend

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

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend:
	npm --prefix frontend run dev
