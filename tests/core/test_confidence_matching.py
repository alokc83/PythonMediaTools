"""
Tests for smart containment confidence matching logic.
Verifies that confidence scores correctly handle narrator and edition metadata.
"""

import pytest
from src.core.audio_shelf.tagger import calculate_confidence, BookQuery, BookMeta


class TestSmartContainmentNarratorPatterns:
    """Tests for narrator pattern detection in confidence matching"""
    
    def test_narrator_as_read_by_gives_perfect_score(self):
        """Query with 'as read by' narrator should get perfect confidence"""
        query = BookQuery(
            title="The Science of Getting Rich",
            author="Wallace D. Wattles as read by Mike DeWitt"
        )
        meta = BookMeta(
            title="The Science of Getting Rich",
            authors=["Wallace D. Wattles"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence == 1.0, "Should give perfect score for narrator pattern"
    
    def test_narrator_narrated_by_gives_perfect_score(self):
        """Query with 'narrated by' should get perfect confidence"""
        query = BookQuery(
            title="1984",
            author="George Orwell narrated by Simon Prebble"
        )
        meta = BookMeta(
            title="1984",
            authors=["George Orwell"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence == 1.0
    
    def test_narrator_read_by_gives_perfect_score(self):
        """Query with 'read by' should get perfect confidence"""
        query = BookQuery(
            title="Dune",
            author="Frank Herbert read by Scott Brick"
        )
        meta = BookMeta(
            title="Dune",
            authors=["Frank Herbert"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence == 1.0
    
    def test_narrator_performed_by_gives_perfect_score(self):
        """Query with 'performed by' should get perfect confidence"""
        query = BookQuery(
            title="The Odyssey",
            author="Homer performed by Ian McKellen"
        )
        meta = BookMeta(
            title="The Odyssey",
            authors=["Homer"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence == 1.0
    
    def test_narrator_voice_gives_perfect_score(self):
        """Query with 'voice' narrator info should get perfect confidence"""
        query = BookQuery(
            title="Pride and Prejudice",
            author="Jane Austen voice Rosamund Pike"
        )
        meta = BookMeta(
            title="Pride and Prejudice",
            authors=["Jane Austen"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence == 1.0


class TestSmartContainmentEditionPatterns:
    """Tests for edition pattern detection in confidence matching"""
    
    def test_edition_unabridged_gives_high_score(self):
        """Query with 'unabridged' should get 0.95 confidence"""
        query = BookQuery(
            title="War and Peace",
            author="Leo Tolstoy Unabridged"
        )
        meta = BookMeta(
            title="War and Peace",
            authors=["Leo Tolstoy"]
        )
        
        confidence = calculate_confidence(query, meta)
        # Edition pattern gets 0.95 (slightly lower than narrator)
        # 0.95 * 0.4 (author weight) + 1.0 * 0.6 (title weight) = 0.98
        assert confidence >= 0.95
    
    def test_edition_full_cast_gives_high_score(self):
        """Query with 'full cast' should get 0.95 confidence"""
        query = BookQuery(
            title="Good Omens",
            author="Neil Gaiman Full Cast Dramatization"
        )
        meta = BookMeta(
            title="Good Omens",
            authors=["Neil Gaiman"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence >= 0.95
    
    def test_edition_annotated_gives_high_score(self):
        """Query with 'annotated' should get 0.95 confidence"""
        query = BookQuery(
            title="Frankenstein",
            author="Mary Shelley Annotated Edition"
        )
        meta = BookMeta(
            title="Frankenstein",
            authors=["Mary Shelley"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence >= 0.95


class TestSmartContainmentFalsePositivePrevention:
    """Tests to ensure smart containment doesn't cause false positives"""
    
    def test_series_collection_not_auto_matched(self):
        """Collection query shouldn't auto-match individual book"""
        query = BookQuery(
            title="Harry Potter Complete Collection",
            author="J.K. Rowling"
        )
        meta = BookMeta(
            title="Harry Potter and the Philosopher's Stone",
            authors=["J.K. Rowling"]
        )
        
        confidence = calculate_confidence(query, meta)
        # Should NOT be 1.0 because title doesn't match exactly
        assert confidence < 0.95, "Collection shouldn't perfectly match individual book"
    
    def test_coauthor_missing_penalized(self):
        """Missing co-author should be penalized"""
        query = BookQuery(
            title="Good Omens",
            author="Neil Gaiman and Terry Pratchett"
        )
        meta = BookMeta(
            title="Good Omens",
            authors=["Neil Gaiman"]  # Missing Terry Pratchett
        )
        
        confidence = calculate_confidence(query, meta)
        # Should be lower than 1.0 because co-author is missing
        # This is NOT a narrator pattern, so fuzzy match applies
        assert confidence < 1.0
    
    def test_unknown_extra_text_uses_fuzzy(self):
        """Unknown extra text should use fuzzy matching, not perfect score"""
        query = BookQuery(
            title="The Art of War",
            author="Sun Tzu translated by Thomas Cleary"
        )
        meta = BookMeta(
            title="The Art of War",
            authors=["Sun Tzu"]
        )
        
        confidence = calculate_confidence(query, meta)
        # "translated by" is NOT in our narrator/edition patterns
        # Should use fuzzy matching
        assert confidence < 1.0 and confidence > 0.5
    
    def test_vague_query_doesnt_overmatch(self):
        """Vague query shouldn't match more specific result"""
        query = BookQuery(
            title="Complete Works",
            author="Shakespeare"
        )
        meta = BookMeta(
            title="Hamlet",
            authors=["William Shakespeare"]
        )
        
        confidence = calculate_confidence(query, meta)
        # "Hamlet" is NOT in "Complete Works" - no substring match
        # Should fuzzy match poorly
        assert confidence < 0.8


class TestSmartContainmentEdgeCases:
    """Edge case tests for smart containment logic"""
    
    def test_empty_author_no_crash(self):
        """Empty author in query shouldn't crash"""
        query = BookQuery(
            title="Some Book",
            author=""
        )
        meta = BookMeta(
            title="Some Book",
            authors=["Author Name"]
        )
        
        confidence = calculate_confidence(query, meta)
        # Should work without crashing
        assert 0.0 <= confidence <= 1.0
    
    def test_no_author_in_query_uses_title_only(self):
        """No author in query should use title-only scoring"""
        query = BookQuery(
            title="The Hobbit",
            author=None
        )
        meta = BookMeta(
            title="The Hobbit",
            authors=["J.R.R. Tolkien"]
        )
        
        confidence = calculate_confidence(query, meta)
        # Should be 1.0 (perfect title match, no author penalty)
        assert confidence == 1.0
    
    def test_exact_match_still_perfect(self):
        """Exact author match should still give perfect score"""
        query = BookQuery(
            title="Foundation",
            author="Isaac Asimov"
        )
        meta = BookMeta(
            title="Foundation",
            authors=["Isaac Asimov"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence == 1.0
    
    def test_multiple_patterns_in_query(self):
        """Query with multiple patterns should still work"""
        query = BookQuery(
            title="Moby Dick",
            author="Herman Melville Unabridged as read by Anthony Heald"
        )
        meta = BookMeta(
            title="Moby Dick",
            authors=["Herman Melville"]
        )
        
        confidence = calculate_confidence(query, meta)
        # Should detect narrator pattern first (higher priority)
        assert confidence == 1.0


class TestSmartContainmentRealWorldCases:
    """Real-world cases from user's actual data"""
    
    def test_user_reported_case_wallace_wattles(self):
        """The exact case user reported: Wallace Wattles with narrator"""
        query = BookQuery(
            title="The Science of getting rich",
            author="Wallace D. Wattles as read by Mike DeWitt"
        )
        meta = BookMeta(
            title="The Science of Getting Rich",
            authors=["Wallace D. Wattles"]
        )
        
        confidence = calculate_confidence(query, meta)
        # Should pass confidence threshold (0.85+)
        assert confidence >= 0.85, f"Should pass threshold, got {confidence}"
        # Should actually be 1.0 with smart containment
        assert confidence == 1.0, "Smart containment should give perfect score"
    
    def test_narrator_with_different_case(self):
        """Case variation shouldn't matter"""
        query = BookQuery(
            title="The 48 Laws of Power",
            author="Robert Greene AS READ BY Richard Poe"
        )
        meta = BookMeta(
            title="The 48 Laws of Power",
            authors=["Robert Greene"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence == 1.0, "Case-insensitive pattern matching"
    
    def test_narrator_with_extra_spaces(self):
        """Extra whitespace shouldn't matter"""
        query = BookQuery(
            title="Sapiens",
            author="Yuval Noah Harari   as  read  by   Derek Perkins"
        )
        meta = BookMeta(
            title="Sapiens",
            authors=["Yuval Noah Harari"]
        )
        
        confidence = calculate_confidence(query, meta)
        assert confidence == 1.0
