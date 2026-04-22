"""
Minimal .env loader/writer for local development.

This avoids adding a runtime dependency on python-dotenv while still supporting:
- Loading `KEY=VALUE` pairs from a project-local `.env`
- Persisting user-provided API keys for the CLI setup flow

Notes:
- Values from `.env` do not override existing `os.environ` by default.
- The parser is intentionally small; it supports basic quoting with `'` and `"`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def get_project_root() -> Path:
    """
    Return the project root directory.

    We locate the nearest ancestor containing `pyproject.toml`, starting from this file.
    """
    start = Path(__file__).resolve()
    for parent in [start.parent, *start.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    # Fallback: best-effort to avoid surprising writes elsewhere.
    return Path.cwd()


def get_dotenv_path() -> Path:
    """Return the project-local `.env` path."""
    return get_project_root() / ".env"


def _parse_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].lstrip()

    if "=" not in stripped:
        return None

    key, raw_value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None

    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        quote = value[0]
        inner = value[1:-1]
        if quote == '"':
            inner = (
                inner.replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\t", "\t")
                .replace('\\"', '"')
                .replace("\\\\", "\\")
            )
        value = inner

    return key, value


def load_dotenv(dotenv_path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """
    Load environment variables from a `.env` file into `os.environ`.

    Args:
        dotenv_path: Optional path to `.env` (defaults to project root `.env`)
        override: If True, overwrite existing env vars.
    """
    path = dotenv_path or get_dotenv_path()
    if not path.exists():
        return {}

    loaded: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_line(line)
        if not parsed:
            continue
        key, value = parsed
        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value

    return loaded


def _format_env_value(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def upsert_dotenv(dotenv_path: Path, updates: Mapping[str, str]) -> None:
    """
    Insert or update key/value pairs in a `.env` file.

    Preserves non-matching lines and comments.
    """
    if not updates:
        return

    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = []
    if dotenv_path.exists():
        existing_lines = dotenv_path.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    new_lines: list[str] = []

    for line in existing_lines:
        parsed = _parse_line(line)
        if not parsed:
            new_lines.append(line)
            continue

        key, _ = parsed
        if key in remaining:
            new_lines.append(f"{key}={_format_env_value(remaining.pop(key))}")
        else:
            new_lines.append(line)

    if new_lines and new_lines[-1].strip():
        new_lines.append("")

    for key, value in remaining.items():
        new_lines.append(f"{key}={_format_env_value(value)}")

    dotenv_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    try:
        dotenv_path.chmod(0o600)
    except OSError:
        # Best-effort; permissions may be managed by the OS/filesystem.
        pass
