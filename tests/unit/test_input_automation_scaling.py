from tools.computer_use.input_automation_tool import InputAutomationTool
from types import SimpleNamespace


def test_scale_coordinates_uses_plain_image_to_desktop_mapping():
    tool = InputAutomationTool()

    scaled = tool._scale_coordinates(
        275,
        181,
        image_width=1024,
        image_height=576,
        original_width=1920,
        original_height=1080,
        use_empirical_correction=False,
    )

    assert scaled == (516, 339)


def test_scale_coordinates_handles_small_raw_points_without_empirical_shift():
    tool = InputAutomationTool()

    scaled = tool._scale_coordinates(
        98,
        39,
        image_width=1024,
        image_height=576,
        original_width=1920,
        original_height=1080,
        use_empirical_correction=False,
    )

    assert scaled == (184, 73)


def test_scale_coordinates_applies_raw_point_y_correction_only_on_fallback_path():
    tool = InputAutomationTool()

    scaled = tool._scale_coordinates(
        288,
        191,
        image_width=1024,
        image_height=576,
        original_width=1920,
        original_height=1080,
        use_empirical_correction=True,
    )

    assert scaled == (540, 207)


def test_scale_coordinates_with_library_bbox_point_matches_expected_desktop_nav_height():
    tool = InputAutomationTool()

    scaled = tool._scale_coordinates(
        290,
        192,
        image_width=1024,
        image_height=576,
        original_width=1920,
        original_height=1080,
        use_empirical_correction=True,
    )

    assert scaled == (544, 208)


def test_scale_coordinates_for_ocr_point_uses_plain_desktop_mapping_without_y_correction():
    tool = InputAutomationTool()

    scaled = tool._scale_coordinates(
        290,
        192,
        image_width=1024,
        image_height=576,
        original_width=1920,
        original_height=1080,
        use_empirical_correction=False,
    )

    assert scaled == (544, 360)


def test_filter_match_to_active_app_window_accepts_point_inside_active_window():
    tool = InputAutomationTool()
    tool.services = SimpleNamespace(
        call_tool=lambda tool_name, operation, **kwargs: {
            "success": True,
            "title": "Steam",
            "position": {"x": 400, "y": 100},
            "size": {"width": 900, "height": 800},
        }
        if tool_name == "SystemControlTool" and operation == "get_active_window"
        else {}
    )

    matched = tool._filter_match_to_active_app_window(
        {
            "x": 284,
            "y": 110,
            "apply_empirical_correction": False,
        },
        image_size={"width": 1024, "height": 576},
        original_size={"width": 1920, "height": 1080},
        target_app="steam",
    )

    assert matched is not None


def test_filter_match_to_active_app_window_rejects_point_outside_active_window():
    tool = InputAutomationTool()
    tool.services = SimpleNamespace(
        call_tool=lambda tool_name, operation, **kwargs: {
            "success": True,
            "title": "Steam",
            "position": {"x": 400, "y": 100},
            "size": {"width": 900, "height": 800},
        }
        if tool_name == "SystemControlTool" and operation == "get_active_window"
        else {}
    )

    matched = tool._filter_match_to_active_app_window(
        {
            "x": 20,
            "y": 20,
            "apply_empirical_correction": False,
        },
        image_size={"width": 1024, "height": 576},
        original_size={"width": 1920, "height": 1080},
        target_app="steam",
    )

    assert matched is None
