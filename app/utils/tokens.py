import logging

import tiktoken

logger = logging.getLogger(__name__)

_ENCODER = None


def _get_encoder():
    global _ENCODER
    if _ENCODER is None:
        try:
            _ENCODER = tiktoken.encoding_for_model("gpt-4o-mini")
        except Exception as exc:
            logger.warning(
                "Failed to initialize tiktoken encoder for gpt-4o-mini: %s. "
                "Falling back to approximate token counting.",
                exc,
            )
            _ENCODER = None
    return _ENCODER


def estimate_tokens(text: str) -> int:
    encoder = _get_encoder()
    if encoder is not None:
        try:
            return max(1, len(encoder.encode(text)))
        except Exception:
            pass
    return max(1, len(text) // 4 + 1)
