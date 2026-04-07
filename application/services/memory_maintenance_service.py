"""Maintenance and consolidation helpers for explicit memory and strategic memory."""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple


class MemoryMaintenanceService:
    """Consolidate duplicate notes and prune stale low-value memory artifacts."""

    def __init__(self, memory_system, strategic_memory=None) -> None:
        self.memory_system = memory_system
        self.strategic_memory = strategic_memory

    def run_maintenance(
        self,
        *,
        note_limit: int = 500,
        keep_recent_compactions: int = 20,
        strategic_stale_days: int = 120,
    ) -> Dict[str, Any]:
        notes = list(self.memory_system.list_memory_notes(limit=max(1, note_limit)))
        duplicate_ids = self._find_duplicate_note_ids(notes)
        compaction_ids = self._find_prunable_compaction_ids(notes, keep_recent=keep_recent_compactions)
        note_ids_to_delete = sorted(set(duplicate_ids + compaction_ids))

        deleted_notes = 0
        if note_ids_to_delete:
            deleted_notes = self.memory_system.delete_memory_notes(note_ids_to_delete)

        strategic_report = {"removed_records": 0, "remaining_records": None}
        if self.strategic_memory and hasattr(self.strategic_memory, "run_maintenance"):
            strategic_report = self.strategic_memory.run_maintenance(stale_days=strategic_stale_days)

        return {
            "success": True,
            "notes_scanned": len(notes),
            "duplicate_notes_removed": len(duplicate_ids),
            "compaction_notes_removed": len(compaction_ids),
            "deleted_notes": deleted_notes,
            "strategic_memory": strategic_report,
        }

    def _find_duplicate_note_ids(self, notes: List[Dict[str, Any]]) -> List[int]:
        winners: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        duplicates: List[int] = []
        for note in notes:
            key = (
                str(note.get("scope", "")).strip().lower(),
                str(note.get("scope_key", "")).strip().lower(),
                str(note.get("title", "")).strip().lower(),
                " ".join(str(note.get("content", "")).strip().lower().split()),
            )
            if key not in winners:
                winners[key] = note
                continue
            current = winners[key]
            current_updated = str(current.get("updated_at", ""))
            note_updated = str(note.get("updated_at", ""))
            if note_updated > current_updated:
                duplicates.append(int(current["id"]))
                winners[key] = note
            else:
                duplicates.append(int(note["id"]))
        return duplicates

    def _find_prunable_compaction_ids(self, notes: List[Dict[str, Any]], *, keep_recent: int) -> List[int]:
        compaction_notes = [
            note for note in notes
            if str((note.get("metadata") or {}).get("type", "")).strip().lower() == "session_compaction"
        ]
        compaction_notes.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return [int(note["id"]) for note in compaction_notes[max(0, keep_recent):]]


class MemoryMaintenanceLoop:
    """Small background loop that periodically consolidates memory stores."""

    def __init__(self, service: MemoryMaintenanceService, interval_seconds: int = 21600) -> None:
        self.service = service
        self.interval_seconds = max(300, int(interval_seconds or 21600))
        self.running = False
        self.thread = None

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _run(self) -> None:
        while self.running:
            try:
                self.service.run_maintenance()
            except Exception:
                pass
            threading.Event().wait(self.interval_seconds)
