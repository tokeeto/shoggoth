from pathlib import Path
from platformdirs import PlatformDirs
import os
import platform
import shoggoth

dirs = PlatformDirs("Shoggoth", "Shoggoth")
root_dir = Path(dirs.user_data_dir)

asset_dir = root_dir / "assets"
defaults_dir = asset_dir / "defaults"
font_dir = asset_dir / "fonts"
overlay_dir = asset_dir / "overlays"
template_dir = asset_dir / "templates"
icon_dir = asset_dir / "icons"
guide_dir = asset_dir / "guide"
tts_dir = None

# TTS Output folder
if platform.system() == "Windows":
    tts_dir = Path(os.environ["USERPROFILE"]) / "Documents" / "My Games" / "Tabletop Simulator" / "Saves" / "Saved Objects"
else:
    tts_dir = Path(os.path.expanduser("~"))/"Library"/"Tabletop Simulator"/"Saves"/"Saved Objects"
    if not tts_dir.exists():
        tts_dir = Path(os.path.expanduser("~"))/".local"/"share"/"Tabletop Simulator"/"Saves"/"Saved Objects"

# fallback
if not tts_dir.exists():
    tts_dir = None


def get_last_path(id:str) -> Path:
    """ Returns the last path used in finding a given resource. """
    if shoggoth.app.storage.exists('last_paths'):
        last_paths = shoggoth.app.storage.get('last_paths')
    else:
        last_paths = {}

    if id not in last_paths:
        return Path.home()
    return Path(last_paths[id])


def set_last_path(id:str, path:Path|str):
    """ Sets the last path used in finding a given resource. """
    if shoggoth.app.storage.exists('last_paths'):
        last_paths = shoggoth.app.storage.get('last_paths')
    else:
        last_paths = {}

    last_paths[id] = str(path)
    shoggoth.app.storage.put('last_paths', **last_paths)
