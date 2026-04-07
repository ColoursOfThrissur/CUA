from tools.computer_use.ocr_clicker import OCRClicker


def test_find_text_match_prefers_exact_match():
    clicker = OCRClicker()
    results = [
        {"text": "STORE", "bbox": (0, 0, 10, 10), "center": (5, 5), "confidence": 0.9},
        {"text": "LIBRARY", "bbox": (20, 0, 80, 20), "center": (50, 10), "confidence": 0.95},
        {"text": "COMMUNITY", "bbox": (90, 0, 160, 20), "center": (125, 10), "confidence": 0.9},
    ]

    match = clicker._find_text_match("Library", results, fuzzy=True)

    assert match is not None
    assert match["text"] == "LIBRARY"
    assert match["center"] == (50, 10)


def test_find_text_match_accepts_ocr_near_match():
    clicker = OCRClicker()
    results = [
        {"text": "LIBR4RY", "bbox": (20, 0, 80, 20), "center": (50, 10), "confidence": 0.92},
    ]

    match = clicker._find_text_match("Library", results, fuzzy=True)

    assert match is not None
    assert match["text"] == "LIBR4RY"


def test_build_ocr_variants_adds_targeted_top_strip_for_text_targets():
    from PIL import Image

    clicker = OCRClicker()
    img = Image.new("RGB", (100, 60), "white")

    variants = clicker._build_ocr_variants(img, target_text="Library")

    names = [variant["name"] for variant in variants]
    assert "full_default" in names
    assert "full_enhanced" in names
    assert "top_strip_enhanced" in names
    assert "left_strip_enhanced" in names
    assert "right_strip_enhanced" in names
    assert "center_band_enhanced" in names


def test_collect_tesseract_results_maps_scaled_variant_back_to_base_coordinates():
    clicker = OCRClicker()
    data = {
        "text": ["LIBRARY"],
        "conf": ["92"],
        "left": [100],
        "top": [40],
        "width": [80],
        "height": [20],
    }

    results = clicker._collect_tesseract_results(data, offset_x=0, offset_y=0, scale=2.0)

    assert len(results) == 1
    assert results[0]["bbox"] == (50, 20, 90, 30)
    assert results[0]["center"] == (70, 25)


def test_expand_with_phrase_candidates_merges_split_ui_label():
    clicker = OCRClicker()
    results = [
        {"text": "Add", "bbox": (10, 10, 40, 24), "center": (25, 17), "confidence": 0.91},
        {"text": "Game", "bbox": (46, 10, 88, 24), "center": (67, 17), "confidence": 0.89},
        {"text": "Friends", "bbox": (10, 40, 60, 54), "center": (35, 47), "confidence": 0.95},
    ]

    expanded = clicker._expand_with_phrase_candidates(results, target_text="Add Game")

    texts = [item["text"] for item in expanded]
    assert "Add Game" in texts


def test_find_text_match_handles_split_phrase_candidate():
    clicker = OCRClicker()
    results = clicker._expand_with_phrase_candidates(
        [
            {"text": "Friends", "bbox": (10, 10, 62, 24), "center": (36, 17), "confidence": 0.92},
            {"text": "&", "bbox": (66, 10, 74, 24), "center": (70, 17), "confidence": 0.87},
            {"text": "Chat", "bbox": (78, 10, 114, 24), "center": (96, 17), "confidence": 0.94},
        ],
        target_text="Friends Chat",
    )

    match = clicker._find_text_match("Friends Chat", results, fuzzy=True)

    assert match is not None
    assert match["text"] in {"Friends & Chat", "Friends Chat"}


def test_find_text_match_handles_common_confusable_characters():
    clicker = OCRClicker()
    results = [
        {"text": "L1brary", "bbox": (20, 0, 90, 20), "center": (55, 10), "confidence": 0.9},
    ]

    match = clicker._find_text_match("Library", results, fuzzy=True)

    assert match is not None
    assert match["text"] == "L1brary"


def test_ocr_clicker_scales_to_desktop_without_empirical_y_correction():
    clicker = OCRClicker()

    scaled = clicker._scale_to_desktop_coordinates(
        290,
        192,
        image_width=1024,
        image_height=576,
        original_width=1920,
        original_height=1080,
    )

    assert scaled == (544, 360)
