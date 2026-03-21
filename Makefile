# Batman Lab — Makefile
# Convenience commands for development and operations
#
# Usage:
#   make help          — show all commands
#   make test          — run all 383+ tests
#   make lint          — lint both repos
#   make run           — start Batman + Nightwing + Dashboard
#   make docker-up     — start everything in Docker
#   make git-save      — quick commit + push

.PHONY: help test test-batman test-nightwing lint typecheck run dashboard docker-up docker-down docker-test git-save clean

PYTHON = python3
PYTEST = $(PYTHON) -m pytest

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─────────────────────── TESTING ───────────────────────

test: test-batman test-nightwing ## Run ALL tests (383+)
	@echo "✅ All tests complete"

test-batman: ## Run Batman tests (228+)
	cd batman_flow_engine && $(PYTEST) tests/ -q --timeout=30

test-nightwing: ## Run Nightwing tests (155+)
	cd nightwing_agent && $(PYTEST) tests/ -q --timeout=30

# ─────────────────────── LINTING ───────────────────────

lint: ## Lint both repos with ruff
	ruff check batman_flow_engine/ --select E,F,W --ignore E501
	ruff check nightwing_agent/ --select E,F,W --ignore E501
	@echo "✅ Lint complete"

typecheck: ## Type check critical modules
	mypy batman_flow_engine/core/gordon.py --ignore-missing-imports || true
	mypy batman_flow_engine/core/harvey.py --ignore-missing-imports || true
	mypy nightwing_agent/core/gordon.py --ignore-missing-imports || true

# ─────────────────────── RUNNING ───────────────────────

run: ## Start Batman + Nightwing in background
	@echo "🦇 Starting Batman..."
	cd batman_flow_engine && nohup $(PYTHON) tools/run_loop.py > storage/logs/overnight.log 2>&1 &
	@echo "🦅 Starting Nightwing..."
	cd nightwing_agent && nohup $(PYTHON) agent.py --mode paper --cycles 0 > storage/logs/overnight.log 2>&1 &
	@echo "✅ Both running. Check: ps aux | grep python"

dashboard: ## Launch Streamlit dashboard
	cd batman_flow_engine && streamlit run dashboard/app.py

briefing: ## Run morning briefing
	cd batman_flow_engine && $(PYTHON) tools/morning_briefing.py

trade: ## Open trade cockpit
	cd batman_flow_engine && $(PYTHON) tools/trade_now.py --explain

status: ## Check system status
	@echo "=== Processes ==="
	@ps aux | grep python | grep -v grep || echo "No Python processes"
	@echo ""
	@echo "=== Batman Health ==="
	@cd batman_flow_engine && $(PYTHON) -c "import json; from pathlib import Path; d=json.loads(Path('storage/latest.json').read_text()); print(f'Last run: {d[\"timestamp\"]}')" 2>/dev/null || echo "Batman not running"

stop: ## Stop Batman + Nightwing
	@pkill -f "run_loop.py" 2>/dev/null && echo "Batman stopped" || echo "Batman not running"
	@pkill -f "agent.py" 2>/dev/null && echo "Nightwing stopped" || echo "Nightwing not running"

# ─────────────────────── DOCKER ───────────────────────

docker-up: ## Start all services in Docker
	docker compose up -d
	@echo "✅ Batman Lab running. Dashboard: http://localhost:8501"

docker-down: ## Stop all Docker services
	docker compose down

docker-test: ## Run tests in Docker
	docker compose run --rm tests

docker-logs: ## Show Docker logs
	docker compose logs -f --tail=50

# ─────────────────────── GIT ───────────────────────

git-save: ## Quick commit + push (usage: make git-save m="your message")
	git add -A
	git commit -m "$(m)"
	git push origin main

git-status: ## Show git status
	git status --short

# ─────────────────────── MAINTENANCE ───────────────────────

clean: ## Clean cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cache cleaned"

install: ## Install all dependencies
	pip install -r batman_flow_engine/requirements.txt
	pip install pytest pytest-timeout ruff mypy streamlit plotly
	@echo "✅ Dependencies installed"
