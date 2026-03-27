"""DataVisualizationTool — generates charts from data using matplotlib."""
import json
import base64
from io import BytesIO
from typing import Dict, List, Any
from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel


class DataVisualizationTool(BaseTool):
    """Generate charts and graphs from data — line, bar, pie, scatter, heatmap."""

    def __init__(self, orchestrator=None):
        self.description = "Generate visual charts from data"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name="render_output",
            description="Context-aware output rendering: detects data type (table, chart, text, code, etc.) and formats it for display. Automatically chooses best visualization.",
            parameters=[
                Parameter("data", ParameterType.STRING, "Data to render (JSON string or raw text)", required=True),
                Parameter("context", ParameterType.STRING, "Context hint: 'metrics', 'comparison', 'trend', 'distribution', 'table', 'code', 'text', 'health', 'finance', etc.", required=False),
                Parameter("title", ParameterType.STRING, "Title for the output", required=False),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["matplotlib"]
        ), self._handle_render_output)

        self.add_capability(ToolCapability(
            name="line_chart",
            description="Generate line chart from x/y data. Returns base64 PNG.",
            parameters=[
                Parameter("x_values", ParameterType.STRING, "X-axis values (JSON array)", required=True),
                Parameter("y_values", ParameterType.STRING, "Y-axis values (JSON array)", required=True),
                Parameter("title", ParameterType.STRING, "Chart title", required=False),
                Parameter("x_label", ParameterType.STRING, "X-axis label", required=False),
                Parameter("y_label", ParameterType.STRING, "Y-axis label", required=False),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["matplotlib"]
        ), self._handle_line_chart)

        self.add_capability(ToolCapability(
            name="bar_chart",
            description="Generate bar chart. Returns base64 PNG.",
            parameters=[
                Parameter("labels", ParameterType.STRING, "Bar labels (JSON array)", required=True),
                Parameter("values", ParameterType.STRING, "Bar values (JSON array)", required=True),
                Parameter("title", ParameterType.STRING, "Chart title", required=False),
                Parameter("x_label", ParameterType.STRING, "X-axis label", required=False),
                Parameter("y_label", ParameterType.STRING, "Y-axis label", required=False),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["matplotlib"]
        ), self._handle_bar_chart)

        self.add_capability(ToolCapability(
            name="pie_chart",
            description="Generate pie chart. Returns base64 PNG.",
            parameters=[
                Parameter("labels", ParameterType.STRING, "Slice labels (JSON array)", required=True),
                Parameter("values", ParameterType.STRING, "Slice values (JSON array)", required=True),
                Parameter("title", ParameterType.STRING, "Chart title", required=False),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["matplotlib"]
        ), self._handle_pie_chart)

        self.add_capability(ToolCapability(
            name="scatter_plot",
            description="Generate scatter plot. Returns base64 PNG.",
            parameters=[
                Parameter("x_values", ParameterType.STRING, "X-axis values (JSON array)", required=True),
                Parameter("y_values", ParameterType.STRING, "Y-axis values (JSON array)", required=True),
                Parameter("title", ParameterType.STRING, "Chart title", required=False),
                Parameter("x_label", ParameterType.STRING, "X-axis label", required=False),
                Parameter("y_label", ParameterType.STRING, "Y-axis label", required=False),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["matplotlib"]
        ), self._handle_scatter_plot)

        self.add_capability(ToolCapability(
            name="multi_line_chart",
            description="Generate multi-line chart. Returns base64 PNG.",
            parameters=[
                Parameter("x_values", ParameterType.STRING, "X-axis values (JSON array)", required=True),
                Parameter("series", ParameterType.STRING, "Series data (JSON array of {name, values})", required=True),
                Parameter("title", ParameterType.STRING, "Chart title", required=False),
                Parameter("x_label", ParameterType.STRING, "X-axis label", required=False),
                Parameter("y_label", ParameterType.STRING, "Y-axis label", required=False),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["matplotlib"]
        ), self._handle_multi_line_chart)

    def execute(self, operation: str, **kwargs):
        return self.execute_capability(operation, **kwargs)

    def _parse_json_param(self, value: Any) -> Any:
        """Parse JSON string or return value as-is."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    def _render_to_base64(self, fig) -> str:
        """Render matplotlib figure to base64 PNG."""
        buf = BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        return b64

    def _handle_line_chart(self, **kwargs) -> dict:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            return {"success": False, "error": "matplotlib not installed. Run: pip install matplotlib"}

        try:
            x = self._parse_json_param(kwargs.get("x_values"))
            y = self._parse_json_param(kwargs.get("y_values"))
            if not isinstance(x, list) or not isinstance(y, list):
                return {"success": False, "error": "x_values and y_values must be JSON arrays"}
            if len(x) != len(y):
                return {"success": False, "error": "x_values and y_values must have same length"}

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(x, y, marker='o', linewidth=2)
            if kwargs.get("title"):
                ax.set_title(kwargs["title"], fontsize=14, fontweight='bold')
            if kwargs.get("x_label"):
                ax.set_xlabel(kwargs["x_label"])
            if kwargs.get("y_label"):
                ax.set_ylabel(kwargs["y_label"])
            ax.grid(True, alpha=0.3)
            plt.tight_layout()

            b64 = self._render_to_base64(fig)
            plt.close(fig)
            return {"success": True, "image": b64, "format": "png"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_bar_chart(self, **kwargs) -> dict:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            return {"success": False, "error": "matplotlib not installed"}

        try:
            labels = self._parse_json_param(kwargs.get("labels"))
            values = self._parse_json_param(kwargs.get("values"))
            if not isinstance(labels, list) or not isinstance(values, list):
                return {"success": False, "error": "labels and values must be JSON arrays"}
            if len(labels) != len(values):
                return {"success": False, "error": "labels and values must have same length"}

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.bar(labels, values, color='steelblue', edgecolor='black')
            if kwargs.get("title"):
                ax.set_title(kwargs["title"], fontsize=14, fontweight='bold')
            if kwargs.get("x_label"):
                ax.set_xlabel(kwargs["x_label"])
            if kwargs.get("y_label"):
                ax.set_ylabel(kwargs["y_label"])
            ax.grid(axis='y', alpha=0.3)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()

            b64 = self._render_to_base64(fig)
            plt.close(fig)
            return {"success": True, "image": b64, "format": "png"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_pie_chart(self, **kwargs) -> dict:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            return {"success": False, "error": "matplotlib not installed"}

        try:
            labels = self._parse_json_param(kwargs.get("labels"))
            values = self._parse_json_param(kwargs.get("values"))
            if not isinstance(labels, list) or not isinstance(values, list):
                return {"success": False, "error": "labels and values must be JSON arrays"}
            if len(labels) != len(values):
                return {"success": False, "error": "labels and values must have same length"}

            fig, ax = plt.subplots(figsize=(8, 8))
            ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
            if kwargs.get("title"):
                ax.set_title(kwargs["title"], fontsize=14, fontweight='bold')
            plt.tight_layout()

            b64 = self._render_to_base64(fig)
            plt.close(fig)
            return {"success": True, "image": b64, "format": "png"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_scatter_plot(self, **kwargs) -> dict:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            return {"success": False, "error": "matplotlib not installed"}

        try:
            x = self._parse_json_param(kwargs.get("x_values"))
            y = self._parse_json_param(kwargs.get("y_values"))
            if not isinstance(x, list) or not isinstance(y, list):
                return {"success": False, "error": "x_values and y_values must be JSON arrays"}
            if len(x) != len(y):
                return {"success": False, "error": "x_values and y_values must have same length"}

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.scatter(x, y, alpha=0.6, s=50, edgecolors='black')
            if kwargs.get("title"):
                ax.set_title(kwargs["title"], fontsize=14, fontweight='bold')
            if kwargs.get("x_label"):
                ax.set_xlabel(kwargs["x_label"])
            if kwargs.get("y_label"):
                ax.set_ylabel(kwargs["y_label"])
            ax.grid(True, alpha=0.3)
            plt.tight_layout()

            b64 = self._render_to_base64(fig)
            plt.close(fig)
            return {"success": True, "image": b64, "format": "png"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_render_output(self, **kwargs) -> dict:
        """Context-aware output rendering - detects data type and formats appropriately."""
        try:
            data_str = kwargs.get("data")
            context = (kwargs.get("context") or "").lower()
            title = kwargs.get("title")

            if not data_str:
                return {"success": False, "error": "No data provided"}

            # Parse data
            data = self._parse_json_param(data_str)

            # Detect output type based on context and data structure
            output_type = self._detect_output_type(data, context)

            if output_type == "chart":
                return self._render_chart(data, context, title)
            elif output_type == "table":
                return self._render_table(data, title)
            elif output_type == "metrics":
                return self._render_metrics(data, title)
            elif output_type == "code":
                return self._render_code(data, title)
            elif output_type == "text":
                return self._render_text(data, title)
            else:
                # Fallback: return structured data for UI to handle
                return {"success": True, "type": "raw", "data": data, "title": title}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _detect_output_type(self, data: Any, context: str) -> str:
        """Detect the best output format based on data structure and context."""
        # Context hints take priority
        if context in ("chart", "trend", "comparison", "distribution"):
            return "chart"
        if context in ("table", "list", "rows"):
            return "table"
        if context in ("metrics", "stats", "health", "performance"):
            return "metrics"
        if context in ("code", "patch", "diff"):
            return "code"
        if context in ("text", "summary", "description"):
            return "text"

        # Auto-detect from data structure
        if isinstance(data, dict):
            # Metrics: scalar key-value pairs
            if all(isinstance(v, (int, float, bool)) for v in data.values()):
                return "metrics"
            # Chart data: has labels/values or x/y structure
            if ("labels" in data and "values" in data) or ("x" in data and "y" in data):
                return "chart"
            # Code: has code/patch field
            if "code" in data or "patch" in data:
                return "code"

        # List of dicts = table
        if isinstance(data, list) and data and isinstance(data[0], dict):
            # If all dicts have numeric values, could be chart data
            first = data[0]
            if "value" in first or "count" in first:
                return "chart"
            return "table"

        # List of numbers = chart
        if isinstance(data, list) and data and isinstance(data[0], (int, float)):
            return "chart"

        # String = text
        if isinstance(data, str):
            return "text"

        return "raw"

    def _render_chart(self, data: Any, context: str, title: str) -> dict:
        """Render data as chart based on context."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            return {"success": False, "error": "matplotlib not installed"}

        try:
            # Normalize data to labels/values
            if isinstance(data, dict):
                if "labels" in data and "values" in data:
                    labels = data["labels"]
                    values = data["values"]
                elif "x" in data and "y" in data:
                    labels = data["x"]
                    values = data["y"]
                else:
                    labels = list(data.keys())
                    values = list(data.values())
            elif isinstance(data, list) and data and isinstance(data[0], dict):
                labels = [d.get("label") or d.get("name") or str(i) for i, d in enumerate(data)]
                values = [d.get("value") or d.get("count") or 0 for d in data]
            elif isinstance(data, list):
                labels = [str(i) for i in range(len(data))]
                values = data
            else:
                return {"success": False, "error": "Cannot convert data to chart format"}

            # Choose chart type based on context
            if context in ("distribution", "breakdown", "share"):
                chart_type = "pie"
            elif context in ("trend", "time", "series"):
                chart_type = "line"
            elif context in ("comparison", "ranking"):
                chart_type = "bar"
            else:
                # Auto-detect: pie if < 8 items and percentages, else bar
                if len(labels) <= 7 and all(isinstance(v, (int, float)) and 0 <= v <= 100 for v in values):
                    chart_type = "pie"
                else:
                    chart_type = "bar"

            fig, ax = plt.subplots(figsize=(10, 6))

            if chart_type == "pie":
                ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
                if title:
                    ax.set_title(title, fontsize=14, fontweight='bold')
            elif chart_type == "line":
                ax.plot(labels, values, marker='o', linewidth=2)
                if title:
                    ax.set_title(title, fontsize=14, fontweight='bold')
                ax.grid(True, alpha=0.3)
                plt.xticks(rotation=45, ha='right')
            else:  # bar
                ax.bar(labels, values, color='steelblue', edgecolor='black')
                if title:
                    ax.set_title(title, fontsize=14, fontweight='bold')
                ax.grid(axis='y', alpha=0.3)
                plt.xticks(rotation=45, ha='right')

            plt.tight_layout()
            b64 = self._render_to_base64(fig)
            plt.close(fig)
            return {"success": True, "type": "chart_image", "renderer": "chart_image", "image": b64, "format": "png", "title": title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _render_table(self, data: Any, title: str) -> dict:
        """Format data as table."""
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return {"success": True, "type": "table", "renderer": "table", "data": data, "title": title}
        return {"success": False, "error": "Data is not table format"}

    def _render_metrics(self, data: Any, title: str) -> dict:
        """Format data as metric cards."""
        if isinstance(data, dict):
            metrics = []
            for k, v in data.items():
                metric = {"label": k.replace("_", " ").title(), "value": v}
                # Auto-detect format
                if isinstance(v, bool):
                    metric["format"] = "text"
                    metric["value"] = "Yes" if v else "No"
                elif isinstance(v, float) and 0 <= v <= 1:
                    metric["format"] = "percent"
                elif isinstance(v, (int, float)):
                    metric["format"] = "number"
                else:
                    metric["format"] = "text"
                metrics.append(metric)
            return {"success": True, "type": "metrics", "renderer": "metrics", "metrics": metrics, "title": title}
        return {"success": False, "error": "Data is not metrics format"}

    def _render_code(self, data: Any, title: str) -> dict:
        """Format data as code block."""
        if isinstance(data, dict):
            code = data.get("code") or data.get("patch") or str(data)
            lang = data.get("language") or "text"
        else:
            code = str(data)
            lang = "text"
        return {"success": True, "type": "code", "renderer": "code", "content": code, "language": lang, "title": title}

    def _render_text(self, data: Any, title: str) -> dict:
        """Format data as text content."""
        text = str(data)
        return {"success": True, "type": "text", "renderer": "text", "content": text, "title": title}

    def _handle_multi_line_chart(self, **kwargs) -> dict:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            return {"success": False, "error": "matplotlib not installed"}

        try:
            x = self._parse_json_param(kwargs.get("x_values"))
            series = self._parse_json_param(kwargs.get("series"))
            if not isinstance(x, list) or not isinstance(series, list):
                return {"success": False, "error": "x_values and series must be JSON arrays"}

            fig, ax = plt.subplots(figsize=(10, 6))
            for s in series:
                name = s.get("name", "Series")
                values = s.get("values", [])
                if len(values) != len(x):
                    return {"success": False, "error": f"Series '{name}' length mismatch"}
                ax.plot(x, values, marker='o', label=name, linewidth=2)

            if kwargs.get("title"):
                ax.set_title(kwargs["title"], fontsize=14, fontweight='bold')
            if kwargs.get("x_label"):
                ax.set_xlabel(kwargs["x_label"])
            if kwargs.get("y_label"):
                ax.set_ylabel(kwargs["y_label"])
            ax.legend()
            ax.grid(True, alpha=0.3)
            plt.tight_layout()

            b64 = self._render_to_base64(fig)
            plt.close(fig)
            return {"success": True, "image": b64, "format": "png"}
        except Exception as e:
            return {"success": False, "error": str(e)}
