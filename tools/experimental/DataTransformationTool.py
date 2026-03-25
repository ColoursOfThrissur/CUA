from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel

class DataTransformationTool(BaseTool):
    def __init__(self, orchestrator=None):
        self.description = "data_operations"
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        convert_format_capability = ToolCapability(
            name="convert_format",
            description="Operation: convert_format",
            parameters=[
                Parameter(name="input_data", type=ParameterType.STRING, description="The input data to be converted.", required=True),
                Parameter(name="from_format", type=ParameterType.STRING, description="The current format of the input data (e.g., JSON, CSV).", required=True),
                Parameter(name="to_format", type=ParameterType.STRING, description="The desired output format for the data (e.g., JSON, CSV).", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.json", "self.services.storage"],
        )
        self.add_capability(convert_format_capability, self._handle_convert_format)

        filter_records_capability = ToolCapability(
            name="filter_records",
            description="Operation: filter_records",
            parameters=[
                Parameter(name="data", type=ParameterType.DICT, description="The input data to filter.", required=True),
                Parameter(name="criteria", type=ParameterType.DICT, description="Filter criteria as a dictionary (e.g., {'key': 'value'}).", required=True),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.json", "self.services.storage"],
        )
        self.add_capability(filter_records_capability, self._handle_filter_records)

        sort_list_capability = ToolCapability(
            name="sort_list",
            description="Operation: sort_list",
            parameters=[
                Parameter(name="data", type=ParameterType.LIST, description="The list to sort.", required=True),
                Parameter(name="key", type=ParameterType.STRING, description="The key to sort by.", required=True),
                Parameter(name="reverse", type=ParameterType.BOOLEAN, description="Whether to reverse the order (default is False).", required=False),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.json", "self.services.storage"],
        )
        self.add_capability(sort_list_capability, self._handle_sort_list)

        aggregate_data_capability = ToolCapability(
            name="aggregate_data",
            description="Operation: aggregate_data",
            parameters=[
                Parameter(name="data", type=ParameterType.LIST, description="The list of records to aggregate.", required=True),
                Parameter(name="function", type=ParameterType.STRING, description="Aggregation function (e.g., sum, average, count).", required=True),
                Parameter(name="key", type=ParameterType.STRING, description="The key to apply the aggregation function on.", required=False),
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=["self.services.json", "self.services.storage"],
        )

        merge_datasets_capability = ToolCapability(
            name="merge_datasets",
            description="Merge multiple datasets based on specified keys.",
            parameters=[
                Parameter(name='datasets', type=ParameterType.LIST, description='List of dataset IDs to merge', required=True),
                Parameter(name='keys', type=ParameterType.LIST, description='List of keys to merge on', required=True)
            ],
            returns="dict",
            safety_level=SafetyLevel.LOW,
            examples=[],
            dependencies=[]
        )
        self.add_capability(merge_datasets_capability, self._handle_merge_datasets)
        self.add_capability(aggregate_data_capability, self._handle_aggregate_data)

    def _handle_merge_datasets(self, **kwargs) -> dict:
        # Extract parameters
        datasets = kwargs.get('datasets')
        keys = kwargs.get('keys', [])

        # Validate required parameters
        if not datasets or not keys:
            return {'error': 'Missing required parameter: datasets or keys'}

        try:
            merged_data = []
            for dataset_id in datasets:
                data = self.services.storage.get(dataset_id)
                if data:
                    merged_data.extend(data)

            # Merge logic based on specified keys
            from collections import defaultdict
            merged_dict = defaultdict(dict)
            for item in merged_data:
                key_value = tuple(item[key] for key in keys)
                merged_dict[key_value].update(item)

            merged_result = list(merged_dict.values())
            return {'success': True, 'data': merged_result, 'count': len(merged_result)}
        except Exception as e:
            self.services.logging.error(f"Operation failed: {e}")
            return {'success': False, 'error': str(e)}

    def execute(self, operation: str, **kwargs):
        return self.execute_capability(operation, **kwargs)

    def _handle_convert_format(self, **kwargs):
            input_data = kwargs.get('input_data')
            from_format = kwargs.get('from_format')
            to_format = kwargs.get('to_format')

            if not all([input_data, from_format, to_format]):
                return {'success': False, 'error': 'Missing required parameters'}

            try:
                # Convert data based on formats
                if from_format == 'json' and to_format == 'dict':
                    converted_data = self.services.json.parse(input_data)
                elif from_format == 'dict' and to_format == 'json':
                    converted_data = self.services.json.stringify(input_data)
                else:
                    return {'success': False, 'error': 'Unsupported format conversion'}

                # Validate the converted data
                if not self.services.json.query(converted_data, '$'):
                    return {'success': False, 'error': 'Conversion failed: Data does not match expected format.'}

                return {'success': True, 'data': converted_data}
            except Exception as e:
                return {'success': False, 'error': str(e)}
    def _handle_filter_records(self, **kwargs):
        data = kwargs.get('data')
        criteria = kwargs.get('criteria')

        if not all([data, criteria]):
            return {'success': False, 'error': 'Missing required parameters'}

        # Placeholder logic for filtering records
        try:
            filtered_data = [record for record in data if all(record.get(key) == value for key, value in criteria.items())]
            return {'success': True, 'data': filtered_data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    def _handle_sort_list(self, **kwargs):
        data = kwargs.get('data')
        key = kwargs.get('key')
        reverse = kwargs.get('reverse', False)

        if not all([data, key]):
            return {'success': False, 'error': 'Missing required parameters'}

        # Placeholder logic for sorting list
        try:
            sorted_data = sorted(data, key=lambda x: x.get(key), reverse=reverse)
            return {'success': True, 'data': sorted_data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    def _handle_aggregate_data(self, **kwargs):
        data = kwargs.get('data')
        function = kwargs.get('function')
        key = kwargs.get('key', None)

        if not all([data, function]):
            return {'success': False, 'error': 'Missing required parameters'}

        # Placeholder logic for aggregating data
        try:
            if function == 'sum' and key is not None:
                aggregated_value = sum(record.get(key, 0) for record in data)
                return {'success': True, 'data': {key: aggregated_value}}
            elif function == 'count':
                count = len(data)
                return {'success': True, 'data': {'count': count}}
            else:
                return {'success': False, 'error': 'Unsupported aggregation function'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
