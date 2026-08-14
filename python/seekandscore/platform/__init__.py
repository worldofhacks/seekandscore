"""Platform context: runtime configuration and system capabilities."""

from seekandscore.platform.capabilities import PlatformCapabilities
from seekandscore.platform.module import DESCRIPTOR
from seekandscore.platform.settings import Settings, get_settings

__all__ = ["DESCRIPTOR", "PlatformCapabilities", "Settings", "get_settings"]
