from tools.computer_use.input_automation_tool import InputAutomationTool


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
