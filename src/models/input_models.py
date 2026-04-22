"""
Pydantic input models for video-mcp tools.

These models define the parameters accepted by MCP tools
with rich descriptions for Claude to understand how to use them.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class OutputFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


class VideoGenerateInput(BaseModel):
    """
    Input model for the `generate_video` tool.

    Submits an async video generation job. Returns immediately with a job_id.
    Poll for completion using `get_job_status`.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    prompt: str = Field(
        ...,
        description=(
            "Text description of the desired video. Be specific about subject, motion, "
            "camera movement, lighting, and mood. "
            "Example: 'A serene mountain lake at golden hour, camera slowly panning right, "
            "4K cinematic.'"
        ),
        min_length=1,
        max_length=4000,
    )

    provider: str | None = Field(
        default=None,
        description=(
            "Canonical provider ID. Options:\n"
            "- 'veo-3.1-standard' (default): 4K, best lip-sync, $0.40/sec\n"
            "- 'veo-3.1-fast': 1080p, faster iteration, $0.15/sec\n"
            "- 'veo-3.1-lite': 720p/1080p, high-volume, $0.05/sec\n"
            "- 'sora-2-pro': stub only — raises NotImplementedError (D010)\n"
            "- 'grok-imagine-video': stub only — raises NotImplementedError (D019)\n"
            "If omitted, defaults to 'veo-3.1-standard'."
        ),
    )

    first_frame: str | None = Field(
        default=None,
        description=(
            "Optional first-frame image for image-to-video generation. "
            "Accepts a base64-encoded PNG string or an absolute path to an image file on disk. "
            "Only Veo 3.1 supports first-frame conditioning."
        ),
    )

    last_frame: str | None = Field(
        default=None,
        description=(
            "Optional last-frame image for bracket-style generation. "
            "Veo 3.1's unique first+last frame specification — generates the video "
            "that would connect these two frames. "
            "Only Veo supports this feature."
        ),
    )

    duration: float | None = Field(
        default=None,
        description=(
            "Video duration in seconds. Supported values: 4.0, 6.0, 8.0, 16.0. "
            "Default: 8.0 seconds."
        ),
    )

    aspect_ratio: str | None = Field(
        default=None,
        description=(
            "Video aspect ratio. Options: '16:9' (landscape, default) "
            "or '9:16' (portrait/vertical)."
        ),
    )

    resolution: str | None = Field(
        default=None,
        description=(
            "Target resolution. Options: '720p', '1080p', '4K'. "
            "Default is determined by the provider tier "
            "(Standard → 4K, Fast → 1080p, Lite → 1080p)."
        ),
    )

    output_path: str | None = Field(
        default=None,
        description=(
            "Optional path to save the downloaded video. "
            "If a directory, saves with auto-generated filename. "
            "Supports `~` expansion. "
            "Defaults to `~/Downloads/videos/{provider}/`. "
            "Note: live download not implemented in Phase 2a stubs."
        ),
    )

    output_format: OutputFormat | None = Field(
        default=OutputFormat.MARKDOWN,
        description="Output format for the tool response (markdown or json).",
    )

    # API key overrides — hidden from repr/serialization
    gemini_api_key: str | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description=(
            "Gemini API key override for Veo (uses GEMINI_API_KEY env var if not provided)."
        ),
    )

    xai_api_key: str | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description=(
            "xAI API key override (uses XAI_API_KEY env var if not provided). "
            "Grok Imagine Video is D019-gated — stub only."
        ),
    )


class VideoJobStatusInput(BaseModel):
    """
    Input model for the `get_job_status` tool.

    Polls the status of a previously submitted video generation job.
    Call every ~15 seconds until status is 'complete' or 'failed'.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    job_id: str = Field(
        ...,
        description=(
            "The job ID returned by `generate_video`. Example: 'stub_veo_standard_abc123def456'"
        ),
        min_length=1,
    )

    output_format: OutputFormat | None = Field(
        default=OutputFormat.MARKDOWN,
        description="Output format for the tool response (markdown or json).",
    )
