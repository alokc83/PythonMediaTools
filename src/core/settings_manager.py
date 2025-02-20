import json
import os
from pathlib import Path

class SettingsManager:
    def __init__(self):
        self.settings_file = Path.home() / '.pmt' / 'settings.json'
        self.settings = self.load_settings()
    
    def load_settings(self):
        default_settings = {
            'google_api_key': '',
            'last_source_dir': '',
            'last_dest_dir': ''
        }
        
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    return {**default_settings, **json.load(f)}
            return default_settings
        except Exception:
            return default_settings
    
    def save_settings(self):
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def get(self, key, default=None):
        return self.settings.get(key, default)
    
    def set(self, key, value):
        self.settings[key] = value
        self.save_settings() 