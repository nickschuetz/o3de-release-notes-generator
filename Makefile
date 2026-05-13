# Common development targets for o3de_release_notes_generator.
# All targets are no-install: they invoke `python -m <tool>` directly so they
# work on a fresh clone without `pip install`. Optional tools (ruff, mypy)
# print a hint and exit cleanly if not installed, rather than failing.

.PHONY: help test sbom lint typecheck dry-run-help all check clean

PYTHON ?= python

help:
	@echo "Targets:"
	@echo "  test         Run pytest"
	@echo "  sbom         Regenerate sbom.cdx.json"
	@echo "  lint         Run ruff (skipped if not installed)"
	@echo "  typecheck    Run mypy (skipped if not installed)"
	@echo "  check        test + lint + typecheck"
	@echo "  clean        Remove __pycache__, .pytest_cache, *.pyc"

test:
	$(PYTHON) -m pytest tests/ -v

sbom:
	$(PYTHON) generate_sbom.py

lint:
	@if $(PYTHON) -m ruff --version >/dev/null 2>&1; then \
		$(PYTHON) -m ruff check release_notes.py generate_sbom.py tests/; \
	else \
		echo "ruff not installed — skipping (install with: pip install ruff)"; \
	fi

typecheck:
	@if $(PYTHON) -m mypy --version >/dev/null 2>&1; then \
		$(PYTHON) -m mypy release_notes.py generate_sbom.py; \
	else \
		echo "mypy not installed — skipping (install with: pip install mypy)"; \
	fi

check: test lint typecheck

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -name '*.pyc' -delete

all: check sbom
