"""
Veo 3.1 video generation provider — STUB IMPLEMENTATION.

Three parameterized tiers: standard, fast, lite.
Each returns a fake job_id and advances from pending → complete after ~2 wallclock seconds.

Phase 2a skeleton — no real API calls are made. Live wiring lands in Phase 2a.2.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from ..config.constants import SUPPORTED_DURATIONS_SECONDS, VEO_MODELS
from ..exceptions import JobNotFoundError
from .base import JobStore, VideoCapabilities, VideoJobResult, VideoProvider

logger = logging.getLogger(__name__)

_STUB_COMPLETE_DELAY_SECONDS = 2.0  # wall-clock seconds before stub transitions to "complete"


class VeoProvider(VideoProvider):
    """Veo 3.1 video generation provider, parameterized by tier.

    Usage:
        VeoProvider("standard")   # veo-3.1-standard — 4K, $0.40/sec
        VeoProvider("fast")       # veo-3.1-fast     — 1080p, $0.15/sec
        VeoProvider("lite")       # veo-3.1-lite      — 1080p, $0.05/sec
    """

    def __init__(self, tier: str) -> None:
        if tier not in ("standard", "fast", "lite"):
            raise ValueError(f"Unknown Veo tier: '{tier}'. Choose from: standard, fast, lite")
        self._tier = tier
        self._model_key = f"veo-3.1-{tier}"
        self._model_info = VEO_MODELS[self._model_key]
        self._capabilities: VideoCapabilities | None = None

    @property
    def name(self) -> str:
        return self._model_key

    @property
    def capabilities(self) -> VideoCapabilities:
        if self._capabilities is None:
            info = self._model_info
            max_res = str(info["max_resolution"])
            resolutions = ["4K", "1080p", "720p"] if max_res == "4K" else ["1080p", "720p"]
            self._capabilities = VideoCapabilities(
                name=self._model_key,
                display_name=str(info["marketing_name"]),
                supported_durations=list(SUPPORTED_DURATIONS_SECONDS),
                supported_resolutions=resolutions,
                supports_first_frame=True,
                supports_last_frame=True,
                max_duration_seconds=max(SUPPORTED_DURATIONS_SECONDS),
                typical_latency_seconds=30.0 if self._tier == "standard" else 20.0,
                cost_tier=str(info["tier"]),
                best_for=[
                    "Cinematic video generation",
                    "Marketing and promotional content",
                    "Creative storytelling",
                    "Image-to-video (first-frame conditioning)",
                ],
                not_recommended_for=[
                    "Real-time or interactive output",
                    "Sub-second latency requirements",
                ],
                supports_audio=True,  # Veo 3.1 has native audio generation
            )
        return self._capabilities

    async def submit(
        self,
        prompt: str,
        *,
        first_frame: str | None = None,
        duration: float | None = None,
        aspect_ratio: str | None = None,
        **kwargs: Any,
    ) -> VideoJobResult:
        """Submit a Veo 3.1 generation job.

        STUB: returns a fake job_id and schedules completion after 2 wallclock seconds.
        No real API call is made.

        # TODO(live-wiring): call google-genai generate_videos() here.
        # from google import genai
        # client = genai.Client(api_key=api_key)
        # operation = client.models.generate_videos(
        #     model=self._model_key,
        #     prompt=prompt,
        #     config=genai.types.GenerateVideosConfig(
        #         aspect_ratio=aspect_ratio or "16:9",
        #         duration_seconds=int(duration or 8),
        #     ),
        # )
        # return VideoJobResult(job_id=operation.name, status="submitted", ...)
        """
        self._validate_prompt(prompt)
        validated_duration = self._validate_duration(duration)
        validated_aspect = self._validate_aspect_ratio(aspect_ratio)

        job_id = f"stub_veo_{self._tier}_{uuid4().hex[:12]}"
        now = time.time()
        submitted_at = datetime.now()

        JobStore.register(
            job_id,
            self.name,
            {
                "complete_at": now + _STUB_COMPLETE_DELAY_SECONDS,
                "submitted_at_ts": now,
                "submitted_at_iso": submitted_at.isoformat(),
                "prompt": prompt,
                "duration_seconds": validated_duration,
                "aspect_ratio": validated_aspect,
                "tier": self._tier,
                "has_first_frame": first_frame is not None,
            },
        )

        logger.info(
            "Veo stub job submitted: job_id=%s tier=%s duration=%.1fs aspect=%s",
            job_id,
            self._tier,
            validated_duration,
            validated_aspect,
        )

        return VideoJobResult(
            job_id=job_id,
            provider=self.name,
            model=self._model_key,
            status="submitted",
            progress=0.0,
            prompt=prompt,
            duration_seconds=validated_duration,
            submitted_at=submitted_at,
        )

    async def get_status(self, job_id: str) -> VideoJobResult:
        """Poll the status of a Veo stub job.

        STUB: returns 'pending' until 2 wallclock seconds have passed since
        submission, then returns 'complete' with a placeholder output_url.

        # TODO(live-wiring): poll google-genai operation status here.
        # operation = client.operations.get(name=job_id)
        # if operation.done: return complete result
        # else: return pending with progress
        """
        if not JobStore.exists(job_id):
            raise JobNotFoundError(
                f"Video job '{job_id}' not found in JobStore.",
                provider=self.name,
                user_message=(
                    f"Video job '{job_id}' not found. "
                    "The job may have expired or the ID is incorrect. "
                    "Submit a new job via generate_video."
                ),
            )

        metadata = JobStore.get_metadata(job_id) or {}
        complete_at: float = float(metadata.get("complete_at", 0.0))
        prompt: str = str(metadata.get("prompt", ""))
        duration_seconds: float = float(metadata.get("duration_seconds", 8.0))
        submitted_at_iso: str = str(metadata.get("submitted_at_iso", datetime.now().isoformat()))
        submitted_at = datetime.fromisoformat(submitted_at_iso)

        now = time.time()

        if now >= complete_at:
            completed_at = datetime.now()
            logger.info("Veo stub job complete: job_id=%s", job_id)
            return VideoJobResult(
                job_id=job_id,
                provider=self.name,
                model=self._model_key,
                status="complete",
                progress=1.0,
                output_url=f"https://stub.example.com/video/{job_id}.mp4",
                prompt=prompt,
                duration_seconds=duration_seconds,
                submitted_at=submitted_at,
                completed_at=completed_at,
            )
        else:
            elapsed = now - (complete_at - _STUB_COMPLETE_DELAY_SECONDS)
            progress = max(0.0, min(0.99, elapsed / _STUB_COMPLETE_DELAY_SECONDS))
            logger.debug("Veo stub job pending: job_id=%s progress=%.2f", job_id, progress)
            return VideoJobResult(
                job_id=job_id,
                provider=self.name,
                model=self._model_key,
                status="pending",
                progress=progress,
                prompt=prompt,
                duration_seconds=duration_seconds,
                submitted_at=submitted_at,
            )
