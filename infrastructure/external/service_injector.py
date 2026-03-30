"""
Service Injector - Dynamically inject services into tool_services.py
"""
import ast
import re
from pathlib import Path

class ServiceInjector:
    def __init__(self, services_file: str = "core/tool_services.py"):
        self.services_file = Path(services_file)
    
    def inject_service(self, service_name: str, method_name: str, code: str, service_type: str) -> dict:
        """Inject service method or full service into tool_services.py"""
        try:
            if service_type == "method":
                return self._inject_method(service_name, method_name, code)
            else:
                return self._inject_full_service(service_name, code)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _inject_method(self, service_name: str, method_name: str, code: str) -> dict:
        """Inject a method into existing service class"""
        content = self.services_file.read_text()
        
        # Find service class
        class_pattern = rf"class {service_name.capitalize()}Service:"
        if not re.search(class_pattern, content):
            return {"success": False, "error": f"Service class {service_name} not found"}
        
        # Find last method in class
        lines = content.split('\n')
        class_start = None
        last_method_end = None
        
        for i, line in enumerate(lines):
            if re.match(class_pattern, line.strip()):
                class_start = i
            elif class_start and line.strip().startswith('def ') and i > class_start:
                # Find end of this method
                indent = len(line) - len(line.lstrip())
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() and not lines[j].startswith(' ' * (indent + 1)):
                        last_method_end = j
                        break
        
        if not last_method_end:
            return {"success": False, "error": "Could not find injection point"}
        
        # Insert method
        indent = "    "
        method_lines = [indent + line for line in code.split('\n')]
        lines.insert(last_method_end, '\n' + '\n'.join(method_lines))
        
        self.services_file.write_text('\n'.join(lines))
        
        return {"success": True, "message": f"Method {method_name} injected into {service_name}"}
    
    def _inject_full_service(self, service_name: str, code: str) -> dict:
        """Inject a full service class"""
        content = self.services_file.read_text()
        
        # Check if service already exists
        if f"class {service_name.capitalize()}Service:" in content:
            return {"success": False, "error": f"Service {service_name} already exists"}
        
        # Find ToolServices class
        match = re.search(r'class ToolServices:', content)
        if not match:
            return {"success": False, "error": "ToolServices class not found"}
        
        # Insert before ToolServices
        lines = content.split('\n')
        insert_pos = None
        for i, line in enumerate(lines):
            if 'class ToolServices:' in line:
                insert_pos = i
                break
        
        if not insert_pos:
            return {"success": False, "error": "Could not find injection point"}
        
        # Insert service class
        lines.insert(insert_pos, code + '\n\n')
        
        # Add service to ToolServices.__init__
        init_pattern = r'def __init__\(self, registry\):'
        for i, line in enumerate(lines):
            if re.search(init_pattern, line):
                # Find end of __init__
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() and not lines[j].startswith('        '):
                        # Insert before end
                        service_var = service_name.lower()
                        lines.insert(j, f"        self.{service_var} = {service_name.capitalize()}Service()")
                        break
                break
        
        self.services_file.write_text('\n'.join(lines))
        
        return {"success": True, "message": f"Service {service_name} injected"}
