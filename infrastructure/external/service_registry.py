"""Service registry for validation - defines available service methods"""

SERVICE_METHODS = {
    'storage': [
        'save(id, data)',
        'get(id)',
        'list(limit=10)',
        'find(filter_fn=None, limit=100)',
        'count()',
        'update(id, updates)',
        'delete(id)',
        'exists(id)',
    ],
    'llm': [
        'generate(prompt, temperature=0.3, max_tokens=500)',
    ],
    'http': [
        'get(url)',
        'post(url, data)',
        'put(url, data)',
        'delete(url)',
        'request(method, url, data=None, headers=None)',
    ],
    'fs': [
        'read(path)',
        'write(path, content)',
        'list(path)',
    ],
    'json': [
        'parse(text)',
        'stringify(data)',
        'query(data, path)',
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
        'now_utc_iso()',
        'now_local_iso()',
    ],
    'ids': [
        'generate(prefix="")',
        'uuid()',
    ],
    'browser': [
        'open_browser()',
        'navigate(url)',
        'find_element(by, value)',
        'find_elements(by, value)',
        'get_page_text()',
        'get_page_source()',
        'get_page_title()',
        'get_current_url()',
        'take_screenshot(filename)',
        'click(by, value)',
        'type_text(by, value, text)',
        'wait_for_element(by, value, timeout=10)',
        'wait_for_page_load(timeout=15)',
        'scroll(direction, amount=500)',
        'execute_js(script)',
        'close()',
        'is_available()',
    ],
    'credentials': [
        'get(key)',
        'set(key, value, description="", allowed_tools=None)',
        'exists(key)',
        'delete(key)',
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
