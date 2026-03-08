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
            parameters=[],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )

        interact_with_form_capability = ToolCapability(
            name="interact_with_form",
            description="Add support for interacting with forms (filling fields, submitting)",
            parameters=[
                Parameter(name='url', type=ParameterType.STRING, description='url parameter', required=True),
                Parameter(name='fields', type=ParameterType.STRING, description='fields parameter', required=False),
                Parameter(name='submit_button_selector', type=ParameterType.STRING, description='submit_button_selector parameter', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(interact_with_form_capability, self._handle_interact_with_form)

        support_capability = ToolCapability(
            name="support",
            description="Add support for interacting with forms (filling fields, submitting)",
            parameters=[
                Parameter(name='form_url', type=ParameterType.STRING, description='form_url parameter', required=True),
                Parameter(name='fields', type=ParameterType.STRING, description='fields parameter', required=False),
                Parameter(name='submit_button_selector', type=ParameterType.STRING, description='submit_button_selector parameter', required=True)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(support_capability, self._handle_support)

        integrate_capability = ToolCapability(
            name="integrate",
            description="Integrate support for headless browser mode to run automation tasks without disp",
            parameters=[
                Parameter(name='run_headless', type=ParameterType.STRING, description='run_headless parameter', required=False)
            ],
            returns="Operation result",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(integrate_capability, self._handle_integrate)
        self.add_capability(get_page_content_capability, self._handle_get_page_content)
    
    def _handle_interact_with_form(self, **kwargs) -> dict:
            # Extract parameters
            url = kwargs.get('url')
            fields_json = kwargs.get('fields', '{}')  # Default to empty JSON string if not provided
            submit_button_selector = kwargs.get('submit_button_selector')

            # Validate required parameters
            if not url or not submit_button_selector:
                return {'error': 'Missing required parameter: url or submit_button_selector'}

            try:
                fields = self.services.json.parse(fields_json)
            except Exception as e:
                return {'success': False, 'error': f'Invalid JSON for fields: {e}'}

            # Use services with error handling
            try:
                self.services.browser.navigate(url)
                for field_name, value in fields.items():
                    element = self.services.browser.find_element('name', field_name)
                    if element:
                        element.send_keys(value)
                    else:
                        return {'success': False, 'error': f'Field {field_name} not found'}

                submit_button = self.services.browser.find_element('css', submit_button_selector)
                if submit_button:
                    submit_button.click()
                else:
                    return {'success': False, 'error': 'Submit button not found'}

                return {'success': True}
            except Exception as e:
                self.services.logging.error(f"Operation failed: {e}")
                return {'success': False, 'error': str(e)}

    def _handle_support(self, **kwargs) -> dict:
        # Extract parameters
        form_url = kwargs.get('form_url')
        fields_json = kwargs.get('fields', '{}')
        submit_button_selector = kwargs.get('submit_button_selector')

        # Validate required parameters
        if not form_url or not submit_button_selector:
            return {'error': 'Missing required parameter: form_url or submit_button_selector'}

        try:
            fields = self.services.json.parse(fields_json)
        except Exception as e:
            return {'success': False, 'error': f'Invalid JSON for fields: {e}'}

        # Use services with error handling
        try:
            self.services.browser.navigate(form_url)
            for field_name, value in fields.items():
                element = self.services.browser.find_element('name', field_name)
                if element:
                    element.send_keys(value)

            submit_button = self.services.browser.find_element('css', submit_button_selector)
            if submit_button:
                submit_button.click()

            return {'success': True, 'message': 'Form submitted successfully'}
        except Exception as e:
            self.services.logging.error(f"Operation failed: {e}")
            return {'success': False, 'error': str(e)}

    def _handle_integrate(self, **kwargs) -> dict:
        # Extract parameters
        run_headless = kwargs.get('run_headless', False)

        # Use services with error handling
        try:
            self.services.browser.open_browser()
            return {'success': True, 'message': 'Browser opened'}
        except Exception as e:
            self.services.logging.error(f"Operation failed: {e}")
            return {'success': False, 'error': str(e)}

    def execute(self, operation: str, **kwargs):
        if operation == "open_and_navigate":
            return self._handle_open_and_navigate(**kwargs)
        
        if operation == "take_screenshot":
            return self._handle_take_screenshot(**kwargs)
        
        if operation == "find_element":
            return self._handle_find_element(**kwargs)
        
        if operation == "get_page_content":
            return self._handle_get_page_content(**kwargs)

        if operation == "interact_with_form":
            return self._handle_interact_with_form(**kwargs)

        if operation == "support":
            return self._handle_support(**kwargs)

        if operation == "integrate":
            return self._handle_integrate(**kwargs)

        raise ValueError(f"Unsupported operation: {operation}")
    
    def _handle_open_and_navigate(self, **kwargs):
            url = kwargs.get('url')
            if not url:
                raise ValueError("Missing required parameter: url")

            try:
                self.services.browser.open_browser()
                self.services.browser.navigate(url)
                page_text = self.services.browser.get_page_text()
                return {'success': True, 'text': page_text}
            except Exception as e:
                self.services.logging.error(f"Error navigating to {url}: {str(e)}")
                return {'success': False, 'error': str(e)}
    
    def _handle_take_screenshot(self, **kwargs):
            filename = kwargs.get('filename')
            if not filename:
                raise ValueError("Missing required parameter: filename")

            try:
                self.services.browser.take_screenshot(filename)
                return {'success': True, 'filename': filename}
            except Exception as e:
                self.services.logging.error(f"Failed to take screenshot: {str(e)}")
                return {'success': False, 'error': str(e)}
    
    def _handle_find_element(self, **kwargs):
            selector = kwargs.get('selector')
            if not selector:
                raise ValueError("Missing required parameter: selector")

            try:
                element = self.services.browser.find_element(by='css', value=selector)
                return {'success': True, 'text': element.text if element else ''}
            except Exception as e:
                self.services.logging.error(f"Error finding element: {str(e)}")
                return {'success': False, 'error': str(e)}
    
    def _handle_get_page_content(self, **kwargs):
            try:
                page_text = self.services.browser.get_page_text()
                return {'success': True, 'content': page_text}
            except Exception as e:
                self.services.logging.error(f"Failed to get page content: {str(e)}")
                return {'success': False, 'error': str(e)}
