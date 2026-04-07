import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional


DetailDict = Dict[str, Any]
DetailRequest = Mapping[str, str]
OCRExtractor = Callable[[List[str], DetailRequest], Optional[DetailDict]]
Normalizer = Callable[[DetailDict, DetailRequest], DetailDict]
PromptRulesBuilder = Callable[[DetailRequest], str]

_REQUEST_TOKEN_STOPWORDS = {"field", "value", "detail", "requested", "specific"}


def _normalize_base_detail(detail: DetailDict) -> DetailDict:
    return {
        "ambiguous": bool(detail.get("ambiguous", False)),
        "confidence": max(0.0, min(float(detail.get("confidence", 0.0) or 0.0), 1.0)),
        "reason": str(detail.get("reason", "") or "").strip(),
        "field_label": str(detail.get("field_label", "") or "").strip(),
        "field_value": str(detail.get("field_value", "") or "").strip(),
        "explicit_text_evidence": str(detail.get("explicit_text_evidence", "") or "").strip(),
        "field_visible": bool(detail.get("field_visible", False)),
        "target_found": bool(detail.get("target_found", True)),
    }


def _field_description_tokens(field_description: str) -> List[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", str(field_description or "").lower())
        if len(token) >= 3 and token not in _REQUEST_TOKEN_STOPWORDS
    ]


def is_supported_playtime_evidence(field_label: str, explicit_text_evidence: str) -> bool:
    combined = " ".join(
        part.strip().lower()
        for part in (field_label or "", explicit_text_evidence or "")
        if part and part.strip()
    )
    if not combined:
        return False

    blocked_phrases = (
        "since last played",
        "last played",
        "past 2 weeks",
        "past two weeks",
        "recently played",
        "recent activity",
        "time since",
        "hours since",
        "minutes ago",
        "days ago",
        "weeks ago",
        "months ago",
    )
    if any(phrase in combined for phrase in blocked_phrases):
        return False

    allowed_phrases = (
        "hrs on record",
        "hours on record",
        "on record",
        "play time",
        "playtime",
        "hours played",
        "played for",
    )
    return any(phrase in combined for phrase in allowed_phrases)


def extract_labeled_playtime_from_text_candidates(
    items: List[str],
    detail_request: DetailRequest,
) -> Optional[DetailDict]:
    del detail_request
    normalized_items = [str(item or "").strip() for item in items if str(item or "").strip()]
    if not normalized_items:
        return None

    patterns = [
        (r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours)\s+on\s+record", "hrs on record"),
        (r"play\s*time[:\s]+(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours)?", "play time"),
        (r"hours?\s+played[:\s]+(\d+(?:\.\d+)?)", "hours played"),
        (r"played[:\s]+(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours)", "played"),
    ]

    for item in normalized_items:
        lower = item.lower()
        for pattern, label in patterns:
            match = re.search(pattern, lower, flags=re.IGNORECASE)
            if match:
                value = str(match.group(1) or "").strip()
                return normalize_playtime_detail(
                    {
                        "field_label": label,
                        "field_value": value,
                        "explicit_text_evidence": item,
                        "confidence": 0.92,
                        "ambiguous": False,
                        "field_visible": True,
                        "target_found": True,
                    },
                    {},
                )
    return None


def extract_labeled_generic_detail_from_text_candidates(
    items: List[str],
    detail_request: DetailRequest,
) -> Optional[DetailDict]:
    normalized_items = [str(item or "").strip() for item in items if str(item or "").strip()]
    if not normalized_items:
        return None

    desired_tokens = _field_description_tokens(str(detail_request.get("field_description", "") or ""))
    if not desired_tokens:
        return None

    patterns = [
        r"^(?P<label>[^:]{2,40})[:\-\u2013]\s*(?P<value>.+)$",
        r"^(?P<label>[A-Za-z][A-Za-z0-9 /_]{2,40})\s{2,}(?P<value>.+)$",
    ]

    for item in normalized_items:
        lower = item.lower()
        for pattern in patterns:
            match = re.search(pattern, item)
            if not match:
                continue
            label = str(match.group("label") or "").strip()
            value = str(match.group("value") or "").strip()
            if value and any(token in label.lower() or token in lower for token in desired_tokens):
                return {
                    "field_label": label,
                    "field_value": value,
                    "explicit_text_evidence": item,
                    "confidence": 0.88,
                    "ambiguous": False,
                    "field_visible": True,
                    "target_found": True,
                }

    related = [item for item in normalized_items if any(token in item.lower() for token in desired_tokens)]
    if len(related) >= 2:
        return {
            "field_label": related[0],
            "field_value": related[1],
            "explicit_text_evidence": f"{related[0]} {related[1]}",
            "confidence": 0.5,
            "ambiguous": True,
            "field_visible": False,
            "target_found": True,
            "reason": "Field-related text is visible, but no clear label/value pair was found.",
        }
    return None


def normalize_playtime_detail(detail: DetailDict, detail_request: DetailRequest) -> DetailDict:
    del detail_request
    normalized = _normalize_base_detail(detail)
    if normalized["field_value"] and not is_supported_playtime_evidence(
        normalized["field_label"],
        normalized["explicit_text_evidence"],
    ):
        normalized["ambiguous"] = True
        normalized["field_visible"] = False
        normalized["confidence"] = min(normalized["confidence"], 0.35)
        normalized["reason"] = (
            normalized["reason"]
            or "A numeric hour value was visible, but the supporting label did not clearly indicate total playtime."
        )
        normalized["field_value"] = ""
    return normalized


def normalize_generic_detail(detail: DetailDict, detail_request: DetailRequest) -> DetailDict:
    normalized = _normalize_base_detail(detail)
    requested = str(detail_request.get("field_description", "") or "").lower()
    evidence_text = " ".join(
        part
        for part in (
            normalized["field_label"].lower(),
            normalized["explicit_text_evidence"].lower(),
        )
        if part
    )
    tokens = _field_description_tokens(requested)
    if normalized["field_value"] and tokens and not any(token in evidence_text for token in tokens):
        normalized["ambiguous"] = True
        normalized["field_visible"] = False
        normalized["confidence"] = min(normalized["confidence"], 0.35)
        normalized["reason"] = (
            normalized["reason"]
            or "A candidate value was visible, but the supporting label did not clearly match the requested detail."
        )
        normalized["field_value"] = ""
    return normalized


def build_playtime_prompt_rules(detail_request: DetailRequest) -> str:
    del detail_request
    return (
        "- Accept labels such as 'hrs on record', 'hours on record', 'play time', or 'hours played'.\n"
        "- Reject labels such as 'since last played', 'last played', 'past 2 weeks', or any other recency/activity metric.\n"
    )


def build_generic_prompt_rules(detail_request: DetailRequest) -> str:
    requested = str(detail_request.get("field_description", "requested detail") or "requested detail")
    return (
        f"- Prefer label/value pairs whose visible label explicitly refers to '{requested}'.\n"
        "- Reject nearby values when the label is missing, generic, or clearly refers to another field.\n"
    )


@dataclass(frozen=True)
class DetailFieldPolicy:
    field_name: str
    prompt_rules_builder: PromptRulesBuilder
    ocr_extractor: OCRExtractor
    normalizer: Normalizer

    def prompt_extra_rules(self, detail_request: DetailRequest) -> str:
        return self.prompt_rules_builder(detail_request)

    def extract_from_ocr(self, items: List[str], detail_request: DetailRequest) -> Optional[DetailDict]:
        return self.ocr_extractor(items, detail_request)

    def normalize(self, detail: DetailDict, detail_request: DetailRequest) -> DetailDict:
        return self.normalizer(detail, detail_request)


PLAYTIME_HOURS_POLICY = DetailFieldPolicy(
    field_name="playtime_hours",
    prompt_rules_builder=build_playtime_prompt_rules,
    ocr_extractor=extract_labeled_playtime_from_text_candidates,
    normalizer=normalize_playtime_detail,
)

GENERIC_DETAIL_POLICY = DetailFieldPolicy(
    field_name="generic_detail",
    prompt_rules_builder=build_generic_prompt_rules,
    ocr_extractor=extract_labeled_generic_detail_from_text_candidates,
    normalizer=normalize_generic_detail,
)


DETAIL_FIELD_POLICIES: Dict[str, DetailFieldPolicy] = {
    PLAYTIME_HOURS_POLICY.field_name: PLAYTIME_HOURS_POLICY,
    GENERIC_DETAIL_POLICY.field_name: GENERIC_DETAIL_POLICY,
}


def get_detail_field_policy(field_name: str) -> DetailFieldPolicy:
    return DETAIL_FIELD_POLICIES.get(str(field_name or "").strip().lower(), GENERIC_DETAIL_POLICY)
