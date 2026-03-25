# Data Operations Skill

## Overview
Data transformation, API interactions, database queries, and structured data processing tasks.

## Capabilities
- **API Integration**: Make HTTP requests to REST APIs and web services
- **JSON Processing**: Parse, transform, and manipulate JSON data structures
- **Database Queries**: Execute SQL queries and retrieve database information
- **Data Transformation**: Convert between different data formats and structures
- **Web Service Integration**: Interact with external web services and APIs

## Preferred Tools
- **HTTPTool**: HTTP requests and API interactions
- **JSONTool**: JSON parsing and manipulation
- **DatabaseQueryTool**: Database queries and schema analysis

## Verification Mode
- **output_validation**: Validates data structure and format of results

## Risk Level
- **Medium**: API calls and database queries can access external systems

## Output Types
- **api_response**: Results from HTTP API calls
- **query_result**: Database query results and metadata
- **transformed_data**: Processed and transformed data structures
- **json_structure**: Parsed and manipulated JSON objects

## Use Cases
1. **API Integration**: Connect to external services and retrieve data
2. **Data Processing**: Transform and manipulate structured data
3. **Database Analysis**: Query databases and analyze schema information
4. **Service Integration**: Integrate with third-party web services
5. **Data Validation**: Validate and process incoming data structures

## Fallback Strategy
Direct tool routing for simple data operations that don't require complex orchestration.

## Managed Tool Updates
- Added `DataTransformationTool` for operations: convert_format, filter_data, sort_data, aggregate_data.

## Managed Workflow Updates
### DataTransformationTool (create_tool)
- Prefer `DataTransformationTool` when the task needs: convert_format, filter_data, sort_data, aggregate_data.
- Added `DataTransformationTool` for operations: convert_format, filter_records, sort_list, aggregate_data.

### DataTransformationTool (create_tool)
- Prefer `DataTransformationTool` when the task needs: convert_format, filter_records, sort_list, aggregate_data.
- Added `DiffComparisonTool` for operations: compare_text_files, compare_json_data, compare_config_files, compare_directory_trees.

### DiffComparisonTool (create_tool)
- Prefer `DiffComparisonTool` when the task needs: compare_text_files, compare_json_data, compare_config_files, compare_directory_trees.
- Updated `DiffComparisonTool` for operations: new workflow support.

### DiffComparisonTool (evolve_tool, tool_evolution)
- Reason: User request: Evolve DiffComparisonTool: replace self.services.storage.get/list with self.services.fs.read/list for file operations. Implement real diff logic: text diff should return line-by-line changes (added/removed lines with line numbers), JSON diff should recursively compare keys and return added/removed/changed paths in dot-notation, directory diff should return lists of added/removed/common files.. Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DiffComparisonTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### DiffComparisonTool (evolve_tool, tool_evolution)
- Reason: User request: Low health score (59.7) - . Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DiffComparisonTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.
- Updated `DataTransformationTool` for operations: new workflow support.

### DataTransformationTool (evolve_tool, tool_evolution)
- Reason: User request: Enhancement opportunity: Add a capability to merge multiple datasets based on specified keys. This will enhance the tool's ability to integrate and analyze data from different sources.. Code quality: HEALTHY, Health: 50/100
- Re-evaluate `DataTransformationTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### DiffComparisonTool (evolve_tool, tool_evolution)
- Reason: User request: Feature enhancements suggested (1 improvements). Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DiffComparisonTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### DiffComparisonTool (evolve_tool, tool_evolution)
- Reason: User request: Low health score (54.7) - . Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DiffComparisonTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### DataTransformationTool (evolve_tool, tool_evolution)
- Reason: User request: Low health score (55.8) - . Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DataTransformationTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### DiffComparisonTool (evolve_tool, tool_evolution)
- Reason: User request: Low health score (59.2) - . Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DiffComparisonTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### DiffComparisonTool (evolve_tool, tool_evolution)
- Reason: User request: Feature enhancements suggested (3 improvements). Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DiffComparisonTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### DataTransformationTool (evolve_tool, tool_evolution)
- Reason: User request: Feature enhancements suggested (2 improvements). Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DataTransformationTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.
- Updated `DatabaseQueryTool` for operations: new workflow support.

### DatabaseQueryTool (evolve_tool, tool_evolution)
- Reason: User request: Feature enhancements suggested (2 improvements). Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DatabaseQueryTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### DiffComparisonTool (evolve_tool, tool_evolution)
- Reason: User request: Enhancement opportunity: Add capability to compare CSV files by comparing rows and columns, returning detailed differences in a structured format.. Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DiffComparisonTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.

### DiffComparisonTool (evolve_tool, tool_evolution)
- Reason: User request: Enhancement opportunity: Implement a capability to compare binary files (e.g., images, PDFs) and report basic differences like size or checksum.. Code quality: HEALTHY, Health: 95/100
- Re-evaluate `DiffComparisonTool` first for improved handling of: existing workflow steps.
- Strengthen the step-by-step workflow before proposing unrelated new tools.
