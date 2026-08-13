.PHONY: help install scrape rebuild dev build preview clean

VENV       := .venv
PYTHON     := $(VENV)/bin/python
SITE_DIR   := site

help:
	@echo "make install  - create venv + install python/npm deps"
	@echo "make scrape   - scrape all sources.yaml sources into data/json + markdown/"
	@echo "make rebuild  - rebuild markdown/ from data/json/ without re-fetching"
	@echo "make dev      - scrape, then run the Astro site at http://localhost:4321"
	@echo "make build    - scrape, then build the static site into site/dist/"
	@echo "make preview  - preview the last `make build` output"
	@echo "make clean    - remove venv, node_modules, and site/dist"

# --- python side ---------------------------------------------------------
# Use a stamp file (not $(VENV)/bin/python) as the target: make stats through
# symlinks to the underlying interpreter, whose mtime reflects when Python
# was built, not when this venv was created — that made the venv look stale
# on every run.

$(VENV)/.installed: requirements.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements.txt
	touch $(VENV)/.installed

install: $(VENV)/.installed $(SITE_DIR)/node_modules

scrape: $(VENV)/.installed
	$(PYTHON) -m scraper.core

rebuild: $(VENV)/.installed
	$(PYTHON) -m scraper.core --rebuild-only

# --- site side -------------------------------------------------------------

$(SITE_DIR)/node_modules: $(SITE_DIR)/package.json
	cd $(SITE_DIR) && npm install

dev: $(SITE_DIR)/node_modules scrape
	cd $(SITE_DIR) && npm run dev

build: $(SITE_DIR)/node_modules scrape
	cd $(SITE_DIR) && npm run build

preview: $(SITE_DIR)/node_modules
	cd $(SITE_DIR) && npm run preview

clean:
	rm -rf $(VENV) $(SITE_DIR)/node_modules $(SITE_DIR)/dist
