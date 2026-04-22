"""
Root conftest.py — ensures /Users/michaeljabbour/dev/video-mcp is on sys.path
so that `from src.*` imports resolve to video-mcp, not any other `src` package
in the Python environment.
"""

import sys
from pathlib import Path

# Ensure video-mcp root is at the FRONT of sys.path so `src.*` imports
# always resolve to this project's src/, regardless of the working directory.
_VIDEO_MCP_ROOT = str(Path(__file__).parent.resolve())
if _VIDEO_MCP_ROOT not in sys.path:
    sys.path.insert(0, _VIDEO_MCP_ROOT)
