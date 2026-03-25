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
        self._cache = {}
        super().__init__()

    def register_capabilities(self):
        """Register tool capabilities"""
        summarize_text_capability = ToolCapability(
            name='summarize_text',
            description='ONLY call this when user says "summarize this text:" followed by actual text content. NEVER use for questions about tools, suggestions, or conversations. This summarizes TEXT CONTENT ONLY.',
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
            description='ONLY use when user explicitly requests key point extraction from text. NOT for meta-questions. Extracts key points from provided text.',
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
            description='ONLY use when user explicitly provides text to analyze. NOT for meta-questions about the system. Analyzes sentiment of provided text.',
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
            description='ONLY use when user requests JSON formatting of existing summary/sentiment data. NOT for generating new analysis. Formats data as JSON.',
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

        batch_summarize_texts_capability = ToolCapability(
            name="batch_summarize_texts",
            description="Add batch processing support to ContextSummarizerTool",
            parameters=[],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(batch_summarize_texts_capability, self._handle_batch_summarize_texts)

        batch_capability = ToolCapability(
            name="batch",
            description="Add batch processing support to ContextSummarizerTool",
            parameters=[
                Parameter(name='texts', type=ParameterType.STRING, description='texts parameter', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(batch_capability, self._handle_batch)

        highlight_important_phrases_capability = ToolCapability(
            name="highlight_important_phrases",
            description="Add a capability to highlight important phrases or quotes from the text content ",
            parameters=[
                Parameter(name='input_text', type=ParameterType.STRING, description='input_text parameter', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(highlight_important_phrases_capability, self._handle_highlight_important_phrases)

        translate_text_capability = ToolCapability(
            name="translate_text",
            description="Add a capability to translate the summarized text into different languages.",
            parameters=[
                Parameter(name='input_text', type=ParameterType.STRING, description='input_text parameter', required=True),
                Parameter(name='target_language', type=ParameterType.STRING, description='target_language parameter', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(translate_text_capability, self._handle_translate_text)
        self.add_capability(generate_json_output_capability, self._handle_generate_json_output)

    def _handle_batch_summarize_texts(self, **kwargs) -> dict:
        texts = kwargs.get('texts', [])
        summaries = []

        for text in texts:
            try:
                prompt = f"Summarize the following text: {text}"
                summary = self.services.llm.generate(prompt)
                summaries.append(summary)
            except Exception as e:
                self.services.logging.error(f"Failed to summarize text: {e}")
                summaries.append(None)

        return {'summaries': summaries}

    def _handle_batch(self, **kwargs) -> dict:
        texts = kwargs.get('texts')
        if not texts or not isinstance(texts, list):
            return {'error': 'Missing or invalid parameter: texts'}
        try:
            results = []
            for text in texts:
                summary = self._handle_summarize_text(input_text=text)
                results.append({'text': text, 'summary': summary})
            return {'success': True, 'results': results}
        except Exception as e:
            self.services.logging.error(f"Batch processing failed: {e}")
            return {'success': False, 'error': str(e)}

    def _handle_highlight_important_phrases(self, **kwargs) -> dict:
        input_text = kwargs.get('input_text')
        if not input_text:
            return {'error': 'Missing required parameter: input_text'}
        try:
            prompt = f"Extract the most important phrases and quotes from this text, one per line:\n\n{input_text}"
            result = self.services.llm.generate(prompt, temperature=0.3, max_tokens=500)
            phrases = [line.strip() for line in result.splitlines() if line.strip()]
            context_snippet = input_text[:200] + ('...' if len(input_text) > 200 else '')
            highlighted = [{'phrase': p, 'context': context_snippet} for p in phrases]
            return {'success': True, 'highlighted_phrases': highlighted}
        except Exception as e:
            self.services.logging.error(f"Operation failed: {e}")
            return {'success': False, 'error': str(e)}

    def _handle_translate_text(self, **kwargs) -> dict:
        input_text = kwargs.get('input_text')
        target_language = kwargs.get('target_language')

        if not input_text or not target_language:
            return {'error': 'Missing required parameters: input_text and target_language'}

        prompt = f"Translate the following text into {target_language}: {input_text}"
        translated_text = self.services.llm.generate(prompt)

        return {'success': True, 'data': translated_text}

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
        if operation == "batch_summarize_texts":
            return self._handle_batch_summarize_texts(**kwargs)

        if operation == "batch":
            return self._handle_batch(**kwargs)

        if operation == "highlight_important_phrases":
            return self._handle_highlight_important_phrases(**kwargs)

        if operation == "translate_text":
            return self._handle_translate_text(**kwargs)

        raise ValueError(f"Unsupported operation: {operation}")

    def _handle_summarize_text(self, **kwargs):
            required_params = ['input_text']
            missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
            if missing:
                self.services.logging.error(f"Missing required parameters: {', '.join(missing)}")
                raise ValueError(f"Missing required parameters: {', '.join(missing)}")

            input_text = kwargs['input_text']
            summary_length = kwargs.get('summary_length', 50)

            if not self.services or not self.services.llm:
                self.services.logging.error("LLM service not available")
                raise RuntimeError("LLM service not available")

            cache_key = (input_text, summary_length)
            if cache_key in self._cache:
                return self._cache[cache_key]

            prompt = f"Summarize the following text in approximately {summary_length} words:\n\n{input_text}"
            try:
                summary = self.services.llm.generate(prompt, temperature=0.3, max_tokens=500)
            except Exception as e:
                self.services.logging.error(f"Failed to generate summary: {e}")
                raise RuntimeError(f"Failed to generate summary: {e}")

            self._cache[cache_key] = {
                "summary": summary,
                "original_length": len(input_text.split()),
                "summary_length": len(summary.split()),
            }
            return self._cache[cache_key]

    def _handle_extract_key_points(self, **kwargs):
            required_params = ['input_text']
            missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
            if missing:
                raise ValueError(f"Missing required parameters: {', '.join(missing)}")

            input_text = kwargs['input_text']
            num_key_points = kwargs.get('num_key_points', 5)

            cache_key = f"{input_text}_{num_key_points}"
            if cache_key in self._cache:
                return self._cache[cache_key]

            prompt = f"List the {num_key_points} most important key points from this text, one per line:\n\n{input_text}"
            result = self.services.llm.generate(prompt, temperature=0.3, max_tokens=500)
            key_points = [line.strip() for line in result.splitlines() if line.strip()][:num_key_points]

            self._cache[cache_key] = {'key_points': key_points}
            return self._cache[cache_key]

    def _handle_sentiment_analysis(self, **kwargs):
            required_params = ['input_text']
            missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
            if missing:
                raise ValueError(f"Missing required parameters: {', '.join(missing)}")

            input_text = kwargs['input_text']
            language = kwargs.get('language', 'en')

            cache_key = hash(input_text)
            if cache_key in self._cache:
                return self._cache[cache_key]

            prompt = f"Analyze the sentiment of this text. Reply with one word: positive, negative, or neutral.\n\n{input_text}"
            label = self.services.llm.generate(prompt, temperature=0.1, max_tokens=10).strip().lower()
            result = {'label': label, 'language': language}
            self._cache[cache_key] = result
            return result

    def _handle_generate_json_output(self, **kwargs):
            required_params = ['summary', 'key_points', 'sentiment']
            missing = [p for p in required_params if p not in kwargs or kwargs[p] in (None, "")]
            if missing:
                raise ValueError(f"Missing required parameters: {', '.join(missing)}")

            import json as _json
            return {'json_output': _json.dumps({'summary': kwargs['summary'], 'key_points': kwargs['key_points'], 'sentiment': kwargs['sentiment']}, indent=2)}
