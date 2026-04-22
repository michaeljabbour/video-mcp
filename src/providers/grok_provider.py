"""
Grok Imagine Video provider — STUB ONLY.

Per DECISIONS D019: xAI DPA/MSA is pending. This stub is gated until the
privacy and terms review (D017) completes for xAI.

When invoked, submit() and get_status() raise NotImplementedError with a link
to the DECISIONS log.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.constants import SUPPORTED_DURATIONS_SECONDS
from .base import VideoCapabilities, VideoJobResult, VideoProvider

logger = logging.getLogger(__name__)

_GROK_NOT_IMPLEMENTED_MSG = (
    "Grok Imagine Video is stub-only per DECISIONS D019. "
    "xAI DPA/MSA is pending — see "
    "https://github.com/michaeljabbour/amplifier-bundle-creative/blob/main/spec/DECISIONS.md#d019"
)


class GrokProvider(VideoProvider):
    """Grok Imagine Video — stub only per DECISIONS D019 (xAI DPA pending).

    Capabilities are populated so the provider is listable and queryable,
    but submit() and get_status() always raise NotImplementedError until
    the xAI privacy review (D017/D019) completes.
    """

    @property
    def name(self) -> str:
        return "grok-imagine-video"

    @property
    def capabilities(self) -> VideoCapabilities:
        return VideoCapabilities(
            name="grok-imagine-video",
            display_name="Grok Imagine Video (stub — D019)",
            supported_durations=list(SUPPORTED_DURATIONS_SECONDS),
            supported_resolutions=["1080p"],
            supports_first_frame=False,
            supports_last_frame=False,
            max_duration_seconds=max(SUPPORTED_DURATIONS_SECONDS),
            typical_latency_seconds=45.0,
            cost_tier="standard",
            best_for=[
                "Creative video synthesis (when live)",
                "xAI ecosystem integration",
            ],
            not_recommended_for=[
                "Production use — stub only, xAI DPA pending (D019)",
                "Any use until D019 privacy review completes",
            ],
            supports_audio=False,
        )

    async def submit(
        self,
        prompt: str,
        *,
        first_frame: str | None = None,
        duration: float | None = None,
        aspect_ratio: str | None = None,
        **kwargs: Any,
    ) -> VideoJobResult:
        """Always raises NotImplementedError per DECISIONS D019."""
        raise NotImplementedError(_GROK_NOT_IMPLEMENTED_MSG)

    async def get_status(self, job_id: str) -> VideoJobResult:
        """Always raises NotImplementedError per DECISIONS D019."""
        raise NotImplementedError(_GROK_NOT_IMPLEMENTED_MSG)
