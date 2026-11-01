.PHONY: install train test run load capacity

install:
	pip install -r requirements.txt

train:
	python -m ml.train

test: train
	python -m pytest -q

run: train
	API_KEYS=dev-key uvicorn app.main:app --reload

load:
	python scripts/loadtest.py --key dev-key --concurrency 32 --duration 15

capacity:
	python scripts/capacity_sim.py
