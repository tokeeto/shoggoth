import argparse
import os
from shoggoth.files import asset_dir, root_dir
import urllib.request
import zipfile


def version_is_up_to_date() -> bool:
    """ Parses the asset pack version """
    if not (asset_dir/'version.txt').exists():
        return False
    with (asset_dir/'version.txt').open('r') as f:
        if not f.read().startswith('0.1.0'):
            return False
    return True

def run():
    os.environ["KIVY_NO_ARGS"] = "1"

    parser = argparse.ArgumentParser(description='Shoggoth Card Creator')
    parser.add_argument('-v', '--view', metavar='FILE', help='Open in viewer mode with specified file')
    args = parser.parse_args()

    # ensure directories exist
    root_dir.mkdir(parents=True, exist_ok=True)

    # ensure assets directory exists
    if not asset_dir.is_dir() or not version_is_up_to_date():
        print("Asset pack not found. Downloading assets...")
        # download assets
        url = 'https://www.dropbox.com/scl/fi/pp70yhzu7saqhhnd7xtb0/assets.zip?rlkey=ln16n1glarlb2z46af52mu2rd&st=ei2gh4t3&dl=1'
        filehandle, _ = urllib.request.urlretrieve(url)
        with zipfile.ZipFile(filehandle, 'r') as file:
            file.extractall(root_dir)
        print("Assets downloaded successfully.")

    if args.view:
        # Start in viewer mode
        from shoggoth.viewer import ViewerApp
        app = ViewerApp(args.view)
    else:
        # Start in normal mode
        from shoggoth.main import ShoggothApp
        app = ShoggothApp()
    app.run()
