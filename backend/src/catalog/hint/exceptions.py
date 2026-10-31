class HintError(Exception):
    pass


class HintClientError(HintError):
    """LLM provider unavailable, timed out, or rate-limited."""
    pass


class HintParseError(HintError):
    """Response was not valid JSON."""
    pass


class HintValidationError(HintError):
    """JSON was valid but violated the contract (unknown key, wrong
    category prefix, malformed selection)."""
    pass