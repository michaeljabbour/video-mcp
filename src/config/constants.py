"""
Constants for video-mcp providers.

Defines provider identifiers, Veo 3.1 tier metadata, supported parameters,
and stub-provider notices.
"""

# ============================
# Veo via Gemini API
# ============================

VIDEO_MCP_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"  # Veo via Gemini API

# Veo 3.1 tier identifiers (as passed to google-genai SDK when we wire live)
VEO_MODELS: dict[str, dict[str, object]] = {
    "veo-3.1-standard": {
        "marketing_name": "Veo 3.1 Standard",
        "description": "4K, best lip-sync, cinematic. $0.40/sec.",
        "max_resolution": "4K",
        "cost_per_second_usd": 0.40,
        "tier": "standard",
    },
    "veo-3.1-fast": {
        "marketing_name": "Veo 3.1 Fast",
        "description": "1080p, same quality backbone, faster iteration. $0.15/sec.",
        "max_resolution": "1080p",
        "cost_per_second_usd": 0.15,
        "tier": "fast",
    },
    "veo-3.1-lite": {
        "marketing_name": "Veo 3.1 Lite",
        "description": "720p/1080p, high-volume apps. $0.05/sec.",
        "max_resolution": "1080p",
        "cost_per_second_usd": 0.05,
        "tier": "lite",
    },
}

DEFAULT_VIDEO_MODEL = "veo-3.1-standard"

# ============================
# Stubbed Providers
# ============================
# See DECISIONS D010 (Sora) and D019 (Grok)

STUBBED_PROVIDERS: dict[str, str] = {
    "sora-2-pro": ("Sora 2 Pro — stub only per DECISIONS D010. API shuts down 2026-09-24."),
    "grok-imagine-video": ("Grok Imagine Video — stub only per DECISIONS D019 (xAI DPA pending)."),
}

# ============================
# Shared Generation Parameters
# ============================

SUPPORTED_ASPECTS: list[str] = ["16:9", "9:16"]  # Veo-specific
SUPPORTED_DURATIONS_SECONDS: list[float] = [4.0, 6.0, 8.0, 16.0]
SUPPORTED_RESOLUTIONS: list[str] = ["720p", "1080p", "4K"]

MAX_PROMPT_LENGTH = 4000
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 300  # seconds — video is slow

# Polling cadence hint (the MCP doesn't itself poll; the task-tool sub-agent does)
SUGGESTED_POLL_INTERVAL_SECONDS = 15.0
