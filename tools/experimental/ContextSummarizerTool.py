"""
ContextSummarizerTool - Auto-generated tool
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class ContextSummarizerTool(BaseTool):
    """Thin tool using orchestrator services."""
    
    def __init__(self, orchestrator=None):
        self.description = "Auto-generated tool"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        """Register tool capabilities"""
        summarize_text_capability = ToolCapability(
            name='summarize_text',
            description='Summarize_Text Operation',
            parameters=[
            Parameter(name='input_text', type=ParameterType.STRING, description='The long text input to be summarized.', required=True),
            Parameter(name='summary_length', type=ParameterType.INTEGER, description='Desired length of the summary in words. Default is 50.', required=False, default=50)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(summarize_text_capability, self._handle_summarize_text)

        extract_key_points_capability = ToolCapability(
            name='extract_key_points',
            description='Extract_Key_Points Operation',
            parameters=[
            Parameter(name='input_text', type=ParameterType.STRING, description='The long text input from which key points are to be extracted.', required=True),
            Parameter(name='num_key_points', type=ParameterType.INTEGER, description='Number of key points to extract. Default is 5.', required=False, default=5)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(extract_key_points_capability, self._handle_extract_key_points)

        sentiment_analysis_capability = ToolCapability(
            name='sentiment_analysis',
            description='Sentiment_Analysis Operation',
            parameters=[
            Parameter(name='input_text', type=ParameterType.STRING, description='The text input for sentiment analysis.', required=True),
            Parameter(name='language', type=ParameterType.STRING, description="Language of the input text. Default is 'en' (English).", required=False, default='en')
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(sentiment_analysis_capability, self._handle_sentiment_analysis)

        generate_json_output_capability = ToolCapability(
            name='generate_json_output',
            description='Generate_Json_Output Operation',
            parameters=[
            Parameter(name='summary', type=ParameterType.STRING, description='The summary of the input text.', required=True),
            Parameter(name='key_points', type=ParameterType.STRING, description='Array of key points extracted from the input text.', required=True),
            Parameter(name='sentiment', type=ParameterType.DICT, description='Sentiment analysis result as an object.', required=True)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(generate_json_output_capability, self._handle_generate_json_output)

    def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute tool operation"""
        parameters = kwargs
        if operation == 'summarize_text':
            return self._handle_summarize_text(**parameters)
        elif operation == 'extract_key_points':
            return self._handle_extract_key_points(**parameters)
        elif operation == 'sentiment_analysis':
            return self._handle_sentiment_analysis(**parameters)
        elif operation == 'generate_json_output':
            return self._handle_generate_json_output(**parameters)
        raise ValueError(f"Unsupported operation: {operation}")

    def _handle_summarize_text(self, **kwargs):
        required_params = ['input_text']
        missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        input_text = kwargs['input_text']
        summary_length = kwargs.get('summary_length', 50)
        tone_style = kwargs.get('tone_style', 'neutral')

        if not self.services or not self.services.llm:
            raise RuntimeError("LLM service not available")

        cache_key = (input_text, summary_length, tone_style)
        if hasattr(self, '_cache') and cache_key in self._cache:
            return self._cache[cache_key]

        prompt = f"Summarize the following text in approximately {summary_length} words with a {tone_style} style:\n\n{input_text}"
        try:
            summary = self.services.llm.generate(prompt, temperature=0.3, max_tokens=500)
        except Exception as e:
            raise RuntimeError(f"Failed to generate summary: {e}")

        if not hasattr(self, '_cache'):
            self._cache = {}
        self._cache[cache_key] = {"summary": summary, "original_length": len(input_text.split()), "summary_length": len(summary.split())}

        return self._cache[cache_key]

    def _handle_extract_key_points(self, **kwargs):
        required_params = ['input_text']
        missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        input_text = kwargs['input_text']
        tone_style = kwargs.get('tone_style', 'bullet')  # Default to bullet style
        cache_key = f"{input_text}_{tone_style}"

        if cache_key in self.cache:
            return self.cache[cache_key]

        language = self.detect_language(input_text)
        prompt = f"Summarize the following text in {tone_style} style: {input_text}"
        try:
            key_points = self.services.llm.generate(prompt, temperature=0.7, max_tokens=150)
        except Exception as e:
            self.services.logging.error(f"Error generating summary: {e}")
            raise

        self.cache[cache_key] = key_points
        return {'key_points': key_points}

    def _handle_sentiment_analysis(self, **kwargs):
        required_params = ['input_text']
        missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")

        input_text = kwargs['input_text']
        cache_key = hash(input_text)
        if cache_key in self.cache:
            return self.cache[cache_key]

        detected_language = self.detect_language(input_text)
        prompt = f"Analyze the sentiment of the following text: {input_text}"
        try:
            sentiment_result = self.services.llm.generate(prompt, temperature=0.5, max_tokens=100)
            self.cache[cache_key] = sentiment_result
            return {'sentiment': sentiment_result}
        except Exception as e:
            self.services.logging.error(f"Error during sentiment analysis: {e}")
            raise RuntimeError("Failed to analyze sentiment") from e

    def _handle_generate_json_output(self, **kwargs):
            required_params = ['summary', 'key_points', 'sentiment']
            missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
            if missing:
                raise ValueError(f"Missing required parameters: {', '.join(missing)}")

            tone_style = kwargs.get('tone_style', 'bullet')
            input_text = f"{kwargs['summary']} {kwargs['key_points']}"

            # Language detection
            detected_language = self.services.detect_language(input_text)

            # Caching logic
            cache_key = (input_text, tone_style, detected_language)
            if cache_key in self.cache:
                return self.cache[cache_key]

            # Generate JSON output using the specified style and language
            prompt = f"Summarize the following text with a {tone_style} tone in {detected_language}: {input_text}"
            json_output = self.services.llm.generate(prompt=prompt, temperature=0.7, max_tokens=150)
            json_output = self.services.json.parse(json_output)

            # Cache the result
            self.cache[cache_key] = json_output

            return json_output
