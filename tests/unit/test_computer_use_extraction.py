from application.planning.create_plan import CreatePlanUseCase
from tools.computer_use.screen_perception_tool import ScreenPerceptionTool


def test_analyze_screen_extraction_prompt_is_rewritten_to_extract_text():
    use_case = CreatePlanUseCase.__new__(CreatePlanUseCase)
    assert use_case._is_extraction_prompt("Extract all visible game titles from the Steam library view")
    assert use_case._is_extraction_prompt("List the visible titles on screen")
    assert not use_case._is_extraction_prompt("Describe what you see on the screen")


def test_filter_extracted_items_removes_steam_nav_noise():
    tool = ScreenPerceptionTool()
    items = [
        "STORE",
        "LIBRARY",
        "COMMUNITY",
        "Apex Legends",
        "Counter-Strike 2",
        "Friends & Chat",
    ]

    filtered = tool._filter_extracted_items(
        items,
        prompt="Extract all visible game titles from the Steam library view",
        target_app="steam",
    )

    assert "Apex Legends" in filtered
    assert "Counter-Strike 2" in filtered
    assert "STORE" not in filtered
    assert "LIBRARY" not in filtered


def test_should_not_trust_noisy_steam_ocr_from_wrong_window():
    tool = ScreenPerceptionTool()

    trusted = tool._should_trust_ocr_extraction(
        ["Forge", "Remote", "Tunnels", "Repo"],
        prompt="Extract all visible game titles from the Steam library view",
        target_app="steam",
        active_window_title="Visual Studio Code",
    )

    assert trusted is False


def test_should_trust_steam_ocr_when_titles_look_real():
    tool = ScreenPerceptionTool()

    trusted = tool._should_trust_ocr_extraction(
        ["Apex Legends", "Counter-Strike 2", "Dota 2"],
        prompt="Extract all visible game titles from the Steam library view",
        target_app="steam",
        active_window_title="Steam",
    )

    assert trusted is True


def test_should_not_trust_fragmented_steam_ocr_noise_even_in_steam_window():
    tool = ScreenPerceptionTool()

    trusted = tool._should_trust_ocr_extraction(
        ["tints", "ome", "eum", "SINCLAIR", "hte", "Raiders", "Pte"],
        prompt="Extract all visible game titles from the Steam library view",
        target_app="steam",
        active_window_title="Steam",
    )

    assert trusted is False


def test_parse_targeted_detail_request_preserves_apostrophes_in_title():
    tool = ScreenPerceptionTool()

    detail = tool._parse_targeted_detail_request(
        prompt="Find the game 'Conqueror's Blade' in the library and extract its playtime in hours.",
        target_app="steam",
    )

    assert detail is not None
    assert detail["target"] == "Conqueror's Blade"
    assert detail["field"] == "playtime_hours"


def test_parse_targeted_detail_request_supports_generic_field_hints():
    tool = ScreenPerceptionTool()

    detail = tool._parse_targeted_detail_request(
        prompt='Extract only the specific detail needed.\nNamed target item: "Invoice 1042"\nRequested field hint: current status',
        target_app="billing_app",
    )

    assert detail is not None
    assert detail["target"] == "Invoice 1042"
    assert detail["field"] == "generic_detail"
    assert detail["field_description"] == "current status"


def test_extract_labeled_playtime_accepts_hours_on_record_text():
    tool = ScreenPerceptionTool()

    detail = tool._extract_labeled_playtime_from_text_candidates(
        ["Conqueror's Blade", "21.2 hrs on record"]
    )

    assert detail is not None
    assert detail["ambiguous"] is False
    assert detail["field_value"] == "21.2"
    assert detail["field_label"] == "hrs on record"


def test_extract_labeled_generic_detail_accepts_status_pair():
    tool = ScreenPerceptionTool()

    detail = tool._extract_labeled_generic_detail_from_text_candidates(
        ["Invoice 1042", "Status: Paid", "Amount: $250.00"],
        field_description="current status",
    )

    assert detail is not None
    assert detail["ambiguous"] is False
    assert detail["field_label"] == "Status"
    assert detail["field_value"] == "Paid"


def test_normalize_targeted_playtime_rejects_since_last_played_metric():
    tool = ScreenPerceptionTool()

    detail = tool._normalize_targeted_playtime_detail(
        {
            "field_label": "hours since last played",
            "field_value": "21.2",
            "explicit_text_evidence": "21.2 hours since last played",
            "confidence": 0.91,
            "ambiguous": False,
            "field_visible": True,
            "target_found": True,
        }
    )

    assert detail["ambiguous"] is True
    assert detail["field_visible"] is False
    assert detail["field_value"] == ""
    assert "did not clearly indicate total playtime" in detail["reason"]


def test_build_targeted_detail_prompt_uses_field_policy_rules():
    tool = ScreenPerceptionTool()

    prompt = tool._build_targeted_detail_prompt(
        target_name="Invoice 1042",
        detail_request={
            "field": "generic_detail",
            "field_description": "current status",
        },
        ocr_preview=["Invoice 1042", "Status: Paid"],
    )

    assert "current status" in prompt
    assert "Reject nearby values when the label is missing" in prompt


def test_should_prefer_vision_first_for_substantive_detail_lookups():
    tool = ScreenPerceptionTool()

    assert tool._should_prefer_vision_first_extraction(
        prompt="Find the order status for this item and extract the visible status value",
        target_app="shop_app",
    ) is True
    assert tool._should_prefer_vision_first_extraction(
        prompt="Read the visible text from this dialog",
        target_app="",
    ) is True
    assert tool._should_prefer_vision_first_extraction(
        prompt="OK",
        target_app="",
    ) is False


def test_normalize_extract_text_result_accepts_array_payloads():
    tool = ScreenPerceptionTool()

    normalized = tool._normalize_extract_text_result([
        {"title": "Invoice 1042", "status": "Paid"},
        {"title": "Invoice 2048", "playtime": "12 hrs"},
    ])

    assert normalized is not None
    assert normalized["items"] == ["Invoice 1042", "Invoice 2048"]
    assert normalized["structured_rows"][1]["playtime"] == "12 hrs"


def test_extract_targeted_title_handles_named_target_hints():
    tool = ScreenPerceptionTool()

    target = tool._extract_targeted_title(
        'Extract only the specific detail needed to answer this request.\nNamed target item: "conquerors balde"\nRequested field hint: playtime in hours'
    )

    assert target == "conquerors balde"


def test_extract_targeted_title_handles_unquoted_natural_language_requests():
    tool = ScreenPerceptionTool()

    target = tool._extract_targeted_title(
        "can u open steam and find out how many hours of game i have in conquerors balde..games are lsited in library"
    )

    assert target == "conquerors balde"


def test_ground_extract_response_confirms_target_app_and_expected_view():
    tool = ScreenPerceptionTool()
    tool.services = type("Services", (), {"llm": object()})()
    tool._get_active_window_title = lambda: "Steam"
    tool._handle_infer_visual_state = lambda **kwargs: {
        "success": True,
        "visual_state": {
            "target_app_visible": True,
            "target_app_active": True,
            "current_view": "library",
            "library_visible": True,
            "visible_targets": ["Apex Legends"],
        },
    }

    grounded = tool._ground_extract_response(
        {
            "success": True,
            "items": ["Apex Legends", "Dota 2"],
            "summary": "Visible library entries include Apex Legends and Dota 2.",
        },
        prompt="Extract all visible game titles from the Steam library view",
        target_app="steam",
        screenshot_path="output/fake.png",
    )

    assert grounded["grounded"] is True
    assert grounded["grounding"]["active_window_matches"] is True
    assert grounded["grounding"]["view_matches"] is True
    assert grounded["visual_state"]["current_view"] == "library"


def test_ground_extract_response_demotes_ungrounded_answer_ready_detail():
    tool = ScreenPerceptionTool()
    tool.services = type("Services", (), {"llm": object()})()
    tool._get_active_window_title = lambda: "Visual Studio Code"
    tool._handle_infer_visual_state = lambda **kwargs: {
        "success": True,
        "visual_state": {
            "target_app_visible": False,
            "target_app_active": False,
            "current_view": "editor",
            "library_visible": False,
            "visible_targets": ["Explorer", "Repo"],
        },
    }

    grounded = tool._ground_extract_response(
        {
            "success": True,
            "target": "Conqueror's Blade",
            "requested_field": "playtime_hours",
            "field_value": "21.2",
            "answer_ready": True,
            "ambiguous": False,
            "summary": "Conqueror's Blade shows 21.2 hours.",
        },
        prompt="Find the game Conqueror's Blade in the Steam library and extract its playtime in hours",
        target_app="steam",
        screenshot_path="output/fake.png",
    )

    assert grounded["grounded"] is False
    assert grounded["answer_ready"] is False
    assert grounded["ambiguous"] is True
    assert grounded["grounding"]["blocking_reason"] in {
        "target_app_not_confirmed:steam",
        "expected_view:library",
    }
