# LLM-Based Tool Health Analysis System

## Overview
Sequential LLM-powered tool code analysis that identifies issues and suggests improvements, integrated with observability and evolution workflows.

## Architecture

### Core Component
**File**: `core/llm_tool_health_analyzer.py`

**4-Step Sequential Analysis**:
1. **Understand Purpose** - LLM explains what the tool is supposed to do
2. **Identify Issues** - Finds bugs, architecture problems, performance issues, maintainability concerns
3. **Suggest Improvements** - Proposes new capabilities and enhancements (not fixes)
4. **Categorize Health** - Classifies as WEAK, NEEDS_IMPROVEMENT, HEALTHY_WITH_ENHANCEMENTS, or HEALTHY

### Issue Categories
- **BUGS** - Actual code errors (wrong variables, missing attributes, logic errors)
- **ARCHITECTURE** - Design problems (not using services, direct implementations)
- **PERFORMANCE** - Inefficiencies (missing caching, redundant operations)
- **MAINTAINABILITY** - Code quality (unclear logic, missing error handling)

### Improvement Types
- **NEW_CAPABILITY** - Additional operations/features
- **ENHANCEMENT** - Improvements to existing features
- **INTEGRATION** - Better use of available services

### Health Categories
- **WEAK** - High severity bugs or 5+ issues → Goes to "Recommended" list
- **NEEDS_IMPROVEMENT** - Has issues but not critical
- **HEALTHY_WITH_ENHANCEMENTS** - No issues but has improvement suggestions
- **HEALTHY** - No issues, no improvements needed

## API Endpoints

### Quality API (`api/quality_api.py`)
```
GET  /quality/llm-analysis/{tool_name}?force_refresh=false
     - Get LLM analysis for specific tool
     - Returns: purpose, issues[], improvements[], category

GET  /quality/llm-analysis-all?force_refresh=false
     - Get analysis for all tools
     - Returns: {tool_name: analysis_result}

GET  /quality/llm-weak?force_refresh=false
     - Get tools categorized as WEAK
     - Returns: [analysis_results]

GET  /quality/llm-summary?force_refresh=false
     - Get summary of all tool health
     - Returns: total_tools, categories{}, weak_tools[], needs_improvement[]

POST /quality/refresh-llm-analysis
     - Manually refresh all tool analysis
     - Returns: status, analyzed count, summary
```

### Observability API (`api/observability_api.py`)
**Fixed**: Now uses absolute paths for database files
- All endpoints working correctly with proper path resolution

## UI Integration

### Evolution Mode (`ui/src/components/EvolutionMode.js`)
**Changes**:
- "Recommended" mode now fetches from `/quality/llm-weak` (LLM-analyzed weak tools)
- Shows LLM analysis card when tool selected:
  - Tool purpose
  - Issues found (with severity badges)
  - Suggested improvements (with priority badges)
- Color-coded display:
  - Issues: RED (high), ORANGE (medium), BLUE (low)
  - Improvements: Priority badges with colors

### Observability Overlay (`ui/src/components/ObservabilityOverlay.js`)
**New Tab**: "LLM Health Analysis"
- Shows all tool analysis results
- **Refresh Analysis** button - Triggers full re-analysis of all tools
- Displays cached results by default
- Manual refresh forces LLM to re-analyze all tools

## Data Flow

### Evolution Workflow
```
User opens Evolution Mode
    ↓
Selects "Recommended" → Fetches /quality/llm-weak
    ↓
Shows WEAK tools only
    ↓
User selects tool → Fetches /quality/llm-analysis/{tool_name}
    ↓
Displays:
  - Current capabilities
  - LLM-identified issues
  - LLM-suggested improvements
    ↓
User clicks "Start Evolution" → Existing evolution flow
```

### Manual Refresh Workflow
```
User opens Observability → LLM Health Analysis tab
    ↓
Clicks "Refresh Analysis" button
    ↓
POST /quality/refresh-llm-analysis
    ↓
LLM analyzes all tools sequentially:
  1. Understand purpose
  2. Identify issues
  3. Suggest improvements
  4. Categorize health
    ↓
Results cached to data/llm_health_cache.json
    ↓
UI refreshes to show updated analysis
```

## Caching System
**File**: `data/llm_health_cache.json`

**Structure**:
```json
{
  "ToolName": {
    "tool_name": "ToolName",
    "purpose": "What the tool does...",
    "issues": [
      {
        "category": "BUGS",
        "severity": "HIGH",
        "description": "Uses self.cache instead of self._cache",
        "line_hint": "line 120"
      }
    ],
    "improvements": [
      {
        "type": "NEW_CAPABILITY",
        "priority": "HIGH",
        "description": "Add batch processing support"
      }
    ],
    "category": "WEAK",
    "timestamp": "1234567890.123"
  }
}
```

**Cache Behavior**:
- Loaded on analyzer initialization
- Used by default unless `force_refresh=true`
- Saved after each tool analysis
- Persists across server restarts

## Key Features

### Sequential LLM Reasoning
- Not one-shot analysis
- LLM first understands purpose
- Then identifies issues based on purpose
- Then suggests improvements considering issues
- Finally categorizes health

### Separation of Concerns
- **Issues** = Problems to fix (bugs, architecture, performance)
- **Improvements** = New features to add (capabilities, enhancements)
- Evolution system can address both

### Integration with Existing Systems
- Works alongside metric-based quality analyzer
- Feeds into evolution "Recommended" list
- Visible in observability dashboard
- Manual refresh capability

### Non-Blocking
- Analysis runs on-demand or manual refresh
- Cached results used by default
- No impact on tool execution performance

## Usage Examples

### Check Tool Health
```bash
curl http://localhost:8000/quality/llm-analysis/ContextSummarizerTool
```

### Get All Weak Tools
```bash
curl http://localhost:8000/quality/llm-weak
```

### Refresh All Analysis
```bash
curl -X POST http://localhost:8000/quality/refresh-llm-analysis
```

### Get Summary
```bash
curl http://localhost:8000/quality/llm-summary
```

## Benefits

1. **Self-Awareness** - System can analyze its own code quality
2. **Proactive** - Identifies issues before they cause failures
3. **Intelligent** - LLM understands context and purpose
4. **Actionable** - Provides specific, categorized feedback
5. **Integrated** - Feeds directly into evolution workflow
6. **Observable** - Visible in observability dashboard
7. **Cacheable** - Fast repeated access to analysis results
8. **Manual Control** - User can trigger re-analysis anytime

## Future Enhancements

- Auto-trigger analysis after tool creation
- Schedule periodic re-analysis
- Track analysis history over time
- Compare analysis before/after evolution
- Generate evolution prompts from analysis results
- Priority-based evolution queue
