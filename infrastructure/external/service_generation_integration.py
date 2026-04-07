"""
Service Generation Integration - Auto-generate missing services during validation
"""
from infrastructure.external.service_generator import ServiceGenerator
from application.managers.pending_services_manager import PendingServicesManager
from infrastructure.validation.enhanced_code_validator import EnhancedCodeValidator

class ServiceGenerationIntegration:
    """Integrates service generation with code validation"""
    
    def __init__(self):
        self.generator = ServiceGenerator()
        self.pending_manager = PendingServicesManager()
        self.validator = EnhancedCodeValidator()
    
    def validate_and_generate_services(self, code: str, class_name: str = None, 
                                      context: str = "", requested_by: str = "evolution") -> dict:
        """Validate code and auto-generate missing services
        
        Returns:
            {
                'valid': bool,
                'error': str,
                'missing_services': list,
                'generated_services': list,
                'pending_approval': bool
            }
        """
        # Run validation
        validation = self.validator.validate(code, class_name)
        is_valid = validation.get('valid', False)
        error = '; '.join(validation.get('errors', []))
        
        # Get missing services
        missing_services = self.validator.get_missing_services()
        
        if not missing_services:
            return {
                'valid': is_valid,
                'error': error,
                'missing_services': [],
                'generated_services': [],
                'pending_approval': False
            }
        
        # Generate missing services
        generated = []
        for service_info in missing_services:
            service_name = service_info['service_name']
            method_name = service_info.get('method_name')
            service_type = service_info['type']
            
            # Check if already pending
            if self.pending_manager.has_pending_service(service_name, method_name):
                continue
            
            # Generate service
            if service_type == 'method':
                result = self.generator.generate_service_method(
                    service_name, method_name, context
                )
            else:
                # Generate full service with common methods
                methods = [method_name] if method_name else ['execute', 'get', 'set']
                result = self.generator.generate_full_service(
                    service_name, methods, context
                )
            
            if result['success']:
                # Add to pending queue
                if service_type == 'method':
                    service_id = self.pending_manager.add_pending_service(
                        service_name, method_name, result['code'], 
                        context, requested_by
                    )
                else:
                    service_id = self.pending_manager.add_pending_full_service(
                        service_name, result['code'], methods,
                        context, requested_by
                    )
                
                generated.append({
                    'service_id': service_id,
                    'service_name': service_name,
                    'method_name': method_name,
                    'type': service_type
                })
        
        return {
            'valid': False,  # Not valid until services approved
            'error': f"Missing services generated, awaiting approval: {', '.join(s['service_name'] for s in generated)}",
            'missing_services': missing_services,
            'generated_services': generated,
            'pending_approval': True
        }
