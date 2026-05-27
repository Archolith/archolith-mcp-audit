"""Tests for tokenizer module."""

from archolith_mcp_audit.tokenizer import count_tokens, estimate_tokens


class TestCountTokens:
    def test_known_text(self):
        tc = count_tokens("Hello world")
        assert tc.chars == 11
        assert tc.tokens_cl100k > 0
        assert tc.tokens_o200k > 0

    def test_empty_string(self):
        tc = count_tokens("")
        assert tc.tokens_cl100k == 0
        assert tc.tokens_o200k == 0
        assert tc.chars == 0

    def test_base64_lower_chars_per_token(self):
        """Base64 should have lower chars/token than source code."""
        base64_text = "aGVsbG8gd29ybGQg" * 50  # Repeated base64
        code_text = "def hello_world():\n    print('hello world')\n" * 10
        tc_b64 = count_tokens(base64_text)
        tc_code = count_tokens(code_text)
        assert tc_b64.chars_per_token_cl100k < tc_code.chars_per_token_cl100k

    def test_bytes_count(self):
        text = "hello"
        tc = count_tokens(text)
        assert tc.bytes == len(text.encode("utf-8"))

    def test_estimate_tokens(self):
        tokens = estimate_tokens("Hello world")
        assert tokens > 0
