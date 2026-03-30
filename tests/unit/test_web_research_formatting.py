from api.chat.response_formatter import build_wra_components
from application.use_cases.chat.web_research_agent import _sanitize_answer


def test_sanitize_answer_removes_inline_references_block():
    text = "Pisces looks steady today.[1]\n\n## References\n[1] https://example.com/pisces"
    assert _sanitize_answer(text) == "Pisces looks steady today.[1]"


def test_build_wra_components_renders_structured_sources_once():
    components = build_wra_components(
        "Pisces looks steady today.[1]",
        [
            {"sources": ["https://example.com/pisces"]},
            {"key_facts": ["Travel may be delayed", "Strength is the card of the day"]},
        ],
    )

    source_components = [c for c in components if c.get("title") == "Sources"]
    assert len(source_components) == 1
    assert source_components[0]["data"][0]["url"] == "https://example.com/pisces"

    key_fact_components = [c for c in components if c.get("title") == "Key Facts"]
    assert len(key_fact_components) == 1
