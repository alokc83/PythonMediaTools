import os
import shutil
import tempfile
import pytest
from src.core.empty_cleaner import JunkCleaner

@pytest.fixture
def temp_dir():
    # Create temp structure
    # root/
    #   notes.txt (Junk) -> DELETE (No audio)
    #   folder_empty/ (Empty) -> DELETE
    #   folder_junk_only/
    #     cover.jpg (Junk) -> DELETE
    #     info.nfo (Junk) -> DELETE
    #   folder_mixed/ (Audio Safe)
    #     track.m4a (Audio)
    #     log.txt (Junk) -> KEEP
    #   folder_nested/
    #     sub_empty/ -> DELETE
    
    d = tempfile.mkdtemp()
    
    # Root files
    # REMOVED audio.mp3 from root to allow testing of root deletion
    with open(os.path.join(d, "notes.txt"), "w") as f: f.write("x")
    
    # Empty folder
    os.makedirs(os.path.join(d, "folder_empty"))
    
    # Junk only folder
    p = os.path.join(d, "folder_junk_only")
    os.makedirs(p)
    with open(os.path.join(p, "cover.jpg"), "w") as f: f.write("x")
    with open(os.path.join(p, "info.nfo"), "w") as f: f.write("x")
    
    # Mixed folder
    p = os.path.join(d, "folder_mixed")
    os.makedirs(p)
    with open(os.path.join(p, "track.m4a"), "w") as f: f.write("x")
    with open(os.path.join(p, "log.txt"), "w") as f: f.write("x")
    
    # Nested empty
    p = os.path.join(d, "folder_nested", "sub_empty")
    os.makedirs(p)
    
    yield d
    shutil.rmtree(d)

def test_scan_logic(temp_dir):
    cleaner = JunkCleaner()
    junk_exts = {".txt", ".nfo", ".jpg"}
    
    ops = cleaner.scan_directory(temp_dir, junk_exts)
    
    # Debug print
    for op in ops:
        print(f"OP: {op}")
        
    ops_paths = [op[1] for op in ops]
    
    # Assertions
    
    # 1. Files to delete
    # notes.txt (root) - Should delete now (no audio in root)
    assert os.path.join(temp_dir, "notes.txt") in ops_paths
    
    # cover.jpg, info.nfo (folder_junk_only)
    assert os.path.join(temp_dir, "folder_junk_only", "cover.jpg") in ops_paths
    assert os.path.join(temp_dir, "folder_junk_only", "info.nfo") in ops_paths
    
    # log.txt (folder_mixed) - Should KEEP because track.m4a exists
    assert os.path.join(temp_dir, "folder_mixed", "log.txt") not in ops_paths
    
    # 2. Folders to delete
    # folder_empty (was empty start)
    assert os.path.join(temp_dir, "folder_empty") in ops_paths
    # folder_junk_only (becomes empty after junk deleted)
    assert os.path.join(temp_dir, "folder_junk_only") in ops_paths
    # folder_nested/sub_empty
    assert os.path.join(temp_dir, "folder_nested", "sub_empty") in ops_paths
    # folder_nested (becomes empty after sub_empty deleted)
    assert os.path.join(temp_dir, "folder_nested") in ops_paths
    
    # 3. Items KEPT
    # folder_mixed (contains audio.mp3)
    assert os.path.join(temp_dir, "folder_mixed") not in ops_paths

def test_execution(temp_dir):
    cleaner = JunkCleaner()
    junk_exts = {".txt", ".nfo", ".jpg"}
    
    ops = cleaner.scan_directory(temp_dir, junk_exts)
    cleaner.execute_operations(ops)
    
    # Verify Physical State
    assert not os.path.exists(os.path.join(temp_dir, "notes.txt")) # Deleted
    # assert os.path.exists(os.path.join(temp_dir, "audio.mp3")) # Removed from fixture
    
    assert not os.path.exists(os.path.join(temp_dir, "folder_empty"))
    assert not os.path.exists(os.path.join(temp_dir, "folder_junk_only"))
    
    assert os.path.exists(os.path.join(temp_dir, "folder_mixed"))
    assert os.path.exists(os.path.join(temp_dir, "folder_mixed", "log.txt")) # Kept (Safeguard)
    assert os.path.exists(os.path.join(temp_dir, "folder_mixed", "track.m4a"))
    
    assert not os.path.exists(os.path.join(temp_dir, "folder_nested"))

def test_audio_safeguard(temp_dir):
    # Setup: Create a folder with Audio + Junk
    # logic should PRESERVE the junk because audio exists.
    
    safeguard_path = os.path.join(temp_dir, "folder_safeguard")
    os.makedirs(safeguard_path)
    with open(os.path.join(safeguard_path, "song.mp3"), "w") as f: f.write("x")
    with open(os.path.join(safeguard_path, "cover.jpg"), "w") as f: f.write("x") # Junk
    
    cleaner = JunkCleaner()
    junk_exts = {".jpg"}
    
    ops = cleaner.scan_directory(temp_dir, junk_exts)
    ops_paths = [op[1] for op in ops]
    
    # Assertions
    # cover.jpg in safeguard folder should NOT be invalid (should NOT be deleted)
    assert os.path.join(safeguard_path, "cover.jpg") not in ops_paths
    
    # folder_safeguard should NOT be deleted (it still has audio and cover)
    assert os.path.join(temp_dir, "folder_safeguard") not in ops_paths
    
    # But other folders (folder_junk_only) SHOULD still be cleaned
    # (Checking if existing logic still works elsewhere)
    assert os.path.join(temp_dir, "folder_junk_only", "cover.jpg") in ops_paths
