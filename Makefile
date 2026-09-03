.PHONY: bootstrap install dev-install run test lint fmt validate deploy deploy-dev destroy clean

VENV := .venv
BIN := $(VENV)/bin
PY := $(BIN)/python
UV := uv

$(PY):
	$(UV) venv $(VENV)

bootstrap: dev-install
	$(PY) -m ruff check app_src tests
	$(PY) -m pytest -q

install: $(PY)
	$(UV) pip install --python $(PY) -r app_src/requirements.txt

dev-install: $(PY)
	$(UV) pip install --python $(PY) -r requirements-dev.txt

run: install
	cd app_src && ../$(PY) -m flask --app app run --debug --port 8000

test: dev-install
	$(PY) -m pytest -q

lint: dev-install
	$(PY) -m ruff check app_src tests

fmt: dev-install
	$(PY) -m ruff format app_src tests

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
