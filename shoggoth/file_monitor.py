import os
import time
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
#logging.getLogger('watchdog').setLevel(logging.WARNING)


class CardFileHandler(FileSystemEventHandler):
    """File system event handler for card files"""

    def __init__(self, callback, monitored_files=None):
        super(CardFileHandler, self).__init__()
        self.callback = callback
        self.monitored_files = monitored_files or []
        self.last_modified = {}

    def on_modified(self, event):
        """When a file is modified"""
        if event.is_directory:
            return

        if not self.monitored_files or event.src_path in self.monitored_files:
            # Add a small delay to avoid multiple reload triggers
            current_time = time.time()
            last_time = self.last_modified.get(event.src_path, 0)

            if current_time - last_time > 0.5:
                self.last_modified[event.src_path] = current_time
                self.callback(event.src_path)

class FileMonitor:
    """Monitors files for changes"""

    def __init__(self, project_path, callback):
        self.project_path = project_path
        self.callback = callback
        self.observer = None
        self.monitored_files = set()

    def start(self):
        """Start monitoring files"""
        if self.observer:
            self.stop()

        self.observer = Observer()
        handler = CardFileHandler(self.callback, self.monitored_files)

        # Monitor the entire project directory
        self.observer.schedule(handler, self.project_path, recursive=True)
        self.observer.start()

    def stop(self):
        """Stop monitoring files"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None

    def add_file(self, file_path):
        """Add a file to monitor"""
        if os.path.exists(file_path):
            self.monitored_files.add(file_path)

    def remove_file(self, file_path):
        """Remove a file from monitoring"""
        if file_path in self.monitored_files:
            self.monitored_files.remove(file_path)
