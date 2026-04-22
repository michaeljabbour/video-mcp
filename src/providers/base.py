"""
Abstract base class and core data models for video generation providers.

Implements the VideoProvider ABC from DECISIONS D021, including:
- VideoCapabilities dataclass
- VideoJobResult dataclass
- VideoProvider ABC with abstract submit() / get_status() and concrete helpers
- JobStore in-memory singleton (job_id -> provider_name + metadata)
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from ..config.constants import (
    MAX_PROMPT_LENGTH,
    MAX_RETRIES,
    SUPPORTED_ASPECTS,
    SUPPORTED_DURATIONS_SECONDS,
)
from ..exceptions import ValidationError

logger = logging.getLogger(__name__)


# ============================
# In-memory Job Store
# ============================


class JobStore:
    """In-memory store mapping job_id -> provider_name + metadata.

    A single module-level class with class-method interface acts as the
    singleton store for the process lifetime. SQLite persistence is a
    future enhancement (Phase 2a.2+).
    """

    _store: dict[str, dict[str, Any]] = {}

    @classmethod
    def register(
        cls,
        job_id: str,
        provider_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a new job."""
        cls._store[job_id] = {
            "provider_name": provider_name,
            **(metadata or {}),
        }

    @classmethod
    def get_provider_name(cls, job_id: str) -> str | None:
        """Return the provider name for a job, or None if unknown."""
        entry = cls._store.get(job_id)
        if entry is None:
            return None
        result: str = entry["provider_name"]
        return result

    @classmethod
    def get_metadata(cls, job_id: str) -> dict[str, Any] | None:
        """Return all metadata for a job, or None if unknown."""
        entry = cls._store.get(job_id)
        if entry is None:
            return None
        return dict(entry)

    @classmethod
    def exists(cls, job_id: str) -> bool:
        """Return True if the job_id is known."""
        return job_id in cls._store

    @classmethod
    def clear(cls) -> None:
        """Clear all jobs. Used in tests."""
        cls._store.clear()


# ============================
# Capability / Result Dataclasses
# ============================


@dataclass
class VideoCapabilities:
    """Describes what a video provider can do.

    Matches the shape from DECISIONS D021 with the additional
    ``not_recommended_for`` and ``supports_audio`` fields.
    """

    name: str
    display_name: str

    # Supported generation parameters
    supported_durations: list[float]
    supported_resolutions: list[str]

    # Frame conditioning support
    supports_first_frame: bool
    supports_last_frame: bool

    # Limits
    max_duration_seconds: float

    # Performance characteristics
    typical_latency_seconds: float
    cost_tier: str  # e.g. "standard", "fast", "lite"

    # Best-fit guidance
    best_for: list[str] = field(default_factory=list)
    not_recommended_for: list[str] = field(default_factory=list)

    # Veo-specific: native audio generation
    supports_audio: bool = False


@dataclass
class VideoJobResult:
    """Result from a video generation job submission or status poll.

    Verbatim from DECISIONS D021 plus ``submitted_at`` and ``completed_at``
    timestamps added for provenance tracking.
    """

    job_id: str
    provider: str
    model: str
    status: str  # submitted | pending | complete | failed

    progress: float | None = None
    output_url: str | None = None
    last_frame_url: str | None = None
    usage: dict[str, Any] | None = None
    error_code: str | None = None
    retry_hint: str | None = None
    prompt: str = ""
    duration_seconds: float | None = None

    # Timestamps (added beyond D021 for provenance)
    submitted_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (for JSON output and provenance records)."""
        return {
            "job_id": self.job_id,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "progress": self.progress,
            "output_url": self.output_url,
            "last_frame_url": self.last_frame_url,
            "usage": self.usage,
            "error_code": self.error_code,
            "retry_hint": self.retry_hint,
            "prompt": self.prompt,
            "duration_seconds": self.duration_seconds,
            "submitted_at": self.submitted_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ============================
# Abstract Base Class
# ============================


class VideoProvider(ABC):
    """Abstract base class for video generation providers.

    Per DECISIONS D021: providers are MCP-internal ABCs, not Amplifier
    Provider protocol implementations. The MCP Tool boundary is the only
    integration point with Amplifier.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Canonical provider identifier (e.g. 'veo-3.1-standard')."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> VideoCapabilities:
        """Provider capabilities and feature support."""
        ...

    @abstractmethod
    async def submit(
        self,
        prompt: str,
        *,
        first_frame: str | None = None,
        duration: float | None = None,
        aspect_ratio: str | None = None,
        **kwargs: Any,
    ) -> VideoJobResult:
        """Submit a generation job. Returns immediately with a job_id.

        Args:
            prompt: Text description of the desired video.
            first_frame: Optional base64 PNG for image-to-video.
            duration: Duration in seconds (4, 6, 8, or 16).
            aspect_ratio: '16:9' or '9:16'.
            **kwargs: Provider-specific parameters.

        Returns:
            VideoJobResult with status='submitted' and a job_id.
        """
        ...

    @abstractmethod
    async def get_status(self, job_id: str) -> VideoJobResult:
        """Poll the status of a previously submitted job.

        Args:
            job_id: The ID returned by submit().

        Returns:
            VideoJobResult with current status.

        Raises:
            JobNotFoundError: If job_id is unknown.
        """
        ...

    async def close(self) -> None:  # noqa: B027
        """Clean up provider resources. Default implementation is a no-op."""
        pass

    def to_provenance_record(self, result: VideoJobResult) -> dict[str, Any]:
        """Return a provenance record dict for audit logging (D007 pattern)."""
        return {
            "provider": result.provider,
            "model": result.model,
            "job_id": result.job_id,
            "status": result.status,
            "output_url": result.output_url,
            "prompt": result.prompt,
            "duration_seconds": result.duration_seconds,
            "submitted_at": result.submitted_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
        }

    def _generate_job_id(self, prefix: str = "") -> str:
        """Generate a unique job ID."""
        token = uuid4().hex[:12]
        return f"{prefix}{token}" if prefix else token

    def _validate_prompt(self, prompt: str) -> None:
        """Raise ValidationError if prompt is empty or too long."""
        if not prompt or not prompt.strip():
            raise ValidationError("Prompt cannot be empty.")
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValidationError(
                f"Prompt too long ({len(prompt)} chars). Maximum is {MAX_PROMPT_LENGTH} characters."
            )

    def _validate_duration(self, duration: float | None) -> float:
        """Validate and return a supported duration (default 8.0s)."""
        if duration is None:
            return 8.0
        if duration not in SUPPORTED_DURATIONS_SECONDS:
            raise ValidationError(
                f"Duration {duration}s is not supported. Choose from: {SUPPORTED_DURATIONS_SECONDS}"
            )
        return duration

    def _validate_aspect_ratio(self, aspect_ratio: str | None) -> str:
        """Validate and return a supported aspect ratio (default '16:9')."""
        if aspect_ratio is None:
            return "16:9"
        if aspect_ratio not in SUPPORTED_ASPECTS:
            raise ValidationError(
                f"Aspect ratio '{aspect_ratio}' is not supported. Choose from: {SUPPORTED_ASPECTS}"
            )
        return aspect_ratio

    async def _retry_with_backoff(
        self,
        func: Any,
        *args: Any,
        max_retries: int = MAX_RETRIES,
        base_delay: float = 1.0,
        **kwargs: Any,
    ) -> Any:
        """Execute an async function with exponential backoff retry.

        Args:
            func: Async function to execute.
            *args: Positional arguments for func.
            max_retries: Maximum retry attempts.
            base_delay: Base delay between retries (doubles each attempt).
            **kwargs: Keyword arguments for func.

        Returns:
            Result of func.

        Raises:
            Last exception if all retries fail.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)

        raise last_error if last_error else RuntimeError("Retry failed with no error")
