import os
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
logging.getLogger('watchdog').setLevel(logging.WARNING)


class CardFileHandler(FileSystemEventHandler):
    """File system event handler for card files"""

    def __init__(self, callback, monitored_files=None, always_trigger_dirs=None):
        super(CardFileHandler, self).__init__()
        self.callback = callback
        self.monitored_files = monitored_files or set()
        self.always_trigger_dirs = always_trigger_dirs or set()  # Always trigger for files in these dirs
        self.last_modified = {}

    def on_modified(self, event):
        """When a file is modified"""
        if event.is_directory:
            return

        # Normalize the path for comparison
        src_path = str(Path(event.src_path).resolve())

        # Check if we should trigger the callback
        should_trigger = False

        # Always trigger for files in always_trigger_dirs (e.g., asset directory)
        for trigger_dir in self.always_trigger_dirs:
            if src_path.startswith(trigger_dir):
                should_trigger = True
                break

        # Also trigger for specifically monitored files (e.g., card illustrations)
        if not should_trigger and src_path in self.monitored_files:
            should_trigger = True

        if should_trigger:
            # Add a small delay to avoid multiple reload triggers
            current_time = time.time()
            last_time = self.last_modified.get(src_path, 0)

            if current_time - last_time > 0.5:
                self.last_modified[src_path] = current_time
                self.callback(src_path)


class FileMonitor:
    """Monitors files for changes"""

    def __init__(self, directory_path, callback):
        self.directory_path = directory_path
        self.callback = callback
        self.observer = None
        self.monitored_files = set()

    def start(self):
        """Start monitoring files"""
        if self.observer:
            self.stop()

        self.observer = Observer()
        handler = CardFileHandler(self.callback, self.monitored_files)

        # Monitor the directory
        if os.path.exists(self.directory_path):
            self.observer.schedule(handler, self.directory_path, recursive=True)
            self.observer.start()

    def stop(self):
        """Stop monitoring files"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None

    def add_file(self, file_path):
        """Add a file to monitor"""
        if file_path and os.path.exists(file_path):
            self.monitored_files.add(str(Path(file_path).resolve()))

    def remove_file(self, file_path):
        """Remove a file from monitoring"""
        normalized = str(Path(file_path).resolve())
        if normalized in self.monitored_files:
            self.monitored_files.remove(normalized)

    def clear_files(self):
        """Clear all monitored files"""
        self.monitored_files.clear()


class CardFileMonitor:
    """
    Monitors files relevant to the current card for changes.

    This includes:
    - Asset directory (templates, overlays, fonts, icons)
    - Illustration files specified by the current card
    """

    def __init__(self, asset_dir, callback):
        self.asset_dir = str(asset_dir)
        self.callback = callback
        self.observer = None
        self.handler = None
        self.card_files = set()  # Files specific to current card
        self._watched_dirs = set()  # Extra directories being watched

    def start(self):
        """Start monitoring"""
        if self.observer:
            self.stop()

        self.observer = Observer()
        # Pass asset_dir as always_trigger_dirs so all asset changes trigger callback
        self.handler = CardFileHandler(
            self._on_change,
            self.card_files,
            always_trigger_dirs={self.asset_dir}
        )

        # Always watch the asset directory
        if os.path.exists(self.asset_dir):
            self.observer.schedule(self.handler, self.asset_dir, recursive=True)

        self.observer.start()

    def stop(self):
        """Stop monitoring"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.handler = None
            self._watched_dirs.clear()

    def _on_change(self, file_path):
        """Internal handler that forwards to the callback"""
        self.callback(file_path)

    def set_card_files(self, files):
        """
        Update the set of card-specific files to monitor.

        Args:
            files: Iterable of file paths to monitor
        """
        self.card_files.clear()
        new_dirs = set()

        for file_path in files:
            if file_path and os.path.exists(file_path):
                resolved = str(Path(file_path).resolve())
                self.card_files.add(resolved)

                # Track the parent directory
                parent_dir = str(Path(resolved).parent)
                if parent_dir != self.asset_dir and not parent_dir.startswith(self.asset_dir):
                    new_dirs.add(parent_dir)

        # Update watched directories if observer is running
        if self.observer and self.handler:
            # Add new directories that aren't already watched
            for dir_path in new_dirs - self._watched_dirs:
                if os.path.exists(dir_path):
                    try:
                        self.observer.schedule(self.handler, dir_path, recursive=False)
                    except Exception as e:
                        logging.warning(f"Could not watch directory {dir_path}: {e}")

            self._watched_dirs = new_dirs

        # Update the handler's monitored files
        if self.handler:
            self.handler.monitored_files = self.card_files

    def get_card_file_dependencies(self, card):
        """
        Extract all file dependencies from a card.

        Args:
            card: Card object to extract dependencies from

        Returns:
            Set of file paths that the card depends on
        """
        files = set()

        for face in (card.front, card.back):
            # Illustration file
            illustration = face.get('illustration')
            if illustration:
                files.add(illustration)

            # Template files are in the asset dir, so no need to track separately

        return files
