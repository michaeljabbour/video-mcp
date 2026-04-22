"""
Provider selection logic for video-mcp.

Minimal for v0.1: only provider override routing is implemented.
If the caller specifies a provider, use it; otherwise default to Veo 3.1 Standard.

Keyword-based heuristics (e.g. 'physics-required' → Sora) are a future enhancement
that will land in the amplifier-bundle-creative orchestration layer, not here.
"""

from __future__ import annotations

import logging

from ..config.constants import DEFAULT_VIDEO_MODEL

logger = logging.getLogger(__name__)


class VideoSelector:
    """Route video generation requests to a provider.

    v0.1: explicit override or default. No prompt analysis.
    """

    def select_provider(
        self,
        provider: str | None,
        *,
        available_providers: list[str] | None = None,
    ) -> str:
        """Return the canonical provider name to use for a request.

        Args:
            provider: Optional explicit provider override from the caller.
            available_providers: Optional list of currently-available providers.
                                 Used only for fallback logging.

        Returns:
            Canonical provider name string.
        """
        if provider:
            logger.info(
                "Provider override requested: '%s' — using as-is (no availability check here).",
                provider,
            )
            return provider

        default = DEFAULT_VIDEO_MODEL
        logger.info(
            "No provider specified — defaulting to '%s'.",
            default,
        )
        return default

    def get_selection_reasoning(self, provider: str | None) -> str:
        """Return a human-readable explanation of the provider selection."""
        if provider:
            return f"Explicit provider override: '{provider}'."
        return f"Default provider: '{DEFAULT_VIDEO_MODEL}' (Veo 3.1 Standard)."
