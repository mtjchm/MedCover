.PHONY: e2e e2e-down test

## Run E2E browser tests (Playwright in Docker)
e2e:
	docker compose -f docker-compose.e2e.yml up --build --abort-on-container-exit --exit-code-from e2e
	docker compose -f docker-compose.e2e.yml down -v

## Tear down E2E containers (cleanup after failure)
e2e-down:
	docker compose -f docker-compose.e2e.yml down -v

## Run unit/integration tests
test:
	pytest tests/ -q
