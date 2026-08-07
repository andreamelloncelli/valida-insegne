.PHONY: serve test docker-build docker-run deploy

serve:
	uv run streamlit run src/silverc/Validazione.py

test:
	uv run pytest

docker-build:
	docker build -t silverc .

docker-run: docker-build
	docker run --rm -e PORT=8501 -p 8501:8501 silverc

deploy:
	railway up
