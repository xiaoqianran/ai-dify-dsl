# ai-dify-dsl：三节点真实 Dify 部署与双向转换测试报告

**日期**：2026-11-15。**环境**：Nexus CNB `/workspace/wk/ai-dify-dsl`、当前自建 Dify 容器。**作用域**：只创建/更新以 `ai-dify-dsl E2E` 命名的三份独立应用，不覆盖已有 ResNet、科研或 Excel 应用。

## 结果摘要

| 测试目标 | Dify App ID | Python→DSL→Python | Dify 导入/发布 | 实际执行 | 节点日志 |
|---|---|---|---|---|---|
| `template-transform` | `a752618f-4dbc-40f4-adad-33f3a9aa0de7` | 完全一致 | 成功 | `hello dify` → `已优化：HELLO DIFY` | Start、Template、End 成功 |
| `loop-start` | `28878b4e-c9d6-4ab9-935e-92b285c34b1e` | 完全一致 | 成功 | 初始 1，每轮 +1，达到 7 后终止；输出 7 | Loop `loop_round=6`，赋值节点执行 6 次 |
| `assigner` | `1d11c335-34fe-49e5-b9ca-cf838b29a9ef` | 完全一致 | 成功 | 初始 1，每轮 +2，达到 5 后终止；输出 5 | Loop `loop_round=2`，赋值节点执行 2 次 |

上述三次运行的首轮 run IDs：`301b6ed7-2869-4609-9332-6e154ac3109a`、`00befd65-e9d0-4c64-85b2-f5c70583d31a`、`63906283-8f67-47fd-9cb0-b2ae97e06e0f`；全部 `succeeded`、HTTP 200，输出与预期相符。

随后针对模板执行更深入的 **split → `template.txt` 修改 → rebuild → YAML→Python→YAML → 更新 Dify → 发布 → 真实运行**，输出为 **`已复核：HELLO DIFY`**（run `cea16b57-d4f8-403f-9629-2cec2cdb5593`），也通过。其他两项第二轮运行分别得到 7 和 5，均正确。

## Dify 原生导出与配置差异

Dify API 服务器对三份已发布测试应用执行原生 `AppDslService.export_dsl()`，输出留存在 `integration_tests/dify_three_nodes/*.server-export.yml`。

验证结果：

- 所有输入节点 ID 与导出节点 ID 一致；**每个节点的完整 `data` 字段完全一致**。
- 所有边的配置完全一致；没有任何节点、连线、变量赋值字段或 Jinja2 模板丢失。
- Dify 可对顶层 `site`、`version`、`app`、`workflow` 等非节点部分作规范化，不能要求整份导入 YAML 与服务器导出 YAML 字节相同。
- 三份服务器导出 YAML 再次进行 `YAML → Python → YAML`，得到完整字段级一致的对象。

## 确认并修复的代码问题

1. **原始输入数据被悄悄修改**：`dify_dsl/models/dsl.py` 的 `@model_validator(mode='before')` 曾直接给传入字典 `graph["nodes"]` 赋值，将原有 `dict` 变为 `Node` 对象。真实 Dify 导出文件校验时复用了同一字典，暴露了这一副作用。已修改为**复制父层 dict 后构建带类型的节点对象**，不改变调用者的数据，新增 `test_model_validation_does_not_mutate_caller_source_dict` 回归测试。
2. **此前确认的模板数据丢失问题**：`template-transform` 在注册专用模型之后，需要在 `dify_dsl/rebuilder.py` 同时接受连字符类型。该修复已覆盖，真实 Dify 的模板修改、重建、部署和执行验证成功。
3. **真正的循环标记与赋值**：`loop-start` 并不单独生成一条 `workflow_node_executions` 记录（属于子图入口结构标记）；循环体中的 `assigner` 实际多轮执行，运行次数符合预期。不能错误地把“没有 loop-start 独立执行日志”判定成运行缺失。

## 导入警告

三份旧版 Dify 官方样例派生的工作流导入状态为 `completed-with-warnings`。重新导入模板时，`result.warnings` 实际为空，`result.error` 也为空；因此这里的状态不能被直接解释为节点运行错误。版本兼容状态或内部兼容转换仍可能参与判定。**未断言所有 Dify 版本都能无警告导入**。

## 最新回归结果

全量测试：**99 passed, 5 skipped, 0 failed**。新增回归覆盖真实服务端导出无损往返、原始字典不被修改。`git diff --check` 通过。

## 复现材料

- `integration_tests/dify_three_nodes/prepare_cases.py`：由 Dify 官方工作流样例构建隔离测试工作流。
- `convert_and_edit.py`：真实调用 CLI 完成 YAML→Python，修改模板、循环条件、累加值，再 Python→YAML→Python 对比。
- `deploy_to_dify.py`：导入并发布三个独立测试应用。
- `run_live_dify.py`：使用临时 Service API Key 执行三个工作流；最终删除临时 Key。
- `inspect_live.py`：只读查看执行日志、循环次数和发布的节点。
- `export_live.py`：Dify 原生导出已发布 DSL。
- `revise_template.py`、`update_template.py`：外置模板编辑、再发布及第二轮端到端验证。
- `tests/test_three_node_support.py`、`tests/test_comprehensive_compatibility.py`：自动回归测试。

**未覆盖**：多层 Loop/Iteration 组合、不同 Dify 版本和插件环境、并行赋值冲突、运行时权限/插件的全部场景。已部署测试 App 暂时保留，方便检查；这次没有删除生产数据，也没有自动推送 GitHub。
