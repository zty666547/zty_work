.PHONY: install setup inspect prepare offline-demo evaluate ablation build check-neo4j query demo app test up down

install:
	pip install -r requirements.txt

setup:
	cp -n .env.example .env || true
	@echo "已生成 .env；如需联网解释，请只在本地填写密钥。"

inspect:
	python scripts/inspect_data.py

prepare:
	python scripts/prepare_graph.py

offline-demo:
	python scripts/offline_demo.py

evaluate:
	python scripts/evaluate_diagnosis.py

ablation:
	python scripts/evaluate_ablation.py

test:
	pytest -q

app:
	streamlit run app.py

query:
	python scripts/query.py "ModuleNotFoundError: No module named pandas"

demo:
	python scripts/run_demo.py

build:
	python scripts/build_kg.py

check-neo4j:
	python scripts/check_neo4j.py

up:
	docker compose up -d neo4j

down:
	docker compose down
