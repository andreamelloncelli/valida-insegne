.PHONY: serve test

serve:
	uv run streamlit run src/silverc/Validazione.py

test:
	uv run pytest
