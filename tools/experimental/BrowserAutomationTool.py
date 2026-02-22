from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class BrowserAutomationTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "web_automation"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()
    
    def register_capabilities(self):
        open_and_navigate_capability = ToolCapability(
            name="open_and_navigate",
            description="Open And Navigate operation",
            parameters=[
                Parameter(name='url', type=ParameterType.STRING, description='The URL to navigate to', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(open_and_navigate_capability, self._handle_open_and_navigate)

        take_screenshot_capability = ToolCapability(
            name="take_screenshot",
            description="Take Screenshot operation",
            parameters=[
                Parameter(name='filename', type=ParameterType.STRING, description='Filename to save screenshot', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(take_screenshot_capability, self._handle_take_screenshot)

        find_element_capability = ToolCapability(
            name="find_element",
            description="Find Element operation",
            parameters=[
                Parameter(name='selector', type=ParameterType.STRING, description='CSS selector to locate element', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(find_element_capability, self._handle_find_element)

        get_page_content_capability = ToolCapability(
            name="get_page_content",
            description="Get Page Content operation",
            parameters=[
                
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(get_page_content_capability, self._handle_get_page_content)
    
    def execute(self, operation: str, **kwargs):
        if operation == "open_and_navigate":
            return self._handle_open_and_navigate(**kwargs)
        
        if operation == "take_screenshot":
            return self._handle_take_screenshot(**kwargs)
        
        if operation == "find_element":
            return self._handle_find_element(**kwargs)
        
        if operation == "get_page_content":
            return self._handle_get_page_content(**kwargs)
        
        raise ValueError(f"Unsupported operation: {operation}")
    
    def _handle_open_and_navigate(self, **kwargs):
            url = kwargs.get('url')
            if not url:
                raise ValueError("Missing required parameter: url")

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.services.browser.open_browser()
                    self.services.browser.navigate(url)
                    return {'success': True, 'text': self.services.browser.get_page_text()}
                except Exception as e:
                    self.services.logging.error(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt < max_retries - 1:
                        self.services.logging.info("Retrying...")
                    else:
                        return {'success': False, 'error': str(e)}
    
    def _handle_take_screenshot(self, **kwargs):
            filename = kwargs.get('filename')
            if not filename:
                raise ValueError("Missing required parameter: filename")

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.services.browser.take_screenshot(filename)
                    return {'success': True}
                except Exception as e:
                    self.services.logging.error(f"Attempt {attempt + 1} failed to take screenshot: {str(e)}")
                    if attempt < max_retries - 1:
                        self.services.time.sleep(2)  # Wait for 2 seconds before retrying
                    else:
                        return {'success': False, 'error': str(e)}
    
    def _handle_find_element(self, **kwargs):
            selector = kwargs.get('selector')
            if not selector:
                raise ValueError("Missing required parameter: selector")

            retries = 3
            for attempt in range(retries):
                try:
                    element = self.services.browser.find_element(by='css selector', value=selector)
                    return {'success': True, 'element': element}
                except Exception as e:
                    if attempt < retries - 1:
                        self.services.logging.warning(f"Attempt {attempt + 1} failed: {str(e)} - Retrying...")
                    else:
                        self.services.logging.error(f"All attempts failed: {str(e)}")
                        return {'success': False, 'error': str(e)}
    
    def _handle_get_page_content(self, **kwargs):
            max_retries = 3
            session_id = self.services.ids.uuid()
            for attempt in range(max_retries):
                try:
                    self.services.browser.open_browser()
                    self.services.browser.navigate('http://example.com')  # Replace with actual URL if needed
                    page_text = self.services.browser.get_page_text()
                    self.services.storage.save(session_id, {'content': page_text})
                    self.services.browser.close()
                    return {'success': True, 'content': page_text}
                except Exception as e:
                    self.services.logging.error(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return {'success': False, 'error': str(e)}
