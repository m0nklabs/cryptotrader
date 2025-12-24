.PHONY: help install install-dev lint format test test-cov run docker-up docker-down frontend clean

# Default target
help:
	@echo "cryptotrader - Available commands:"
	@echo ""
	@echo "  make install       Install production dependencies"
	@echo "  make install-dev   Install all dependencies (including dev)"
	@echo "  make lint          Run ruff linter"
	@echo "  make format        Format code with ruff"
	@echo "  make test          Run tests"
	@echo "  make test-cov      Run tests with coverage"
	@echo "  make run           Start backend API"
	@echo "  make frontend      Start frontend dev server"
	@echo "  make docker-up     Start docker-compose services"
	@echo "  make docker-down   Stop docker-compose services"
	@echo "  make clean         Remove caches and build artifacts"

# Python setup
install:
	pip install --upgrade pip
	pip install -r requirements.txt

install-dev: install
	pip install -r requirements-dev.txt
	pre-commit install

# Code quality
lint:
	ruff check .

format:
	ruff check --fix .
	ruff format .

# Testing
test:
	pytest -q

test-cov:
	pytest --cov=core --cov=api --cov-report=term-missing --cov-report=html

# Run services
run:
	python -m api.main

frontend:
	cd frontend && npm run dev

# Docker
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# Database
db-migrate:
	alembic upgrade head

db-shell:
	docker-compose exec db psql -U postgres -d cryptotrader

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
