.PHONY: install dev-install run test lint fmt validate deploy deploy-dev destroy clean

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install:
	python3 -m venv $(VENV)
	$(PIP) install -q -r app_src/requirements.txt

dev-install:
	python3 -m venv $(VENV)
	$(PIP) install -q -r requirements-dev.txt

run:
	cd app_src && ../$(PY) -m flask --app app run --debug --port 8000

test: dev-install
	$(VENV)/bin/pytest -q

lint: dev-install
	$(VENV)/bin/ruff check app_src tests

fmt: dev-install
	$(VENV)/bin/ruff format app_src tests

validate:
	./scripts/validate.sh prod

deploy:
	./scripts/deploy.sh prod

deploy-dev:
	./scripts/deploy.sh dev

destroy:
	databricks bundle destroy -t prod

clean:
	rm -rf $(VENV) app_src/__pycache__ tests/__pycache__ .pytest_cache .ruff_cache
