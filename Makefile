PYTHON ?= python3.11
VENV := .venv
BIN := $(VENV)/bin

.PHONY: setup run test app pg-up pg-down pg-run clean

setup:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -r requirements.txt

run:
	$(BIN)/python -m src.pipeline

app:
	$(BIN)/pip install --quiet -r requirements-app.txt
	$(BIN)/streamlit run app/streamlit_app.py

pg-up:
	docker compose up -d --wait postgres

pg-down:
	docker compose down -v

# Same pipeline, plus publish the star schema to PostgreSQL and reconcile against DuckDB
pg-run:
	PG_DSN=postgresql://warehouse:warehouse@localhost:5433/warehouse $(BIN)/python -m src.pipeline

test:
	$(BIN)/python -m pytest -q

clean:
	rm -rf data output .pytest_cache
