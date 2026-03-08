"""Service registry for validation - defines available service methods"""

SERVICE_METHODS = {
    'storage': [
        'save(id, data)',
        'get(id)',
        'list(limit=10)',
        'update(id, updates)',
        'delete(id)',
    ],
    'llm': [
        'generate(prompt, temperature=0.3, max_tokens=500)',
    ],
    'http': [
        'get(url)',
        'post(url, data)',
    ],
    'fs': [
        'read(path)',
        'write(path, content)',
    ],
    'json': [
        'parse(text)',
        'stringify(data)',
    ],
    'shell': [
        'execute(command)',
    ],
    'logging': [
        'info(message)',
        'error(message)',
        'warning(message)',
        'debug(message)',
    ],
    'time': [
        'now_utc()',
        'now_local()',
    ],
    'ids': [
        'generate(prefix="")',
        'uuid()',
    ],
    'browser': [
        'open_browser()',
        'navigate(url)',
        'find_element(by, value)',
        'get_page_text()',
        'take_screenshot(filename)',
        'close()',
    ],
}

def get_service_methods(service_name: str):
    """Get methods for a service"""
    return SERVICE_METHODS.get(service_name, [])

def service_exists(service_name: str) -> bool:
    """Check if service exists"""
    return service_name in SERVICE_METHODS

def method_exists(service_name: str, method_name: str) -> bool:
    """Check if service method exists"""
    if service_name not in SERVICE_METHODS:
        return False
    methods = SERVICE_METHODS[service_name]
    return any(method_name in m for m in methods)
