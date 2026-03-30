"""Shared branding helpers for platform-facing names and labels."""
from __future__ import annotations

from dataclasses import dataclass

from shared.config.config_manager import get_config


@dataclass(frozen=True)
class Branding:
    internal_project_name: str
    platform_name: str
    assistant_name: str


def get_branding() -> Branding:
    """Return the current branding configuration with safe fallbacks."""
    try:
        config = get_config()
        branding = getattr(config, "branding", None)
    except Exception:
        branding = None

    internal_project_name = getattr(branding, "internal_project_name", "CUA") or "CUA"
    platform_name = getattr(branding, "platform_name", "Autonomous Agent Platform") or "Autonomous Agent Platform"
    assistant_name = getattr(branding, "assistant_name", "Platform Assistant") or "Platform Assistant"
    return Branding(
        internal_project_name=internal_project_name,
        platform_name=platform_name,
        assistant_name=assistant_name,
    )


def get_platform_name() -> str:
    return get_branding().platform_name


def get_assistant_name() -> str:
    return get_branding().assistant_name


def get_internal_project_name() -> str:
    return get_branding().internal_project_name
