.PHONY: install setup inspect offline-demo evaluate build-llm build query demo app test clean up down

# 依赖安装
install:
	pip install -r requirements.txt

# 初始化环境（复制环境变量模板）
setup:
	cp -n .env.example .env || true
	@echo "已生成 .env，请填入 DEEPSEEK_API_KEY 与 Neo4j 密码。"

# 用结构化数据建图（无需 LLM）
build:
	python scripts/build_kg.py

# 用 DeepSeek 抽取实体/关系后建图（需在 .env 中设置 EXTRACTION_MODE=llm）
build-llm:
	EXTRACTION_MODE=llm python scripts/build_kg.py

# 交互式问答
query:
	python scripts/query.py "知识工程是多少学分，建议在哪个学期修读？"

# 一键演示（建图 + 问答）
demo:
	python scripts/run_demo.py

# 运行测试
test:
	pytest -q

# 启动 / 停止 Neo4j 容器
up:
	docker compose up -d neo4j

down:
	docker compose down

clean:
	rm -rf data/processed/* data/kg/*.csv __pycache__
# 离线检查数据与 Schema（无需 Neo4j / DeepSeek）
inspect:
	python scripts/inspect_data.py

# 无需 Neo4j / DeepSeek 的检索演示
offline-demo:
	python scripts/offline_demo.py

# 离线检索评测（无需 Neo4j / DeepSeek）
evaluate:
	python scripts/evaluate_retrieval.py

# 启动学生端网页
app:
	streamlit run app.py
