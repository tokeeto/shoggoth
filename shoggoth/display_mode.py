"""
Terminal display mode for Shoggoth.

Watches a project file and shows the most recently edited card in the
terminal, rendered with the normal card renderer. Intended for the
external-text-editor workflow: edit the project JSON in your editor and
watch the card update live in a terminal next to it.

Images are drawn with the kitty graphics protocol (kitty, ghostty,
WezTerm, ...) or, as a fallback, piped through chafa if installed.
Set SHOGGOTH_DISPLAY_BACKEND to 'kitty' or 'chafa' to override detection.
"""
import base64
import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
from io import BytesIO
from pathlib import Path

from PIL import Image
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from shoggoth.project import Project
from shoggoth.renderer import CardRenderer

RENDER_SIZE = {'width': 750, 'height': 1050, 'bleed': 36}
FACE_GAP = 24  # pixels between front and back in the composed image
DEBOUNCE_SECONDS = 0.3


# --- terminal helpers -------------------------------------------------------

def _terminal_geometry():
    """Return (cols, rows, cell_width_px, cell_height_px)."""
    try:
        import fcntl
        import termios
        buf = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b'\0' * 8)
        rows, cols, xpix, ypix = struct.unpack('HHHH', buf)
    except (OSError, ImportError, ValueError):
        rows, cols, xpix, ypix = 0, 0, 0, 0
    if not rows or not cols:
        cols, rows = shutil.get_terminal_size()
        xpix = ypix = 0
    # Fall back to a common cell size when the terminal doesn't report pixels
    cell_w = xpix / cols if xpix else 9
    cell_h = ypix / rows if ypix else 18
    return cols, rows, cell_w, cell_h


def detect_backend():
    override = os.environ.get('SHOGGOTH_DISPLAY_BACKEND')
    if override:
        return override
    term = os.environ.get('TERM', '')
    if (os.environ.get('KITTY_WINDOW_ID')
            or 'kitty' in term
            or 'ghostty' in term
            or os.environ.get('TERM_PROGRAM') in ('WezTerm', 'ghostty')):
        return 'kitty'
    if shutil.which('chafa'):
        return 'chafa'
    return 'none'


def _show_kitty(image):
    cols, rows, cell_w, cell_h = _terminal_geometry()
    avail_rows = max(rows - 4, 5)  # leave room for the header and prompt
    scale = min(cols * cell_w / image.width, avail_rows * cell_h / image.height, 1.0)
    c = max(int(image.width * scale / cell_w), 1)
    r = max(int(image.height * scale / cell_h), 1)

    buf = BytesIO()
    image.save(buf, format='PNG')
    payload = base64.standard_b64encode(buf.getvalue())

    out = sys.stdout
    out.write('\x1b_Ga=d,d=A\x1b\\')  # delete previously transmitted images
    first = True
    while payload:
        chunk, payload = payload[:4096], payload[4096:]
        m = 1 if payload else 0
        if first:
            out.write(f'\x1b_Ga=T,f=100,c={c},r={r},m={m};{chunk.decode("ascii")}\x1b\\')
            first = False
        else:
            out.write(f'\x1b_Gm={m};{chunk.decode("ascii")}\x1b\\')
    out.write('\n')
    out.flush()


def _show_chafa(image):
    cols, rows, _, _ = _terminal_geometry()
    with tempfile.NamedTemporaryFile(suffix='.png') as f:
        image.save(f, format='PNG')
        f.flush()
        subprocess.run(['chafa', f'--size={cols}x{max(rows - 4, 5)}', f.name])


def compose_faces(front, back):
    """Place front and back side by side on a dark canvas."""
    height = max(front.height, back.height)
    canvas = Image.new('RGB', (front.width + FACE_GAP + back.width, height), (30, 30, 30))
    for img, x in ((front, 0), (back, front.width + FACE_GAP)):
        mask = img if img.mode == 'RGBA' else None
        canvas.paste(img, (x, (height - img.height) // 2), mask)
    return canvas


# --- display app ------------------------------------------------------------

class DisplayApp(FileSystemEventHandler):
    """Watches the project folder and re-renders the last-edited card."""

    def __init__(self, project_path, card_id=None, backend=None):
        self.project_path = Path(project_path).resolve()
        self.backend = backend or detect_backend()
        self.renderer = CardRenderer()
        self.project = None
        self.current_card_id = card_id
        self.snapshot = {}  # card id -> serialized card entry, for change detection
        self.status = ''
        self._lock = threading.Lock()
        self._timer = None

    # -- project loading and change detection --

    def load_project(self):
        """(Re)load the project from disk. Returns False if the file is unreadable
        (e.g. a half-written save), keeping the previous state."""
        try:
            with open(self.project_path, 'r') as f:
                data = json.load(f)
            project = Project(self.project_path, data)
        except Exception as e:
            self.status = f'waiting for a valid save ({e.__class__.__name__})'
            return False
        self.project = project
        return True

    def _take_snapshot(self):
        return {
            entry['id']: json.dumps(entry, sort_keys=True)
            for entry in self.project.data.get('cards', [])
            if entry.get('id')
        }

    def reload(self):
        """Reload the project, switch to the card that changed, re-render."""
        with self._lock:
            if not self.load_project():
                self._print_header()
                return
            new_snapshot = self._take_snapshot()
            changed = [
                card_id for card_id, serialized in new_snapshot.items()
                if self.snapshot.get(card_id) != serialized
            ]
            self.snapshot = new_snapshot
            if changed:
                self.current_card_id = changed[0]
            elif self.current_card_id not in new_snapshot:
                self.current_card_id = None  # current card was deleted
            self._render_current()

    def rerender_images(self):
        """An image file changed on disk: drop cached pixels and re-render."""
        with self._lock:
            self.renderer.invalidate_cache()
            self.renderer.clear_illustration_caches()
            self._render_current()

    # -- rendering --

    def _current_card(self):
        if self.project is None:
            return None
        if self.current_card_id:
            card = self.project.get_card(self.current_card_id)
            if card:
                return card
        cards = self.project.cards
        return cards[0] if cards else None

    def _print_header(self, card=None):
        sys.stdout.write('\x1b[2J\x1b[H')  # clear screen, home cursor
        name = f'{card.name}' if card else '(no card)'
        stamp = time.strftime('%H:%M:%S')
        print(f'shoggoth display · {self.project.name if self.project else self.project_path.name}'
              f' · {name} · {stamp} · ctrl+c to quit')
        if self.status:
            print(self.status)

    def _render_current(self):
        card = self._current_card()
        if card is None:
            self.status = 'project has no cards yet'
            self._print_header()
            return
        try:
            front, back = self.renderer.get_card_textures(card, RENDER_SIZE, bleed=False)
            image = compose_faces(front, back)
            self.status = ''
        except Exception as e:
            self.status = f'render failed: {e}'
            self._print_header(card)
            return
        self._print_header(card)
        if self.backend == 'kitty':
            _show_kitty(image)
        else:
            _show_chafa(image)

    def render_now(self):
        with self._lock:
            self._render_current()

    # -- watchdog events --

    def on_any_event(self, event):
        if event.is_directory:
            return
        paths = {getattr(event, 'src_path', None), getattr(event, 'dest_path', None)}
        paths.discard(None)
        if str(self.project_path) in paths:
            self._schedule(self.reload)
        elif any(Path(p).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.svg', '.pdf')
                 for p in paths):
            self._schedule(self.rerender_images)

    def _schedule(self, action):
        """Debounce bursts of filesystem events (editors save via tmp+rename)."""
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(DEBOUNCE_SECONDS, action)
        self._timer.daemon = True
        self._timer.start()


def run_display_mode(project_path, card_id=None):
    app = DisplayApp(project_path, card_id=card_id)

    if app.backend == 'none':
        print('No image-capable terminal detected and chafa is not installed.')
        print('Use kitty/ghostty/WezTerm, or install chafa, or set SHOGGOTH_DISPLAY_BACKEND.')
        return 1
    if app.backend == 'chafa' and not shutil.which('chafa'):
        print('chafa backend selected but the chafa binary was not found on PATH.')
        return 1

    if not app.load_project():
        print(f'Could not load project: {project_path}')
        return 1
    app.snapshot = app._take_snapshot()
    app.render_now()

    # Redraw to fit when the terminal is resized
    signal.signal(signal.SIGWINCH, lambda *_: app.render_now())

    observer = Observer()
    observer.schedule(app, str(app.project_path.parent), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
    return 0
