
import os
import shutil
import pytest
from src.core.audio_shelf.atf_cleaner import ATFCleaner

@pytest.fixture
def temp_atf_dir(tmp_path):
    """Create a temporary directory structure with .atf files."""
    root = tmp_path / "atf_root"
    root.mkdir()
    
    # Root level file
    (root / "test1.atf").touch()
    (root / "keep.mp3").touch()
    
    # Subdirectory
    sub = root / "subdir"
    sub.mkdir()
    (sub / "test2.atf").touch()
    (sub / "keep2.txt").touch()
    
    # Deep Subdirectory
    deep = sub / "deep"
    deep.mkdir()
    (deep / "test3.ATF").touch() # Case insensitivity check
    
    return root

def test_atf_cleaner_recursive(temp_atf_dir):
    cleaner = ATFCleaner()
    
    # Count before
    atf_files = list(temp_atf_dir.rglob("*.atf")) + list(temp_atf_dir.rglob("*.ATF"))
    assert len(atf_files) == 3
    
    # Run Cleaner
    cleaner.clean_files(str(temp_atf_dir))
    
    # Count after
    remaining_atf = list(temp_atf_dir.rglob("*.atf")) + list(temp_atf_dir.rglob("*.ATF"))
    remaining_others = list(temp_atf_dir.rglob("*"))
    
    # Assertions
    assert len(remaining_atf) == 0, f"Failed to delete ATF files: {remaining_atf}"
    
    # Ensure other files remain (folders exist, so count > 0)
    assert (temp_atf_dir / "keep.mp3").exists()
    assert (temp_atf_dir / "subdir" / "keep2.txt").exists()
