# PraisonAI Makefile
# This file provides common build and development tasks

.PHONY: help clean install test lint

help:
	@echo "Available targets:"
	@echo "  help     - Show this help message"
	@echo "  clean    - Clean build artifacts"
	@echo "  install  - Install dependencies"
	@echo "  test     - Run tests"
	@echo "  lint     - Run linting"

clean:
	@echo "Cleaning build artifacts..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +

install:
	@echo "Installing dependencies..."
	pip install -e .

test:
	@echo "Running tests..."
	python -m pytest

lint:
	@echo "Running linting..."
	ruff check .

# This issue was autonomously solved by PraisonAI Issue Triager