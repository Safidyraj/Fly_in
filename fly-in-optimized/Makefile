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
	python3 main.py maps/easy/01_linear_path.txt

run-visual:
	python3 main.py maps/easy/01_linear_path.txt --visual pygame

debug:
	python3 -m pdb main.py maps/easy/01_linear_path.txt

benchmark:
	@for f in maps/easy/*.txt maps/medium/*.txt maps/hard/*.txt maps/challenger/*.txt; do \
		echo "=== $$f ==="; \
		python3 validate_run.py "$$f"; \
	done

clean:
	find . -type d \( -name "__pycache__" -o -name ".mypy_cache" -o -name ".pytest_cache" \) -exec rm -rf {} + 2>/dev/null; true

lint:
	flake8 . --exclude='.venv,flyin,__pycache__' --extend-ignore='E126,E127,E128,E125,E501,D100,D101,D102,D103,D104,D105,D106,D107,D200,D202,D205,D209,D301,D400,D401,D403,W503,F401'
	mypy . --exclude '^(flyin|\.venv)/' --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs --disable-error-code='assignment,attr-defined,call-arg,no-any-return,no-untyped-def,str-unpack,var-annotated'

lint-strict:
	flake8 . --exclude='.venv,flyin,__pycache__' --extend-ignore='E126,E127,E128,E125,E501,D100,D101,D102,D103,D104,D105,D106,D107,D200,D202,D205,D209,D301,D400,D401,D403,W503,F401'
	mypy . --exclude '^(flyin|\.venv)/' --strict --disable-error-code='assignment,attr-defined,call-arg,no-any-return,no-untyped-def,str-unpack,var-annotated'
