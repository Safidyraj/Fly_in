export PYGAME_HIDE_SUPPORT_PROMPT = 1
VENV = flyin
PYTHON = $(VENV)/bin/python3
PIP = $(VENV)/bin/pip

$(VENV):
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PIP) install rich
	$(PIP) install pygame
	$(PIP) install colorama

install: $(VENV)

run:
	$(PYTHON) main.py maps/easy/01_linear_path.txt

run-visual:
	$(PYTHON) main.py maps/easy/01_linear_path.txt --visual pygame

make-visual: run-visual

visual: run-visual

debug:
	$(PYTHON) -m pdb main.py maps/easy/01_linear_path.txt

benchmark:
	@for f in maps/easy/*.txt maps/medium/*.txt maps/hard/*.txt maps/challenger/*.txt; do \
		echo "=== $$f ==="; \
		$(PYTHON) validate_run.py "$$f"; \
	done

clean:
	find . -type d \( -name "__pycache__" -o -name ".mypy_cache" -o -name ".pytest_cache" \) -exec rm -rf {} + 2>/dev/null; true

lint:
	flake8 . --exclude='.venv,flyin,__pycache__'
	mypy . --exclude '^(flyin|\.venv)/' --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	flake8 . --exclude='.venv,flyin,__pycache__'
	mypy . --exclude '^(flyin|\.venv)/' --strict --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs
