PYTHON ?= python
export PYTHONPATH := src

.PHONY: install pipeline refresh report dashboard all test lint clean

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

pipeline:     ## ingest -> warehouse -> alerts -> backtest -> forecasts -> quality checks
	$(PYTHON) -m surveil

refresh:      ## same, ignoring the download cache
	$(PYTHON) -m surveil --refresh

report:       ## reports/bulletin.md + figures
	$(PYTHON) -m surveil.report

dashboard:    ## docs/index.html (served by GitHub Pages)
	$(PYTHON) -m surveil.dashboard

all: pipeline report dashboard

test:
	$(PYTHON) -m pytest -q

lint:
	ruff check .

clean:
	rm -rf data/ .pytest_cache .ruff_cache
