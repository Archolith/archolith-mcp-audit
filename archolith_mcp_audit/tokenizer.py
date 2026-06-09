"""Token counting using tiktoken (cl100k_base + o200k_base encodings)."""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken


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


def get_encodings() -> dict[str, tiktoken.Encoding]:
    """Return cached tiktoken encodings (cl100k + o200k)."""
    global _encodings
    if _encodings is None:
        _encodings = {
            "cl100k_base": tiktoken.get_encoding("cl100k_base"),
            "o200k_base": tiktoken.get_encoding("o200k_base"),
        }
    return _encodings


def count_tokens(text: str, encodings: dict[str, tiktoken.Encoding] | None = None) -> TokenCount:
    """Count tokens in text using both cl100k and o200k encodings."""
    if encodings is None:
        encodings = get_encodings()

    chars = len(text)
    byte_count = len(text.encode("utf-8"))

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
    encodings = get_encodings()
    enc = encodings.get(encoding, encodings["cl100k_base"])
    return len(enc.encode(text))
