"""A deliberately small TOML reader for this project's Python 3.9/3.10 config.

Python 3.11+ uses the standard library's full tomllib instead. This fallback only
accepts the strings, booleans, numbers, arrays, tables, and array-of-tables used
by config.example.toml.
"""
from __future__ import annotations

import ast
from typing import Any, BinaryIO


def _commentless(line: str) -> str:
    quote: str | None = None
    escaped = False
    result = []
    for char in line:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\" and quote == '"':
            result.append(char)
            escaped = True
            continue
        if char in "\"'":
            quote = None if quote == char else (char if quote is None else quote)
        if char == "#" and quote is None:
            break
        result.append(char)
    return "".join(result).strip()


def _value(raw: str) -> Any:
    value = raw.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError) as exc:
        raise ValueError(f"Unsupported TOML value: {value}") from exc


def loads(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    current = root
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = _commentless(raw_line)
        if not line:
            continue
        if line.startswith("[[") and line.endswith("]]" ):
            name = line[2:-2].strip()
            if "." in name:
                raise ValueError(f"Nested array tables are unsupported (line {line_number})")
            current = {}
            root.setdefault(name, []).append(current)
        elif line.startswith("[") and line.endswith("]"):
            names = [part.strip() for part in line[1:-1].split(".")]
            current = root
            for name in names:
                current = current.setdefault(name, {})
        elif "=" in line:
            key, raw_value = line.split("=", 1)
            current[key.strip()] = _value(raw_value)
        else:
            raise ValueError(f"Invalid TOML syntax on line {line_number}")
    return root


def load(handle: BinaryIO) -> dict[str, Any]:
    return loads(handle.read().decode("utf-8"))
