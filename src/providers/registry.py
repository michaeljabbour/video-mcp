"""
Provider registry for video-mcp.

Manages provider instances, routes job_id lookups to the correct provider,
and provides factory methods for creating and accessing providers.

Pattern mirrors imagen-mcp/src/providers/registry.py.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from ..config.constants import VEO_MODELS
from ..config.settings import get_settings
from ..exceptions import JobNotFoundError
from .base import JobStore, VideoCapabilities, VideoProvider
from .grok_provider import GrokProvider
from .selector import VideoSelector
from .sora_provider import SoraProvider
from .veo_provider import VeoProvider

logger = logging.getLogger(__name__)

_ALL_PROVIDER_NAMES = [
    "veo-3.1-standard",
    "veo-3.1-fast",
    "veo-3.1-lite",
    "sora-2-pro",
    "grok-imagine-video",
]


class ProviderRegistry:
    """Registry for video generation providers.

    Manages provider instances and provides methods for:
    - Getting specific providers by name
    - Routing get_job_status requests to the provider that owns a job
    - Listing available / all providers
    """

    def __init__(self) -> None:
        """Initialize the provider registry."""
        self._providers: dict[str, VideoProvider] = {}
        self._selector = VideoSelector()
        self._settings = get_settings()

    def get_provider(self, name: str) -> VideoProvider:
        """Get a provider by canonical name.

        Args:
            name: Provider name (e.g. 'veo-3.1-standard', 'sora-2-pro')

        Returns:
            VideoProvider instance (cached after first creation).

        Raises:
            ValueError: If provider name is unknown or Veo key is missing.
        """
        name = name.strip().lower()

        # Return cached instance if available
        if name in self._providers:
            return self._providers[name]

        provider: VideoProvider

        if name in VEO_MODELS:
            # Veo providers require GEMINI_API_KEY
            if not self._settings.has_gemini_key():
                raise ValueError(
                    f"Veo provider '{name}' not available. Set GEMINI_API_KEY environment variable."
                )
            tier = name.split("-")[-1]  # "veo-3.1-standard" → "standard"
            provider = VeoProvider(tier)

        elif name == "sora-2-pro":
            # Sora is always a stub — no key required
            provider = SoraProvider()

        elif name == "grok-imagine-video":
            # Grok is always a stub — no key required (D019-gated at submit time)
            provider = GrokProvider()

        else:
            raise ValueError(
                f"Unknown provider: '{name}'. Available: {', '.join(_ALL_PROVIDER_NAMES)}"
            )

        self._providers[name] = provider
        return provider

    def get_provider_for_job(self, job_id: str) -> VideoProvider:
        """Look up the provider that owns a job_id.

        Args:
            job_id: The job ID returned by a prior generate_video call.

        Returns:
            The VideoProvider that submitted this job.

        Raises:
            JobNotFoundError: If the job_id is not in the JobStore.
        """
        provider_name = JobStore.get_provider_name(job_id)
        if provider_name is None:
            raise JobNotFoundError(
                f"Video job '{job_id}' not found in any known provider.",
                provider="unknown",
                user_message=(
                    f"Video job '{job_id}' not found. "
                    "The job may have expired or the ID is incorrect. "
                    "Submit a new job via generate_video."
                ),
            )
        return self.get_provider(provider_name)

    def list_providers(self) -> list[str]:
        """List providers that are currently available (have API keys set)."""
        return [p for p in self.list_all_providers() if self.is_provider_available(p)]

    def list_all_providers(self) -> list[str]:
        """List all supported provider names (including stubs and unavailable)."""
        return list(_ALL_PROVIDER_NAMES)

    def is_provider_available(self, name: str) -> bool:
        """Check if a provider is usable (key present + not always-stubbed).

        - Veo providers: require GEMINI_API_KEY
        - Sora 2: always False (stub per D010)
        - Grok: always False (stub per D019)
        """
        name = name.strip().lower()
        if name in VEO_MODELS:
            return self._settings.has_gemini_key()
        # Sora and Grok are always unavailable (stub-only)
        return False

    def get_provider_info(self, name: str) -> dict[str, Any]:
        """Get capability information about a provider."""
        name = name.strip().lower()

        # Use cached instance when possible to avoid throwaway construction
        if name in self._providers:
            caps: VideoCapabilities = self._providers[name].capabilities
        elif name in VEO_MODELS:
            tier = name.split("-")[-1]
            caps = VeoProvider(tier).capabilities
        elif name == "sora-2-pro":
            caps = SoraProvider().capabilities
        elif name == "grok-imagine-video":
            caps = GrokProvider().capabilities
        else:
            raise ValueError(f"Unknown provider: '{name}'")

        return {
            "name": caps.name,
            "display_name": caps.display_name,
            "available": self.is_provider_available(name),
            "supported_durations": caps.supported_durations,
            "supported_resolutions": caps.supported_resolutions,
            "supports_first_frame": caps.supports_first_frame,
            "supports_last_frame": caps.supports_last_frame,
            "max_duration_seconds": caps.max_duration_seconds,
            "typical_latency_seconds": caps.typical_latency_seconds,
            "cost_tier": caps.cost_tier,
            "supports_audio": caps.supports_audio,
            "best_for": caps.best_for,
            "not_recommended_for": caps.not_recommended_for,
        }

    def get_comparison(self) -> str:
        """Return a formatted Markdown comparison table of all providers."""
        lines = [
            "## Video Provider Comparison",
            "",
            "| Provider | Available | Tier | Max Res | Latency | Audio | Status |",
            "|----------|-----------|------|---------|---------|-------|--------|",
        ]
        for pname in _ALL_PROVIDER_NAMES:
            available = self.is_provider_available(pname)
            avail_icon = "✅" if available else "❌"
            try:
                info = self.get_provider_info(pname)
                tier = str(info.get("cost_tier", "—"))
                res = ", ".join(str(r) for r in (info.get("supported_resolutions") or []))
                lat = f"~{info.get('typical_latency_seconds', '?')}s"
                audio = "✅" if info.get("supports_audio") else "❌"
            except Exception:
                tier = res = lat = audio = "—"

            if "veo" in pname:
                status = "stub (live pending)"
            elif pname == "sora-2-pro":
                status = "stub — D010 (EOL 2026-09-24)"
            else:
                status = "stub — D019 (xAI DPA pending)"

            lines.append(
                f"| `{pname}` | {avail_icon} | {tier} | {res} | {lat} | {audio} | {status} |"
            )

        lines.extend(
            [
                "",
                "### Phase 2a skeleton — all providers are stubs.",
                "Live Veo 3.1 wiring lands in Phase 2a.2.",
            ]
        )
        return "\n".join(lines)

    def select_provider(self, provider: str | None) -> VideoProvider:
        """Resolve provider name (or default) and return the provider instance."""
        name = self._selector.select_provider(provider)
        return self.get_provider(name)

    async def close_all(self) -> None:
        """Close all provider instances."""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()


@lru_cache(maxsize=1)
def get_provider_registry() -> ProviderRegistry:
    """Get the singleton provider registry."""
    return ProviderRegistry()
