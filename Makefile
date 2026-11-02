PYTHON ?= python3.11
VENV := .venv
BIN := $(VENV)/bin

.PHONY: setup run test app clean

setup:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -r requirements.txt

run:
	$(BIN)/python -m src.pipeline

app:
	$(BIN)/pip install --quiet -r requirements-app.txt
	$(BIN)/streamlit run app/streamlit_app.py

test:
	$(BIN)/python -m pytest -q

clean:
	rm -rf data output .pytest_cache
