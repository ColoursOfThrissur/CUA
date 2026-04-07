from tools.computer_use.detail_field_policy import (
    GENERIC_DETAIL_POLICY,
    PLAYTIME_HOURS_POLICY,
    get_detail_field_policy,
)


def test_get_detail_field_policy_returns_registered_playtime_policy():
    policy = get_detail_field_policy("playtime_hours")

    assert policy is PLAYTIME_HOURS_POLICY


def test_get_detail_field_policy_falls_back_to_generic_policy():
    policy = get_detail_field_policy("status_value")

    assert policy is GENERIC_DETAIL_POLICY


def test_playtime_policy_prompt_rules_capture_total_playtime_guardrails():
    rules = PLAYTIME_HOURS_POLICY.prompt_extra_rules({"field_description": "playtime in hours"})

    assert "hrs on record" in rules
    assert "past 2 weeks" in rules


def test_generic_policy_prompt_rules_echo_requested_field_description():
    rules = GENERIC_DETAIL_POLICY.prompt_extra_rules({"field_description": "current status"})

    assert "current status" in rules
    assert "Reject nearby values" in rules


def test_generic_policy_rejects_candidate_when_label_does_not_match_requested_field():
    normalized = GENERIC_DETAIL_POLICY.normalize(
        {
            "field_label": "Amount",
            "field_value": "$250.00",
            "explicit_text_evidence": "Amount: $250.00",
            "confidence": 0.9,
            "ambiguous": False,
            "field_visible": True,
            "target_found": True,
        },
        {"field_description": "current status"},
    )

    assert normalized["ambiguous"] is True
    assert normalized["field_value"] == ""
