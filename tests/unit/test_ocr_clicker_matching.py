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
