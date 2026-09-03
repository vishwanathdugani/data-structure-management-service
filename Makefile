.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help
help:  ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV):
	python3 -m venv $(VENV)

.PHONY: install
install: $(VENV)  ## Create the virtualenv and install all dependencies.
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

.PHONY: migrate
migrate:  ## Apply database migrations.
	$(PY) manage.py migrate

.PHONY: seed
seed:  ## Load an example catalog (2 datasets, 8 data elements).
	$(PY) manage.py seed_catalog

.PHONY: run
run: migrate  ## Run the development server on http://localhost:8000.
	$(PY) manage.py runserver 0.0.0.0:8000

.PHONY: test
test:  ## Run the test suite.
	$(VENV)/bin/pytest

.PHONY: coverage
coverage:  ## Run the test suite with a coverage report.
	$(VENV)/bin/pytest --cov --cov-report=term-missing

.PHONY: lint
lint:  ## Check formatting and lint rules.
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

.PHONY: format
format:  ## Auto-format and auto-fix.
	$(VENV)/bin/ruff format .
	$(VENV)/bin/ruff check --fix .

.PHONY: migrations-check
migrations-check:  ## Fail if a model change has no migration.
	$(PY) manage.py makemigrations --check --dry-run

.PHONY: deploy-check
deploy-check:  ## Run Django's production readiness checks.
	DJANGO_DEBUG=false DJANGO_SECRET_KEY=local-check-key-not-used-to-protect-anything-x7f2q9m4z8 \
		$(PY) manage.py check --deploy --fail-level ERROR

.PHONY: schema-check
schema-check:  ## Fail if the OpenAPI schema cannot be generated cleanly.
	$(PY) manage.py spectacular --fail-on-warn --file /dev/null

.PHONY: check
check: lint migrations-check deploy-check schema-check test  ## Everything CI runs.

.PHONY: schema
schema:  ## Write the OpenAPI schema to openapi.yaml.
	$(PY) manage.py spectacular --color --file openapi.yaml

.PHONY: docker-up
docker-up:  ## Build and run the service in Docker on http://localhost:8000.
	docker compose up --build

.PHONY: docker-test
docker-test:  ## Run the test suite inside the Docker image.
	docker compose run --rm api pytest
