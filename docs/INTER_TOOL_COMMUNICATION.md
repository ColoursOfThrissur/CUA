# Inter-Tool Communication Guide

## Overview

Tools can now communicate with each other through the orchestrator, enabling composable tool architectures where tools can discover and call other tools dynamically.

## Features Added

### 1. Tool Discovery
Tools can discover what other tools are available:

```python
class MyTool(BaseTool):
    def _handle_process(self, **kwargs):
        # List all available tools
        available_tools = self.services.list_tools()
        print(f"Available: {available_tools}")
        
        # Check if specific capability exists
        if self.services.has_capability('validate_email'):
            # Use it
            pass
```

### 2. Inter-Tool Calls
Tools can call other tools directly:

```python
class MyTool(BaseTool):
    def _handle_create(self, **kwargs):
        email = kwargs.get('email')
        
        # Call another tool to validate email
        try:
            validation = self.services.call_tool(
                tool_name="EmailValidator",
                operation="validate",
                email=email
            )
            
            if not validation.get('valid'):
                raise ValueError("Invalid email")
        except ValueError as e:
            # Tool not found or validation failed
            pass
        
        # Continue with normal logic
        return self.services.storage.save(...)
```

### 3. Service Methods

#### `services.call_tool(tool_name, operation, **parameters)`
Call another tool and get its result.

**Parameters:**
- `tool_name` (str): Name of the tool to call (e.g., "FilesystemTool")
- `operation` (str): Operation to execute (e.g., "read_file")
- `**parameters`: Parameters to pass to the operation

**Returns:** Result data from the tool (plain dict)

**Raises:**
- `RuntimeError`: If orchestrator/registry not available
- `ValueError`: If tool not found
- `RuntimeError`: If tool call fails

**Example:**
```python
content = self.services.call_tool(
    "FilesystemTool",
    "read_file",
    path="data/config.json"
)
```

#### `services.list_tools()`
Get list of all available tools.

**Returns:** List of tool names (e.g., ["FilesystemTool", "HTTPTool"])

**Example:**
```python
tools = self.services.list_tools()
if "EmailValidator" in tools:
    # Use it
```

#### `services.has_capability(capability_name)`
Check if a capability exists in any registered tool.

**Parameters:**
- `capability_name` (str): Name of capability (e.g., "validate_email")

**Returns:** bool - True if capability exists

**Example:**
```python
if self.services.has_capability('send_email'):
    # Email capability available
```

## Architecture

### Flow Diagram
```
Tool A
  ↓
self.services.call_tool("Tool B", "operation", params)
  ↓
ToolServices.call_tool()
  ↓
Registry.get_tool_by_name("Tool B")
  ↓
Orchestrator.execute_tool_step(tool_b, operation, params)
  ↓
Tool B executes
  ↓
Result returned to Tool A
```

### Component Relationships
```
ToolOrchestrator
  ├─ registry: CapabilityRegistry
  └─ get_services() → ToolServices
                        ├─ orchestrator: ToolOrchestrator
                        ├─ registry: CapabilityRegistry
                        └─ call_tool() / list_tools() / has_capability()
```

## Use Cases

### 1. Validation Chain
```python
class ContactTool(BaseTool):
    def _handle_create(self, **kwargs):
        # Validate email if validator available
        if self.services.has_capability('validate_email'):
            result = self.services.call_tool(
                "EmailValidator", 
                "validate",
                email=kwargs['email']
            )
            if not result['valid']:
                raise ValueError("Invalid email")
        
        # Validate phone if validator available
        if self.services.has_capability('validate_phone'):
            result = self.services.call_tool(
                "PhoneValidator",
                "validate", 
                phone=kwargs['phone']
            )
            if not result['valid']:
                raise ValueError("Invalid phone")
        
        return self.services.storage.save(...)
```

### 2. Data Enrichment
```python
class UserTool(BaseTool):
    def _handle_create(self, **kwargs):
        user_data = {
            "name": kwargs['name'],
            "email": kwargs['email']
        }
        
        # Enrich with geolocation if available
        if self.services.has_capability('geolocate'):
            try:
                geo = self.services.call_tool(
                    "GeoTool",
                    "geolocate",
                    ip=kwargs.get('ip')
                )
                user_data['location'] = geo
            except Exception:
                pass  # Optional enrichment
        
        return self.services.storage.save(...)
```

### 3. Multi-Step Processing
```python
class ReportTool(BaseTool):
    def _handle_generate(self, **kwargs):
        # Step 1: Fetch data
        data = self.services.call_tool(
            "DatabaseTool",
            "query",
            sql="SELECT * FROM users"
        )
        
        # Step 2: Process with LLM
        analysis = self.services.call_tool(
            "LLMTool",
            "analyze",
            data=data,
            prompt="Summarize user trends"
        )
        
        # Step 3: Generate PDF
        pdf = self.services.call_tool(
            "PDFTool",
            "create",
            content=analysis
        )
        
        return {"report": pdf}
```

## Error Handling

### Tool Not Found
```python
try:
    result = self.services.call_tool("NonExistent", "op")
except ValueError as e:
    # Handle missing tool
    print(f"Tool not available: {e}")
```

### Tool Call Failed
```python
try:
    result = self.services.call_tool("SomeTool", "op", param="value")
except RuntimeError as e:
    # Handle execution error
    print(f"Tool call failed: {e}")
```

### Graceful Degradation
```python
# Optional feature - degrade gracefully if not available
if self.services.has_capability('advanced_feature'):
    result = self.services.call_tool("AdvancedTool", "process", data=data)
else:
    # Fallback to basic processing
    result = self._basic_process(data)
```

## Best Practices

### 1. Check Before Calling
Always check if capability exists before calling:
```python
if self.services.has_capability('validate'):
    self.services.call_tool("Validator", "validate", ...)
```

### 2. Handle Errors Gracefully
Wrap inter-tool calls in try/except:
```python
try:
    result = self.services.call_tool(...)
except (ValueError, RuntimeError) as e:
    # Handle error or use fallback
```

### 3. Make Features Optional
Don't require other tools - make them optional enhancements:
```python
# Good: Optional enrichment
if self.services.has_capability('enrich'):
    data = self.services.call_tool("Enricher", "enrich", data=data)

# Bad: Required dependency
data = self.services.call_tool("Enricher", "enrich", data=data)  # Fails if not available
```

### 4. Avoid Circular Dependencies
Don't create circular call chains:
```python
# Bad: Tool A calls Tool B calls Tool A
# This will cause infinite recursion
```

## Backward Compatibility

All changes are backward compatible:
- Tools without orchestrator still work (limited functionality)
- Legacy tools unaffected
- Inter-tool features only available when orchestrator provided

## Testing

See `tests/test_inter_tool_communication.py` for comprehensive test examples.

## Future Enhancements

Planned features:
- Call stack tracking (prevent infinite loops)
- Parallel tool execution
- Conditional routing (if/else logic)
- Output transformation layer
- Explicit parameter mapping syntax
