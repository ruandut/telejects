# Shortcuts. Each target is a plain command you can also run by hand (see README.md).
VP := $(shell command -v vp 2>/dev/null || echo $(CURDIR)/frontend/node_modules/.bin/vp)

.PHONY: env up down setup hatchet-token migrate seed superuser api worker web stop test check

# The app always runs on the same ports, so the frontend's proxy, links in emails and bookmarks
# keep working. Starting a server takes its port over from whatever still holds it (usually an
# earlier run left open in another terminal) instead of failing or drifting to the next free port.
API_PORT := 8010
WEB_PORT := 5184

env:           ## Create .env with generated local secrets (keeps an existing one)
	./scripts/init_env.sh

up: env        ## Start Postgres and Hatchet
	docker compose up -d --wait

down:          ## Stop them (data is kept in volumes)
	docker compose down

setup: up      ## First-time setup: deps, migrations, Hatchet token, local sign-in
	cd backend && uv sync
	cd frontend && pnpm install
	$(MAKE) migrate hatchet-token seed

hatchet-token: ## Create a Hatchet API token and write it into .env
	./scripts/hatchet_token.sh

migrate:
	cd backend && uv run python manage.py migrate

seed:          ## Local sign-in from .env. Safe to re-run.
	cd backend && uv run python manage.py seed

superuser:
	cd backend && uv run python manage.py createsuperuser

api:           ## Django on :8010, over ASGI (Daphne): HTTP and websockets
	./scripts/free_port.sh $(API_PORT)
	cd backend && uv run python manage.py runserver $(API_PORT)

worker:        ## Hatchet worker (restart it after changing task code). Replaces an earlier one.
	./scripts/stop_worker.sh
	cd backend && uv run python manage.py hatchet_worker

web:           ## Vite+ dev server on :5184
	./scripts/free_port.sh $(WEB_PORT)
	cd frontend && $(VP) dev

stop:          ## Stop the API, the web server and the worker, wherever they were started
	./scripts/free_port.sh $(API_PORT)
	./scripts/free_port.sh $(WEB_PORT)
	./scripts/stop_worker.sh

test:
	cd backend && uv run pytest -q

check:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && $(VP) check
