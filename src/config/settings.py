"""
Settings management for video-mcp.

Handles API keys and configuration from environment variables.
"""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Settings:
    """Application settings loaded from environment."""

    # API Keys
    gemini_api_key: str | None = None  # For Veo 3.1; also checks GOOGLE_API_KEY
    xai_api_key: str | None = None  # For Grok Imagine Video (D019-gated)

    # Request behavior
    request_timeout: float = 300.0  # seconds — video is slow

    # Output
    output_dir: str | None = None

    # Logging
    log_dir: str | None = None
    log_level: str = "INFO"
    log_max_bytes: int = 5_242_880  # 5 MiB
    log_backup_count: int = 3
    log_prompts: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables."""
        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        log_dir = os.getenv("VIDEO_MCP_LOG_DIR") or os.getenv("LOG_DIR")
        log_level = os.getenv("VIDEO_MCP_LOG_LEVEL") or os.getenv("LOG_LEVEL", "INFO")

        return cls(
            gemini_api_key=gemini_key,
            xai_api_key=os.getenv("XAI_API_KEY"),
            request_timeout=float(os.getenv("VIDEO_MCP_REQUEST_TIMEOUT", "300")),
            output_dir=os.getenv("OUTPUT_DIR"),
            log_dir=log_dir,
            log_level=log_level,
            log_max_bytes=int(
                os.getenv("VIDEO_MCP_LOG_MAX_BYTES") or os.getenv("LOG_MAX_BYTES", "5242880")
            ),
            log_backup_count=int(
                os.getenv("VIDEO_MCP_LOG_BACKUP_COUNT") or os.getenv("LOG_BACKUP_COUNT", "3")
            ),
            log_prompts=(
                os.getenv("VIDEO_MCP_LOG_PROMPTS") or os.getenv("LOG_PROMPTS", "false")
            ).lower()
            == "true",
        )

    def get_gemini_api_key(self, provided_key: str | None = None) -> str:
        """Get Gemini API key from provided value or settings."""
        api_key = provided_key or self.gemini_api_key
        if not api_key:
            raise ValueError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable "
                "or provide api_key parameter."
            )
        return api_key

    def get_xai_api_key(self, provided_key: str | None = None) -> str:
        """Get xAI API key from provided value or settings (Grok, D019-gated)."""
        api_key = provided_key or self.xai_api_key
        if not api_key:
            raise ValueError(
                "xAI API key not found. Set XAI_API_KEY environment variable. "
                "Note: Grok Imagine Video is gated on DPA completion — see DECISIONS D019."
            )
        return api_key

    def has_gemini_key(self) -> bool:
        """Check if Gemini API key is available."""
        return bool(self.gemini_api_key)

    def has_xai_key(self) -> bool:
        """Check if xAI API key is available."""
        return bool(self.xai_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.from_env()
