"""
Windows self-update launcher stub.

Built as its own tiny, dependency-free PyInstaller executable
(ShoggothLauncher.exe) that ships alongside Shoggoth.exe inside the same
onedir install folder. It is never the user-facing entry point - the main
app spawns it, right before quitting, only when an update has been staged.

Handoff contract: the main app writes a JSON marker at
`root_dir / "pending_update.json"` (see shoggoth/files.py for root_dir)
before launching this process:

    {
        "staging_dir": "<folder containing the new build's exe + files>",
        "install_dir": "<folder containing the currently running exe>",
        "exe_name": "Shoggoth.exe",
        "version": "0.7.17"
    }

This process then: waits for the main exe to release its file lock, swaps
staging_dir into install_dir's place (atomic rename where possible, with
rollback on failure), cleans up, and relaunches the app. Deliberately
stdlib-only (plus tkinter, also stdlib) so it rarely needs to change - a
running exe can't replace itself, so this file does not get updated by its
own swap logic.
"""
import sys
import json
import time
import shutil
import logging
import subprocess
from pathlib import Path

from shoggoth.files import root_dir

MARKER_PATH = root_dir / "pending_update.json"
LOCK_WAIT_TIMEOUT = 15.0
LOCK_WAIT_INTERVAL = 0.3

logger = logging.getLogger("shoggoth.launcher")


def _setup_logging():
    root_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=root_dir / "launcher.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def _read_marker() -> dict | None:
    if not MARKER_PATH.exists():
        return None
    try:
        return json.loads(MARKER_PATH.read_text())
    except Exception:
        logger.exception("Failed to read pending_update.json")
        return None


def _wait_for_unlock(exe_path: Path) -> bool:
    """Poll until exe_path is no longer held open by the exiting main process."""
    deadline = time.monotonic() + LOCK_WAIT_TIMEOUT
    while time.monotonic() < deadline:
        try:
            with open(exe_path, "r+b"):
                return True
        except OSError:
            time.sleep(LOCK_WAIT_INTERVAL)
    return False


def _swap(staging_dir: Path, install_dir: Path, status_cb=None) -> None:
    """Replace install_dir's contents with staging_dir's, with rollback on failure."""
    old_dir = install_dir.parent / (install_dir.name + "_old")
    if old_dir.exists():
        shutil.rmtree(old_dir, ignore_errors=True)

    if status_cb:
        status_cb("Installing update...")

    install_dir.rename(old_dir)
    try:
        try:
            staging_dir.rename(install_dir)
        except OSError:
            # staging_dir lives on a different volume than install_dir
            # (rename can't cross drives) - fall back to a copy.
            logger.info("Cross-volume rename failed, falling back to copy")
            shutil.copytree(staging_dir, install_dir)
            shutil.rmtree(staging_dir, ignore_errors=True)
    except Exception:
        logger.exception("Swap failed, rolling back")
        if install_dir.exists():
            shutil.rmtree(install_dir, ignore_errors=True)
        old_dir.rename(install_dir)
        raise

    shutil.rmtree(old_dir, ignore_errors=True)


def _show_error(message: str) -> None:
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("Shoggoth Update Failed", message)
        root.destroy()
    except Exception:
        logger.exception("Failed to show error dialog")


class _StatusWindow:
    """Minimal always-on-top status label. No-ops if tkinter is unavailable."""

    def __init__(self, initial_text: str):
        self._root = None
        try:
            import tkinter
            self._root = tkinter.Tk()
            self._root.title("Shoggoth Update")
            self._root.attributes("-topmost", True)
            self._root.resizable(False, False)
            width, height = 360, 80
            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
            x, y = (screen_w - width) // 2, (screen_h - height) // 2
            self._root.geometry(f"{width}x{height}+{x}+{y}")
            self._label = tkinter.Label(self._root, text=initial_text, padx=16, pady=16)
            self._label.pack(expand=True, fill="both")
            self._root.update()
        except Exception:
            logger.exception("Failed to create status window")
            self._root = None

    def set_text(self, text: str):
        logger.info(text)
        if self._root is None:
            return
        try:
            self._label.config(text=text)
            self._root.update()
        except Exception:
            pass

    def close(self):
        if self._root is None:
            return
        try:
            self._root.destroy()
        except Exception:
            pass


def main():
    _setup_logging()
    logger.info("Launcher starting")

    marker = _read_marker()
    if marker is None:
        logger.info("No pending_update.json marker found; nothing to do")
        return

    try:
        staging_dir = Path(marker["staging_dir"])
        install_dir = Path(marker["install_dir"])
        exe_name = marker["exe_name"]
        version = marker.get("version", "")
    except KeyError:
        logger.exception("Malformed pending_update.json")
        MARKER_PATH.unlink(missing_ok=True)
        return

    status = _StatusWindow(f"Updating Shoggoth to v{version}...")

    try:
        if not _wait_for_unlock(install_dir / exe_name):
            raise TimeoutError(f"Timed out waiting for {exe_name} to close")

        if not staging_dir.is_dir():
            raise FileNotFoundError(f"Staged update folder missing: {staging_dir}")

        status.set_text("Installing update...")
        _swap(staging_dir, install_dir, status_cb=status.set_text)

        status.set_text("Restarting Shoggoth...")
        subprocess.Popen([str(install_dir / exe_name)], cwd=str(install_dir))
    except Exception as exc:
        logger.exception("Update install failed")
        status.close()
        _show_error(
            f"Shoggoth couldn't finish installing the update:\n{exc}\n\n"
            "The previous version has been kept. Please try again, or download "
            "the latest release manually from GitHub."
        )
        # Best effort: relaunch whatever is currently in install_dir, even if
        # the update itself failed, so the user isn't left with nothing.
        try:
            if (install_dir / exe_name).exists():
                subprocess.Popen([str(install_dir / exe_name)], cwd=str(install_dir))
        except Exception:
            logger.exception("Failed to relaunch after failed update")
        return
    finally:
        MARKER_PATH.unlink(missing_ok=True)

    status.close()
    logger.info("Update installed and app relaunched successfully")


if __name__ == "__main__":
    main()
