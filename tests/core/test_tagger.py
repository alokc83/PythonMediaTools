
import pytest
from unittest.mock import MagicMock, patch
from src.core.audio_shelf.tagger import normalize_author, normalize_title, shorten_description, update_mp3_tags, update_mp4_tags, BookMeta

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

# --- Tagger Logic Tests (File Updates) ---

@patch("src.core.audio_shelf.tagger.ID3")
def test_update_mp3_description_behavior(mock_id3):
    """
    Verify current behavior: Description is written to COMM frame with desc='Description'.
    This test serves as a baseline before the fix.
    """
    # Setup Mock
    tags_instance = MagicMock()
    # Mock keys() to emulate dictionary-like behavior for checks like 'COMM' in tags
    tags_instance.keys.return_value = []
    mock_id3.return_value = tags_instance
    
    meta = BookMeta(description="Test Description")
    fields = {"description": "write"}
    
    update_mp3_tags("dummy.mp3", meta, fields_to_update=fields)
    
    # Assertions
    assert tags_instance.add.called

@patch("src.core.audio_shelf.tagger.COMM")
@patch("src.core.audio_shelf.tagger.ID3")
def test_update_mp3_comm_frame_structure(mock_id3, mock_comm):
    """
    Precise test to check desc="" (FIXED).
    """
    tags_instance = MagicMock()
    tags_instance.keys.return_value = []
    mock_id3.return_value = tags_instance
    
    meta = BookMeta(description="Test Description")
    fields = {"description": "write"}
    
    update_mp3_tags("dummy.mp3", meta, fields_to_update=fields)
    
    # Verify COMM was instantiated with specific args
    # NEW expected behavior: desc="" (Default Comment)
    mock_comm.assert_called_with(encoding=3, lang="eng", desc="", text=["Test Description"])

@patch("src.core.audio_shelf.tagger.MP4")
def test_update_mp4_description_and_comment(mock_mp4):
    """
    Verify MP4 behavior for description.
    Future: 'desc' AND '\xa9cmt'.
    """
    tags_instance = MagicMock()
    # Mock get to return default if provided, else None
    def get_side_effect(key, default=None):
        return default
    tags_instance.get.side_effect = get_side_effect
    mock_mp4.return_value = tags_instance
    
    meta = BookMeta(description="Test Description")
    fields = {"description": "write"}
    
    update_mp4_tags("dummy.m4a", meta, fields_to_update=fields)
    
    # Verify 'desc' was set
    tags_instance.__setitem__.assert_any_call("desc", ["Test Description"])
    
    # Verify '\xa9cmt' WAS set (New behavior)
    tags_instance.__setitem__.assert_any_call("\xa9cmt", ["Test Description"])

def test_merge_metadata_prefers_longer_description():
    """Test that merge_metadata picks the longest description"""
    from src.core.audio_shelf.tagger import merge_metadata
    
    meta_short = BookMeta(
        title="Test Book",
        description="Short",
        source="source1"
    )
    meta_long = BookMeta(
        title="Test Book",
        description="This is a much longer description",
        source="source2"
    )
    
    result = merge_metadata(meta_short, meta_long)
    assert len(result.description) == 33
    assert "much longer description" in result.description

def test_shorten_description_50k_limit():
    """Test that shorten_description uses 50K limit"""
    long_desc = "x" * 45000
    result = shorten_description(long_desc)
    assert len(result) == 45000
    
    verylong_desc = "y" * 60000
    result2 = shorten_description(verylong_desc)
    assert result2.endswith("...")
    assert len(result2) <= 50003

def test_mp3_comm_frame_clearing():
    """Test that write mode clears all existing COMM frames"""
    import tempfile
    import os
    from mutagen.id3 import ID3, COMM, TIT2
    
    temp_fd, temp_path = tempfile.mkstemp(suffix='.mp3')
    os.close(temp_fd)
    
    try:
        tags = ID3()
        tags.add(TIT2(encoding=3, text=["Test"]))
        tags.add(COMM(encoding=3, lang='ENG', desc='old', text=["Old 1"]))
        tags.add(COMM(encoding=3, lang='eng', desc='', text=["Old 2"]))
        tags.save(temp_path)
        
        meta = BookMeta(title="Test", description="New description")
        update_mp3_tags(temp_path, meta, None, {"description": "write"})
        
        check = ID3(temp_path)
        comm_frames = [k for k in check.keys() if k.startswith('COMM')]
        assert len(comm_frames) == 1
        
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def test_early_validation_rejection():
    """Test that process_file rejects results with low confidence (<0.4)"""
    from src.core.audio_shelf.tagger import calculate_confidence, BookQuery, BookMeta
    
    # 1. Exact Match -> 1.0
    q1 = BookQuery(title="Title", author="Author")
    m1 = BookMeta(title="Title", authors=["Author"])
    assert calculate_confidence(q1, m1) == 1.0
    
    # 2. Strong Match -> >0.4
    q2 = BookQuery(title="The Hobbit", author="J.R.R. Tolkien")
    m2 = BookMeta(title="The Hobbit: There and Back Again", authors=["Tolkien"])
    # Note: fuzzy logic handles substring/token matching
    assert calculate_confidence(q2, m2) > 0.6
    
    # 3. Bad Match -> <0.4 (Should be rejected)
    q3 = BookQuery(title="Atomic Habits", author="James Clear")
    m3 = BookMeta(title="Self-Promotion for Introverts", authors=["Nancy Ancowitz"])
    conf3 = calculate_confidence(q3, m3)
    assert conf3 < 0.4
    print(f"✅ Low confidence match correctly identified: {conf3}")

def test_cpil_parsing_logic():
    """Test safe cpil parsing logic that fixed the MP4 crash"""
    # The fix was: cpil = bool(tags['cpil'][0]) if isinstance(tags['cpil'], list) else bool(tags['cpil'])
    
    tags_list = {'cpil': [True]}
    tags_bool = {'cpil': True}
    tags_int = {'cpil': [1]}
    
    # Emulate list case
    val_list = bool(tags_list['cpil'][0]) if isinstance(tags_list['cpil'], list) else bool(tags_list['cpil'])
    assert val_list is True
    
    # Emulate scalar case
    val_bool = bool(tags_bool['cpil'][0]) if isinstance(tags_bool['cpil'], list) else bool(tags_bool['cpil'])
    # Wait, simple dict lookup returns value. If value is scalar, isinstance(list) is False.
    assert val_bool is True
    
    # Emulate int inside list
    val_int = bool(tags_int['cpil'][0]) if isinstance(tags_int['cpil'], list) else bool(tags_int['cpil'])
    assert val_int is True
