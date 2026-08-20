.PHONY: install run enable-autostart disable-autostart format lint clean

AUTOSTART_DIR := $(HOME)/.config/autostart
DESKTOP_FILE  := $(AUTOSTART_DIR)/bobby.desktop

install:
	uv sync

run:
	uv run bobby

enable-autostart: install
	@mkdir -p $(AUTOSTART_DIR)
	@sed "s|PROJECT_DIR|$(CURDIR)|g" bobby.desktop > $(DESKTOP_FILE)
	@echo "bobby will now start automatically with your desktop session."

disable-autostart:
	@rm -f $(DESKTOP_FILE)
	@echo "bobby autostart removed."

format:
	uvx ruff format src

lint:
	uvx ruff check src --fix

clean:
	rm -rf .venv
