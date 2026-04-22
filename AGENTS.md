# Repository Guidelines

For contributors building and maintaining the video-mcp MCP server.

## Project Structure & Module Organization

- `src/server.py` is the MCP entry point exporting the registered tools (`generate_video`, `get_job_status`).
- `src/providers/` holds provider implementations (`veo_provider.py`, `sora_provider.py`, `grok_provider.py`),
  `selector.py` for routing, and `registry.py` for factory wiring.
- `src/config/` contains constants and settings; `src/models/input_models.py` defines Pydantic request models.
- Tests live in `tests/` mirroring modules (`test_providers.py`, `test_server.py`).

## Build, Test, and Development Commands

- Create a venv and install deps:
  `python3 -m venv venv && source venv/bin/activate && pip install -e ".[dev]"`.
- Run the server locally: `python -m src.server` (export `GEMINI_API_KEY` first).
- Format and lint: `ruff format . && ruff check . --fix`.
- Type check: `pyright src tests`.
- Tests: `pytest tests/ -v`.

## Coding Style & Naming Conventions

- Python 3.10+; Ruff line length 100; prefer explicit imports and typed signatures.
- Use snake_case for modules/functions, PascalCase for classes.
- Keep provider IDs consistent with registry keys (`veo-3.1-standard`, `veo-3.1-fast`, etc.).
- Keep side effects out of import time; guard script entry with `if __name__ == "__main__":`.

## Testing Guidelines

- Add or extend tests in `tests/` near the related module using `test_*.py` / `test_*` patterns.
- Mock time for Veo stub tests (`unittest.mock.patch('time.time')`).
- No live API calls in tests — stubs only.
- For async tests, `asyncio_mode = "auto"` is configured in `pyproject.toml`.

## Provider Status

| Provider | Status | Decision |
|----------|--------|----------|
| Veo 3.1 Standard | Stub (live-wiring pending) | Phase 2a.2 |
| Veo 3.1 Fast | Stub (live-wiring pending) | Phase 2a.2 |
| Veo 3.1 Lite | Stub (live-wiring pending) | Phase 2a.2 |
| Grok Imagine Video | Stub, always raises NotImplementedError | D019 (xAI DPA pending) |
| Sora 2 Pro | Stub, always raises NotImplementedError | D010 (API EOL 2026-09-24) |

## Commit & Pull Request Guidelines

- Follow Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`); subjects under ~72 chars.
- PRs should list testing (`ruff`, `pyright`, `pytest`) and note impacted tools.
- Link to relevant DECISIONS.md entries when applicable.

## Security & Configuration Tips

- Never commit API keys; load via env (`GEMINI_API_KEY`, optional `XAI_API_KEY`).
- Avoid logging sensitive prompts or keys; `VIDEO_MCP_LOG_PROMPTS=false` by default.
