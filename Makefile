.PHONY: all dev sync remake build sdist check clean demos demos-supernova help \
		lint format typecheck qa test publish publish-test reset \
		docs docs-serve docs-deploy bench bench-check bench-baseline
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
	@uv run pytest tests/  --cov=nanosynth --cov-report term-missing:skip-covered

lint:
	@uv run ruff check --fix src/ tests/ demos/ benchmarks/

format:
	@uv run ruff format src/ tests/ demos/ benchmarks/

typecheck:
	@uv run mypy --strict src/

qa: lint test typecheck format

bench: ## Run performance benchmarks (writes benchmarks/last.json)
	@uv run pytest benchmarks/ --benchmark-disable-gc --benchmark-json=benchmarks/last.json

bench-check: ## Run benchmarks; fail if >25% slower than benchmarks/baseline.json (same machine only)
	@uv run pytest benchmarks/ --benchmark-disable-gc --benchmark-json=benchmarks/last.json -q
	@uv run python benchmarks/check_regression.py benchmarks/baseline.json benchmarks/last.json --threshold 25

bench-baseline: ## Regenerate the committed baseline (run on a quiet machine, then commit)
	@uv run pytest benchmarks/ --benchmark-disable-gc --benchmark-json=benchmarks/baseline.json

demos: ## Run scsynth demo scripts sequentially
	@for f in demos/scsynth/*.py; do echo "--- $$f ---"; uv run python "$$f"; done

demos-supernova: ## Run supernova demo scripts sequentially
	@for f in demos/supernova/*.py; do echo "--- $$f ---"; uv run python "$$f"; done

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
