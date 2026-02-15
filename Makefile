.PHONY: all dev sync remake build sdist check clean demos help \
		lint format typecheck qa test publish publish-test reset \
		docs docs-serve docs-deploy
# .DEFAULT_GOAL := help

all: dev

help: ## This help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

dev:
	@uv sync
	@uv pip install -e .

sync:
	@uv sync --reinstall-package nanosynth

remake: reset sync qa

build: ## Build wheel (incremental via build cache)
	@rm -rf dist/
	@uv build --wheel --no-build-isolation
	@case $$(uname -s) in \
		Darwin) uv run delocate-wheel -v dist/*.whl ;; \
		Linux)  uv run auditwheel repair -w dist/ dist/*.whl ;; \
	esac
	@uv run twine check dist/*

sdist: ## Build source distribution
	@uv build --sdist

test: ## Run tests via uv
	@uv run pytest tests/

lint:
	@uv run ruff check --fix src/ tests/ demos/

format:
	@uv run ruff format src/ tests/ demos/

typecheck:
	@uv run mypy --strict src/

qa: test lint typecheck format

demos: ## Run demo scripts sequentially
	@for f in demos/*.py; do echo "--- $$f ---"; uv run python "$$f"; done

check: ## Validate dist/ with twine
	@uv run twine check dist/*

publish: check ## Upload dist/ to PyPI
	@uv run twine upload dist/*

publish-test: check ## Upload dist/ to TestPyPI
	@uv run twine upload --repository testpypi dist/*

docs: ## Build documentation site
	@uv run mkdocs build

docs-serve: ## Serve docs locally with live reload
	@uv run mkdocs serve

docs-deploy: ## Deploy docs to GitHub Pages
	@uv run mkdocs gh-deploy --force

clean: ## Clean transitory files (preserves build cache)
	@rm -rf dist/ *.egg-info/ .pytest_cache/ __pycache__
	@find . -name '*.pyc' -delete
	@find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

reset: clean ## Clean everything including build cache
	@rm -rf build/
