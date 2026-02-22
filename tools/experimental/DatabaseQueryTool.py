"""
DatabaseQueryTool - Query system operational data (Legacy Tool)
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class DatabaseQueryTool(BaseTool):
    """Query and analyze system's operational data from SQLite databases."""
    
    def __init__(self, orchestrator=None):
        self.description = "Query and analyze system operational data"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        self.data_dir = Path(__file__).parent.parent.parent / "data"
        from core.database_schema_registry import get_schema_for_llm, DATABASE_SCHEMAS
        self.schema_registry = DATABASE_SCHEMAS
        self.get_schema = get_schema_for_llm
        super().__init__()

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name='query_logs',
            description='Use this when user asks about system logs, errors in logs, or wants to search log messages. Queries the system logs database.',
            parameters=[
                Parameter(name='level', type=ParameterType.STRING, description='Log level filter: INFO, WARNING, ERROR, DEBUG', required=False),
                Parameter(name='hours_ago', type=ParameterType.INTEGER, description='Filter logs from last N hours', required=False, default=24),
                Parameter(name='pattern', type=ParameterType.STRING, description='Search pattern in log messages', required=False),
                Parameter(name='limit', type=ParameterType.INTEGER, description='Max results to return', required=False, default=100)
            ],
            returns="List of log entries",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        ), self._handle_query_logs)

        self.add_capability(ToolCapability(
            name='analyze_tool_performance',
            description='ACTION: Query and return tool execution statistics from database. Use when user asks to analyze performance, check success rates, or get execution metrics.',
            parameters=[
                Parameter(name='tool_name', type=ParameterType.STRING, description='Specific tool name to analyze (optional)', required=False),
                Parameter(name='hours_ago', type=ParameterType.INTEGER, description='Analyze executions from last N hours', required=False, default=24)
            ],
            returns="Tool performance statistics",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        ), self._handle_analyze_tool_performance)

        self.add_capability(ToolCapability(
            name='find_failure_patterns',
            description='ACTION: Query and return actual tool failure data from execution database. Use when user asks "which tools are failing", "show failures", "what errors", "why failing". This retrieves real execution data.',
            parameters=[
                Parameter(name='tool_name', type=ParameterType.STRING, description='Filter by tool name', required=False),
                Parameter(name='hours_ago', type=ParameterType.INTEGER, description='Look back N hours', required=False, default=24),
                Parameter(name='limit', type=ParameterType.INTEGER, description='Max results', required=False, default=50)
            ],
            returns="Failed executions with error details",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        ), self._handle_find_failure_patterns)

        self.add_capability(ToolCapability(
            name='get_evolution_history',
            description='Query tool evolution attempts and outcomes',
            parameters=[
                Parameter(name='tool_name', type=ParameterType.STRING, description='Filter by tool name', required=False),
                Parameter(name='status', type=ParameterType.STRING, description='Filter by status: pending, approved, rejected', required=False),
                Parameter(name='limit', type=ParameterType.INTEGER, description='Max results', required=False, default=50)
            ],
            returns="Evolution history with step details",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        ), self._handle_get_evolution_history)

        self.add_capability(ToolCapability(
            name='export_to_json',
            description='Export query results to JSON file',
            parameters=[
                Parameter(name='data', type=ParameterType.DICT, description='Data to export', required=True),
                Parameter(name='filename', type=ParameterType.STRING, description='Output filename', required=True)
            ],
            returns="Export confirmation",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        ), self._handle_export_to_json)

        self.add_capability(ToolCapability(
            name='get_database_schema',
            description='Get schema information for databases to help construct correct queries',
            parameters=[
                Parameter(name='database_name', type=ParameterType.STRING, description='Database name (e.g., logs.db, tool_executions.db)', required=False)
            ],
            returns="Database schema with tables, columns, and query examples",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        ), self._handle_get_database_schema)

        self.add_capability(ToolCapability(
            name='validate_schema',
            description='Validate actual database schema matches registry and update if needed',
            parameters=[
                Parameter(name='database_name', type=ParameterType.STRING, description='Database to validate', required=True)
            ],
            returns="Validation results with any schema mismatches",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        ), self._handle_validate_schema)

    def execute(self, operation: str, **kwargs) -> ToolResult:
        try:
            if operation == 'query_logs':
                result = self._handle_query_logs(**kwargs)
            elif operation == 'analyze_tool_performance':
                result = self._handle_analyze_tool_performance(**kwargs)
            elif operation == 'find_failure_patterns':
                result = self._handle_find_failure_patterns(**kwargs)
            elif operation == 'get_evolution_history':
                result = self._handle_get_evolution_history(**kwargs)
            elif operation == 'export_to_json':
                result = self._handle_export_to_json(**kwargs)
            elif operation == 'get_database_schema':
                result = self._handle_get_database_schema(**kwargs)
            elif operation == 'validate_schema':
                result = self._handle_validate_schema(**kwargs)
            else:
                return ToolResult(
                    tool_name=self.__class__.__name__,
                    capability_name=operation,
                    status=ResultStatus.FAILURE,
                    error_message=f"Unsupported operation: {operation}"
                )
            
            return ToolResult(
                tool_name=self.__class__.__name__,
                capability_name=operation,
                status=ResultStatus.SUCCESS,
                data=result
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.__class__.__name__,
                capability_name=operation,
                status=ResultStatus.FAILURE,
                error_message=str(e)
            )

    def _handle_query_logs(self, **kwargs):
            db_paths = [self.data_dir / "logs.db"]
            if not any(db_path.exists() for db_path in db_paths):
                self.services.logging.error("Database not found")
                return {"logs": [], "count": 0, "error": "Database not found"}

            level = kwargs.get('level')
            hours_ago = kwargs.get('hours_ago', 24)
            pattern = kwargs.get('pattern')
            limit = kwargs.get('limit', 100)

            cutoff_time = self.services.time.now_utc() - timedelta(hours=hours_ago)
            results = []

            for db_path in db_paths:
                try:
                    conn = sqlite3.connect(str(db_path))
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()

                    query = "SELECT * FROM logs WHERE timestamp >= ?"
                    params = [cutoff_time.isoformat()]

                    if level:
                        query += " AND level = ?"
                        params.append(level.upper())

                    if pattern:
                        query += " AND message LIKE ?"
                        params.append(f"%{pattern}%")

                    query += " ORDER BY timestamp DESC LIMIT ?"
                    params.append(limit)

                    cursor.execute(query, params)
                    results.extend([dict(row) for row in cursor.fetchall()])
                    conn.close()
                except Exception as e:
                    self.services.logging.error(f"Error executing query on {db_path}: {str(e)}")

            self.services.logging.info("Query executed successfully")
            return {"logs": results, "count": len(results)}

    def _handle_analyze_tool_performance(self, **kwargs):
            db_paths = [self.data_dir / "tool_executions.db"]
            if not any(db_path.exists() for db_path in db_paths):
                return {"performance": [], "count": 0, "error": "Database not found"}

            tool_name = kwargs.get('tool_name')
            hours_ago = kwargs.get('hours_ago', 24)
            cutoff_time = self.services.time.now_utc().timestamp() - (hours_ago * 3600)

            results = []
            for db_path in db_paths:
                try:
                    conn = sqlite3.connect(str(db_path))
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()

                    if tool_name:
                        query = """
                            SELECT 
                                tool_name,
                                COUNT(*) as total_executions,
                                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors,
                                AVG(execution_time_ms) as avg_duration,
                                MAX(timestamp) as last_execution
                            FROM executions
                            WHERE tool_name = ? AND timestamp >= ?
                            GROUP BY tool_name
                        """
                        cursor.execute(query, [tool_name, cutoff_time])
                    else:
                        query = """
                            SELECT 
                                tool_name,
                                COUNT(*) as total_executions,
                                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors,
                                AVG(execution_time_ms) as avg_duration,
                                MAX(timestamp) as last_execution
                            FROM executions
                            WHERE timestamp >= ?
                            GROUP BY tool_name
                            ORDER BY total_executions DESC
                        """
                        cursor.execute(query, [cutoff_time])

                    for row in cursor.fetchall():
                        data = dict(row)
                        if data['total_executions'] > 0:
                            data['success_rate'] = round((data['successes'] / data['total_executions']) * 100, 2)
                        results.append(data)

                    conn.close()
                except Exception as e:
                    self.services.logging.error(f"Error analyzing tool performance in {db_path}: {str(e)}")

            self.services.logging.info(f"Analyzed tool performance for {tool_name} with {len(results)} tools.")
            return {"performance": results, "count": len(results)}

    def _handle_find_failure_patterns(self, **kwargs):
        db_paths = [self.data_dir / "tool_executions.db"]
        if not any(db_path.exists() for db_path in db_paths):
            self.services.logging.error("Database not found")
            return {"failures": [], "count": 0, "error": "Database not found"}

        tool_name = kwargs.get('tool_name')
        hours_ago = kwargs.get('hours_ago', 24)
        limit = kwargs.get('limit', 50)
        cutoff_time = self.services.time.now_utc().timestamp() - (hours_ago * 3600)

        failures = []
        for db_path in db_paths:
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = "SELECT * FROM executions WHERE success = 0 AND timestamp >= ?"
                params = [cutoff_time]

                if tool_name:
                    query += " AND tool_name = ?"
                    params.append(tool_name)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                failures.extend([dict(row) for row in cursor.fetchall()])
                conn.close()
            except Exception as e:
                self.services.logging.error(f"Error fetching failures from {db_path}: {str(e)}")

        self.services.logging.info(f"Found {len(failures)} failures")
        return {"failures": failures, "count": len(failures)}

    def _handle_get_evolution_history(self, **kwargs):
            db_paths = [self.data_dir / "tool_evolution.db"]
            if not any(db_path.exists() for db_path in db_paths):
                self.services.logging.warning("Database not found")
                return {"evolutions": [], "count": 0, "error": "Database not found"}

            tool_name = kwargs.get('tool_name')
            status = kwargs.get('status')
            limit = kwargs.get('limit', 50)

            try:
                evolutions = []
                for db_path in db_paths:
                    schema = self.schema_registry.get('tool_evolution.db', {})
                    tables = list(schema.get('tables', {}).keys())
                    table_name = tables[0] if tables else 'evolution_runs'

                    conn = sqlite3.connect(str(db_path))
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()

                    query = f"SELECT * FROM {table_name} WHERE 1=1"
                    params = []

                    if tool_name:
                        query += " AND tool_name = ?"
                        params.append(tool_name)

                    if status:
                        query += " AND status = ?"
                        params.append(status)

                    query += " ORDER BY timestamp DESC LIMIT ?"
                    params.append(limit)

                    cursor.execute(query, params)
                    evolutions.extend([dict(row) for row in cursor.fetchall()])
                    conn.close()

                self.services.logging.info(f"Retrieved {len(evolutions)} evolution records")
                return {"evolutions": evolutions, "count": len(evolutions)}
            except Exception as e:
                self.services.logging.error(f"Error retrieving evolution history: {str(e)}")
                return {"evolutions": [], "count": 0, "error": str(e)}

    def _handle_export_to_json(self, **kwargs):
            if 'data' not in kwargs or 'filename' not in kwargs:
                raise ValueError("Missing required parameters: data, filename")

            data = kwargs['data']
            filename = kwargs['filename']

            if not filename.endswith('.json'):
                filename += '.json'

            output_path = self.data_dir / filename

            try:
                json_str = self.services.json.stringify(data, indent=2)
                self.services.fs.write(output_path, json_str, encoding='utf-8')
                self.services.logging.info(f"Exported JSON to {output_path}")
                return {"status": "exported", "path": str(output_path), "size": len(json_str)}
            except Exception as e:
                self.services.logging.error(f"Failed to export JSON: {str(e)}")
                return {"status": "failed", "error": str(e)}

    def _handle_get_database_schema(self, **kwargs):
            database_names = kwargs.get('database_name', [])
            if isinstance(database_names, str):
                database_names = [database_names]

            results = []
            for db_name in database_names:
                try:
                    schema_text = self.get_schema(db_name)
                    if not schema_text or "Database:" not in schema_text:
                        self.services.logging.warning(f"Schema not found for {db_name}")
                        results.append({"error": f"Schema not found for {db_name}", "available": list(self.schema_registry.keys())})
                    else:
                        self.services.logging.info(f"Schema retrieved for {db_name}")
                        results.append({"schema": schema_text, "database": db_name})
                except Exception as e:
                    self.services.logging.error(f"Error handling get_database_schema for {db_name}: {e}")
                    results.append({"error": str(e)})

            if not database_names:
                self.services.logging.warning("No database name provided")
                return {"schema": self.get_schema(), "databases": list(self.schema_registry.keys())}

            return {"results": results}

    def _handle_validate_schema(self, **kwargs):
            database_names = kwargs.get('database_names', [kwargs.get('database_name')])
            if not database_names:
                raise ValueError("At least one database_name required")

            results = []
            for db_name in database_names:
                db_path = self.data_dir / db_name
                if not db_path.exists():
                    self.services.logging.warning(f"Database {db_name} not found at {db_path}")
                    results.append({"database": db_name, "error": f"Database {db_name} not found", "path": str(db_path)})
                    continue

                registry_schema = self.schema_registry.get(db_name)
                if not registry_schema:
                    self.services.logging.warning(f"No registry entry for {db_name}")
                    results.append({"database": db_name, "error": f"No registry entry for {db_name}"})
                    continue

                try:
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()

                    mismatches = []
                    for table_name, table_info in registry_schema['tables'].items():
                        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table_name])
                        if not cursor.fetchone():
                            mismatches.append({"type": "missing_table", "table": table_name})
                            continue

                        cursor.execute(f"PRAGMA table_info({table_name})")
                        actual_cols = {row[1]: row[2] for row in cursor.fetchall()}
                        registry_cols = list(table_info['columns'].keys())

                        for col in registry_cols:
                            if col not in actual_cols:
                                mismatches.append({"type": "missing_column", "table": table_name, "column": col})

                        for col in actual_cols:
                            if col not in registry_cols:
                                mismatches.append({"type": "undocumented_column", "table": table_name, "column": col, "type": actual_cols[col]})

                    conn.close()

                    result = {
                        "database": db_name,
                        "valid": len(mismatches) == 0,
                        "mismatches": mismatches,
                        "message": "Schema matches registry" if not mismatches else f"Found {len(mismatches)} mismatches"
                    }
                    self.services.logging.info(f"Schema validation result for {db_name}: {result}")
                    results.append(result)
                except Exception as e:
                    self.services.logging.error(f"Error validating schema for {db_name}: {str(e)}")
                    results.append({"database": db_name, "error": str(e)})

            return {"results": results}
