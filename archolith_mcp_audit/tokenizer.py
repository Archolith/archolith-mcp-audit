"""Token counting using tiktoken (cl100k_base + o200k_base encodings)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import tiktoken

__all__ = [
    "TokenCount",
    "get_encodings",
    "count_tokens",
    "count_tokens_batch",
    "estimate_tokens",
]


@dataclass
class TokenCount:
    """Token measurement for a single result."""

    chars: int
    bytes: int
    tokens_cl100k: int
    tokens_o200k: int
    chars_per_token_cl100k: float
    chars_per_token_o200k: float


# Singleton cache for encodings
_encodings: dict[str, tiktoken.Encoding] | None = None


def _reset_encodings() -> None:
    """Clear the cached tiktoken encodings. Used in testing."""
    global _encodings
    _encodings = None
    _count_tokens_default.cache_clear()


def get_encodings() -> dict[str, tiktoken.Encoding]:
    """Return cached tiktoken encodings (cl100k + o200k)."""
    global _encodings
    if _encodings is None:
        _encodings = {
            "cl100k_base": tiktoken.get_encoding("cl100k_base"),
            "o200k_base": tiktoken.get_encoding("o200k_base"),
        }
    return _encodings


@lru_cache(maxsize=4096)
def _count_tokens_default(text: str) -> tuple[int, int]:
    """Count default encodings with a bounded cache for repeated detector passes."""
    encodings = get_encodings()
    return (
        len(encodings["cl100k_base"].encode(text)),
        len(encodings["o200k_base"].encode(text)),
    )


def count_tokens(text: str, encodings: dict[str, tiktoken.Encoding] | None = None) -> TokenCount:
    """Count tokens in text using both cl100k and o200k encodings."""
    chars = len(text)
    byte_count = len(text.encode("utf-8"))

    if encodings is None:
        tokens_cl, tokens_o2 = _count_tokens_default(text)
    else:
        tokens_cl = len(encodings["cl100k_base"].encode(text))
        tokens_o2 = len(encodings["o200k_base"].encode(text))

    cpt_cl = chars / tokens_cl if tokens_cl > 0 else 0.0
    cpt_o2 = chars / tokens_o2 if tokens_o2 > 0 else 0.0

    return TokenCount(
        chars=chars,
        bytes=byte_count,
        tokens_cl100k=tokens_cl,
        tokens_o200k=tokens_o2,
        chars_per_token_cl100k=cpt_cl,
        chars_per_token_o200k=cpt_o2,
    )


def count_tokens_batch(
    texts: list[str],
    encodings: dict[str, tiktoken.Encoding] | None = None,
) -> list[TokenCount]:
    """Count tokens for multiple texts.

    Uses per-text encoding for reliability across all input sizes.
    """
    if not texts:
        return []

    if encodings is None:
        encodings = get_encodings()

    # Per-text encoding (simple, reliable)
    results = []
    for text in texts:
        results.append(count_tokens(text, encodings))
    return results


def estimate_tokens(text: str, encoding: str = "cl100k_base") -> int:
    """Estimate token count for a single text with one encoding.

    Convenience function for quick estimates.
    """
    if encoding in {"cl100k_base", "o200k_base"}:
        return len(get_encodings()[encoding].encode(text))
    return len(tiktoken.get_encoding(encoding).encode(text))
