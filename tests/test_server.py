"""Tests for video-mcp MCP server.

Phase 2a.2: End-to-end tests updated to mock the google-genai SDK.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

import pytest

# Set dummy API keys BEFORE any src imports
os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")

from src.models.input_models import (  # type: ignore
    OutputFormat,
    VideoGenerateInput,  # type: ignore
    VideoJobStatusInput,  # type: ignore
)


class TestServerImportsCleanly:
    """Server module imports without errors."""

    def test_server_imports(self) -> None:
        from src.server import mcp  # type: ignore

        assert mcp is not None

    def test_generate_video_tool_registered(self) -> None:
        from src.server import generate_video  # type: ignore

        assert generate_video is not None
        assert callable(generate_video)

    def test_get_job_status_tool_registered(self) -> None:
        from src.server import get_job_status  # type: ignore

        assert get_job_status is not None
        assert callable(get_job_status)

    def test_config_imports(self) -> None:
        from src.config.constants import (  # type: ignore
            DEFAULT_VIDEO_MODEL,  # type: ignore
            STUBBED_PROVIDERS,  # type: ignore
            SUPPORTED_ASPECTS,  # type: ignore
            SUPPORTED_DURATIONS_SECONDS,  # type: ignore
            VEO_MODELS,  # type: ignore
        )

        assert DEFAULT_VIDEO_MODEL == "veo-3.1-standard"
        assert len(VEO_MODELS) == 3
        assert "veo-3.1-standard" in VEO_MODELS
        assert "veo-3.1-fast" in VEO_MODELS
        assert "veo-3.1-lite" in VEO_MODELS
        assert "sora-2-pro" in STUBBED_PROVIDERS
        assert "grok-imagine-video" in STUBBED_PROVIDERS
        assert "16:9" in SUPPORTED_ASPECTS
        assert 8.0 in SUPPORTED_DURATIONS_SECONDS

    def test_provider_imports(self) -> None:
        from src.providers import (  # type: ignore
            VideoCapabilities,  # type: ignore
            VideoJobResult,  # type: ignore
            VideoProvider,  # type: ignore
            get_provider_registry,  # type: ignore
        )

        assert VideoProvider is not None
        assert VideoCapabilities is not None
        assert VideoJobResult is not None
        assert get_provider_registry() is not None

    def test_exception_imports(self) -> None:
        from src.exceptions import (  # type: ignore
            AuthenticationError,
            ConfigurationError,
            GenerationError,
            JobNotFoundError,  # type: ignore
            ProviderError,
            RateLimitError,
            ValidationError,
            VideoError,  # type: ignore
        )

        # Verify hierarchy
        assert issubclass(ConfigurationError, VideoError)
        assert issubclass(ProviderError, VideoError)
        assert issubclass(AuthenticationError, ProviderError)
        assert issubclass(RateLimitError, ProviderError)
        assert issubclass(GenerationError, ProviderError)
        assert issubclass(JobNotFoundError, ProviderError)
        assert issubclass(ValidationError, VideoError)


class TestInputModelsValidate:
    """Pydantic input models validate correctly."""

    def test_video_generate_input_minimal(self) -> None:
        inp = VideoGenerateInput(prompt="A sunset over the ocean")
        assert inp.prompt == "A sunset over the ocean"
        assert inp.provider is None  # defaults to None (server picks default)
        assert inp.duration is None
        assert inp.aspect_ratio is None
        assert inp.output_format == OutputFormat.MARKDOWN

    def test_video_generate_input_full(self) -> None:
        inp = VideoGenerateInput(
            prompt="A cinematic shot",
            provider="veo-3.1-fast",
            duration=6.0,
            aspect_ratio="9:16",
            output_format=OutputFormat.JSON,
        )
        assert inp.provider == "veo-3.1-fast"
        assert inp.duration == 6.0
        assert inp.aspect_ratio == "9:16"
        assert inp.output_format == OutputFormat.JSON

    def test_video_generate_input_rejects_empty_prompt(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            VideoGenerateInput(prompt="")

    def test_video_generate_input_rejects_extra_fields(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            VideoGenerateInput(**{"prompt": "A sunset", "unknown_field": "bad"})  # type: ignore[call-arg]

    def test_video_generate_api_key_excluded_from_repr(self) -> None:
        inp = VideoGenerateInput(
            prompt="A test",
            gemini_api_key="super-secret-key-12345",
        )
        assert "super-secret-key-12345" not in repr(inp)

    def test_video_job_status_input_minimal(self) -> None:
        inp = VideoJobStatusInput(job_id="models/veo-3.1-standard/operations/test-job")
        assert inp.job_id == "models/veo-3.1-standard/operations/test-job"
        assert inp.output_format == OutputFormat.MARKDOWN

    def test_video_job_status_input_json_format(self) -> None:
        inp = VideoJobStatusInput(job_id="test_job", output_format=OutputFormat.JSON)
        assert inp.output_format == OutputFormat.JSON

    def test_video_job_status_rejects_empty_job_id(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            VideoJobStatusInput(job_id="")

    def test_video_job_status_rejects_extra_fields(self) -> None:
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            VideoJobStatusInput(**{"job_id": "test", "bogus": "field"})  # type: ignore[call-arg]

    def test_output_format_enum_values(self) -> None:
        assert OutputFormat.MARKDOWN.value == "markdown"
        assert OutputFormat.JSON.value == "json"


@pytest.fixture
def mock_veo_sdk(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock the google-genai SDK globals for server-level end-to-end tests.

    Returns the mock ``genai.Client`` instance.
    """
    import src.providers.veo_provider as veo_mod

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


class TestGenerateVideoEndToEndStubbed:
    """End-to-end: generate_video → get_job_status with mocked SDK."""

    async def test_full_stub_cycle_markdown(
        self, mock_veo_sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Calls generate_video, extracts job_id, polls get_job_status to completion."""
        import asyncio

        from src.providers.base import JobStore  # type: ignore
        from src.server import generate_video, get_job_status  # type: ignore

        JobStore.clear()

        # --- Set up mock operations ---
        mock_submitted_op = MagicMock()
        mock_submitted_op.name = "models/veo-3.1-standard/operations/e2e-test-abc"

        mock_pending_op = MagicMock()
        mock_pending_op.done = False
        mock_pending_op.error = None
        mock_pending_op.metadata = None

        # Build a mocked "write" so we don't hit disk
        write_calls: list = []

        async def _mock_write(data: bytes, output_path, filename_hint: str):
            write_calls.append(filename_hint)
            from pathlib import Path  # noqa: PLC0415

            return Path("/mocked/output/e2e-video.mp4")

        mock_video = MagicMock()
        mock_video.video_bytes = b"e2e-video-bytes"
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

        # submit → pending → complete
        call_seq: list[int] = [0]

        async def _fake_to_thread(func, *args, **kwargs):
            count = call_seq[0]
            call_seq[0] += 1
            if count == 0:
                # First call: generate_videos → returns submitted op
                mock_veo_sdk.models.generate_videos.return_value = mock_submitted_op
                return func(*args, **kwargs)
            elif count == 1:
                # Second call: operations.get → returns pending
                mock_veo_sdk.operations.get.return_value = mock_pending_op
                return func(*args, **kwargs)
            else:
                # Third call: operations.get → returns done
                mock_veo_sdk.operations.get.return_value = mock_done_op
                return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        # Step 1: Submit
        gen_params = VideoGenerateInput(
            prompt="A golden-hour timelapse of city lights coming on",
            provider="veo-3.1-standard",
            duration=8.0,
            aspect_ratio="16:9",
        )

        submit_result = await generate_video(gen_params)

        # Verify submit response contains a job_id
        assert "Job ID" in submit_result or "job_id" in submit_result.lower()
        assert "submitted" in submit_result.lower()
        assert "models/veo-3.1-standard/operations/e2e-test-abc" in submit_result

        # Extract job_id from the response
        job_id = "models/veo-3.1-standard/operations/e2e-test-abc"

        # Step 2: Poll — should be pending
        status_params = VideoJobStatusInput(job_id=job_id)
        pending_result = await get_job_status(status_params)
        assert "pending" in pending_result.lower() or "submitted" in pending_result.lower()

        # Step 3: Poll again — should be complete (with mocked write)
        # Patch _write_video_bytes on the provider instance
        from src.providers.registry import ProviderRegistry  # type: ignore

        registry = ProviderRegistry()
        provider = registry.get_provider("veo-3.1-standard")
        monkeypatch.setattr(provider, "_write_video_bytes", _mock_write)

        complete_result = await get_job_status(status_params)
        assert "complete" in complete_result.lower()
        assert job_id in complete_result

    async def test_generate_video_json_output(
        self, mock_veo_sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """generate_video with JSON output returns parseable JSON."""
        import asyncio

        from src.providers.base import JobStore  # type: ignore
        from src.server import generate_video  # type: ignore

        JobStore.clear()

        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-fast/operations/json-test-xyz"
        mock_veo_sdk.models.generate_videos.return_value = mock_operation

        async def _fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        gen_params = VideoGenerateInput(
            prompt="A slow-motion waterfall",
            provider="veo-3.1-fast",
            output_format=OutputFormat.JSON,
        )

        result = await generate_video(gen_params)

        data = json.loads(result)
        assert "job_id" in data
        assert data["job_id"] == "models/veo-3.1-fast/operations/json-test-xyz"
        assert data["status"] == "submitted"
        assert data["provider"] == "veo-3.1-fast"

    async def test_get_job_status_unknown_job_returns_error(self) -> None:
        """get_job_status with unknown job_id returns a helpful error."""
        from src.providers.base import JobStore  # type: ignore
        from src.server import get_job_status  # type: ignore

        JobStore.clear()

        params = VideoJobStatusInput(job_id="totally_nonexistent_job_aabbccdd1122")
        result = await get_job_status(params)

        assert "not found" in result.lower() or "Job Not Found" in result
        assert "generate_video" in result or "resubmit" in result.lower()

    async def test_sora_returns_not_implemented_error(self) -> None:
        """generate_video with sora-2-pro returns a not-implemented response."""
        from src.server import generate_video  # type: ignore

        gen_params = VideoGenerateInput(
            prompt="A physics simulation",
            provider="sora-2-pro",
        )
        result = await generate_video(gen_params)
        assert "D010" in result or "not implemented" in result.lower()

    async def test_grok_returns_not_implemented_error(self) -> None:
        """generate_video with grok-imagine-video returns a not-implemented response."""
        from src.server import generate_video  # type: ignore

        gen_params = VideoGenerateInput(
            prompt="A creative scene",
            provider="grok-imagine-video",
        )
        result = await generate_video(gen_params)
        assert "D019" in result or "not implemented" in result.lower()

    async def test_default_provider_is_veo_standard(
        self, mock_veo_sdk: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """generate_video with no provider defaults to veo-3.1-standard."""
        import asyncio

        from src.providers.base import JobStore  # type: ignore
        from src.server import generate_video  # type: ignore

        JobStore.clear()

        mock_operation = MagicMock()
        mock_operation.name = "models/veo-3.1-standard/operations/default-test"
        mock_veo_sdk.models.generate_videos.return_value = mock_operation

        async def _fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

        gen_params = VideoGenerateInput(
            prompt="A mountain sunrise",
            output_format=OutputFormat.JSON,
        )

        result = await generate_video(gen_params)

        data = json.loads(result)
        assert data["provider"] == "veo-3.1-standard"
        assert "job_id" in data
        assert data["status"] == "submitted"
