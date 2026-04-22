"""
Veo 3.1 video generation provider — LIVE IMPLEMENTATION (Phase 2a.2).

Three parameterized tiers: standard, fast, lite.
Wires real google-genai SDK calls for submit() and get_status().

Architecture notes (Phase 2a.2):
- SDK calls (generate_videos, operations.get) are SYNCHRONOUS; run via asyncio.to_thread.
- Video data arrives as either inline bytes (video.video_bytes) or a GCS/HTTPS URI
  (video.uri). URI case is downloaded via httpx (noted in implementation report).
- D025 path guard runs before every disk write.
- D024 billing reminder is logged once per provider instance on first submit().

SDK DISCREPANCIES (reported — not silently resolved):
  1. Model IDs: constants.py uses veo-3.1-standard / veo-3.1-fast / veo-3.1-lite but
     the SDK's own test file confirms the live API model ID is "veo-3.1-generate-preview"
     (VEO_MODEL_LATEST in tests/models/test_generate_videos.py). The constants keys are
     passed as-is per spec instruction ("model = canonical Veo tier ID from VEO_MODELS").
     A mapping table will be needed before hitting the live API. See DECISIONS tracker.
  2. operations.get() signature: spec documents client.operations.get(name=job_id) but
     the installed SDK (v1.73.1) accepts client.operations.get(operation: T) where T is
     a GenerateVideosOperation instance. We reconstruct the object from the stored name.
  3. Both generate_videos() and operations.get() are synchronous (not async).
     They are wrapped in asyncio.to_thread() throughout.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ..config.constants import SUPPORTED_DURATIONS_SECONDS, VEO_MODELS
from ..config.paths import resolve_output_path
from ..config.settings import get_settings
from ..exceptions import (
    AuthenticationError,
    ConfigurationError,
    GenerationError,
    JobNotFoundError,
    RateLimitError,
    ValidationError,
)
from .base import JobStore, VideoCapabilities, VideoJobResult, VideoProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy SDK imports — mirrors imagen-mcp/src/providers/gemini_provider.py pattern
# ---------------------------------------------------------------------------
genai: Any = None
genai_types: Any = None
genai_errors: Any = None

# D025 forbidden prefixes, computed once on first use
_D025_FORBIDDEN_PREFIXES: tuple[str, ...] | None = None


def _import_dependencies() -> None:
    """Lazily import google-genai SDK dependencies.

    Keeps the module importable even when the SDK is not installed,
    and avoids import-time side-effects.
    """
    global genai, genai_types, genai_errors
    if genai is None:
        try:
            from google import genai as _genai  # type: ignore[attr-defined]
            from google.genai import errors as _errors  # type: ignore[import-untyped]
            from google.genai import types as _types  # type: ignore[import-untyped]

            genai = _genai
            genai_types = _types
            genai_errors = _errors
        except ImportError as e:
            raise ImportError(
                "VeoProvider requires the google-genai package. "
                "Install with: pip install google-genai"
            ) from e


def _get_forbidden_prefixes() -> tuple[str, ...]:
    """Build the D025 forbidden path prefix list (computed once and cached)."""
    global _D025_FORBIDDEN_PREFIXES
    if _D025_FORBIDDEN_PREFIXES is None:
        home = Path.home()
        tmpdir_env = os.environ.get("TMPDIR", "")
        package_root = Path(__file__).parent.parent.resolve()
        prefixes = [
            "/tmp",
            str((home / ".cache").resolve()),
            str((home / ".amplifier").resolve()),
            str(package_root),
        ]
        if tmpdir_env:
            prefixes.append(str(Path(tmpdir_env).resolve()))
        _D025_FORBIDDEN_PREFIXES = tuple(prefixes)
    return _D025_FORBIDDEN_PREFIXES


def _check_d025(resolved_path: Path) -> None:
    """Raise ValidationError if resolved_path lands in a D025 forbidden location.

    Forbidden locations (per DECISIONS D025):
    - /tmp  (and $TMPDIR if set)
    - ~/.cache/
    - ~/.amplifier/
    - Inside the video-mcp package directory itself
    """
    resolved_str = str(resolved_path)
    for forbidden in _get_forbidden_prefixes():
        if resolved_str == forbidden or resolved_str.startswith(forbidden + "/"):
            raise ValidationError(
                f"Output path '{resolved_path}' resolves to a forbidden location (D025). "
                "Video outputs must not be written to /tmp, $TMPDIR, ~/.cache/, "
                "~/.amplifier/, or inside the video-mcp package directory. "
                "Use ~/Downloads/videos/<tier>/ or set OUTPUT_DIR to a safe path."
            )


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------


class VeoProvider(VideoProvider):
    """Veo 3.1 video generation provider, parameterized by tier.

    Phase 2a.2: Live google-genai SDK integration replaces stub behaviour.

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
        self._client: Any = None
        self._active_api_key: str | None = None
        self._billing_warning_issued = False

    # ------------------------------------------------------------------
    # VideoProvider abstract properties
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_client(self) -> Any:
        """Initialize (or return existing) google-genai Client.

        Re-initializes if the API key has changed (supports per-request key
        override via settings, mirroring imagen-mcp's pattern).
        """
        _import_dependencies()
        settings = get_settings()
        try:
            api_key = settings.get_gemini_api_key()
        except ValueError as exc:
            raise ConfigurationError(
                f"Gemini API key not available for Veo: {exc}",
                user_message=(
                    "Set the GEMINI_API_KEY environment variable to use Veo. "
                    "The key must be tied to an active Cloud Billing account."
                ),
            ) from exc

        if self._client is None or api_key != self._active_api_key:
            self._client = genai.Client(api_key=api_key)
            self._active_api_key = api_key

        return self._client

    def _issue_billing_warning(self) -> None:
        """Log D024 billing/training reminder once per provider instance."""
        if not self._billing_warning_issued:
            logger.info(
                "Veo invocations expect the Gemini API key to be tied to an active "
                "Cloud Billing account; free-tier usage feeds Google training data. "
                "(D024 runtime reminder — the Amplifier bundle gates consent in Phase 2b.)"
            )
            self._billing_warning_issued = True

    def _resolve_frame_image(self, frame: str | None) -> Any:
        """Resolve a frame reference to a genai types.Image, or None.

        Accepted formats:
        - Data URI: ``"data:image/png;base64,<b64data>"``
        - Filesystem path: ``"/path/to/image.png"`` or ``"~/photo.png"``
        - GCS URI: ``"gs://bucket/image.png"``
        - None: returns None
        """
        if frame is None:
            return None

        _import_dependencies()

        if frame.startswith("data:"):
            # Parse data URI: data:<mime>;base64,<data>
            try:
                header, encoded = frame.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
                image_bytes = base64.b64decode(encoded)
                return genai_types.Image(image_bytes=image_bytes, mime_type=mime_type)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse data URI frame: %s", exc)
                return None

        if frame.startswith("gs://"):
            return genai_types.Image(gcs_uri=frame)

        # Treat as filesystem path
        path = Path(frame).expanduser()
        if path.exists():
            mime_type, _ = mimetypes.guess_type(str(path))
            return genai_types.Image(
                image_bytes=path.read_bytes(),
                mime_type=mime_type or "image/png",
            )

        logger.warning("Frame path does not exist or is not a supported URI: %s", frame)
        return None

    async def _write_video_bytes(
        self,
        data: bytes,
        output_path: str | None,
        filename_hint: str,
    ) -> Path:
        """Write video bytes to disk, enforcing D025 path rules.

        Args:
            data: Raw video bytes to write.
            output_path: Caller-supplied path (directory or file), or None for default.
            filename_hint: Suggested filename when output_path resolves to a directory.

        Returns:
            Resolved absolute path where the file was written.

        Raises:
            ValidationError: If output_path resolves to a D025-forbidden location.
        """
        save_path = resolve_output_path(
            output_path,
            default_filename=filename_hint,
            provider=self._tier,
        )

        # D025 defense-in-depth: check the fully-resolved absolute path
        _check_d025(save_path.resolve())

        # Async write to avoid blocking the event loop on large files
        def _write() -> None:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(data)

        await asyncio.to_thread(_write)
        logger.info("Video written: %s", save_path)
        return save_path

    async def _download_video_uri(self, uri: str) -> bytes:
        """Download video from a GCS or HTTPS URI using httpx.

        The google-genai SDK returns video data as either inline ``video_bytes``
        or a GCS/HTTPS ``uri``. When only a URI is returned we use httpx for
        the download step (documented in implementation report).
        """
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            response = await http_client.get(uri)
            response.raise_for_status()
            return response.content

    def _map_sdk_error(self, exc: Exception) -> Exception:
        """Map google-genai SDK exceptions to the video-mcp exception hierarchy."""
        _import_dependencies()

        if isinstance(exc, genai_errors.ClientError):
            code: int = getattr(exc, "code", 0)
            if code in (401, 403):
                return AuthenticationError(
                    f"Gemini API authentication failed (HTTP {code}): {exc}",
                    provider=self.name,
                    status_code=code,
                    user_message=(
                        "Gemini API key is invalid or lacks active Cloud Billing. "
                        "Verify GEMINI_API_KEY and billing account status."
                    ),
                )
            if code == 429:
                retry_after: float | None = None
                response_obj = getattr(exc, "response", None)
                if response_obj is not None:
                    headers = getattr(response_obj, "headers", {}) or {}
                    ra = headers.get("Retry-After") or headers.get("retry-after")
                    if ra:
                        try:
                            retry_after = float(ra)
                        except (ValueError, TypeError):
                            pass
                return RateLimitError(
                    f"Gemini API rate limit exceeded: {exc}",
                    provider=self.name,
                    status_code=code,
                    retry_after=retry_after,
                )

        if isinstance(
            exc,
            (genai_errors.ClientError, genai_errors.ServerError, genai_errors.APIError),
        ):
            return GenerationError(
                f"Gemini API error during Veo generation: {exc}",
                provider=self.name,
                status_code=getattr(exc, "code", None),
                user_message=(f"Video generation failed: {getattr(exc, 'message', str(exc))}"),
            )

        return exc

    # ------------------------------------------------------------------
    # VideoProvider abstract methods
    # ------------------------------------------------------------------

    async def submit(
        self,
        prompt: str,
        *,
        first_frame: str | None = None,
        last_frame: str | None = None,
        duration: float | None = None,
        aspect_ratio: str | None = None,
        output_path: str | None = None,
        **kwargs: Any,
    ) -> VideoJobResult:
        """Submit a Veo 3.1 generation job via the google-genai SDK.

        Returns immediately after the SDK acknowledges the job (D018 async pattern).
        The operation runs on Google's backend; poll via get_status().

        Args:
            prompt: Text description of the desired video.
            first_frame: Image for I2V conditioning — data URI, filesystem path, or
                GCS URI (``gs://...``). If omitted, text-to-video mode is used.
            last_frame: Image for last-frame conditioning (same formats as first_frame).
                Veo-specific; ignored by other providers.
            duration: Duration in seconds (4, 6, 8, or 16). Defaults to 8.
            aspect_ratio: ``'16:9'`` or ``'9:16'``. Defaults to ``'16:9'``.
            output_path: Where to save the downloaded video when complete (D025-governed).
                If None, defaults to ``~/Downloads/videos/<tier>/``.
            **kwargs: Optional overrides: ``resolution`` (str).

        Returns:
            VideoJobResult with ``status='submitted'`` and ``job_id = operation.name``.

        Raises:
            ValidationError: If prompt, duration, or aspect_ratio is invalid.
            ConfigurationError: If Gemini API key is not configured.
            AuthenticationError: If the API key is rejected (401/403).
            RateLimitError: If the API quota is exhausted (429).
            GenerationError: For other API-level failures.
        """
        self._validate_prompt(prompt)
        validated_duration = self._validate_duration(duration)
        validated_aspect = self._validate_aspect_ratio(aspect_ratio)
        self._issue_billing_warning()

        client = self._ensure_client()
        submitted_at = datetime.now()

        # Resolve optional frame images to genai Image objects
        first_frame_image = self._resolve_frame_image(first_frame)
        last_frame_image = self._resolve_frame_image(last_frame)

        # Build GenerateVideosConfig
        config_kwargs: dict[str, Any] = {
            "duration_seconds": int(validated_duration),
            "aspect_ratio": validated_aspect,
        }
        resolution = kwargs.get("resolution") or str(
            self._model_info.get("max_resolution", "1080p")
        )
        config_kwargs["resolution"] = resolution

        if last_frame_image is not None:
            config_kwargs["last_frame"] = last_frame_image

        _import_dependencies()
        config = genai_types.GenerateVideosConfig(**config_kwargs)

        # Build generate_videos call arguments
        call_kwargs: dict[str, Any] = {
            "model": self._model_key,
            "prompt": prompt,
            "config": config,
        }
        if first_frame_image is not None:
            call_kwargs["image"] = first_frame_image

        # SDK call is synchronous — run in thread executor per D018 async pattern
        try:
            operation = await asyncio.to_thread(
                lambda: client.models.generate_videos(**call_kwargs)
            )
        except Exception as exc:
            mapped = self._map_sdk_error(exc)
            if mapped is exc:
                raise GenerationError(
                    f"Unexpected error submitting Veo job: {exc}",
                    provider=self.name,
                ) from exc
            raise mapped from exc

        # operation.name is the canonical job ID used for polling
        job_id: str = operation.name or f"veo_{self._tier}_{id(operation)}"

        # Persist all metadata needed by get_status()
        JobStore.register(
            job_id,
            self.name,
            {
                "operation_name": job_id,
                "submitted_at_iso": submitted_at.isoformat(),
                "prompt": prompt,
                "duration_seconds": validated_duration,
                "aspect_ratio": validated_aspect,
                "tier": self._tier,
                "output_path": output_path,
                "has_first_frame": first_frame is not None,
                "has_last_frame": last_frame is not None,
            },
        )

        logger.info(
            "Veo job submitted: job_id=%s tier=%s duration=%.1fs aspect=%s",
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
        """Poll the status of a Veo generation job via the google-genai SDK.

        Calls ``client.operations.get(operation)`` where the operation object is
        reconstructed from the stored ``operation_name``. The SDK only uses
        ``operation.name`` internally, so this is safe.

        Args:
            job_id: The operation name returned by submit().

        Returns:
            VideoJobResult with current status (pending/complete/failed).
            On ``status='complete'``, ``output_url`` is a ``file://`` URI pointing
            to the downloaded video on disk.

        Raises:
            JobNotFoundError: If job_id is unknown.
            AuthenticationError: On 401/403.
            RateLimitError: On 429.
            GenerationError: For other API failures.
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
        operation_name: str = str(metadata.get("operation_name", job_id))
        prompt: str = str(metadata.get("prompt", ""))
        duration_seconds: float = float(metadata.get("duration_seconds", 8.0))
        submitted_at_iso: str = str(metadata.get("submitted_at_iso", datetime.now().isoformat()))
        submitted_at = datetime.fromisoformat(submitted_at_iso)
        output_path: str | None = metadata.get("output_path")

        client = self._ensure_client()

        # Reconstruct the operation object from the stored name.
        # operations.get() only uses operation.name internally (SDK discrepancy #2).
        _import_dependencies()
        stub_op = genai_types.GenerateVideosOperation(name=operation_name)

        try:
            operation = await asyncio.to_thread(lambda: client.operations.get(stub_op))
        except Exception as exc:
            mapped = self._map_sdk_error(exc)
            if mapped is exc:
                raise GenerationError(
                    f"Unexpected error polling Veo job: {exc}",
                    provider=self.name,
                ) from exc
            raise mapped from exc

        # --- Map operation state to VideoJobResult ---

        if not operation.done:
            # Parse optional progress from operation metadata dict
            progress: float | None = None
            meta = operation.metadata or {}
            if isinstance(meta, dict):
                pct = meta.get("progressPercent") or meta.get("progress_percent")
                if pct is not None:
                    try:
                        progress = min(1.0, max(0.0, float(pct) / 100.0))
                    except (ValueError, TypeError):
                        pass

            logger.debug("Veo job pending: job_id=%s progress=%s", job_id, progress)
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

        # operation.done is True — check for error
        if operation.error:
            error_info = operation.error
            if isinstance(error_info, dict):
                error_code = str(error_info.get("code", "UNKNOWN"))
            else:
                error_code = str(getattr(error_info, "code", "UNKNOWN"))
            logger.error("Veo job failed: job_id=%s error=%s", job_id, error_info)
            return VideoJobResult(
                job_id=job_id,
                provider=self.name,
                model=self._model_key,
                status="failed",
                prompt=prompt,
                duration_seconds=duration_seconds,
                submitted_at=submitted_at,
                error_code=error_code,
                retry_hint=(
                    "Re-submit the job. If the error persists, check the prompt "
                    "for policy violations or reduce duration/resolution."
                ),
            )

        # Successful completion — extract and download video
        response = operation.response or operation.result
        local_path: Path | None = None

        if response and response.generated_videos:
            gen_video = response.generated_videos[0]
            video_obj = gen_video.video if gen_video else None

            if video_obj:
                # Use trailing 8 chars of job_id as a stable short identifier
                short_id = job_id[-8:].replace("/", "_").replace(".", "_")
                filename_hint = f"veo_{self._tier}_{short_id}.mp4"

                if video_obj.video_bytes:
                    # Inline bytes — write directly
                    local_path = await self._write_video_bytes(
                        video_obj.video_bytes,
                        output_path,
                        filename_hint,
                    )
                elif video_obj.uri:
                    # GCS / HTTPS URI — download via httpx (see module docstring)
                    logger.info("Downloading Veo video from URI: %s", video_obj.uri)
                    video_bytes = await self._download_video_uri(video_obj.uri)
                    local_path = await self._write_video_bytes(
                        video_bytes,
                        output_path,
                        filename_hint,
                    )

        output_url: str | None = f"file://{local_path}" if local_path else None
        completed_at = datetime.now()

        logger.info("Veo job complete: job_id=%s output=%s", job_id, local_path)

        return VideoJobResult(
            job_id=job_id,
            provider=self.name,
            model=self._model_key,
            status="complete",
            progress=1.0,
            output_url=output_url,
            last_frame_url=None,
            usage={"tier": self._tier, "duration_seconds": duration_seconds},
            prompt=prompt,
            duration_seconds=duration_seconds,
            submitted_at=submitted_at,
            completed_at=completed_at,
        )
