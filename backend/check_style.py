"""Check Betty-inspired function size and documentation in Python sources."""

import ast
from pathlib import Path


def check_file(path: Path) -> list[str]:
    """Reject undocumented definitions and functions over forty lines."""
    failures = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, kinds):
            continue
        if not ast.get_docstring(node):
            failures.append(f"{path}:{node.lineno}: document {node.name}")
        if isinstance(node, ast.ClassDef):
            continue
        size = node.end_lineno - node.lineno + 1
        if size > 40:
            failures.append(
                f"{path}:{node.lineno}: {node.name} is {size} lines"
            )
    return failures


def main() -> None:
    """Apply language-appropriate structural rules alongside Ruff."""
    failures = []
    for path in Path("app").glob("*.py"):
        failures.extend(check_file(path))
    if failures:
        raise SystemExit("\n".join(failures))
    print("Application definitions documented; functions at most 40 lines.")


if __name__ == "__main__":
    main()
