"""Command-line interface for Dify DSL tools.

Usage:
    python -m dify_dsl parse workflow.yml
    python -m dify_dsl split workflow.yml -o output_dir/
    python -m dify_dsl rebuild output_dir/ -o rebuilt.yml
    python -m dify_dsl validate workflow.yml
    python -m dify_dsl compare original.yml modified.yml
    python -m dify_dsl analyze workflow.yml
    python -m dify_dsl info workflow.yml
"""

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="dify-dsl",
        description="Dify DSL Parser & Generator v3.0 — parse, edit, and regenerate Dify workflows",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- parse ---
    p_parse = sub.add_parser("parse", help="Parse a DSL file and show summary")
    p_parse.add_argument("file", help="Path to Dify DSL YAML file")

    # --- info ---
    p_info = sub.add_parser("info", help="Show detailed workflow information")
    p_info.add_argument("file", help="Path to Dify DSL YAML file")

    # --- validate ---
    p_val = sub.add_parser("validate", help="Validate DSL structure")
    p_val.add_argument("file", help="Path to Dify DSL YAML file")

    # --- split ---
    p_split = sub.add_parser("split", help="Split DSL into editable files")
    p_split.add_argument("file", help="Path to Dify DSL YAML file")
    p_split.add_argument("-o", "--output", help="Output directory", default=None)

    # --- rebuild ---
    p_rebuild = sub.add_parser("rebuild", help="Rebuild DSL from split files")
    p_rebuild.add_argument("dir", help="Path to split directory")
    p_rebuild.add_argument("-o", "--output", help="Output YAML file", default=None)

    # --- compare ---
    p_compare = sub.add_parser("compare", help="Compare two DSL files")
    p_compare.add_argument("file1", help="First YAML file")
    p_compare.add_argument("file2", help="Second YAML file")
    p_compare.add_argument("--html", help="Generate HTML diff report", default=None)

    # --- analyze ---
    p_analyze = sub.add_parser("analyze", help="Analyze workflow topology and tools")
    p_analyze.add_argument("file", help="Path to Dify DSL YAML file")
    p_analyze.add_argument("--topology", action="store_true", help="Show topology analysis")
    p_analyze.add_argument("--tools", action="store_true", help="Show tool usage analysis")
    p_analyze.add_argument("--variables", action="store_true", help="Show variable flow analysis")

    # 安全的 Python 数据声明与 YAML 双向转换，不执行任意 Python 程序。
    p_to_py = sub.add_parser("to-python", help="将 Dify YAML 转为可编辑的 Python 数据声明")
    p_to_py.add_argument("file")
    p_to_py.add_argument("-o", "--output", required=True)
    p_to_py.add_argument("--force", action="store_true")

    p_from_py = sub.add_parser("from-python", help="将 Python 数据声明转为 Dify YAML")
    p_from_py.add_argument("file")
    p_from_py.add_argument("-o", "--output", required=True)
    p_from_py.add_argument("--force", action="store_true")

    p_sync = sub.add_parser("sync", help="基于内容指纹双向同步 Python 与 YAML，冲突时拒绝覆盖")
    p_sync.add_argument("yaml")
    p_sync.add_argument("python")
    p_sync.add_argument("--state", default=None)
    p_sync.add_argument("--watch", action="store_true", help="持续监视两侧文件变化")
    p_sync.add_argument("--interval", type=float, default=1.0)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command in ("to-python", "from-python", "sync"):
            from dify_dsl.python_sync import dsl_to_python, python_to_yaml, sync_pair, watch_pair
            if args.command == "to-python":
                print(dsl_to_python(args.file, args.output, overwrite=args.force))
            elif args.command == "from-python":
                print(python_to_yaml(args.file, args.output, overwrite=args.force))
            else:
                if args.watch:
                    watch_pair(args.yaml, args.python, state_file=args.state, interval=args.interval)
                else:
                    print(sync_pair(args.yaml, args.python, state_file=args.state))
            return 0
        if args.command == "parse":
            return _cmd_parse(args)
        elif args.command == "info":
            return _cmd_info(args)
        elif args.command == "validate":
            return _cmd_validate(args)
        elif args.command == "split":
            return _cmd_split(args)
        elif args.command == "rebuild":
            return _cmd_rebuild(args)
        elif args.command == "compare":
            return _cmd_compare(args)
        elif args.command == "analyze":
            return _cmd_analyze(args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def _cmd_parse(args) -> int:
    from dify_dsl.parser import parse_dsl
    dsl = parse_dsl(args.file)
    print(dsl.summary())
    return 0


def _cmd_info(args) -> int:
    from dify_dsl.parser import parse_dsl
    dsl = parse_dsl(args.file)
    print(dsl.summary())
    print()

    # Detailed node list
    print("Nodes:")
    for node in dsl.nodes:
        title = node.data.title or "(untitled)"
        print(f"  [{node.data.type:20s}] {node.id} — {title}")

    print(f"\nEdges: {len(dsl.edges)}")
    for edge in dsl.edges:
        src_type = edge.data.sourceType or "?"
        tgt_type = edge.data.targetType or "?"
        print(f"  {edge.source} ({src_type}) -> {edge.target} ({tgt_type})")

    return 0


def _cmd_validate(args) -> int:
    from dify_dsl.parser import parse_dsl
    from dify_dsl.validator import validate

    dsl = parse_dsl(args.file)
    result = validate(dsl)

    if result.is_valid:
        print("[OK] DSL validation passed")
        if result.warnings:
            for w in result.warnings:
                print(f"  [WARN] {w}")
    else:
        print("[FAIL] DSL validation failed")
        for e in result.errors:
            print(f"  [ERROR] {e}")
        for w in result.warnings:
            print(f"  [WARN] {w}")
        return 1

    return 0


def _cmd_split(args) -> int:
    from datetime import datetime
    from dify_dsl.parser import parse_dsl
    from dify_dsl.splitter import split_workflow

    dsl = parse_dsl(args.file)

    if args.output:
        out_dir = args.output
    else:
        stem = Path(args.file).stem
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = f"split_{stem}_{ts}"

    result_dir = split_workflow(dsl, out_dir)
    print(f"[OK] Workflow split into: {result_dir}")
    print(f"  Nodes: {len(dsl.nodes)}")
    print(f"  Edges: {len(dsl.edges)}")
    return 0


def _cmd_rebuild(args) -> int:
    from datetime import datetime
    from dify_dsl.rebuilder import rebuild_workflow
    from dify_dsl.generator import generate_dsl

    dsl = rebuild_workflow(args.dir)

    if args.output:
        out_file = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = f"rebuilt_{ts}.yml"

    generate_dsl(dsl, out_file)
    print(f"[OK] Workflow rebuilt: {out_file}")
    print(f"  Nodes: {len(dsl.nodes)}")
    print(f"  Edges: {len(dsl.edges)}")
    return 0


def _cmd_compare(args) -> int:
    from dify_dsl.comparator import compare_files, generate_html_diff

    result = compare_files(args.file1, args.file2)
    print(result.summary)

    if args.html:
        generate_html_diff(args.file1, args.file2, args.html)
        print(f"\nHTML diff report: {args.html}")

    return 0 if not result.has_changes else 1


def _cmd_analyze(args) -> int:
    from dify_dsl.parser import parse_dsl
    from dify_dsl.analyzer import analyze_topology, analyze_tools, analyze_variable_flow

    dsl = parse_dsl(args.file)

    # Default: show all if none specified
    show_all = not (args.topology or args.tools or args.variables)

    if show_all or args.topology:
        topo = analyze_topology(dsl)
        print("=== Topology Analysis ===")
        print(topo.summary)
        print()

    if show_all or args.tools:
        tools = analyze_tools(dsl)
        print("=== Tool Usage ===")
        print(tools.summary)
        print()

    if show_all or args.variables:
        vars_result = analyze_variable_flow(dsl)
        print("=== Variable Flow ===")
        print(vars_result.summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
