"""
LLM Interaction Logger - Consolidated logging with rotation
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import gzip
import shutil

class LLMLogger:
    def __init__(self, log_dir: str = "logs/llm", max_session_size_mb: int = 10):
        # Use absolute path to avoid issues when CWD changes (e.g., in sandbox)
        self.log_dir = Path(log_dir).resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.interaction_count = 0
        self.max_session_size = max_session_size_mb * 1024 * 1024
        self.session_file = self.log_dir / f"session_{self.session_id}.jsonl"
        self.error_file = self.log_dir / f"errors_{self.session_id}.jsonl"
        
        # Clean old sessions on init
        self._cleanup_old_sessions()
    
    def log_interaction(self, prompt: str, response: str, metadata: Optional[Dict] = None):
        """Log single LLM interaction to consolidated session file"""
        self.interaction_count += 1
        
        log_entry = {
            "session_id": self.session_id,
            "interaction": self.interaction_count,
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt[:1000],  # Truncate long prompts
            "response": response[:2000] if response else "<empty>",  # Truncate long responses
            "metadata": metadata or {}
        }
        
        # Append to single session file
        with open(self.session_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        # Check if rotation needed
        if self.session_file.stat().st_size > self.max_session_size:
            self._rotate_session()
    
    def log_error(self, error: str, context: Optional[Dict] = None):
        """Log LLM error"""
        self.interaction_count += 1
        
        log_entry = {
            "session_id": self.session_id,
            "interaction": self.interaction_count,
            "timestamp": datetime.now().isoformat(),
            "error": error,
            "context": context or {}
        }
        
        with open(self.error_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def _rotate_session(self):
        """Rotate session file when it gets too large"""
        # Compress old session
        archive_name = self.log_dir / f"session_{self.session_id}_archived.jsonl.gz"
        with open(self.session_file, 'rb') as f_in:
            with gzip.open(archive_name, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Start new session
        self.session_file.unlink()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_file = self.log_dir / f"session_{self.session_id}.jsonl"
        self.interaction_count = 0
    
    def _cleanup_old_sessions(self, keep_days: int = 7):
        """Clean up old session files"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=keep_days)
        
        for log_file in self.log_dir.glob("session_*.jsonl"):
            try:
                # Extract date from filename
                date_str = log_file.stem.split('_')[1]
                file_date = datetime.strptime(date_str, "%Y%m%d")
                
                if file_date < cutoff:
                    # Compress before deleting
                    archive_name = log_file.with_suffix('.jsonl.gz')
                    if not archive_name.exists():
                        with open(log_file, 'rb') as f_in:
                            with gzip.open(archive_name, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                    log_file.unlink()
            except:
                pass
        
        # Delete individual interaction files (old format)
        for old_file in self.log_dir.glob("llm_*.json"):
            try:
                old_file.unlink()
            except:
                pass
