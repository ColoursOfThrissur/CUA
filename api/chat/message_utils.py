"""Message handling utilities for chat requests."""

_SIMPLE_PATTERNS = {
    "hi", "hello", "hey", "thanks", "thank you", "bye", "goodbye",
    "how are you", "what's up", "good morning", "good afternoon", "good evening",
    "ok", "okay", "yes", "no", "sure", "great", "nice", "cool", "awesome",
}


def is_simple_message(message: str) -> bool:
    """Check if message is a simple greeting/acknowledgment."""
    lower = message.lower().strip()
    words = lower.split()
    return (
        lower in _SIMPLE_PATTERNS
        or (
            len(message.strip()) < 20
            and not any(k in lower for k in [
                "?", "what", "how", "when", "where", "why", "can you", "please",
                "help", "do", "get", "find", "search", "open", "run", "execute",
                "create", "make", "build", "write", "read", "list", "show",
            ])
        )
        or (len(words) <= 3 and all(w in _SIMPLE_PATTERNS or len(w) <= 4 for w in words))
    )


def simple_reply(message: str) -> str:
    """Generate simple reply for greetings/acknowledgments."""
    lower = message.lower()
    if any(g in lower for g in ["hi", "hello", "hey"]):
        return "Hello! How can I assist you today?"
    if any(t in lower for t in ["thanks", "thank you"]):
        return "You're welcome! Let me know if you need anything else."
    if any(b in lower for b in ["bye", "goodbye"]):
        return "Goodbye! Feel free to come back anytime."
    if lower in ("ok", "okay", "yes", "sure"):
        return "Great! What would you like to do next?"
    if lower == "no":
        return "No problem. Let me know if you change your mind."
    return "I'm here to help! What can I do for you?"


def needs_runtime_refresh(message: str) -> bool:
    """Check if message requires registry refresh."""
    lower = message.lower()
    return any(k in lower for k in ["tool", "capability", "create", "evolve", "new tool"])


def has_referenced_tools_loaded(reg, message: str) -> bool:
    """Check if referenced tools are already loaded."""
    if not reg:
        return False
    lower = message.lower()
    return any(lower in t.__class__.__name__.lower() for t in reg.tools)
