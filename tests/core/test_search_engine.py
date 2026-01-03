
import pytest
from unittest.mock import patch, MagicMock
from src.core.audio_shelf.search_engine import search_duckduckgo_audible, search_goodreads_direct, search_duckduckgo_amazon

# Sample HTML Responses
DDG_AUDIBLE_HTML = """
<html>
    <div class="result__a" href="https://www.audible.com/pd/Some-Book-Audiobook/B00FAKEASIN">Title</div>
    <div class="result__a" href="https://other.com">Ignore</div>
</html>
"""

GOODREADS_HTML = """
<html>
    <table class="tableList">
        <a class="bookTitle" href="/book/show/12345.Some_Book">Some Book</a>
    </table>
</html>
"""

# Test DuckDuckGo Audible Search
@patch('src.core.audio_shelf.search_engine.requests.post')
def test_search_duckduckgo_audible_success(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.text = DDG_AUDIBLE_HTML
    
    results = search_duckduckgo_audible("Some Book")
    assert len(results) == 1
    assert "audible.com/pd/Some-Book" in results[0]

@patch('src.core.audio_shelf.search_engine.requests.post')
def test_search_duckduckgo_audible_failure(mock_post):
    mock_post.return_value.status_code = 500
    
    results = search_duckduckgo_audible("Fail")
    assert results == []

# Test Goodreads Direct Search
@patch('src.core.audio_shelf.search_engine.requests.get')
def test_search_goodreads_direct_success(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = GOODREADS_HTML
    
    results = search_goodreads_direct("Some Book")
    assert len(results) == 1
    assert "goodreads.com/book/show/12345" in results[0]

# Test Retry Logic (Indirectly via search function)
@patch('src.core.audio_shelf.search_engine.requests.post')
def test_retry_logic_eventual_success(mock_post):
    # Fail twice, succeed third time
    fail_response = MagicMock()
    fail_response.raise_for_status.side_effect = Exception("Timeout")
    
    success_response = MagicMock()
    success_response.status_code = 200
    success_response.text = DDG_AUDIBLE_HTML
    
    # We need to simulate side effects on the CALL not the return object for exceptions
    # But search_engine uses requests.post(...)
    # If the decorator handles specific exceptions, we should mock side_effect to raise them.
    # The current retry_on_failure catches request exceptions.
    import requests
    mock_post.side_effect = [requests.exceptions.RequestException("Fail 1"), requests.exceptions.Timeout("Fail 2"), success_response]
    
    results = search_duckduckgo_audible("Retry Me")
    assert len(results) == 1
    assert mock_post.call_count == 3

# Test Amazon Search
@patch('src.core.audio_shelf.search_engine.requests.post')
def test_search_duckduckgo_amazon_success(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.text = """
    <html>
        <div class="result__a" href="https://www.amazon.com/Some-Book/dp/B00FAKE">Title</div>
    </html>
    """
    
    results = search_duckduckgo_amazon("Some Book")
    assert len(results) == 1
    assert "amazon.com/Some-Book" in results[0]
