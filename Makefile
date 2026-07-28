PATH := $(HOME)/.local/bin:$(PATH)
UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

.PHONY: install api test lint format check services-up services-down services-logs docker-build compose-config container-smoke locust-smoke version-check activation-manifest qdrant-inventory staging-smoke smoke-test doctor help

.DEFAULT_GOAL := help

help: ## Display available commands
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies using uv
	$(UV) sync

api: ## Start FastAPI application web server locally
	$(UV) run company-graphrag api

test: ## Run unit and integration tests with pytest
	$(UV) run pytest

lint: ## Run ruff and mypy static code analysis
	$(UV) run ruff check .
	$(UV) run mypy src

format: ## Auto-format code with ruff
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

check: ## Run full lint and test checks
	$(UV) run ruff check .
	$(UV) run mypy src
	$(UV) run pytest

services-up: ## Start core Docker services (API, Qdrant, Neo4j)
	docker compose --profile core up -d

services-down: ## Stop Docker services
	docker compose --profile core down

services-logs: ## View real-time logs for Docker services
	docker compose --profile core logs -f

docker-build: ## Build local production Docker image
	docker build -t company-graphrag:latest .

compose-config: ## Validate all Docker Compose profiles
	docker compose --profile core --profile observability --profile load-test config --quiet

container-smoke: ## Run isolated liveness/version smoke checks against the image
	./scripts/container_smoke.sh company-graphrag:latest

locust-smoke: ## Run a short headless load smoke test against a running API
	$(UV) run locust -f tests/load/locustfile.py --headless --tags smoke -u 1 -r 1 -t 10s --host http://127.0.0.1:8000

version-check: ## Validate prompt and artifact version consistency
	$(UV) run company-graphrag version-check

activation-manifest: ## Generate a secret-free production activation manifest
	$(UV) run python scripts/generate_activation_manifest.py

qdrant-inventory: ## Inventory the local Qdrant collection for migration evidence
	$(UV) run python scripts/qdrant_activation.py inventory --path data/vector_store/qdrant_db --collection company_documents --output artifacts/production_activation/qdrant/pre-migration-inventory.json

staging-smoke: ## Run bounded smoke checks; requires STAGING_URL and optional API_KEY
	test -n "$(STAGING_URL)"
	$(UV) run python scripts/staging_smoke.py --base-url "$(STAGING_URL)"

smoke-test: ## Run API and health check smoke tests
	$(UV) run pytest tests/test_api.py tests/test_versioning.py tests/test_reliability.py -v

doctor: ## Run system connection health check for Qdrant and Neo4j
	$(UV) run company-graphrag doctor
