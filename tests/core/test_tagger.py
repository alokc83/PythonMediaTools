
import pytest
from src.core.audio_shelf.tagger import normalize_author, normalize_title, shorten_description

def test_normalize_author():
    assert normalize_author("George R. R. Martin") == "George R.R. Martin"
    assert normalize_author("J. K. Rowling") == "J.K. Rowling"
    assert normalize_author("Normal Name") == "Normal Name"

def test_normalize_title():
    # "Title: Subtitle" -> "Title" -> "The " stripped -> "Hobbit"
    assert normalize_title("The Hobbit: There and Back Again") == "Hobbit"
    # "Title (Narrator)" -> "Title"
    assert normalize_title("The Hobbit (Unabridged)") == "Hobbit"
    # Combined
    assert normalize_title("Dune: A Novel (Audiobook)") == "Dune"

def test_shorten_description():
    desc = "A" * 1000
    short = shorten_description(desc, limit=10)
    assert len(short) <= 13 # 10 + "..."
    assert short.endswith("...")
    assert shorten_description("Short", limit=100) == "Short"
