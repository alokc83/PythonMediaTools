
import os
import shutil

class ATFCleaner:
    def __init__(self):
        pass

    def clean_files(self, directory: str, log_callback=None):
        """
        Recursively deletes all .atf files in the given directory.
        """
        def log(msg):
            if log_callback:
                log_callback(msg)

        if not os.path.isdir(directory):
            log("Error: Valid directory is required.")
            return

        log(f"Starting ATF Clean in: {directory}")
        
        found_count = 0
        deleted_count = 0
        error_count = 0

        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(".atf"):
                    found_count += 1
                    path = os.path.join(root, file)
                    try:
                        os.remove(path)
                        log(f"Deleted: {file}")
                        deleted_count += 1
                    except Exception as e:
                        log(f"Error deleting {file}: {e}")
                        error_count += 1
        
        log("-" * 40)
        log(f"Completed.")
        log(f"Found: {found_count}")
        log(f"Deleted: {deleted_count}")
        if error_count > 0:
            log(f"Errors: {error_count}")
