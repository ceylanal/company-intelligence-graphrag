PATH := $(HOME)/.local/bin:$(PATH)
UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

.PHONY: install test lint format check services-up services-down services-logs doctor help

.DEFAULT_GOAL := help

help: ## Display available commands
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies using uv
	$(UV) sync

test: ## Run unit and integration tests with pytest
	$(UV) run pytest

lint: ## Run ruff and mypy static code analysis
	$(UV) run ruff check .
	$(UV) run mypy src

format: ## Auto-format code with ruff
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

check: ## Run full lint and test checks
	$(UV) run pytest
	$(UV) run ruff check .
	$(UV) run mypy src

services-up: ## Start Qdrant and Neo4j local Docker services
	docker compose up -d

services-down: ## Stop local Docker services
	docker compose down

services-logs: ## View real-time logs for Docker services
	docker compose logs -f

doctor: ## Run system connection health check for Qdrant and Neo4j
	$(UV) run company-graphrag doctor
