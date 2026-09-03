.PHONY: install setup build-llm build query demo test clean up down

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
	python scripts/query.py "克里斯托弗·诺兰导演了哪些电影？"

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
