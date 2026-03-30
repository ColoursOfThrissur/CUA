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
