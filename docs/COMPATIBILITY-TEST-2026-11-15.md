# ai-dify-dsl：综合兼容性测试（2026-11-15）

## 环境和测试出处

- 工作区：Nexus CNB `/workspace/wk/ai-dify-dsl`。
- 测试基线：CNB 当时安装的 Dify API 容器 `/app/api/tests/fixtures/workflow/*.yml`，共 25 个 YAML；暂时复制到 `/tmp/dify-node-fixtures`，未复制到 Git 仓库，保持上游示例文件来源不变。
- 同时读取 CNB 当前三个真实业务 DSL：Excel 质量检查、科研论文工作流、ResNet 专用科研工作流。
- 新增可重复自动测试：`tests/test_comprehensive_compatibility.py`。
- 完整测试命令：`.venv/bin/python -m pytest -q`。
- **结果：85 passed, 5 skipped，0 failed**。5 skipped 为原项目依赖不可用私人路径的旧测试，并非本轮新增失败。

## 已实际证明的范围

| 测试层级 | 测试对象 | 结果 | 证明范围 |
|---|---|---|---|
| Dify 官方实物案例 | 25 个工作流、114 个节点实例、16 种实际节点字符串 | 25/25 YAML→Python→YAML、拆分重建无损 | 字段/结构数据保真 |
| 完整注册表压力测试 | 35 个注册名称 + 3 个新/未知名称，37 个连接，未知嵌套字段 | 通过 | 已知、别名、未来未知字段的保留 |
| 真实业务案例 | Excel、科研报告、ResNet 共 3 个 DSL | 通过 | 复杂真实业务配置保真 |
| 结构验证 | 25 个官方样例 | 25/25 通过 | `ai-dify-dsl.validator` 基础结构校验 |
| 双向编辑 | 代码节点外置文件、复杂 LLM 参数 `max_tokens` 和 YAML ↔ Python 同步 | 通过 | 双向修改传播，防止默默覆盖 |
| 原有测试 | 原有 29 个通过、5 个跳过 | 未出现回归 | 核心现有功能 |

注意：**这只是数据级别和本地结构验证**。它不表示全部节点已经逐个导入、运行并在 Dify 服务器中验证了业务语义。现有 ResNet/科研流程曾成功在 Dify 运行，但不能据此推导 Agent、MCP、Webhook、Loop 等全部真实执行通过。

## 本轮发现的真实缺口

当前注册表有 35 个字符串键，映射至 **24 个不同的类型模型**（有多个连字符/下划线别名）。Dify 随安装版本提供的 25 份工作流共涉及 16 种节点字符串，其中 **4 种没有匹配专用模型**：

| Dify 原生节点字符串 | ai-dify-dsl 当前行为 | 待处理 |
|---|---|---|
| `template-transform` | 经通用 NodeData 无损保存 | 将标准连字符名称注册到 TemplateTransformNodeData |
| `loop-start` | 经通用 NodeData 无损保存 | 增加循环起始节点模型和相关字段 |
| `assigner` | 经通用 NodeData 无损保存 | 建立与当前变量赋值配置兼容的模型 |
| `knowledge-retrieval-v2` | 经通用 NodeData 无损保存 | 对新检索节点的 query、dataset、检索参数建模与校验 |

**没有证据支持“全部 Dify 节点实际运行通过”或“已支持任意 Python 业务代码自动转 Dify 图”。** 以下仍需验证：

1. 上述 4 种节点的专用类型 Schema，以及新版本 Dify 的其余节点类型。
2. Agent、Tool、MCP、Webhook/Schedule/Plugin Trigger 等工具与凭证依赖的运行级兼容性。
3. 多层 Loop/Iteration 作用域、子图边连接、异常分支和变量绑定语义。
4. Dify 不同版本的 import、publish、run 完整兼容矩阵。
5. 在线工作流的同步与自动更新，当前双向同步仅发生在本地 Python 声明和 YAML 之间。

## 重跑

在 CNB 上：

```bash
cd /workspace/wk/ai-dify-dsl
# 如原容器已存在，可以更新其真实工作流示例快照
mkdir -p /tmp/dify-node-fixtures
docker cp dify-api-1:/app/api/tests/fixtures/workflow/. /tmp/dify-node-fixtures/
.venv/bin/python -m pytest tests/test_comprehensive_compatibility.py -q
.venv/bin/python -m pytest -q
```

测试不调用生产 Dify 的修改 API，也不会覆盖当前线上科研工作流或知识库；没有创建生产应用。运行级别的兼容性矩阵应在独立测试应用内进行，而不应直接污染已有业务。

## 三节点补齐结果（同日后续实现）

之前列出的 `template-transform`、`loop-start`、`assigner` **现在均已注册专用类型**。此文前面的四节点缺口表为修复之前的历史基线。

- `template-transform`：映射至 `TemplateTransformNodeData`。`splitter.py` 会把模板拆为 `template.txt`；修复 `rebuilder.py` 对连字符类型的重建分支，避免模板静默丢失。旧版通用 `config.yaml` 拆分目录仍能读取。
- `loop-start`：新增 `LoopStartNodeData`，保留循环 `parentId`、`isInLoop` 和未来扩展字段。
- `assigner`：映射至现有 `VariableAssignerNodeData`，`items`、`variable_selector`、`operation`、`write_mode` 等原始数据保持无损；支持通过拆分文件编辑变量赋值。
- `tests/test_three_node_support.py`：10 个新增专项测试，通过 Dify 原样例检查类型、模板编辑、嵌套关系、变量赋值、旧版拆分兼容。
- **最新全量结果：95 passed, 5 skipped, 0 failed**。当前 Dify 25 份官方工作流包含 16 种节点字符串，未注册的只剩 `knowledge-retrieval-v2` 一种（按用户要求暂不处理）。

本次完成的是专用类型支持、数据保真、编辑与恢复测试；不等于已经在 Dify 中单独部署并执行所有节点。
