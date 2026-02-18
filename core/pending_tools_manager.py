"""
PendingToolsManager - Manages tools awaiting user approval
"""
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import json


class PendingToolsManager:
    def __init__(self):
        self.pending_tools = {}  # {tool_id: tool_metadata}
        self.tool_history = []
        self.storage_path = Path("data/pending_tools.json")
        self._load_from_disk()
    
    def add_pending_tool(self, tool_metadata: Dict) -> str:
        """Add tool to pending queue"""
        tool_id = f"tool_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Detect if new tool or update
        tool_file = tool_metadata.get('tool_file', '')
        is_new = not Path(tool_file).exists() if tool_file else True
        
        self.pending_tools[tool_id] = {
            **tool_metadata,
            'tool_id': tool_id,
            'status': 'pending',
            'type': 'new_tool' if is_new else 'tool_update',
            'created_at': datetime.now().isoformat(),
            'approved_at': None
        }
        
        self._save_to_disk()
        return tool_id
    
    def approve_tool(self, tool_id: str) -> Dict:
        """Mark tool as approved"""
        if tool_id not in self.pending_tools:
            return {'success': False, 'error': 'Tool not found'}
        
        tool = self.pending_tools[tool_id]
        tool['status'] = 'approved'
        tool['approved_at'] = datetime.now().isoformat()
        
        self.tool_history.append(tool)
        del self.pending_tools[tool_id]
        
        self._save_to_disk()
        return {'success': True, 'tool': tool}
    
    def reject_tool(self, tool_id: str, reason: str = '') -> Dict:
        """Reject and remove tool"""
        if tool_id not in self.pending_tools:
            return {'success': False, 'error': 'Tool not found'}
        
        tool = self.pending_tools[tool_id]
        tool['status'] = 'rejected'
        tool['rejection_reason'] = reason
        
        # Clean up generated files if they exist
        tool_file = tool.get('tool_file')
        test_file = tool.get('test_file')
        
        if tool_file and Path(tool_file).exists():
            Path(tool_file).unlink()
        if test_file and Path(test_file).exists():
            Path(test_file).unlink()
        
        del self.pending_tools[tool_id]
        self._save_to_disk()
        
        return {'success': True}
    
    def get_pending_list(self) -> List[Dict]:
        """Get all pending tools"""
        return list(self.pending_tools.values())
    
    def get_tool(self, tool_id: str) -> Optional[Dict]:
        """Get specific tool metadata"""
        return self.pending_tools.get(tool_id)
    
    def _save_to_disk(self):
        """Persist to disk"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'pending': self.pending_tools,
                'history': self.tool_history[-50:]  # Keep last 50
            }
            self.storage_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass
    
    def _load_from_disk(self):
        """Load from disk"""
        try:
            if self.storage_path.exists():
                data = json.loads(self.storage_path.read_text())
                self.pending_tools = data.get('pending', {})
                self.tool_history = data.get('history', [])
        except Exception:
            pass
