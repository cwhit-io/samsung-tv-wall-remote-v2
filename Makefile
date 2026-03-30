# Makefile for Samsung TV Wall Remote v2

.PHONY: help setup activate run clean test docker-build docker-run

# Default target
help:
	@echo "Available targets:"
	@echo "  setup       - Create virtual environment and install dependencies"
	@echo "  activate    - Activate the virtual environment (prints command)"
	@echo "  run         - Run the FastAPI application"
	@echo "  clean       - Remove virtual environment and cache files"
	@echo "  test        - Run tests (if any)"
	@echo "  docker-build - Build Docker image"
	@echo "  docker-run   - Run the application in Docker"

# Setup virtual environment and install dependencies
setup:
	@echo "Creating virtual environment..."
	python3 -m venv venv
	@echo "Activating virtual environment and installing dependencies..."
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	@echo "Setup complete. Use 'make activate' to activate the environment."

# Activate virtual environment (prints the command since Make can't persist shell state)
activate:
	@echo "To activate the virtual environment, run:"
	@echo "source ./venv/bin/activate"

# Run the FastAPI application
run:
	@echo "Running FastAPI application..."
	./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8009 --reload

# Clean up virtual environment and cache files
clean:
	@echo "Removing virtual environment and cache files..."
	rm -rf venv
	rm -rf __pycache__
	rm -rf app/__pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	@echo "Clean complete."

# Run tests (placeholder - add actual test commands if you have tests)
test:
	@echo "Running tests..."
	./venv/bin/python -m pytest 2>/dev/null || echo "No tests found or pytest not installed."

# Build Docker image
docker-build:
	@echo "Building Docker image..."
	DOCKER_BUILDKIT=0 docker build -t samsung-tv-remote .

# Run the application with Docker Compose
compose-up:
	@echo "Starting application with Docker Compose..."
	docker-compose up --build

# Stop Docker Compose
compose-down:
	@echo "Stopping Docker Compose..."
	docker-compose down