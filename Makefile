.PHONY: up down ps logs build migrate seed api worker frontend frontend-dev

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

ps:
	docker compose -f infra/docker-compose.yml ps

logs:
	docker compose -f infra/docker-compose.yml logs -f

build:
	docker compose -f infra/docker-compose.yml build

api:
	docker compose -f infra/docker-compose.yml up api

worker:
	docker compose -f infra/docker-compose.yml up worker

migrate:
	cd backend && .venv/bin/alembic upgrade head

seed:
	cd backend && .venv/bin/python -m clipforge.scripts.seed

frontend:
	cd frontend && npm run build

frontend-dev:
	cd frontend && npm run dev
