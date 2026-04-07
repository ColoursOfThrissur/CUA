from infrastructure.services.llm_service import LLMService


class _FakeClient:
    def _extract_json(self, response):
        return None


def test_coerce_structured_recovers_json_from_fenced_thinking_text():
    service = LLMService(_FakeClient())
    response = """
Thinking...

```json
{"active_app":"Steam","target_app_active":true}
```
"""

    parsed = service._coerce_structured(response, container="object")

    assert parsed == {"active_app": "Steam", "target_app_active": True}


def test_coerce_structured_prefers_nested_response_payload():
    service = LLMService(_FakeClient())
    response = {
        "thinking": "I should answer in JSON",
        "response": '{"items":["Apex Legends","Dota 2"],"summary":"Visible games."}',
    }

    parsed = service._coerce_structured(response, container="object")

    assert parsed == {"items": ["Apex Legends", "Dota 2"], "summary": "Visible games."}
