import os
import json
import base64
from typing import Dict, Optional, Tuple

class ATFHandler:
    """
    Handles reading and writing of .atf (Auto Toolbox File) files.
    Format:
    Line 1: STATUS (SUCCESS, METADATA_NOT_FOUND, LOW_CONFIDENCE)
    Line 2+: JSON payload with metadata and base64 cover
    """
    
    @staticmethod
    def get_atf_path(directory: str) -> Optional[str]:
        """Finds the first .atf file in the directory."""
        if not os.path.exists(directory):
            return None
        
        for f in os.listdir(directory):
            if f.endswith(".atf"):
                return os.path.join(directory, f)
        return None

    @staticmethod
    def read_atf(directory: str) -> Tuple[str, Dict]:
        """
        Reads the .atf file in the directory.
        Returns (status, data_dict).
        Status is None if no file found or error.
        """
        path = ATFHandler.get_atf_path(directory)
        if not path:
            return None, {}

        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    return None, {}
                
                status = lines[0].strip()
                json_content = "".join(lines[1:])
                data = {}
                if json_content.strip():
                    data = json.loads(json_content)
                
                return status, data
        except Exception as e:
            print(f"Error reading ATF: {e}")
            return None, {}

    @staticmethod
    def write_atf(directory: str, filename_base: str, status: str, metadata: Dict = None, cover_bytes: bytes = None):
        """
        Writes an .atf file.
        filename_base: usually the book title.
        """
        if metadata is None:
            metadata = {}

        # Sanitize filename
        safe_name = "".join([c for c in filename_base if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
        filename = f"{safe_name}.atf"
        path = os.path.join(directory, filename)

        # Prepare data
        data_to_write = metadata.copy()
        
        # Convert cover to base64 if provided
        if cover_bytes:
            try:
                b64_cover = base64.b64encode(cover_bytes).decode('utf-8')
                data_to_write['cover_base64'] = b64_cover
            except Exception as e:
                print(f"Failed to encode cover: {e}")

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(f"{status}\n")
                json.dump(data_to_write, f, indent=4)
        except Exception as e:
            print(f"Error writing ATF: {e}")
