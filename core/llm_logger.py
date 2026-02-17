"""
LLM Interaction Logger - Debug LLM inputs/outputs
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

class LLMLogger:
    def __init__(self, log_dir: str = "logs/llm"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.interaction_count = 0
    
    def log_interaction(self, prompt: str, response: str, metadata: Optional[Dict] = None):
        """Log single LLM interaction"""
        self.interaction_count += 1
        
        log_entry = {
            "session_id": self.session_id,
            "interaction": self.interaction_count,
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "response": response,
            "metadata": metadata or {}
        }
        
        # Save to file
        filename = f"llm_{self.session_id}_{self.interaction_count:03d}.json"
        filepath = self.log_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(log_entry, f, indent=2)
        
        # Also append to session log
        session_file = self.log_dir / f"session_{self.session_id}.jsonl"
        with open(session_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
    
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
        
        error_file = self.log_dir / f"errors_{self.session_id}.jsonl"
        with open(error_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
