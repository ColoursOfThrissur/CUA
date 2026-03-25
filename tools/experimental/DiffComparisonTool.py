from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class DiffComparisonTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "data_operations"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        compare_text_files_capability = ToolCapability(
            name="compare_text_files",
            description="Operation: compare_text_files",
            parameters=[
                Parameter(name="file_path1", type=ParameterType.STRING, description="Path to the first text file", required=True),
                Parameter(name="file_path2", type=ParameterType.STRING, description="Path to the second text file", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.fs", "self.services.json"],
        )
        self.add_capability(compare_text_files_capability, self._handle_compare_text_files)

        compare_json_data_capability = ToolCapability(
            name="compare_json_data",
            description="Operation: compare_json_data",
            parameters=[
                Parameter(name="json_data1", type=ParameterType.DICT, description="First JSON data structure", required=True),
                Parameter(name="json_data2", type=ParameterType.DICT, description="Second JSON data structure", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.fs", "self.services.json"],
        )
        self.add_capability(compare_json_data_capability, self._handle_compare_json_data)

        compare_config_files_capability = ToolCapability(
            name="compare_config_files",
            description="Operation: compare_config_files",
            parameters=[
                Parameter(name="config_file_path1", type=ParameterType.STRING, description="Path to the first configuration file", required=True),
                Parameter(name="config_file_path2", type=ParameterType.STRING, description="Path to the second configuration file", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.fs", "self.services.json"],
        )
        self.add_capability(compare_config_files_capability, self._handle_compare_config_files)

        compare_directory_trees_capability = ToolCapability(
            name="compare_directory_trees",
            description="Operation: compare_directory_trees",
            parameters=[
                Parameter(name="dir_path1", type=ParameterType.STRING, description="Path to the first directory", required=True),
                Parameter(name="dir_path2", type=ParameterType.STRING, description="Path to the second directory", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.fs", "self.services.json"],
        )
        self.add_capability(compare_directory_trees_capability, self._handle_compare_directory_trees)

    def execute(self, operation: str, **kwargs):
        return self.execute_capability(operation, **kwargs)

    def _handle_compare_text_files(self, **kwargs):
            file_path1 = kwargs.get('file_path1')
            file_path2 = kwargs.get('file_path2')

            if not file_path1 or not file_path2:
                return {'success': False, 'error': 'Both file paths are required'}

            try:
                content1 = self.services.fs.read(file_path1)
                content2 = self.services.fs.read(file_path2)

                if content1 is None:
                    return {'success': False, 'error': f'File {file_path1} is missing'}
                if content2 is None:
                    return {'success': False, 'error': f'File {file_path2} is missing'}

                comparison_result = 'Files are identical' if content1 == content2 else 'Files differ'

                # Output validation step
                if not isinstance(comparison_result, str):
                    return {'success': False, 'error': 'Invalid result format'}

                return {'success': True, 'result': comparison_result}
            except Exception as e:
                self.services.logging.error(f"Error comparing files: {e}")
                return {'success': False, 'error': str(e)}
    def _handle_compare_json_data(self, **kwargs):
            json_data1 = kwargs.get('json_data1')
            json_data2 = kwargs.get('json_data2')

            if not json_data1 or not json_data2:
                return {'success': False, 'error': 'Both JSON data inputs are required'}

            try:
                parsed_json1 = self.services.json.parse(json_data1)
                parsed_json2 = self.services.json.parse(json_data2)

                if not parsed_json1 or not parsed_json2:
                    return {'success': False, 'error': 'One or both JSON data is invalid'}

                comparison_result = parsed_json1 == parsed_json2

                # Output validation step
                if not isinstance(comparison_result, bool):
                    return {'success': False, 'error': 'Invalid comparison result format'}

                return {'success': True, 'result': comparison_result}
            except Exception as e:
                self.services.logging.error(f"Error comparing JSON data: {e}")
                return {'success': False, 'error': str(e)}
    def _handle_compare_config_files(self, **kwargs):
            config_file_path1 = kwargs.get('config_file_path1')
            config_file_path2 = kwargs.get('config_file_path2')

            if not config_file_path1 or not config_file_path2:
                return {'success': False, 'error': 'Both configuration file paths are required'}

            try:
                content1 = self.services.fs.read(config_file_path1)
                content2 = self.services.fs.read(config_file_path2)

                if content1 is None:
                    return {'success': False, 'error': f'Configuration file {config_file_path1} is missing'}
                if content2 is None:
                    return {'success': False, 'error': f'Configuration file {config_file_path2} is missing'}

                # Compare file contents
                comparison_result = 'Configuration files are identical' if content1 == content2 else 'Configuration files differ'

                # Validate the result
                if not isinstance(comparison_result, str):
                    return {'success': False, 'error': 'Invalid comparison result format'}

                return {'success': True, 'result': comparison_result}
            except Exception as e:
                self.services.logging.error(f"Error comparing configuration files: {e}")
                return {'success': False, 'error': str(e)}
    def _handle_compare_directory_trees(self, **kwargs):
            dir_path1 = kwargs.get('dir_path1')
            dir_path2 = kwargs.get('dir_path2')

            if not dir_path1 or not dir_path2:
                return {'success': False, 'error': 'Both directory paths are required'}

            try:
                files1 = self.services.fs.list(path=dir_path1)
                files2 = self.services.fs.list(path=dir_path2)

                if not files1 or not files2:
                    return {'success': False, 'error': 'One or both directories are empty'}

                # Simple comparison of file lists
                comparison_result = set(files1) == set(files2)

                # Validate the result format
                if not isinstance(comparison_result, bool):
                    self.services.logging.error("Invalid comparison result format")
                    return {'success': False, 'error': 'Invalid comparison result format'}

                return {'success': True, 'result': 'Directory trees are identical' if comparison_result else 'Directory trees differ'}
            except Exception as e:
                self.services.logging.error(f"Error comparing directory trees: {e}")
                return {'success': False, 'error': str(e)}
