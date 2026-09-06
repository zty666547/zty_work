# Neo4j答辩演示

## 构建与核验

```bash
python scripts/prepare_graph.py
docker compose up -d neo4j
python scripts/build_kg.py
python scripts/check_neo4j.py
```

第一条命令不依赖Neo4j，会将两份原始JSON合并、执行Schema与端点校验，并生成带SHA-256内容指纹的`data/processed/debugpath_graph.json`。第三条命令仅删除并重建`project=DebugPath`的子图。最后一条命令只读比较本地与数据库的节点数、关系数、实体类型和关系类型。

## Browser可视化查询

打开`http://localhost:7474`后，可依次演示以下查询。

### 查看完整Schema概况

```cypher
CALL db.schema.visualization()
```

### 查看一个故障的三跳诊断网络

```cypher
MATCH path=(issue:Issue {project: 'DebugPath', name: 'PyTorch无法使用GPU'})-[*1..3]-(node)
RETURN path
LIMIT 150
```

### 查看文本证据如何连接原因与修复

```cypher
MATCH path=(source:DocumentSource)-[:SOURCE_CONTAINS_CHUNK]->(chunk:EvidenceChunk)
  -[:CHUNK_SUPPORTS_CAUSE|CHUNK_SUPPORTS_CHECK|CHUNK_SUPPORTS_REPAIR]->(target)
WHERE source.project = 'DebugPath'
RETURN path
LIMIT 100
```

### 核对节点和关系规模

```cypher
MATCH (node:Entity {project: 'DebugPath'})
OPTIONAL MATCH (node)-[relation]->(:Entity {project: 'DebugPath'})
RETURN count(DISTINCT node) AS nodes, count(relation) AS relationships
```

答辩时应说明：Streamlit默认使用同一份本地图谱以保证离线稳定，Neo4j负责持久化、可视化和结构查询；两者由内容指纹和一致性检查避免出现“两份图谱不同步”。
