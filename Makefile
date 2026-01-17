.PHONY: install run clean setup test

# Install dependencies
install:
	pip install -r requirements.txt

# Setup environment
setup: install
	@echo "Setup complete! API keys are configured in config.py"

# Run the application
run:
	python app.py

# Clean generated files
clean:
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache
	rm -f *.csv

# Test (if you add tests later)
test:
	@echo "Tests not implemented yet"

# Format code
format:
	black *.py || echo "black not installed, skipping"
	isort *.py || echo "isort not installed, skipping"

# Help
help:
	@echo "Available commands:"
	@echo "  make install  - Install Python dependencies"
	@echo "  make setup    - Setup the project"
	@echo "  make run      - Run the Flask application"
	@echo "  make clean    - Clean generated files"
	@echo "  make format   - Format Python code"





