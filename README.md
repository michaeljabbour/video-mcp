# video-mcp

**Phase 2a skeleton — stubs only, no live API wiring yet.**
Live Veo wiring lands in Phase 2a.2.

An async video generation MCP server with multi-provider support.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Status

> ⚠️ **This is a Phase 2a skeleton.** All providers return stub responses — fake job IDs that
> advance from `submitted` → `pending` → `complete` after ~2 seconds of wall-clock time.
> No real video bytes are generated. Live Veo 3.1 wiring is the next milestone (Phase 2a.2).

## Purpose

Provides an MCP interface for async video generation using multiple backend providers. Designed
for use with the `amplifier-bundle-creative` orchestration bundle.

## Related Links

- **Spec + decisions log:** https://github.com/michaeljabbour/amplifier-bundle-creative/blob/main/spec/DECISIONS.md
  - D018: Async pattern — `generate_video` returns a `job_id` immediately; callers poll via `get_job_status`
  - D021: VideoProvider ABC shape (this repo's `src/providers/base.py`)
- **Sibling image MCP:** https://github.com/michaeljabbour/imagen-mcp (image generation)

## Providers

| Provider | Status | Notes |
|----------|--------|-------|
| Veo 3.1 Standard | Stub — live wiring pending | $0.40/sec, 4K, best lip-sync |
| Veo 3.1 Fast | Stub — live wiring pending | $0.15/sec, 1080p, faster iteration |
| Veo 3.1 Lite | Stub — live wiring pending | $0.05/sec, 720p/1080p, high volume |
| Grok Imagine Video | Stub only — raises NotImplementedError | D019: xAI DPA/MSA pending |
| Sora 2 Pro | Stub only — raises NotImplementedError | D010: API EOL 2026-09-24 |

**Stub behavior:** Veo stubs return a fake `job_id` (e.g. `stub_veo_standard_abc123`). A call
to `get_job_status` with that ID will return `status: pending` for ~2 seconds, then `status: complete`
with a placeholder `output_url`. No real video is produced.

## Setup

**Required environment variables:**

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Veo 3.1 provider (live wiring pending) |

**Optional:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `XAI_API_KEY` | — | Grok Imagine Video (gated — see D019) |
| `OUTPUT_DIR` | `~/Downloads/videos/` | Base output directory |
| `VIDEO_MCP_REQUEST_TIMEOUT` | `300` | Request timeout in seconds |
| `VIDEO_MCP_LOG_PROMPTS` | `false` | Log full prompts to events log |

## Quickstart

### generate_video

Submit a video generation job (returns immediately with a `job_id`):

```json
{
  "tool": "generate_video",
  "params": {
    "prompt": "A serene mountain lake at golden hour, camera slowly panning right",
    "provider": "veo-3.1-standard",
    "duration": 8.0,
    "aspect_ratio": "16:9"
  }
}
```

Response:
```
## ✅ Video Job Submitted

**Provider:** veo-3.1-standard
**Job ID:** `stub_veo_standard_a1b2c3d4e5f6`
**Status:** submitted

### ⏰ Polling Instructions
Call `get_job_status` with job_id `stub_veo_standard_a1b2c3d4e5f6` every ~15 seconds.
Typical completion: 30–120s for live Veo calls (2s for stubs).
```

### get_job_status

Poll for completion:

```json
{
  "tool": "get_job_status",
  "params": {
    "job_id": "stub_veo_standard_a1b2c3d4e5f6"
  }
}
```

Response (after ~2s with stubs):
```
## ✅ Video Complete

**Job ID:** `stub_veo_standard_a1b2c3d4e5f6`
**Status:** complete
**Progress:** 100%
**Output URL:** https://stub.example.com/video/stub_veo_standard_a1b2c3d4e5f6.mp4
```

## Project Structure

```
video-mcp/
├── src/
│   ├── server.py              # MCP entry point — generate_video, get_job_status
│   ├── config/
│   │   ├── constants.py       # VEO_MODELS, STUBBED_PROVIDERS, limits
│   │   ├── settings.py        # Env-var settings (GEMINI_API_KEY, XAI_API_KEY, ...)
│   │   ├── paths.py           # Output path resolution
│   │   └── dotenv.py          # .env loader shim
│   ├── providers/
│   │   ├── base.py            # VideoProvider ABC, VideoCapabilities, VideoJobResult, JobStore
│   │   ├── veo_provider.py    # Veo 3.1 Standard/Fast/Lite stubs
│   │   ├── sora_provider.py   # Sora 2 stub (D010)
│   │   ├── grok_provider.py   # Grok Imagine stub (D019)
│   │   ├── selector.py        # Provider routing (override + default)
│   │   └── registry.py        # Provider factory + JobStore routing
│   ├── models/
│   │   └── input_models.py    # Pydantic models for MCP tools
│   ├── exceptions.py          # VideoError hierarchy
│   └── services/
│       └── logging_config.py  # Structured JSONL event logging
└── tests/
    ├── test_providers.py
    └── test_server.py
```

## Development

```bash
# Clone and install
git clone https://github.com/michaeljabbour/video-mcp.git
cd video-mcp
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Verify server loads
python3 -c "from src.server import mcp; print('Server loads OK')"

# Start server (waits for MCP stdio)
python -m src.server
```

## License

MIT
