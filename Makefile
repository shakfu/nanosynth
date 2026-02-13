.PHONY: build build-scsynth clean help install-scsynth \
		lint format typecheck qa test
.DEFAULT_GOAL := help

help: ## This help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

build: ## Build wheel via uv
	@uv build

build-scsynth: ## Build wheel with embedded libscsynth
	@uv build \
		-C cmake.define.NANOSYNTH_EMBED_SCSYNTH=ON

install-scsynth: ## Install editable with embedded libscsynth
	@uv pip install -e . \
		-C cmake.define.NANOSYNTH_EMBED_SCSYNTH=ON

test: ## Run tests via uv
	@uv run pytest tests/

lint:
	@uv run ruff check --fix src/ tests/ demos/

format:
	@uv run ruff format src/ tests/ demos/

typecheck:
	@uv run mypy --strict src/

qa: test lint typecheck format

clean: ## Clean-out transitory files
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ __pycache__
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
