from api.chat_helpers import _sanitize_llm_response_text


def test_sanitize_llm_response_text_removes_internal_drafting_scaffold():
    raw = """3.  **Drafting the Response:**
    *   *Attempt 1:* I searched the Steam library, but I was unable to confirm the playtime.
    *   *Critique 1:* Too long.
    *   *Attempt 2:* Conqueror's Blade is visible in Steam, but the playtime was not clearly readable.

Final response:
Conqueror's Blade is visible in your Steam library, but I couldn't confidently verify the playtime from the visible text."""

    cleaned = _sanitize_llm_response_text(raw)

    assert "Drafting the Response" not in cleaned
    assert "Attempt 1" not in cleaned
    assert "Critique 1" not in cleaned
    assert cleaned == "Conqueror's Blade is visible in your Steam library, but I couldn't confidently verify the playtime from the visible text."


def test_sanitize_llm_response_text_keeps_last_non_meta_paragraph_when_no_final_marker():
    raw = """Attempt 1: Draft answer.

Critique 1: too vague.

The visible Steam text suggests Conqueror's Blade is selected, but the playtime label is still not clearly grounded."""

    cleaned = _sanitize_llm_response_text(raw)

    assert cleaned == "The visible Steam text suggests Conqueror's Blade is selected, but the playtime label is still not clearly grounded."
