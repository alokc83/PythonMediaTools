"""
Tests for language detection in metadata merging.
Ensures non-English descriptions are properly rejected.
"""

import pytest
from src.core.audio_shelf.tagger import merge_metadata, BookMeta


class TestEnglishLanguageDetection:
    """Tests for is_likely_english() heuristic"""
    
    def test_indonesian_description_detected(self):
        """Indonesian description should be rejected"""
        primary = BookMeta(
            title="Ego Is the Enemy",
            authors=["Ryan Holiday"],
            source="audnexus",
            description="Buku yang Anda pegang saat ini ditulis dengan satu asumsi optimis: Ego Anda bukanlah kekuatan yang harus Anda puaskan pada setiap kesempatan."
        )
        secondary = BookMeta(
            title="Ego Is the Enemy",
            authors=["Ryan Holiday"],
            source="english_source",
            description="The obstacle is the way. This book teaches you to turn adversity into advantage."
        )
        
        merged = merge_metadata(primary, secondary)
        
        # Should use English description from secondary, not Indonesian from primary
        assert "The obstacle" in merged.description
        assert "Buku yang Anda" not in merged.description
    
    def test_spanish_description_detected(self):
        """Spanish description should be rejected"""
        primary = BookMeta(
            title="Test Book",
            authors=["Author"],
            source="spanish_source",
            description="El libro que usted está leyendo ahora fue escrito para ayudarle a comprender."
        )
        secondary = BookMeta(
            title="Test Book",
            authors=["Author"],
            source="english_source",
            description="This book will help you understand the key concepts."
        )
        
        merged = merge_metadata(primary, secondary)
        
        # Should use English description
        assert "This book will help" in merged.description
        assert "El libro que" not in merged.description
    
    def test_french_description_detected(self):
        """French description should be rejected"""
        primary = BookMeta(
            title="Test Book",
            authors=["Author"],
            source="french_source",
            description="Le livre que vous tenez maintenant est écrit pour vous aider."
        )
        secondary = BookMeta(
            title="Test Book",
            authors=["Author"],
            source="english_source",
            description="The book you are now holding was written to help you."
        )
        
        merged = merge_metadata(primary, secondary)
        
        # Should use English description
        assert "The book you are now holding" in merged.description
        assert "Le livre que vous" not in merged.description
    
    def test_english_description_preferred_when_both_available(self):
        """When both are English, should prefer longer one"""
        short_english = "Short description."
        long_english = "This is a much longer English description with significantly more content that provides detailed information about the book and its themes."
        
        primary = BookMeta(
            title="Test Book",
            authors=["Author"],
            source="source1",
            description=short_english
        )
        secondary = BookMeta(
            title="Test Book",
            authors=["Author"],
            source="source2",
            description=long_english
        )
        
        merged = merge_metadata(primary, secondary)
        
        # Should use longer English description
        assert merged.description == long_english
    
    def test_english_description_kept_over_longer_non_english(self):
        """Short English description should be preferred over longer non-English"""
        english_desc = "This is a relatively short English description."
        indonesian_desc = "Buku yang Anda pegang saat ini ditulis dengan satu asumsi optimis dan sangat panjang: Ego Anda bukanlah kekuatan yang harus Anda puaskan pada setiap kesempatan dengan cara yang berbeda-beda."
        
        primary = BookMeta(
            title="Test Book",
            authors=["Author"],
            source="english_source",
            description=english_desc
        )
        secondary = BookMeta(
            title="Test Book",
            authors=["Author"],
            source="indonesian_source",
            description=indonesian_desc
        )
        
        merged = merge_metadata(primary, secondary)
        
        # Should keep shorter English over longer Indonesian
        assert merged.description == english_desc


class TestLanguageDetectionEdgeCases:
    """Edge case tests for language detection"""
    
    def test_very_short_description_accepted(self):
        """Very short descriptions (< 10 chars) should be accepted as valid"""
        primary = BookMeta(
            title="Test",
            authors=["Author"],
            source="source1",
            description="Short"
        )
        secondary = BookMeta(
            title="Test",
            authors=["Author"],
            source="source2",
            description=""
        )
        
        merged = merge_metadata(primary, secondary)
        
        # Should accept short description
        assert merged.description == "Short"
    
    def test_empty_descriptions_handled(self):
        """Empty descriptions should be handled gracefully"""
        primary = BookMeta(
            title="Test",
            authors=["Author"],
            source="source1",
            description=""
        )
        secondary = BookMeta(
            title="Test",
            authors=["Author"],
            source="source2",
            description="Valid English description"
        )
        
        merged = merge_metadata(primary, secondary)
        
        # Should use available description
        assert merged.description == "Valid English description"
    
    def test_mixed_language_with_english_keywords(self):
        """Text with English keywords but mostly non-English should be rejected"""
        # Real-world case: Indonesian text starting with "Buku yang Anda"
        mixed_desc = "Buku yang Anda pegang is a book about success and achievement."
        
        primary = BookMeta(
            title="Test",
            authors=["Author"],
            source="mixed_source",
            description=mixed_desc
        )
        secondary = BookMeta(
            title="Test",
            authors=["Author"],
            source="english_source",
            description="A book about success and achievement in business."
        )
        
        merged = merge_metadata(primary, secondary)
        
        # Should reject mixed description with Indonesian marker
        assert "Buku yang Anda" not in merged.description
        assert "A book about success" in merged.description


class TestRealWorldCases:
    """Real-world cases from actual data"""
    
    def test_user_reported_ego_is_enemy_case(self):
        """The exact Indonesian description case user reported"""
        audnexus_desc = "Some description from Audnexus in English." # Audnexus is usually English
        google_indonesian = "Buku yang Anda pegang saat ini ditulis dengan satu asumsi optimis: Ego Anda bukanlah kekuatan yang harus Anda puaskan pada setiap kesempatan. Ego dapat diatur."
        
        primary = BookMeta(
            title="Ego Is the Enemy",
            authors=["Ryan Holiday"],
            source="aud nexus",
            description=audnexus_desc
        )
        secondary = BookMeta(
            title="Ego Is the Enemy",
            authors=["Ryan Holiday"],
            source="google_books",
            description=google_indonesian
        )
        
        merged = merge_metadata(primary, secondary)
        
        # Should reject Indonesian from Google Books, keep English from Audnexus
        assert merged.description == audnexus_desc
        assert "Buku yang Anda" not in merged.description
