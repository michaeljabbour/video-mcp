#!/usr/bin/env python3
"""
video-mcp: Multi-Provider Video Generation MCP Server

An MCP server that provides async video generation using multiple providers:
- Google Veo 3.1 Standard/Fast/Lite: Primary provider (stub — live wiring pending)
- Grok Imagine Video: Stub only, D019-gated (xAI DPA pending)
- Sora 2 Pro: Stub only per D010 (API EOL 2026-09-24)

Phase 2a skeleton — stubs only, no live API wiring yet.
See DECISIONS D018 (async pattern) and D021 (VideoProvider ABC).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hashlib import sha256
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from .config.constants import SUGGESTED_POLL_INTERVAL_SECONDS
from .config.settings import get_settings
from .exceptions import JobNotFoundError, VideoError, _sanitize_message
from .models.input_models import OutputFormat, VideoGenerateInput, VideoJobStatusInput
from .providers import VideoJobResult, get_provider_registry
from .services.logging_config import configure_logging, log_event

logger = logging.getLogger(__name__)


# ============================
# Lifespan (startup / shutdown)
# ============================


@asynccontextmanager
async def _lifespan(_app: FastMCP) -> AsyncIterator[None]:
    """Manage server-wide resources across the process lifetime."""
    # --- startup ---
    configure_logging()
    logger.info("video-mcp server starting (Phase 2a skeleton — stubs only)")
    yield
    # --- shutdown ---
    logger.info("video-mcp server shutting down — closing providers")
    try:
        registry = get_provider_registry()
        await registry.close_all()
    except Exception:
        logger.exception("Error during provider cleanup")


# Initialize MCP server
mcp = FastMCP("video_mcp", lifespan=_lifespan)


# ============================
# Helper Functions
# ============================


def format_job_markdown(
    result: VideoJobResult,
    *,
    is_submit: bool = False,
    reasoning: str | None = None,
) -> str:
    """Format a video job result as Markdown."""
    if result.status == "failed":
        lines = [
            "## ❌ Video Generation Failed",
            "",
            f"**Job ID:** `{result.job_id}`",
            f"**Provider:** {result.provider}",
        ]
        if result.error_code:
            lines.append(f"**Error Code:** {result.error_code}")
        if result.retry_hint:
            lines.append(f"**Hint:** {result.retry_hint}")
        return "\n".join(lines)

    if is_submit:
        lines = [
            "## ✅ Video Job Submitted",
            "",
            f"**Provider:** {result.provider}",
            f"**Job ID:** `{result.job_id}`",
            f"**Status:** {result.status}",
        ]
        if result.duration_seconds:
            lines.append(f"**Requested Duration:** {result.duration_seconds}s")
        if reasoning:
            lines.append(f"**Selection:** {reasoning}")
        lines.extend(
            [
                "",
                "### ⏰ Polling Instructions",
                f"Call `get_job_status` with job_id `{result.job_id}` "
                f"every ~{int(SUGGESTED_POLL_INTERVAL_SECONDS)} seconds.",
                "Typical completion: 30–120s for live Veo calls (~2s for stubs).",
                "",
                "> ⚠️ **Phase 2a stub** — no real video is generated. "
                "Output URL will be a placeholder.",
            ]
        )
        return "\n".join(lines)

    # Status poll response
    if result.status == "complete":
        lines = [
            "## ✅ Video Complete",
            "",
            f"**Job ID:** `{result.job_id}`",
            f"**Provider:** {result.provider}",
            "**Status:** complete",
        ]
        if result.progress is not None:
            lines.append(f"**Progress:** {int(result.progress * 100)}%")
        if result.output_url:
            lines.append(f"**Output URL:** {result.output_url}")
        if result.completed_at:
            lines.append(f"**Completed At:** {result.completed_at.isoformat()}")
        return "\n".join(lines)

    # pending
    lines = [
        "## 🕐 Video Pending",
        "",
        f"**Job ID:** `{result.job_id}`",
        f"**Provider:** {result.provider}",
        f"**Status:** {result.status}",
    ]
    if result.progress is not None:
        lines.append(f"**Progress:** {int(result.progress * 100)}%")
    lines.extend(
        [
            "",
            f"Poll again in ~{int(SUGGESTED_POLL_INTERVAL_SECONDS)} seconds.",
        ]
    )
    return "\n".join(lines)


def format_job_json(
    result: VideoJobResult,
    *,
    reasoning: str | None = None,
) -> str:
    """Format a video job result as JSON."""
    data: dict[str, Any] = result.to_dict()
    if reasoning:
        data["selection_reasoning"] = reasoning
    return json.dumps(data, indent=2, default=str)


# ============================
# MCP Tools
# ============================


@mcp.tool(name="generate_video")
async def generate_video(params: VideoGenerateInput) -> str:
    """Generate a video using the best available provider.

    Submits an async video generation job and returns immediately with a
    `job_id`. Poll for completion using `get_job_status` every ~15 seconds.

    **Phase 2a skeleton — stubs only:**
    - Veo 3.1 stubs return a fake `job_id` that transitions to `complete`
      after ~2 wallclock seconds with a placeholder output_url.
    - Grok Imagine Video raises NotImplementedError (D019 — xAI DPA pending).
    - Sora 2 raises NotImplementedError (D010 — API EOL 2026-09-24).

    **Providers:**
    - `veo-3.1-standard` (default): 4K, best lip-sync, $0.40/sec
    - `veo-3.1-fast`: 1080p, faster iteration, $0.15/sec
    - `veo-3.1-lite`: 720p/1080p, high volume, $0.05/sec

    **Async Pattern (DECISIONS D018):**
    This tool returns immediately. Use `get_job_status` to poll until complete.

    Args:
        params: Video generation parameters including prompt and optional settings.

    Returns:
        Formatted response containing job_id and polling guidance.
    """
    request_id = uuid4().hex[:12]
    try:
        registry = get_provider_registry()
        settings = get_settings()

        prompt_hash = sha256(params.prompt.encode("utf-8")).hexdigest()
        start_event: dict[str, object] = {
            "request_id": request_id,
            "tool": "generate_video",
            "provider_requested": params.provider,
            "prompt_length": len(params.prompt),
            "prompt_sha256": prompt_hash,
            "duration": params.duration,
            "aspect_ratio": params.aspect_ratio,
            "has_first_frame": params.first_frame is not None,
            "has_last_frame": params.last_frame is not None,
            "output_format": params.output_format.value if params.output_format else None,
        }
        if settings.log_prompts:
            start_event["prompt"] = params.prompt
        log_event("video.generate.start", **start_event)

        # Select and get the provider
        provider = registry.select_provider(params.provider)
        reasoning = registry._selector.get_selection_reasoning(params.provider)

        logger.info("Submitting video job via provider: %s", provider.name)
        log_event(
            "video.provider.selected",
            request_id=request_id,
            provider=provider.name,
            reasoning=reasoning,
        )

        # Submit the job (returns immediately with job_id)
        result = await provider.submit(
            params.prompt,
            first_frame=params.first_frame,
            duration=params.duration,
            aspect_ratio=params.aspect_ratio,
            gemini_api_key=params.gemini_api_key,
        )

        log_event(
            "video.generate.submitted",
            request_id=request_id,
            job_id=result.job_id,
            provider=result.provider,
            model=result.model,
            status=result.status,
        )

        # Format response
        if params.output_format == OutputFormat.JSON:
            return format_job_json(result, reasoning=reasoning)
        return format_job_markdown(result, is_submit=True, reasoning=reasoning)

    except NotImplementedError as e:
        logger.warning("Provider stub raised NotImplementedError: %s", e)
        log_event("video.generate.not_implemented", request_id=request_id, error=str(e))
        error_response = {"success": False, "error": str(e)}
        if params.output_format == OutputFormat.JSON:
            return json.dumps(error_response, indent=2)
        return f"## ❌ Provider Not Implemented\n\n{e}"

    except VideoError as e:
        logger.exception("Video generation failed")
        log_event("video.generate.error", request_id=request_id, error=str(e))
        error_response = {"success": False, "error": e.user_message}
        if params.output_format == OutputFormat.JSON:
            return json.dumps(error_response, indent=2)
        return f"## ❌ Video Generation Failed\n\n**Error ({type(e).__name__}):** {e.user_message}"

    except Exception as e:
        logger.exception("Video generation failed")
        sanitized = _sanitize_message(str(e))
        log_event("video.generate.error", request_id=request_id, error=sanitized)
        error_response = {"success": False, "error": sanitized}
        if params.output_format == OutputFormat.JSON:
            return json.dumps(error_response, indent=2)
        return f"## ❌ Video Generation Failed\n\n**Error:** {sanitized}"


@mcp.tool(name="get_job_status")
async def get_job_status(params: VideoJobStatusInput) -> str:
    """Poll the status of a previously submitted video generation job.

    Call every ~15 seconds until status is `complete` or `failed`.

    **Status values:**
    - `submitted`: Job accepted, not yet started.
    - `pending`: Job is processing.
    - `complete`: Video is ready. `output_url` contains the download URL.
    - `failed`: Generation failed. See `error_code` and `retry_hint`.

    **Phase 2a stub behavior:**
    Veo stubs advance to `complete` ~2 wallclock seconds after submission.
    `output_url` will be a placeholder (no real video).

    Args:
        params: Job status query including job_id.

    Returns:
        Formatted status response including progress and output_url when complete.
    """
    request_id = uuid4().hex[:12]
    try:
        registry = get_provider_registry()

        log_event(
            "video.status.poll",
            request_id=request_id,
            job_id=params.job_id,
        )

        provider = registry.get_provider_for_job(params.job_id)
        result = await provider.get_status(params.job_id)

        log_event(
            "video.status.result",
            request_id=request_id,
            job_id=params.job_id,
            provider=result.provider,
            status=result.status,
            progress=result.progress,
            output_url=result.output_url,
        )

        if params.output_format == OutputFormat.JSON:
            return format_job_json(result)
        return format_job_markdown(result)

    except JobNotFoundError as e:
        logger.warning("Job not found: %s — %s", params.job_id, e.user_message)
        log_event(
            "video.status.not_found",
            request_id=request_id,
            job_id=params.job_id,
            error=str(e),
        )
        error_response = {
            "success": False,
            "job_id": params.job_id,
            "error": e.user_message,
            "hint": "Submit a new job via generate_video.",
        }
        if params.output_format == OutputFormat.JSON:
            return json.dumps(error_response, indent=2)
        return (
            f"## ❌ Job Not Found\n\n"
            f"**Job ID:** `{params.job_id}`\n\n"
            f"**Error:** {e.user_message}\n\n"
            f"Submit a new job via `generate_video`."
        )

    except VideoError as e:
        logger.exception("Job status check failed")
        log_event("video.status.error", request_id=request_id, error=str(e))
        error_response = {"success": False, "error": e.user_message}
        if params.output_format == OutputFormat.JSON:
            return json.dumps(error_response, indent=2)
        return f"## ❌ Status Check Failed\n\n**Error ({type(e).__name__}):** {e.user_message}"

    except Exception as e:
        logger.exception("Job status check failed")
        sanitized = _sanitize_message(str(e))
        log_event("video.status.error", request_id=request_id, error=sanitized)
        error_response = {"success": False, "error": sanitized}
        if params.output_format == OutputFormat.JSON:
            return json.dumps(error_response, indent=2)
        return f"## ❌ Status Check Failed\n\n**Error:** {sanitized}"


# ============================
# Server Entry Point
# ============================


if __name__ == "__main__":
    from .config.dotenv import load_dotenv

    load_dotenv(override=False)
    mcp.run()
