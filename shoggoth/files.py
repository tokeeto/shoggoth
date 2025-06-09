from pathlib import Path
from platformdirs import PlatformDirs

dirs = PlatformDirs("Shoggoth", "Shoggoth")
root_dir = Path(dirs.user_data_dir)

asset_dir = root_dir / "assets"
defaults_dir = asset_dir / "defaults"
font_dir = asset_dir / "fonts"
overlay_dir = asset_dir / "overlays"
template_dir = asset_dir / "templates"
icon_dir = asset_dir / "icons"
