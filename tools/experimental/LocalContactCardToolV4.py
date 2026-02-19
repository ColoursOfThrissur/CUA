"""
LocalContactCardToolV4 - Auto-generated tool
"""
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class LocalContactCardToolV4(BaseTool):
    def __init__(self):
        self.name = "LocalContactCardToolV4"
        self.description = "Auto-generated tool"
        super().__init__()

    def register_capabilities(self):
        """Register tool capabilities"""
        create_capability = ToolCapability(
            name='create',
            description='Create Operation',
            parameters=[
            Parameter(name='contact_id', type=ParameterType.STRING, description='Parameter contact_id', required=True),
            Parameter(name='name', type=ParameterType.STRING, description='Parameter name', required=True),
            Parameter(name='email', type=ParameterType.STRING, description='Parameter email', required=True),
            Parameter(name='phone', type=ParameterType.STRING, description='Parameter phone', required=False),
            Parameter(name='tags', type=ParameterType.LIST, description='Parameter tags', required=False),
            Parameter(name='notes', type=ParameterType.STRING, description='Parameter notes', required=False)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(create_capability, self._handle_create)

        get_capability = ToolCapability(
            name='get',
            description='Get Operation',
            parameters=[
            Parameter(name='contact_id', type=ParameterType.STRING, description='Parameter contact_id', required=True)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(get_capability, self._handle_get)

        list_capability = ToolCapability(
            name='list',
            description='List Operation',
            parameters=[
            Parameter(name='limit', type=ParameterType.INTEGER, description='Parameter limit', required=False, default=10),
            Parameter(name='tag_filter', type=ParameterType.STRING, description='Parameter tag_filter', required=False)
        ],
            returns="Operation result payload",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(list_capability, self._handle_list)

    def execute(self, operation: str, parameters: dict) -> ToolResult:
        """Execute tool operation"""
        parameters = parameters or {}
        if not isinstance(parameters, dict):
            return ToolResult(
                tool_name=self.name,
                capability_name=operation,
                status=ResultStatus.FAILURE,
                data=None,
                error_message="parameters must be a dict"
            )
        if operation == 'create':
            return self._handle_create(**parameters)
        elif operation == 'get':
            return self._handle_get(**parameters)
        elif operation == 'list':
            return self._handle_list(**parameters)
        return ToolResult(
            tool_name=self.name,
            capability_name=operation,
            status=ResultStatus.FAILURE,
            data=None,
            error_message=f"Unsupported operation: {operation}"
        )

    def _handle_create(self, **kwargs) -> ToolResult:
            # Validate required parameters
            required_params = {
                'name': ParameterType.STRING,
                'phone_number': ParameterType.STRING,
                'email': ParameterType.STRING
            }

            for param_name, param_type in required_params.items():
                if param_name not in kwargs or not isinstance(kwargs[param_name], param_type):
                    return ToolResult(
                        tool_name=self.name,
                        capability_name='create',
                        status=ResultStatus.FAILURE,
                        data=None,
                        error_message=f"Missing or invalid parameter: {param_name}"
                    )

            # Extract parameters
            name = kwargs['name']
            phone_number = kwargs['phone_number']
            email = kwargs['email']

            # Create deterministic local path
            contact_path = Path('data/contacts')
            contact_file_path = contact_path / f"{name.replace(' ', '_')}.txt"

            # Ensure parent directories exist
            contact_path.mkdir(parents=True, exist_ok=True)

            # Write contact information to file
            try:
                with open(contact_file_path, 'w') as file:
                    file.write(f"Name: {name}\n")
                    file.write(f"Phone Number: {phone_number}\n")
                    file.write(f"Email: {email}\n")
            except Exception as e:
                return ToolResult(
                    tool_name=self.name,
                    capability_name='create',
                    status=ResultStatus.FAILURE,
                    data=None,
                    error_message=f"Failed to write contact file: {str(e)}"
                )

            # Return success result
            return ToolResult(
                tool_name=self.name,
                capability_name='create',
                status=ResultStatus.SUCCESS,
                data={'file_path': str(contact_file_path)},
                error_message=None
            )

    def _handle_get(self, **kwargs) -> ToolResult:
            contact_id = kwargs.get("contact_id")

            if not contact_id:
                return ToolResult(
                    tool_name=self.name,
                    capability_name='get',
                    status=ResultStatus.FAILURE,
                    data=None,
                    error_message="Missing required parameter 'contact_id'"
                )

            # Simulate retrieving a contact from local storage
            try:
                # Assuming core.storage_broker.get_storage_broker(self.name) is used for reads/writes
                storage = core.storage_broker.get_storage_broker(self.name)
                contact_data = storage.read(f"data/contacts/{contact_id}.json")

                if not contact_data:
                    return ToolResult(
                        tool_name=self.name,
                        capability_name='get',
                        status=ResultStatus.FAILURE,
                        data=None,
                        error_message="Contact not found"
                    )

                return ToolResult(
                    tool_name=self.name,
                    capability_name='get',
                    status=ResultStatus.SUCCESS,
                    data=contact_data,
                    error_message=None
                )

            except Exception as e:
                return ToolResult(
                    tool_name=self.name,
                    capability_name='get',
                    status=ResultStatus.FAILURE,
                    data=None,
                    error_message=str(e)
                )

    def _handle_list(self, **kwargs) -> ToolResult:
            limit = kwargs.get('limit', 10)
            tag_filter = kwargs.get('tag_filter')

            if not isinstance(limit, int) or limit < 1 or limit > 100:
                return ToolResult(
                    tool_name=self.name,
                    capability_name='list',
                    status=ResultStatus.FAILURE,
                    data=None,
                    error_message="Invalid limit value"
                )

            # Simulate fetching contacts from a local storage
            contacts = [
                {"name": "Alice", "tags": ["friend", "work"]},
                {"name": "Bob", "tags": ["family"]},
                {"name": "Charlie", "tags": ["colleague", "friend"]}
            ]

            if tag_filter:
                filtered_contacts = [contact for contact in contacts if tag_filter in contact.get('tags', [])]
            else:
                filtered_contacts = contacts

            limited_contacts = filtered_contacts[:limit]

            return ToolResult(
                tool_name=self.name,
                capability_name='list',
                status=ResultStatus.SUCCESS,
                data=limited_contacts,
                error_message=None
            )
