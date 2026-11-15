"""安全的 Dify DSL ⇄ 声明式 Python 表示，以及冲突保护双向同步。"""

import ast
import hashlib
import json
import pprint
from pathlib import Path
from typing import Any

from dify_dsl.generator import generate_dsl
from dify_dsl.models.dsl import DifyDSL
from dify_dsl.parser import parse_dsl


class SyncConflictError(ValueError):
    """两侧发生不同修改或同步目标不安全时抛出。"""


def _plain(model: DifyDSL) -> dict[str, Any]:
    return model.model_dump(mode="python", serialize_as_any=True, exclude_unset=True)


def _signature(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_python_source(dsl: DifyDSL) -> str:
    """生成可编辑、无需执行便能反解析的 Python 数据声明。"""
    value = pprint.pformat(_plain(dsl), width=100, sort_dicts=False)
    return '# Dify Workflow Python 数据声明；修改 WORKFLOW_DSL 后可同步回 YAML。\nWORKFLOW_DSL = ' + value + '\n'


def parse_python_source(source: str) -> DifyDSL:
    """使用 AST 字面量解析，禁止执行任意 Python 代码。"""
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
        raise ValueError("Python 文件只能包含一个 WORKFLOW_DSL 字面量赋值")
    assignment = tree.body[0]
    if len(assignment.targets) != 1 or not isinstance(assignment.targets[0], ast.Name) or assignment.targets[0].id != 'WORKFLOW_DSL':
        raise ValueError("需要 WORKFLOW_DSL = {...} 数据声明")
    try:
        value = ast.literal_eval(assignment.value)
    except (ValueError, TypeError, RecursionError, MemoryError, SyntaxError) as error:
        raise ValueError("WORKFLOW_DSL 只能使用 Python 字面量（禁止执行代码）") from error
    if not isinstance(value, dict):
        raise ValueError("WORKFLOW_DSL 必须是字典")
    return DifyDSL.model_validate(value)


def python_to_dsl(source_file: str | Path) -> DifyDSL:
    return parse_python_source(Path(source_file).read_text(encoding='utf-8'))


def dsl_to_python(source_file: str | Path, output_file: str | Path, *, overwrite: bool = False) -> Path:
    destination = Path(output_file)
    if destination.exists() and not overwrite:
        raise SyncConflictError(f"文件已存在，拒绝覆盖: {destination}")
    value = to_python_source(parse_dsl(source_file))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(value, encoding='utf-8')
    return destination


def python_to_yaml(source_file: str | Path, output_file: str | Path, *, overwrite: bool = False) -> Path:
    destination = Path(output_file)
    if destination.exists() and not overwrite:
        raise SyncConflictError(f"文件已存在，拒绝覆盖: {destination}")
    dsl = python_to_dsl(source_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    generate_dsl(dsl, destination)
    return destination


def sync_pair(yaml_file: str | Path, python_file: str | Path, *, state_file: str | Path | None = None) -> str:
    """双向同步：只传播单侧修改；两侧冲突时保留原文件并报错。"""
    yaml_path, python_path = Path(yaml_file), Path(python_file)
    state_path = Path(state_file) if state_file else yaml_path.with_name(yaml_path.name + '.sync.json')
    has_yaml, has_python = yaml_path.is_file(), python_path.is_file()
    if not has_yaml and not has_python:
        raise FileNotFoundError("两侧文件均不存在")

    yaml_data = _plain(parse_dsl(yaml_path)) if has_yaml else None
    python_data = _plain(python_to_dsl(python_path)) if has_python else None
    yaml_hash = _signature(yaml_data) if yaml_data is not None else None
    python_hash = _signature(python_data) if python_data is not None else None

    prior = None
    if state_path.is_file():
        stored = json.loads(state_path.read_text(encoding='utf-8'))
        if stored.get('version') != 1:
            raise SyncConflictError("未知的同步状态文件格式")
        if stored.get('yaml_path') != str(yaml_path.resolve()) or stored.get('python_path') != str(python_path.resolve()):
            raise SyncConflictError("同步状态文件属于其他文件对")
        prior = stored['fingerprint']

    action = 'unchanged'
    if not has_python:
        if prior and yaml_hash != prior:
            raise SyncConflictError("Python 文件丢失，且 YAML 已修改；无法安全恢复")
        dsl_to_python(yaml_path, python_path)
        action = 'yaml-to-python'
    elif not has_yaml:
        if prior and python_hash != prior:
            raise SyncConflictError("YAML 文件丢失，且 Python 已修改；无法安全恢复")
        python_to_yaml(python_path, yaml_path)
        action = 'python-to-yaml'
    elif yaml_hash != python_hash:
        if prior is None:
            raise SyncConflictError("首次同步时两侧内容不同：请明确选择权威源，不自动覆盖")
        if yaml_hash == prior and python_hash != prior:
            python_to_yaml(python_path, yaml_path, overwrite=True)
            action = 'python-to-yaml'
        elif python_hash == prior and yaml_hash != prior:
            dsl_to_python(yaml_path, python_path, overwrite=True)
            action = 'yaml-to-python'
        else:
            raise SyncConflictError("两侧都发生不一致修改：同步冲突，未覆盖任何文件")

    final = _signature(_plain(parse_dsl(yaml_path)))
    if final != _signature(_plain(python_to_dsl(python_path))):
        raise SyncConflictError("写入后校验失败")
    state = {'version': 1, 'yaml_path': str(yaml_path.resolve()),
             'python_path': str(python_path.resolve()), 'fingerprint': final}
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return action


def watch_pair(yaml_file: str | Path, python_file: str | Path, *, state_file: str | Path | None = None, interval: float = 1.0) -> None:
    """前台监视文件更改并同步；出现冲突或无效数据立即停止。"""
    import time
    if interval < 0.1:
        raise ValueError("监视间隔必须不小于 0.1 秒")
    try:
        while True:
            action = sync_pair(yaml_file, python_file, state_file=state_file)
            if action != 'unchanged':
                print(action, flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print('stopped', flush=True)
