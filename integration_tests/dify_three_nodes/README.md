# 三节点：Python↔DSL↔Dify 实际集成测试

## 目标和边界

针对 `template-transform`、`loop-start`、`assigner`，分别验证**独立测试工作流**的 YAML→Python、Python 编辑→YAML、导入→发布→Dify Service API 实际运行、Dify 再次导出→Python→YAML，以及拆分编辑模板→重建→重新发布→重跑。

采用 Dify API 容器自带的 `/app/api/tests/fixtures/workflow` 原始官方 DSL 作为只读数据源。仓库中的 `*.source.yml` 为派生测试工作流，`*.server-export.yml` 为 Dify 实际导出的已发布工作流，请保留其来源，不要把它当作源码原件覆盖。

## 实测记录（CNB，2026-11-15）

| 应用 | 测试 App ID | 初次执行结果 | 第二轮结果 |
|---|---|---|---|
| template | `a752618f-4dbc-40f4-adad-33f3a9aa0de7` | `已优化：HELLO DIFY` | `已复核：HELLO DIFY` |
| loop-start | `28878b4e-c9d6-4ab9-935e-92b285c34b1e` | `num=7`，循环体 6 次 | `num=7` |
| assigner | `1d11c335-34fe-49e5-b9ca-cf838b29a9ef` | `num=5`，赋值节点 2 次 | `num=5` |

- 三个 App 初次导入均 `completed-with-warnings`，成功发布且正常运行。具体导入警告尚未逐项排除，不把成功运行等同于零警告。
- 检查数据库 `workflow_node_executions`：`loop-start` 是结构标记，无独立执行记录，但执行图中存在该节点且循环体执行 6 次；`assigner` 实际写入了循环变量。
- Dify 重新导出的原始**节点配置和边配置**与导入版本完全一致，其他顶层信息（版本、站点元信息等）可能由 Dify 正常重写。
- 导出的三份服务端 YAML 再次完成了双向无损转换。
- 通过 `template.txt` 编辑后重建、Python→DSL、更新隔离 App 和实际调用，返回 `已复核：HELLO DIFY`。
- 修复 `dify_dsl/models/dsl.py` 原始数据意外被 `model_validate()` 就地修改的缺陷，并加入回归测试。该问题是在真实 Dify 导出复用同一字典时发现的，并非 Dify 服务器运行故障。

## 在同一 CNB 上复跑

```bash
cd /workspace/wk/ai-dify-dsl
mkdir -p /tmp/dify-node-fixtures
docker cp dify-api-1:/app/api/tests/fixtures/workflow/. /tmp/dify-node-fixtures/
.venv/bin/python integration_tests/dify_three_nodes/prepare_cases.py
.venv/bin/python integration_tests/dify_three_nodes/convert_and_edit.py

for kind in template loop assigner; do
  docker cp integration_tests/dify_three_nodes/$kind.deploy.yml dify-api-1:/tmp/dify-e2e-$kind.yml
done
docker cp integration_tests/dify_three_nodes/deploy_to_dify.py dify-api-1:/tmp/dify-e2e-deploy.py
docker exec dify-api-1 sh -lc 'PYTHONPATH=/app/api /app/api/.venv/bin/python /tmp/dify-e2e-deploy.py'

# 检查真实 Dify 节点行为之前，执行第二轮模板编辑与发布
.venv/bin/python integration_tests/dify_three_nodes/revise_template.py
docker cp integration_tests/dify_three_nodes/template.revised.deploy.yml dify-api-1:/tmp/dify-e2e-template-revised.yml
docker cp integration_tests/dify_three_nodes/update_template.py dify-api-1:/tmp/dify-e2e-template-update.py
docker exec dify-api-1 sh -lc 'PYTHONPATH=/app/api /app/api/.venv/bin/python /tmp/dify-e2e-template-update.py'

docker cp integration_tests/dify_three_nodes/run_live_dify.py dify-api-1:/tmp/dify-e2e-run.py
docker exec dify-api-1 sh -lc 'PYTHONPATH=/app/api /app/api/.venv/bin/python /tmp/dify-e2e-run.py'

.venv/bin/python -m pytest -q
```

脚本中的 App ID 是此次隔离测试 App 的固定值。测试 API Key 由 Dify 在执行时临时生成，`finally` 内删除。不能在其他 Dify 租户直接复用这些 ID；应重新创建测试 App 并更新配置。脚本没有主动清理 Dify 测试 App，以便后续检查发布状态；三个 App 可在确认不再需要后单独删除。

## 本次未覆盖

Loop 的复杂多层嵌套、break 之外的异常终止、动态文件/列表变量赋值、插件依赖、并发发布冲突、所有版本的 Dify 导入兼容性，仍需专门验证；这次只证明上述真实样例的指定行为。
