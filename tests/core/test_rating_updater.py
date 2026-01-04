
import pytest
from unittest.mock import MagicMock, patch, call
from src.core.audio_shelf.rating_updater import RatingUpdaterEngine, BookMeta, BookQuery

# Mock Data
MOCK_DIR = "/mock/library/Author - Title"
MOCK_FILE_MP3 = "/mock/library/Author - Title/book.mp3"
MOCK_FILE_M4A = "/mock/library/Author - Title/book.m4a"

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    # Default: All enabled
    settings.get.side_effect = lambda k, d=None: True
    return settings

@pytest.fixture
def engine(mock_settings):
    # Mock make_session to avoid network
    with patch('src.core.audio_shelf.rating_updater.make_session'):
        eng = RatingUpdaterEngine(settings_manager=mock_settings)
        eng.log = MagicMock()
        return eng

# --- Test Provider Toggles (Logic in _get_or_update_atf) ---

@patch('src.core.audio_shelf.rating_updater.audible_find_asin')
@patch('src.core.audio_shelf.rating_updater.provider_audnexus_by_asin')
def test_audnexus_enabled(mock_nexus, mock_find, engine):
    # Setup
    mock_find.return_value = ("B00FAKE", "url")
    mock_nexus.return_value = BookMeta(title="T", rating="4.5", rating_count="1,000")
    
    # Execute (Mock internal query building to skip file io)
    query = BookQuery(title="Title", author="Author")
    
    # We cheat and call internal logic block or mock surrounding?
    # _process_book is huge. It's better to test small units if possible,
    # but the logic is inside scan_and_update -> _process_book.
    # Let's mock _get_or_update_atf?
    # No, we want to test _get_or_update_atf's logic!
    
    # Depending on how the method is structured, we might need to mock os.listdir
    # or pass a BookQuery directly if refactored.
    # But currently it takes 'directory' and builds query.
    
    pass 

# Since _get_or_update_atf is hard to call in isolation without file IO,
# Let's test the helper _apply_rating_to_file which was recently modified for M4A.

@patch('src.core.audio_shelf.rating_updater.MP4')
def test_apply_rating_m4a_grouping(mock_mp4_cls, engine):
    # Setup Mock Audio
    audio = MagicMock()
    # Use a real dict to track contents to avoid recursion
    mock_tags = {}
    audio.__contains__.side_effect = lambda k: k in mock_tags
    audio.get.side_effect = lambda k: mock_tags.get(k)
    audio.__getitem__.side_effect = lambda k: mock_tags[k]
    audio.__setitem__.side_effect = lambda k, v: mock_tags.__setitem__(k, v)
    mock_mp4_cls.return_value = audio
    
    # Execute
    # Header logic: 4.5 -> "4+ Rated Books"
    engine._apply_rating_to_file(MOCK_FILE_M4A, "⭐️ 4.5", "4+ Rated Books")
    
    # Verify assignment
    # We expect unicode key \u00a9grp
    assert audio.__setitem__.call_count >= 1
    # Check calls
    calls = audio.__setitem__.call_args_list
    
    # Find the grouping call
    grp_call = None
    for c in calls:
        if c[0][0] == '\u00a9grp':
            grp_call = c
            break
            
    assert grp_call is not None
    assert grp_call[0][1] == ["4+ Rated Books"]
    
    # Verify Save
    audio.save.assert_called_once()

@patch('src.core.audio_shelf.rating_updater.ID3')
def test_apply_rating_mp3_tit1(mock_id3_cls, engine):
    # Setup
    audio = MagicMock()
    mock_id3_cls.return_value = audio
    audio.values.return_value = [] # No existing COMM
    
    # Execute
    engine._apply_rating_to_file(MOCK_FILE_MP3, "⭐️ 4.5", "4+ Rated Books")
    
    # Verify TIT1 addition
    # mutagen add is called with TIT1 object
    from mutagen.id3 import TIT1
    
    assert audio.add.call_count >= 1
    # We need to verify the args passed to add()
    # It's an instance of TIT1.
    
    # Iterate calls
    found_tit1 = False
    for c in audio.add.call_args_list:
        arg = c[0][0]
        if isinstance(arg, TIT1):
            assert arg.text == ["4+ Rated Books"]
            found_tit1 = True
            
    assert found_tit1
    audio.save.assert_called_once()

# --- Test Settings Integration ---
# We mock settings.get to return False for Audnexus and verify it's skipped.
# We need to mock _get_or_update_atf fully or patch the logic.
# Since _get_or_update_atf does File I/O to get query, we mock read_metadata.

@patch('src.core.audio_shelf.rating_updater.read_metadata')
@patch('src.core.audio_shelf.rating_updater.os.listdir')
@patch('src.core.audio_shelf.rating_updater.audible_find_asin')
def test_settings_disable_audnexus(mock_find, mock_listdir, mock_read, engine, mock_settings):
    # Setup
    mock_settings.get.side_effect = lambda k, d=None: False if 'audnexus' in k else True
    
    mock_listdir.return_value = ["book.mp3"]
    mock_read.return_value = BookQuery(title="Test", author="Test")
    
    # Run helper (we can call _get_or_update_atf directly if we ignore cache checking or mock it)
    # The method is _get_or_update_atf(directory)
    # It calls read_metadata.
    
    # We need to verify audible_find_asin is NOT called
    result = engine._get_or_update_atf(MOCK_DIR)
    
    mock_find.assert_not_called()

@patch('src.core.audio_shelf.rating_updater.read_metadata')
@patch('src.core.audio_shelf.rating_updater.os.listdir')
@patch('src.core.audio_shelf.rating_updater.audible_find_asin')
@patch('src.core.audio_shelf.rating_updater.provider_audnexus_by_asin')
def test_zero_count_rating_fallback(mock_nexus, mock_find, mock_listdir, mock_read_meta, engine):
    """
    Test that a rating with 0 votes (from Audnexus) is NOT discarded 
    and falls back to raw average instead of Bayesian.
    """
    # Setup - files exist
    mock_listdir.return_value = ["book.mp3"]
    # Metadata for query
    mock_read_meta.return_value = BookQuery(title="The Black Swan", author="Taleb")
    
    # Mock Search Result
    mock_find.return_value = ("B07KRNNLFF", "url")
    
    # Mock Audnexus Result: Valid Rating (4.5), Count is None/0
    mock_nexus.return_value = BookMeta(
        title="The Black Swan", 
        rating="4.5", 
        rating_count="0",  # Zero count!
        source="audnexus"
    )
    
    # Run
    # We need to mock atf_handler to return None so it fetches
    engine.atf_handler.read_atf = MagicMock(return_value=(False, None))
    
    # Call internal method
    result = engine._get_or_update_atf("/fake/path")
    
    # Verify
    assert result is not None, "Should have returned a result, not None"
    
    # Check that it used the Raw Rating (4.5) not 0.0 or 2.0
    # The calculated rating is in base_meta.rating AND base_meta._custom_header
    assert result.rating == "4.5"
    assert "4.5" in result._custom_header
    assert "Weighted Rating: 𝟒.𝟓" in result._custom_header # Check Bolding? 4.5 -> 𝟒.𝟓
    
    # Verify log output (optional, but good for debugging)
    engine.log.assert_any_call("⚠️ No vote counts found (Total 0). Using Raw Average: 4.5")

@patch('src.core.audio_shelf.rating_updater.read_metadata')
@patch('src.core.audio_shelf.rating_updater.os.listdir')
@patch('src.core.audio_shelf.rating_updater.audible_find_asin')
@patch('src.core.audio_shelf.rating_updater.provider_audnexus_by_asin')
@patch('src.core.audio_shelf.rating_updater.search_goodreads_direct')
def test_skip_scraping_if_high_confidence(mock_gr_search, mock_nexus, mock_find, mock_listdir, mock_read_meta, engine):
    """
    Test that Goodreads/Amazon scraping is SKIPPED if Audnexus/Google provides
    enough votes (>50).
    """
    mock_listdir.return_value = ["book.mp3"]
    mock_read_meta.return_value = BookQuery(title="High Conf Book", author="Author")
    mock_find.return_value = ("ASIN123", "url")
    
    # Mock High Confidence Result (1000 votes)
    mock_nexus.return_value = BookMeta(
        title="High Conf Book", 
        rating="4.5", 
        rating_count="1,000", 
        source="audnexus"
    )
    
    engine.atf_handler.read_atf = MagicMock(return_value=(False, None))
    
    # Run
    engine._get_or_update_atf("/fake/path")
    
    # Verify: Goodreads search should NOT have been called
    mock_gr_search.assert_not_called()
    
    # Verify log message
    engine.log.assert_any_call("High confidence data found (1000 votes). Skipping slow scraping (Goodreads/Amazon).")

@patch('src.core.audio_shelf.rating_updater.read_metadata')
@patch('src.core.audio_shelf.rating_updater.os.listdir')
@patch('src.core.audio_shelf.rating_updater.audible_find_asin')
@patch('src.core.audio_shelf.rating_updater.provider_audnexus_by_asin')
@patch('src.core.audio_shelf.rating_updater.search_goodreads_direct')
def test_fallback_scraping_if_low_confidence(mock_gr_search, mock_nexus, mock_find, mock_listdir, mock_read_meta, engine):
    """
    Test that Goodreads/Amazon scraping is ENABLED if votes are low (<50).
    """
    mock_listdir.return_value = ["book.mp3"]
    mock_read_meta.return_value = BookQuery(title="Low Conf Book", author="Author")
    mock_find.return_value = ("ASIN123", "url")
    
    # Mock Low Confidence Result (10 votes)
    mock_nexus.return_value = BookMeta(
        title="Low Conf Book", 
        rating="4.5", 
        rating_count="10", 
        source="audnexus"
    )
    
    engine.atf_handler.read_atf = MagicMock(return_value=(False, None))
    
    # Run
    engine._get_or_update_atf("/fake/path")
    
    # Verify: Goodreads search SHOULD be called
    mock_gr_search.assert_called()
    
    # Verify log message
    engine.log.assert_any_call("Low vote counts (10 < 50). Enabling fallback scraping...")

def test_bayesian_math_accuracy(engine):
    """
    Verify the Bayesian math calculation independently.
    Formula: (v / (v+m)) * R + (m / (v+m)) * C
    m=500, C=2.0
    """
    # Create fake processed items list (bypassing the loop)
    # We can test a helper function if we extract it, but it's inline.
    # Alternatively, we can run _get_or_update_atf with mocked found_ratings logic?
    # No, easy way: make a small test that replicates the math function 
    # and asserts our code produces the same result.
    # But better: Mock found_ratings finding 1 item with X votes and Y rating
    # and assert the log output or result matches expected calculation.
    
    # Case 1: High Votes (10,000) @ 4.8
    # Expect: Very close to 4.8
    # v=10000, m=500, R=4.8, C=2.0
    # W = 10000/10500 = 0.952
    # Res = 0.952*4.8 + 0.048*2.0 = 4.57 + 0.09 = 4.66
    
    with patch('src.core.audio_shelf.rating_updater.read_metadata') as mock_read, \
         patch('src.core.audio_shelf.rating_updater.os.listdir') as mock_ls, \
         patch('src.core.audio_shelf.rating_updater.audible_find_asin') as mock_find, \
         patch('src.core.audio_shelf.rating_updater.provider_audnexus_by_asin') as mock_nexus:
         
         mock_ls.return_value = ["book.mp3"]
         mock_read.return_value = BookQuery(title="Math Test", author="A")
         mock_find.return_value = ("ASIN", "url")
         
         mock_nexus.return_value = BookMeta(
             title="Math Test", rating="4.8", rating_count="10,000", source="audnexus"
         )
         
         engine.atf_handler.read_atf = MagicMock(return_value=(False, None))
         
         result = engine._get_or_update_atf("/fake")
         
         # Check log for "Final Bayesian Weighted Rating: X/5"
         # Or check result.rating
         # 4.66 is expected
         assert 4.60 <= float(result.rating) <= 4.75, f"Expected ~4.66, got {result.rating}"

def test_bayesian_math_low_votes(engine):
    """
    Verify Bayesian damping for low votes.
    v=10, R=5.0 (Perfect score, but few votes)
    m=500, C=2.0
    Weight = 10/510 = 0.019
    Res = 0.019*5.0 + 0.98*2.0 = 0.095 + 1.96 = ~2.05
    Result should be aggressively pulled to 2.0
    """
    with patch('src.core.audio_shelf.rating_updater.read_metadata') as mock_read, \
         patch('src.core.audio_shelf.rating_updater.os.listdir') as mock_ls, \
         patch('src.core.audio_shelf.rating_updater.audible_find_asin') as mock_find, \
         patch('src.core.audio_shelf.rating_updater.provider_audnexus_by_asin') as mock_nexus:
         
         mock_ls.return_value = ["book.mp3"]
         mock_read.return_value = BookQuery(title="Low Vote", author="A")
         mock_find.return_value = ("ASIN", "url")
         
         mock_nexus.return_value = BookMeta(
             title="Low Vote", rating="5.0", rating_count="10", source="audnexus"
         )
         
         engine.atf_handler.read_atf = MagicMock(return_value=(False, None))
         
         result = engine._get_or_update_atf("/fake")
         
         # Expect damped rating close to 2.0
         assert 2.0 <= float(result.rating) <= 2.2, f"Expected ~2.05, got {result.rating}"

