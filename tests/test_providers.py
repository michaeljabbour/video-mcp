"""Tests for video provider implementations."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# Set dummy API keys BEFORE any src imports so settings cache is populated correctly
os.environ.setdefault("GEMINI_API_KEY", "test-key-gemini")

from src.exceptions import JobNotFoundError  # type: ignore
from src.providers.base import JobStore, VideoCapabilities, VideoJobResult  # type: ignore
from src.providers.grok_provider import GrokProvider  # type: ignore
from src.providers.registry import ProviderRegistry  # type: ignore
from src.providers.sora_provider import SoraProvider  # type: ignore
from src.providers.veo_provider import VeoProvider  # type: ignore

# ============================
# Veo Provider Tests
# ============================


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


class TestVeoSubmitReturnsJobId:
    """submit() returns a VideoJobResult with the correct shape."""

    async def test_submit_returns_job_result(self) -> None:
        provider = VeoProvider("standard")
        result = await provider.submit("A serene mountain lake at golden hour")
        assert isinstance(result, VideoJobResult)
        assert result.job_id.startswith("stub_veo_standard_")
        assert result.status == "submitted"
        assert result.provider == "veo-3.1-standard"
        assert result.model == "veo-3.1-standard"
        assert result.submitted_at is not None

    async def test_submit_registers_in_job_store(self) -> None:
        provider = VeoProvider("fast")
        result = await provider.submit("A product commercial")
        assert JobStore.exists(result.job_id)
        assert JobStore.get_provider_name(result.job_id) == "veo-3.1-fast"

    async def test_submit_validates_empty_prompt(self) -> None:
        from src.exceptions import ValidationError  # type: ignore

        provider = VeoProvider("standard")
        with pytest.raises(ValidationError, match="empty"):
            await provider.submit("")

    async def test_submit_uses_default_duration(self) -> None:
        provider = VeoProvider("lite")
        result = await provider.submit("A nature documentary scene")
        assert result.duration_seconds == 8.0

    async def test_submit_accepts_custom_duration(self) -> None:
        provider = VeoProvider("standard")
        result = await provider.submit("A short clip", duration=4.0)
        assert result.duration_seconds == 4.0

    async def test_submit_rejects_invalid_duration(self) -> None:
        from src.exceptions import ValidationError  # type: ignore

        provider = VeoProvider("standard")
        with pytest.raises(ValidationError, match="not supported"):
            await provider.submit("A clip", duration=7.0)

    async def test_submit_rejects_invalid_aspect_ratio(self) -> None:
        from src.exceptions import ValidationError  # type: ignore

        provider = VeoProvider("standard")
        with pytest.raises(ValidationError, match="not supported"):
            await provider.submit("A clip", aspect_ratio="4:3")


class TestVeoGetStatusPendingThenComplete:
    """Stub advances pending → complete after the configured delay."""

    async def test_status_pending_then_complete(self) -> None:
        """Stub transitions: submitted → pending → complete after 2s."""
        provider = VeoProvider("standard")

        # Patch time.time to control the clock
        fixed_time = 1_000_000.0

        with patch("time.time", return_value=fixed_time):
            result = await provider.submit("A cinematic landscape")
            job_id = result.job_id

        # Just after submission (0.5s later) → pending
        with patch("time.time", return_value=fixed_time + 0.5):
            status = await provider.get_status(job_id)
        assert status.status == "pending"
        assert status.progress is not None
        assert 0.0 <= status.progress < 1.0

        # After 2+ seconds → complete
        with patch("time.time", return_value=fixed_time + 3.0):
            status = await provider.get_status(job_id)
        assert status.status == "complete"
        assert status.progress == 1.0
        assert status.output_url is not None
        assert job_id in status.output_url
        assert status.completed_at is not None

    async def test_get_status_unknown_job_raises(self) -> None:
        provider = VeoProvider("standard")
        with pytest.raises(JobNotFoundError):
            await provider.get_status("nonexistent_job_id_xyz_abc")

    async def test_complete_status_has_output_url(self) -> None:
        provider = VeoProvider("lite")
        fixed_time = 2_000_000.0

        with patch("time.time", return_value=fixed_time):
            result = await provider.submit("A timelapse")
            job_id = result.job_id

        with patch("time.time", return_value=fixed_time + 10.0):
            status = await provider.get_status(job_id)

        assert status.status == "complete"
        assert status.output_url is not None
        assert status.output_url.endswith(".mp4")


# ============================
# Sora Provider Tests
# ============================


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


# ============================
# Grok Provider Tests
# ============================


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


# ============================
# Registry Tests
# ============================


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

    async def test_known_job_id_returns_provider(self) -> None:
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
