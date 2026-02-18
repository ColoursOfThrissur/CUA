"""
Pending Libraries Manager - Approve library installations during self-improvement
"""

import ast
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime

class PendingLibrariesManager:
    """Manages pending library installation approvals"""
    
    def __init__(self, storage_path: str = "data/pending_libraries.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(exist_ok=True)
        self.pending = {}
        self._load()
    
    def detect_new_imports(self, code: str) -> List[str]:
        """Detect new imports in code that aren't installed"""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split('.')[0])
        
        # Filter to only uninstalled libraries
        new_imports = []
        for lib in imports:
            if not self._is_installed(lib):
                # Map common import names to package names
                package = self._map_import_to_package(lib)
                if package:
                    new_imports.append(package)
        
        return new_imports
    
    def add_pending(self, library: str, reason: str, proposed_by: str = "self_improvement") -> str:
        """Add library to pending approvals"""
        import json
        
        lib_id = f"lib_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{library}"
        
        self.pending[lib_id] = {
            "library": library,
            "reason": reason,
            "proposed_by": proposed_by,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }
        
        self._save()
        return lib_id
    
    def approve(self, lib_id: str) -> Dict:
        """Approve and install library"""
        if lib_id not in self.pending:
            return {"success": False, "error": "Library not found"}
        
        lib_data = self.pending[lib_id]
        library = lib_data["library"]
        
        # Install library
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", library],
                capture_output=True,
                text=True,
                check=True
            )
            
            lib_data["status"] = "approved"
            lib_data["installed_at"] = datetime.now().isoformat()
            self._save()
            
            return {"success": True, "library": library}
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or e.stdout or str(e)
            lib_data["status"] = "failed"
            lib_data["error"] = error_msg
            self._save()
            
            return {"success": False, "error": f"Installation failed: {error_msg}"}
    
    def reject(self, lib_id: str, reason: str = "User rejected") -> Dict:
        """Reject library installation"""
        if lib_id not in self.pending:
            return {"success": False, "error": "Library not found"}
        
        self.pending[lib_id]["status"] = "rejected"
        self.pending[lib_id]["rejection_reason"] = reason
        self._save()
        
        return {"success": True}
    
    def get_pending(self) -> List[Dict]:
        """Get all pending libraries"""
        return [
            {"id": lib_id, **data}
            for lib_id, data in self.pending.items()
            if data["status"] == "pending"
        ]
    
    def _is_installed(self, library: str) -> bool:
        """Check if library is installed"""
        try:
            __import__(library)
            return True
        except ImportError:
            return False
    
    def _map_import_to_package(self, import_name: str) -> Optional[str]:
        """Map import name to pip package name"""
        # Common mappings
        mappings = {
            "bs4": "beautifulsoup4",
            "cv2": "opencv-python",
            "PIL": "Pillow",
            "sklearn": "scikit-learn",
            "yaml": "pyyaml"
        }
        
        # Check if it's a standard library
        stdlib = {
            "os", "sys", "json", "time", "datetime", "pathlib", "re",
            "collections", "itertools", "functools", "typing", "enum",
            "dataclasses", "ast", "subprocess", "hashlib", "logging"
        }
        
        if import_name in stdlib:
            return None
        
        return mappings.get(import_name, import_name)
    
    def _load(self):
        """Load pending libraries from disk"""
        import json
        
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    self.pending = json.load(f)
            except Exception:
                self.pending = {}
    
    def _save(self):
        """Save pending libraries to disk"""
        import json
        
        with open(self.storage_path, 'w') as f:
            json.dump(self.pending, f, indent=2)
