"""Compatibility export for the current skill repository implementation."""

from infrastructure.persistence.file_storage.skill_file_storage import SkillFileStorage


class SkillRepository(SkillFileStorage):
    """Backwards-compatible alias while skills remain file-backed."""
