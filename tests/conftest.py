import pytest

from archolith_mcp_audit.mcp_server import _reset_caches
from archolith_mcp_audit.tokenizer import _reset_encodings


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset module-level caches before and after each test."""
    _reset_encodings()
    _reset_caches()
    yield
    _reset_encodings()
    _reset_caches()
