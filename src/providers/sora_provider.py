"""
Sora 2 video generation provider — STUB ONLY.

Per DECISIONS D010: Sora 2 implementation is deferred indefinitely.
The API shuts down 2026-09-24. This stub allows routing logic to be
tested end-to-end without real Sora API code.

When invoked, submit() and get_status() raise NotImplementedError directing
callers to Veo 3.1 Standard.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config.constants import SUPPORTED_DURATIONS_SECONDS
from .base import VideoCapabilities, VideoJobResult, VideoProvider

logger = logging.getLogger(__name__)

_SORA_NOT_IMPLEMENTED_MSG = (
    "Sora 2 is stub-only per DECISIONS D010. "
    "API shuts down 2026-09-24. "
    "Reroute this shot to Veo 3.1 Standard (veo-3.1-standard) for acceptable physics quality."
)


class SoraProvider(VideoProvider):
    """Sora 2 Pro — stub only per DECISIONS D010.

    Capabilities are populated so the provider is listable and queryable,
    but submit() and get_status() always raise NotImplementedError.
    """

    @property
    def name(self) -> str:
        return "sora-2-pro"

    @property
    def capabilities(self) -> VideoCapabilities:
        return VideoCapabilities(
            name="sora-2-pro",
            display_name="Sora 2 Pro (stub — D010)",
            supported_durations=list(SUPPORTED_DURATIONS_SECONDS),
            supported_resolutions=["1080p", "4K"],
            supports_first_frame=True,
            supports_last_frame=False,
            max_duration_seconds=max(SUPPORTED_DURATIONS_SECONDS),
            typical_latency_seconds=60.0,
            cost_tier="premium",
            best_for=[
                "Physics-accurate video (when live)",
                "High-fidelity motion",
            ],
            not_recommended_for=[
                "Production use — stub only, API EOL 2026-09-24",
                "Any use: prefer Veo 3.1 Standard",
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
        """Always raises NotImplementedError per DECISIONS D010."""
        raise NotImplementedError(_SORA_NOT_IMPLEMENTED_MSG)

    async def get_status(self, job_id: str) -> VideoJobResult:
        """Always raises NotImplementedError per DECISIONS D010."""
        raise NotImplementedError(_SORA_NOT_IMPLEMENTED_MSG)
