"""Scan Python source files for Name.Load references that are never bound in
the enclosing function/module scope (a common source of NameError at runtime).

Usage: python scripts/scan_undefined_names.py [path ...]
"""
from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

BUILTINS = set(dir(builtins))


def collect_module_globals(tree: ast.Module) -> set[str]:
    """Top-level names bound in the module (defs, classes, imports, assigns)."""
    names: set[str] = set()
    for node in tree.body:
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(child.name)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    _collect_bound(target, names)
            elif isinstance(child, (ast.AnnAssign, ast.AugAssign)):
                _collect_bound(child.target, names)
            elif isinstance(child, ast.ExceptHandler):
                if child.name:
                    names.add(child.name)
            elif isinstance(child, (ast.For, ast.AsyncFor)):
                _collect_bound(child.target, names)
            elif isinstance(child, (ast.With, ast.AsyncWith)):
                for item in child.items:
                    if item.optional_vars:
                        _collect_bound(item.optional_vars, names)
            elif isinstance(child, ast.NamedExpr):
                _collect_bound(child.target, names)
            elif isinstance(child, ast.Global):
                names.update(child.names)
            elif isinstance(child, ast.Nonlocal):
                names.update(child.names)
    return names


def _collect_bound(target: ast.AST, names: set[str]) -> None:
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _collect_bound(elt, names)
    elif isinstance(target, ast.Starred):
        _collect_bound(target.value, names)


def collect_function_bindings(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names bound inside a function body (params + assignments + imports...)."""
    names: set[str] = set()
    for arg in node.args.args + node.args.kwonlyargs:
        names.add(arg.arg)
    if node.args.vararg:
        names.add(node.args.vararg.arg)
    if node.args.kwarg:
        names.add(node.args.kwarg.arg)
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(child.name)
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            for alias in child.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                _collect_bound(target, names)
        elif isinstance(child, (ast.AnnAssign, ast.AugAssign)):
            _collect_bound(child.target, names)
        elif isinstance(child, ast.ExceptHandler):
            if child.name:
                names.add(child.name)
        elif isinstance(child, (ast.For, ast.AsyncFor)):
            _collect_bound(child.target, names)
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            for item in child.items:
                if item.optional_vars:
                    _collect_bound(item.optional_vars, names)
        elif isinstance(child, ast.NamedExpr):
            _collect_bound(child.target, names)
        elif isinstance(child, ast.Global):
            names.update(child.names)
        elif isinstance(child, ast.Nonlocal):
            names.update(child.names)
        elif isinstance(child, ast.Lambda):
            for arg in child.args.args + child.args.kwonlyargs:
                names.add(arg.arg)
            if child.args.vararg:
                names.add(child.args.vararg.arg)
            if child.args.kwarg:
                names.add(child.args.kwarg.arg)
        elif isinstance(child, ast.comprehension):
            _collect_bound(child.target, names)
    return names


def scan_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module_globals: set[str],
    path: Path,
) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    bound = collect_function_bindings(node)
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            name = child.id
            if name in bound or name in module_globals or name in BUILTINS:
                continue
            if name in {"self", "cls", "super"}:
                continue
            findings.append((child.lineno, child.col_offset, name))
    return findings


def scan_file(path: Path) -> list[tuple[int, int, str, str]]:
    """Returns (lineno, col, function, name) for suspicious references."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [(0, 0, "<parse-error>", str(exc))]
    module_globals = collect_module_globals(tree)
    out: list[tuple[int, int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for lineno, col, name in scan_function(node, module_globals, path):
                out.append((lineno, col, node.name, name))
    return out


def main() -> int:
    roots = [Path(p) for p in sys.argv[1:]] or [Path("backend"), Path("mock_services")]
    total_findings = 0
    for root in roots:
        if not root.exists():
            print(f"SKIP (missing): {root}")
            continue
        files = sorted(root.rglob("*.py")) if root.is_dir() else [root]
        for file in files:
            findings = scan_file(file)
            if findings:
                total_findings += len(findings)
                print(f"\n{file}")
                for lineno, col, func, name in findings:
                    if lineno == 0:
                        print(f"  [PARSE ERROR] {name}")
                    else:
                        print(f"  L{lineno}:{col}  {func}() references undefined name: {name!r}")
    print(f"\nTotal suspicious references: {total_findings}")
    return 1 if total_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
