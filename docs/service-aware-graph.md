# 服务感知因果图谱

## 要解决的问题

第一版把“服务地址配置错误”直接连接到通用检查和修复。原因排名可能正确，但系统不知道用户实际连接的是Ollama、Neo4j还是其他服务，因此可能给出对象错误的检查命令。

第二版增加服务、端点和部署环境，让通用原因先落到具体运行上下文，再选择检查和修复。

## 新增节点

| 类型 | 当前实例 | 作用 |
| --- | --- | --- |
| `Service` | Open WebUI、Ollama | 区分客户端与目标服务 |
| `Endpoint` | Ollama `/api/tags` | 保存真正需要检查的地址和方法 |
| `DeploymentContext` | Open WebUI容器访问宿主机Ollama | 表达容器与宿主机的网络边界 |

案例还新增一个诊断问题、一个观察、一个检查、一个修复、一个风险和三个官方来源节点。

## 因果路径

```text
服务或配置连接失败
  → 服务地址配置错误
  → Open WebUI容器访问宿主机Ollama
  → Open WebUI
  → Ollama
  → Ollama /api/tags
  → 从Open WebUI容器检查Ollama端点
  → 配置OLLAMA_BASE_URL
  → 修改配置前保留原值
  → Docker、Open WebUI、Ollama官方文档
```

诊断问题“宿主机访问Ollama正常，但Open WebUI容器使用当前地址访问失败吗”连接到对应观察。该观察在“服务地址配置错误”成立时出现的条件概率为0.97，在“目标服务未启动”成立时为0.04，因此能够直接区分“服务本身不可用”和“容器地址不正确”。

## 固定演示轨迹

| 阶段 | 系统行为 | 首位原因 | 概率 |
| --- | --- | --- | ---: |
| 初始 | 图文检索并识别服务上下文 | 服务地址配置错误 | 36.7% |
| 第一次回答 | 用户确认宿主机成功、容器失败 | 服务地址配置错误 | 91.1% |
| 第二次回答 | 用户确认必需变量并未缺失 | 服务地址配置错误 | 93.3% |

第二次回答后，最高概率、领先差距和有效回答数同时达到停止条件。系统随后给出Ollama专属的`/api/tags`检查、`OLLAMA_BASE_URL`修复、低风险提示和三个官方来源。

## 每一步的实际子图

- 初始阶段：14个节点、14条边，包含故障、候选原因、证据片段、当前问题、服务、端点和部署环境；
- 第一次回答：15个节点、20条边，增加用户观察及其条件概率关系；
- 完成阶段：22个节点、34条边，只沿最终原因展开检查、修复、风险和来源路径。

这些数字描述固定案例中真正参与推理的子图，不是整张知识图谱规模。完整机器可读轨迹位于`data/demo/open_webui_ollama_trajectory.json`。

运行`python scripts/prepare_graph_v2.py`可重新校验并生成确定性的`data/processed/debugpath_graph_v2.json`；运行`python scripts/export_v2_demo.py`可重新生成相同的三阶段演示轨迹。

## 官方依据

- Docker说明容器可以通过`host.docker.internal`访问宿主机服务：<https://docs.docker.com/desktop/features/networking/networking-how-tos/>
- Open WebUI快速开始文档说明Docker部署可连接`http://host.docker.internal:11434`：<https://docs.openwebui.com/getting-started/quick-start/>
- Ollama文档将`GET /api/tags`定义为列出本地模型的API：<https://docs.ollama.com/api/tags>

## 当前边界

服务感知叠加层目前只完整覆盖Open WebUI容器访问宿主机Ollama。Neo4j、vLLM和远程服务器场景仍属于下一步扩展，不能把一个案例的结果表述为所有服务配置问题均已解决。
