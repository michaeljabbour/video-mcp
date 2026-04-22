"""Tests for video provider implementations.

Phase 2a.2: VeoProvider tests use mocked google-genai SDK.
Sora/Grok stub tests remain unchanged.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Set dummy API keys BEFORE any src imports so settings cache is populated correctly
os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")

from src.exceptions import JobNotFoundError, ValidationError  # type: ignore
from src.providers.base import JobStore, VideoCapabilities, VideoJobResult  # type: ignore
from src.providers.grok_provider import GrokProvider  # type: ignore
from src.providers.registry import ProviderRegistry  # type: ignore
from src.providers.sora_provider import SoraProvider  # type: ignore
from src.providers.veo_provider import VeoProvider  # type: ignore

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_job_store():
    """Clear the JobStore before each test to avoid state leakage."""
    JobStore.clear()
    yield
    JobStore.clear()


@pytest.fixture
def mock_sdk(monkeypatch):
    """Replace lazy-loaded google-genai module globals with safe mocks.

    Returns the mock ``genai.Client`` instance.  Tests should configure
    ``mock_sdk.models.generate_videos.return_value`` etc. as needed.
    """
    import src.providers.veo_provider as veo_mod

    # ---- Fake error classes so isinstance() checks work in _map_sdk_error ----
    class FakeAPIError(Exception):
        def __init__(self, code: int = 500, message: str = "error"):
            self.code = code
            self.message = message
            self.response = None
            super().__init__(f"{code}: {message}")

    class FakeClientError(FakeAPIError):
        pass

    class FakeServerError(FakeAPIError):
        pass

    mock_client = MagicMock()
    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client

    mock_types = MagicMock()
    mock_errors = MagicMock()
    mock_errors.APIError = FakeAPIError
    mock_errors.ClientError = FakeClientError
    mock_errors.ServerError = FakeServerError

    monkeypatch.setattr(veo_mod, "genai", mock_genai)
    monkeypatch.setattr(veo_mod, "genai_types", mock_types)
    monkeypatch.setattr(veo_mod, "genai_errors", mock_errors)
    monkeypatch.setattr(veo_mod, "_import_dependencies", lambda: None)

    return mock_client


@pytest.fixture
def sync_to_thread(monkeypatch):
    """Replace asyncio.to_thread with a synchronous equivalent.

    The veo_provider wraps synchronous SDK calls in asyncio.to_thread.
    This fixture makes those calls run synchronously so tests can control
    return values directly via mock_sdk.
    """

    async def _fake_to_thread(func, *args, **kwargs):
        # Execute the callable synchronously (it's already mocked)
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)


# ---------------------------------------------------------------------------
# Veo Provider — name and capabilities (no SDK involved)
# ---------------------------------------------------------------------------


class TestVeoProviderName:
    """Provider name matches canonical IDs."""

    def test_standard_name(self) -> None:
        assert VeoProvider("standard").name == "veo-3.1-standard"

    def test_fast_name(self) -> None:
        assert VeoProvider("fast").name == "veo-3.1-fast"

    def test_lite_name(self) -> None:
        assert VeoProvider("lite").name == "veo-3.1-lite"

    def test_invalid_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown Veo tier"):
            VeoProvider("ultra")


class TestVeoCapabilitiesPopulated:
    """Each tier's capabilities match VEO_MODELS dict entries."""

    def test_standard_capabilities(self) -> None:
        caps = VeoProvider("standard").capabilities
        assert isinstance(caps, VideoCapabilities)
        assert caps.name == "veo-3.1-standard"
        assert "Veo 3.1 Standard" in caps.display_name
        assert "4K" in caps.supported_resolutions
        assert caps.supports_first_frame is True
        assert caps.supports_last_frame is True
        assert caps.supports_audio is True
        assert caps.cost_tier == "standard"

    def test_fast_capabilities(self) -> None:
        caps = VeoProvider("fast").capabilities
        assert caps.name == "veo-3.1-fast"
        assert "Fast" in caps.display_name
        assert caps.cost_tier == "fast"
        assert caps.supports_audio is True
        assert 8.0 in caps.supported_durations

    def test_lite_capabilities(self) -> None:
        caps = VeoProvider("lite").capabilities
        assert caps.name == "veo-3.1-lite"
        assert "Lite" in caps.display_name
        assert caps.cost_tier == "lite"
        assert caps.max_duration_seconds == 16.0

    def test_capabilities_have_durations(self) -> None:
        for tier in ("standard", "fast", "lite"):
            caps = VeoProvider(tier).capabilities
            assert len(caps.supported_durations) > 0
            assert 8.0 in caps.supported_durations

    def test_capabilities_have_best_for(self) -> None:
        caps = VeoProvider("standard").capabilities
        assert len(caps.best_for) > 0


# ---------------------------------------------------------------------------
# Veo Provider — submit() validation (no SDK involved)
# ---------------------------------------------------------------------------


class TestVeoSubmitValidation:
    """Input validation in submit() fires before any SDK call."""

    async def test_submit_validates_empty_prompt(self) -> None:
        provider = VeoProvider("standard")
        with pytest.raises(ValidationError, match="empty"):
            await provider.submit("")

    async def test_submit_rejects_invalid_duration(self) -> None:
        provider = VeoProvider("standard")
        with pytest.raises(ValidationError, match="not supported"):
            await provider.submit("A clip", duration=7.0)

    async def test_submit_rejects_invalid_aspect_ratio(self) -> None:
        provider = VeoProvider("standard")
        with pytest.raises(ValidationError, match="not supported"):
            await provider.submit("A clip", aspect_ratio="4:3")


# ---------------------------------------------------------------------------
# Veo Provider — submit() with mocked SDK
# ---------------------------------------------------------------------------


class TestVeoSubmitWithSDK:
    """VeoProvider.submit() calls google-genai and returns a valid job result."""

    async def test_submit_returns_job_result(
        self, mock_sdk: MagicMock, sync_to_thread: None
    ) -> None:
        """submit() returns VideoJobResult with status='submitted'."""
        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-standard/operations/test-op-abc"
        mock_sdk.models.generate_videos.return_value = mock_operation

        provider = VeoProvider("standard")
        result = await provider.submit("A serene mountain lake at golden hour")

        assert isinstance(result, VideoJobResult)
        assert result.job_id == "models/veo-3.1-standard/operations/test-op-abc"
        assert result.status == "submitted"
        assert result.provider == "veo-3.1-standard"
        assert result.model == "veo-3.1-standard"
        assert result.submitted_at is not None
        # SDK was called
        mock_sdk.models.generate_videos.assert_called_once()

    async def test_submit_registers_in_job_store(
        self, mock_sdk: MagicMock, sync_to_thread: None
    ) -> None:
        """submit() registers the job in JobStore with provider name."""
        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-fast/operations/fast-op-xyz"
        mock_sdk.models.generate_videos.return_value = mock_operation

        provider = VeoProvider("fast")
        result = await provider.submit("A product commercial")

        assert JobStore.exists(result.job_id)
        assert JobStore.get_provider_name(result.job_id) == "veo-3.1-fast"
        # Metadata should contain the operation_name for get_status()
        meta = JobStore.get_metadata(result.job_id) or {}
        assert meta.get("operation_name") == result.job_id

    async def test_submit_uses_default_duration(
        self, mock_sdk: MagicMock, sync_to_thread: None
    ) -> None:
        """submit() defaults to 8.0s when duration is omitted."""
        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-lite/operations/lite-op-001"
        mock_sdk.models.generate_videos.return_value = mock_operation

        provider = VeoProvider("lite")
        result = await provider.submit("A nature documentary scene")
        assert result.duration_seconds == 8.0

    async def test_submit_accepts_custom_duration(
        self, mock_sdk: MagicMock, sync_to_thread: None
    ) -> None:
        """submit() accepts a valid custom duration."""
        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-standard/operations/dur-op-004"
        mock_sdk.models.generate_videos.return_value = mock_operation

        provider = VeoProvider("standard")
        result = await provider.submit("A short clip", duration=4.0)
        assert result.duration_seconds == 4.0

    async def test_submit_passes_mapped_sdk_model_id_to_sdk(
        self, mock_sdk: MagicMock, sync_to_thread: None
    ) -> None:
        """submit() resolves the tier key → SDK model ID via VEO_SDK_MODEL_IDS and passes
        the resolved ID (not the raw tier key) to generate_videos()."""
        from src.config.constants import VEO_SDK_MODEL_IDS  # type: ignore

        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-generate-preview/operations/model-check"
        mock_sdk.models.generate_videos.return_value = mock_operation

        provider = VeoProvider("standard")
        await provider.submit("Check model key")

        call_kwargs = mock_sdk.models.generate_videos.call_args
        assert call_kwargs is not None
        # Must be the SDK-accepted model ID, NOT the raw tier key "veo-3.1-standard"
        assert call_kwargs.kwargs.get("model") == "veo-3.1-generate-preview"
        assert call_kwargs.kwargs.get("model") == VEO_SDK_MODEL_IDS["veo-3.1-standard"]

    async def test_submit_maps_fast_tier_to_sdk_model_id(
        self, mock_sdk: MagicMock, sync_to_thread: None
    ) -> None:
        """submit() maps veo-3.1-fast tier key to its distinct SDK model ID."""
        from src.config.constants import VEO_SDK_MODEL_IDS  # type: ignore

        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-fast-generate-preview/operations/fast-check"
        mock_sdk.models.generate_videos.return_value = mock_operation

        provider = VeoProvider("fast")
        await provider.submit("Check fast tier model ID")

        call_kwargs = mock_sdk.models.generate_videos.call_args
        assert call_kwargs is not None
        assert call_kwargs.kwargs.get("model") == "veo-3.1-fast-generate-preview"
        assert call_kwargs.kwargs.get("model") == VEO_SDK_MODEL_IDS["veo-3.1-fast"]

    async def test_submit_maps_lite_tier_to_sdk_model_id(
        self, mock_sdk: MagicMock, sync_to_thread: None
    ) -> None:
        """submit() maps veo-3.1-lite tier key to its distinct SDK model ID."""
        from src.config.constants import VEO_SDK_MODEL_IDS  # type: ignore

        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-lite-generate-preview/operations/lite-check"
        mock_sdk.models.generate_videos.return_value = mock_operation

        provider = VeoProvider("lite")
        await provider.submit("Check lite tier model ID")

        call_kwargs = mock_sdk.models.generate_videos.call_args
        assert call_kwargs is not None
        assert call_kwargs.kwargs.get("model") == "veo-3.1-lite-generate-preview"
        assert call_kwargs.kwargs.get("model") == VEO_SDK_MODEL_IDS["veo-3.1-lite"]

    async def test_submit_auth_error_mapped_to_authentication_error(
        self, mock_sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AuthenticationError is raised on 401/403 SDK errors."""
        import src.providers.veo_provider as veo_mod

        class FakeClientError(Exception):
            def __init__(self):
                self.code = 403
                self.message = "Forbidden"
                self.response = None
                super().__init__("403: Forbidden")

        mock_sdk.models.generate_videos.side_effect = FakeClientError()
        monkeypatch.setattr(veo_mod.genai_errors, "ClientError", FakeClientError)
        monkeypatch.setattr(veo_mod.genai_errors, "APIError", Exception)
        monkeypatch.setattr(veo_mod.genai_errors, "ServerError", Exception)

        async def _fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        from src.exceptions import AuthenticationError  # type: ignore

        provider = VeoProvider("standard")
        with pytest.raises(AuthenticationError):
            await provider.submit("Test auth error")

    async def test_submit_rate_limit_mapped_to_rate_limit_error(
        self, mock_sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RateLimitError is raised on 429 SDK errors."""
        import src.providers.veo_provider as veo_mod

        class FakeClientError(Exception):
            def __init__(self):
                self.code = 429
                self.message = "Too Many Requests"
                self.response = None
                super().__init__("429: Too Many Requests")

        mock_sdk.models.generate_videos.side_effect = FakeClientError()
        monkeypatch.setattr(veo_mod.genai_errors, "ClientError", FakeClientError)
        monkeypatch.setattr(veo_mod.genai_errors, "APIError", Exception)
        monkeypatch.setattr(veo_mod.genai_errors, "ServerError", Exception)

        async def _fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        from src.exceptions import RateLimitError  # type: ignore

        provider = VeoProvider("standard")
        with pytest.raises(RateLimitError):
            await provider.submit("Test rate limit")


# ---------------------------------------------------------------------------
# Veo Provider — get_status() with mocked SDK
# ---------------------------------------------------------------------------


class TestVeoGetStatusWithSDK:
    """VeoProvider.get_status() polls google-genai operations correctly."""

    async def test_get_status_unknown_job_raises(self) -> None:
        """JobNotFoundError is raised for unknown job IDs (no SDK needed)."""
        provider = VeoProvider("standard")
        with pytest.raises(JobNotFoundError):
            await provider.get_status("nonexistent_job_id_xyz_abc")

    async def test_get_status_pending(
        self, mock_sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_status() returns status='pending' when operation is not done."""
        mock_submitted_op = MagicMock()
        mock_submitted_op.name = "models/veo-3.1-standard/operations/pending-job"

        mock_pending_op = MagicMock()
        mock_pending_op.done = False
        mock_pending_op.error = None
        mock_pending_op.metadata = {"progressPercent": 30}

        calls: list[str] = []

        async def _fake_to_thread(func, *args, **kwargs):
            result = func(*args, **kwargs)
            calls.append("called")
            return result

        mock_sdk.models.generate_videos.return_value = mock_submitted_op
        mock_sdk.operations.get.return_value = mock_pending_op

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        provider = VeoProvider("standard")
        submit_result = await provider.submit("A cinematic landscape")
        job_id = submit_result.job_id

        status = await provider.get_status(job_id)

        assert status.status == "pending"
        assert status.job_id == job_id
        assert status.progress == pytest.approx(0.30)
        mock_sdk.operations.get.assert_called_once()

    async def test_get_status_complete(
        self, mock_sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_status() returns status='complete' when operation is done."""
        mock_submitted_op = MagicMock()
        mock_submitted_op.name = "models/veo-3.1-standard/operations/done-job"

        # Build completed operation with inline video bytes
        mock_video = MagicMock()
        mock_video.video_bytes = b"fake-mp4-content"
        mock_video.uri = None

        mock_gen_video = MagicMock()
        mock_gen_video.video = mock_video

        mock_response = MagicMock()
        mock_response.generated_videos = [mock_gen_video]

        mock_done_op = MagicMock()
        mock_done_op.done = True
        mock_done_op.error = None
        mock_done_op.response = mock_response
        mock_done_op.result = None

        mock_sdk.models.generate_videos.return_value = mock_submitted_op
        mock_sdk.operations.get.return_value = mock_done_op

        # Mock _write_video_bytes to avoid actual disk writes
        captured_write_args: list[tuple] = []

        async def _mock_write(data: bytes, output_path, filename_hint: str) -> Path:
            captured_write_args.append((data, output_path, filename_hint))
            return Path("/mocked/output/video.mp4")

        async def _fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        provider = VeoProvider("standard")
        monkeypatch.setattr(provider, "_write_video_bytes", _mock_write)

        submit_result = await provider.submit("A timelapse")
        job_id = submit_result.job_id

        status = await provider.get_status(job_id)

        assert status.status == "complete"
        assert status.progress == 1.0
        assert status.output_url == "file:///mocked/output/video.mp4"
        assert status.completed_at is not None
        # Verify video bytes were written
        assert len(captured_write_args) == 1
        assert captured_write_args[0][0] == b"fake-mp4-content"

    async def test_get_status_complete_with_uri(
        self, mock_sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_status() downloads via httpx when operation returns a URI (not bytes)."""
        mock_submitted_op = MagicMock()
        mock_submitted_op.name = "models/veo-3.1-fast/operations/uri-job"

        mock_video = MagicMock()
        mock_video.video_bytes = None
        mock_video.uri = "https://storage.googleapis.com/fake-bucket/video.mp4"

        mock_gen_video = MagicMock()
        mock_gen_video.video = mock_video

        mock_response = MagicMock()
        mock_response.generated_videos = [mock_gen_video]

        mock_done_op = MagicMock()
        mock_done_op.done = True
        mock_done_op.error = None
        mock_done_op.response = mock_response
        mock_done_op.result = None

        mock_sdk.models.generate_videos.return_value = mock_submitted_op
        mock_sdk.operations.get.return_value = mock_done_op

        download_calls: list[str] = []
        write_calls: list[bytes] = []

        async def _mock_download(uri: str) -> bytes:
            download_calls.append(uri)
            return b"downloaded-bytes"

        async def _mock_write(data: bytes, output_path, filename_hint: str) -> Path:
            write_calls.append(data)
            return Path("/mocked/output/uri-video.mp4")

        async def _fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        provider = VeoProvider("fast")
        monkeypatch.setattr(provider, "_download_video_uri", _mock_download)
        monkeypatch.setattr(provider, "_write_video_bytes", _mock_write)

        submit_result = await provider.submit("Test URI download")
        status = await provider.get_status(submit_result.job_id)

        assert status.status == "complete"
        assert len(download_calls) == 1
        assert "googleapis.com" in download_calls[0]
        assert len(write_calls) == 1
        assert write_calls[0] == b"downloaded-bytes"

    async def test_get_status_failed(
        self, mock_sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_status() returns status='failed' when operation has an error."""
        mock_submitted_op = MagicMock()
        mock_submitted_op.name = "models/veo-3.1-standard/operations/failed-job"

        mock_failed_op = MagicMock()
        mock_failed_op.done = True
        mock_failed_op.error = {"code": 400, "message": "Invalid prompt"}
        mock_failed_op.response = None
        mock_failed_op.result = None

        mock_sdk.models.generate_videos.return_value = mock_submitted_op
        mock_sdk.operations.get.return_value = mock_failed_op

        async def _fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        provider = VeoProvider("standard")
        submit_result = await provider.submit("Problematic prompt")
        status = await provider.get_status(submit_result.job_id)

        assert status.status == "failed"
        assert status.error_code == "400"
        assert status.retry_hint is not None


# ---------------------------------------------------------------------------
# Veo Provider — D025 path validation (new tests per spec)
# ---------------------------------------------------------------------------


class TestVeoD025PathValidation:
    """D025 path checks reject forbidden output locations."""

    def test_veo_rejects_tmp_path(self) -> None:
        """ValidationError with D025 reference is raised for /tmp paths."""
        from src.providers.veo_provider import _check_d025  # type: ignore

        with pytest.raises(ValidationError, match="D025"):
            _check_d025(Path("/tmp/some/video.mp4"))

    def test_veo_rejects_cache_path(self) -> None:
        """ValidationError is raised for ~/.cache/ paths."""
        from src.providers.veo_provider import _check_d025  # type: ignore

        with pytest.raises(ValidationError, match="D025"):
            _check_d025(Path.home() / ".cache" / "video.mp4")

    def test_veo_rejects_amplifier_path(self) -> None:
        """ValidationError is raised for ~/.amplifier/ paths."""
        from src.providers.veo_provider import _check_d025  # type: ignore

        with pytest.raises(ValidationError, match="D025"):
            _check_d025(Path.home() / ".amplifier" / "video.mp4")

    def test_veo_rejects_package_internal_path(self) -> None:
        """ValidationError is raised for paths inside the package directory."""
        from src.providers.veo_provider import _check_d025, _get_forbidden_prefixes  # type: ignore

        prefixes = _get_forbidden_prefixes()
        # The package root is one of the forbidden prefixes
        # (it ends with 'src' directory which is the package root)
        package_prefix = next(
            (p for p in prefixes if "video-mcp" in p or "src" in p.split("/")[-1:]), None
        )
        if package_prefix is None:
            # Skip if we can't identify package prefix in this env
            pytest.skip("Could not identify package-root forbidden prefix")

        with pytest.raises(ValidationError, match="D025"):
            _check_d025(Path(package_prefix) / "providers" / "video.mp4")

    def test_veo_rejects_forbidden_output_path(self) -> None:
        """Combined: all four D025 forbidden locations raise ValidationError."""
        from src.providers.veo_provider import _check_d025  # type: ignore

        forbidden_paths = [
            Path("/tmp/video.mp4"),
            Path.home() / ".cache" / "video.mp4",
            Path.home() / ".amplifier" / "video.mp4",
        ]
        for path in forbidden_paths:
            with pytest.raises(ValidationError, match="D025"):
                _check_d025(path)

    async def test_veo_writes_video_to_output_path_on_complete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_write_video_bytes writes bytes to the expected path on disk.

        D025 check is patched out so we can use tmp_path (which is under
        $TMPDIR — a forbidden location per D025 but safe for unit tests).
        """
        import src.providers.veo_provider as veo_mod

        # Bypass D025 check so tmp_path is usable
        monkeypatch.setattr(veo_mod, "_check_d025", lambda p: None)

        provider = VeoProvider("standard")
        output_file = tmp_path / "test_video.mp4"
        video_bytes = b"fake-video-content-bytes"

        result_path = await provider._write_video_bytes(
            video_bytes,
            str(output_file),
            "veo_standard_fallback.mp4",
        )

        # File should exist at the resolved path
        assert result_path.exists()
        assert result_path.read_bytes() == video_bytes

    async def test_write_video_bytes_creates_parent_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_write_video_bytes creates missing parent directories."""
        import src.providers.veo_provider as veo_mod

        monkeypatch.setattr(veo_mod, "_check_d025", lambda p: None)

        provider = VeoProvider("lite")
        deep_path = tmp_path / "a" / "b" / "c" / "video.mp4"

        result_path = await provider._write_video_bytes(
            b"bytes",
            str(deep_path),
            "fallback.mp4",
        )

        assert result_path.exists()
        assert result_path.read_bytes() == b"bytes"

    def test_safe_path_passes_d025_check(self) -> None:
        """A path under ~/Downloads/videos passes the D025 check without error."""
        from src.providers.veo_provider import _check_d025  # type: ignore

        safe_path = Path.home() / "Downloads" / "videos" / "standard" / "video.mp4"
        # Should not raise
        _check_d025(safe_path)


# ---------------------------------------------------------------------------
# Sora Provider Tests  (unchanged — still stubs per DECISIONS D010)
# ---------------------------------------------------------------------------


class TestSoraRaisesNotImplemented:
    """Sora submit/get_status raise NotImplementedError with D010 message."""

    async def test_submit_raises_not_implemented(self) -> None:
        provider = SoraProvider()
        with pytest.raises(NotImplementedError) as exc_info:
            await provider.submit("A physics simulation")
        assert "D010" in str(exc_info.value)
        assert "veo-3.1-standard" in str(exc_info.value)

    async def test_get_status_raises_not_implemented(self) -> None:
        provider = SoraProvider()
        with pytest.raises(NotImplementedError) as exc_info:
            await provider.get_status("any_job_id")
        assert "D010" in str(exc_info.value)

    def test_name(self) -> None:
        assert SoraProvider().name == "sora-2-pro"

    def test_capabilities_populated(self) -> None:
        caps = SoraProvider().capabilities
        assert isinstance(caps, VideoCapabilities)
        assert caps.name == "sora-2-pro"
        assert len(caps.supported_durations) > 0


# ---------------------------------------------------------------------------
# Grok Provider Tests  (unchanged — still stubs per DECISIONS D019)
# ---------------------------------------------------------------------------


class TestGrokRaisesNotImplemented:
    """Grok submit/get_status raise NotImplementedError with D019 message."""

    async def test_submit_raises_not_implemented(self) -> None:
        provider = GrokProvider()
        with pytest.raises(NotImplementedError) as exc_info:
            await provider.submit("A cinematic scene")
        assert "D019" in str(exc_info.value)
        assert "DPA" in str(exc_info.value)

    async def test_get_status_raises_not_implemented(self) -> None:
        provider = GrokProvider()
        with pytest.raises(NotImplementedError) as exc_info:
            await provider.get_status("any_job_id")
        assert "D019" in str(exc_info.value)

    def test_name(self) -> None:
        assert GrokProvider().name == "grok-imagine-video"

    def test_capabilities_populated(self) -> None:
        caps = GrokProvider().capabilities
        assert isinstance(caps, VideoCapabilities)
        assert caps.name == "grok-imagine-video"


# ---------------------------------------------------------------------------
# Registry Tests
# ---------------------------------------------------------------------------


class TestRegistryGetProvider:
    """Registry retrieves each known provider."""

    def test_get_veo_standard(self) -> None:
        registry = ProviderRegistry()
        provider = registry.get_provider("veo-3.1-standard")
        assert provider.name == "veo-3.1-standard"
        assert isinstance(provider, VeoProvider)

    def test_get_veo_fast(self) -> None:
        registry = ProviderRegistry()
        provider = registry.get_provider("veo-3.1-fast")
        assert provider.name == "veo-3.1-fast"

    def test_get_veo_lite(self) -> None:
        registry = ProviderRegistry()
        provider = registry.get_provider("veo-3.1-lite")
        assert provider.name == "veo-3.1-lite"

    def test_get_sora(self) -> None:
        registry = ProviderRegistry()
        provider = registry.get_provider("sora-2-pro")
        assert provider.name == "sora-2-pro"
        assert isinstance(provider, SoraProvider)

    def test_get_grok(self) -> None:
        registry = ProviderRegistry()
        provider = registry.get_provider("grok-imagine-video")
        assert provider.name == "grok-imagine-video"
        assert isinstance(provider, GrokProvider)

    def test_get_unknown_raises(self) -> None:
        registry = ProviderRegistry()
        with pytest.raises(ValueError, match="Unknown provider"):
            registry.get_provider("unknown-provider-xyz")

    def test_provider_cached_after_first_get(self) -> None:
        registry = ProviderRegistry()
        p1 = registry.get_provider("sora-2-pro")
        p2 = registry.get_provider("sora-2-pro")
        assert p1 is p2


class TestRegistryGetProviderForJobUnknownRaises:
    """JobNotFoundError is raised for unknown job IDs."""

    def test_unknown_job_id_raises_job_not_found(self) -> None:
        registry = ProviderRegistry()
        JobStore.clear()  # ensure clean state
        with pytest.raises(JobNotFoundError) as exc_info:
            registry.get_provider_for_job("totally_nonexistent_job_xyz_12345")  # type: ignore
        assert "not found" in str(exc_info.value).lower()

    async def test_known_job_id_returns_provider(
        self, mock_sdk: MagicMock, sync_to_thread: None
    ) -> None:
        """After a successful submit, the registry can route the job_id."""
        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-standard/operations/registry-routing"
        mock_sdk.models.generate_videos.return_value = mock_operation

        registry = ProviderRegistry()
        provider = registry.get_provider("veo-3.1-standard")
        result = await provider.submit("Test prompt for job routing")  # type: ignore
        found_provider = registry.get_provider_for_job(result.job_id)  # type: ignore
        assert found_provider.name == "veo-3.1-standard"  # type: ignore


class TestRegistryListProvidersRespectsKeyPresence:
    """list_providers() includes Veo iff GEMINI_API_KEY is set."""

    def test_with_gemini_key_veo_providers_available(self) -> None:
        # Key is set at top of file via os.environ.setdefault
        from src.config.settings import get_settings  # type: ignore

        get_settings.cache_clear()
        os.environ["GEMINI_API_KEY"] = "test-key-for-availability"

        registry = ProviderRegistry()
        available = registry.list_providers()
        assert any("veo" in p for p in available)
        # Sora and Grok are never available
        assert "sora-2-pro" not in available
        assert "grok-imagine-video" not in available
        # Restore
        get_settings.cache_clear()

    def test_without_gemini_key_no_veo_providers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.config.settings import get_settings  # type: ignore

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        get_settings.cache_clear()

        registry = ProviderRegistry()
        available = registry.list_providers()
        assert not any("veo" in p for p in available)

        # Restore cache
        get_settings.cache_clear()

    def test_list_all_providers_always_complete(self) -> None:
        registry = ProviderRegistry()
        all_providers = registry.list_all_providers()
        assert "veo-3.1-standard" in all_providers
        assert "veo-3.1-fast" in all_providers
        assert "veo-3.1-lite" in all_providers
        assert "sora-2-pro" in all_providers
        assert "grok-imagine-video" in all_providers
        assert len(all_providers) == 5

    def test_sora_never_available(self) -> None:
        registry = ProviderRegistry()
        assert not registry.is_provider_available("sora-2-pro")

    def test_grok_never_available(self) -> None:
        registry = ProviderRegistry()
        assert not registry.is_provider_available("grok-imagine-video")

    def test_get_comparison_markdown(self) -> None:
        registry = ProviderRegistry()
        comparison = registry.get_comparison()
        assert "Veo" in comparison or "veo" in comparison
        assert "sora" in comparison or "Sora" in comparison
        assert "grok" in comparison or "Grok" in comparison
