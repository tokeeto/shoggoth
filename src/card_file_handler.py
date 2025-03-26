from watchdog.events import FileSystemEventHandler
import time

class CardFileHandler(FileSystemEventHandler):
    def __init__(self, card_renderer):
        super().__init__()
        self.card_renderer = card_renderer
        self.last_modified = 0

    def on_modified(self, event):
        if not event.is_directory and event.src_path == self.card_renderer.file_path:
            # Add a small delay to avoid multiple reload triggers
            current_time = time.time()
            if current_time - self.last_modified > 0.5:
                self.last_modified = current_time
                self.card_renderer.load_and_render_card()
