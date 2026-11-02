PYTHON ?= python3.11
VENV := .venv
BIN := $(VENV)/bin

.PHONY: setup run test clean

setup:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -r requirements.txt

run:
	$(BIN)/python -m src.pipeline

test:
	$(BIN)/python -m pytest -q

clean:
	rm -rf data output .pytest_cache
