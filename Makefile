.PHONY: install run format lint clean

install:
	uv sync

run:
	uv run bobby

format:
	uvx ruff format src

lint:
	uvx ruff check src --fix

clean:
	rm -rf .venv
