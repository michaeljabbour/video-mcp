"""
Public interface for video-mcp providers.

Re-exports the core types and registry accessor used by server.py
and external consumers.
"""

from .base import JobStore, VideoCapabilities, VideoJobResult, VideoProvider
from .registry import get_provider_registry

__all__ = [
    "JobStore",
    "VideoCapabilities",
    "VideoJobResult",
    "VideoProvider",
    "get_provider_registry",
]
