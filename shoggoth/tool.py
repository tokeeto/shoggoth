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
        if not f.read().startswith('0.3.0'):
            return False
    return True

def run():
    os.environ["KIVY_NO_ARGS"] = "1"
    os.environ["KIVY_IMAGE"] = "sdl2, pil"

    parser = argparse.ArgumentParser(description='Shoggoth Card Creator')
    parser.add_argument('-v', '--view', metavar='FILE', help='Open in viewer mode with specified file')
    args = parser.parse_args()

    # ensure directories exist
    root_dir.mkdir(parents=True, exist_ok=True)

    # ensure assets directory exists
    if not asset_dir.is_dir() or not version_is_up_to_date():
        print("Asset pack not found. Downloading assets...")
        # download assets
        url = 'https://www.dropbox.com/scl/fi/x6zkehc27bhd0epvma9ha/assets-0-3-0.zip?rlkey=o0fdiku3pcr7glrnvcmr0zepp&st=tis0yugs&dl=1'
        filehandle, _ = urllib.request.urlretrieve(url)
        with zipfile.ZipFile(filehandle, 'r') as file:
            file.extractall(root_dir)
        print("Assets downloaded successfully.")
    else:
        print("Asset pack up to date.")

    if args.view:
        # Start in viewer mode
        from shoggoth.viewer import ViewerApp
        app = ViewerApp(args.view)
    else:
        # Start in normal mode
        from shoggoth.main import ShoggothApp
        app = ShoggothApp()
    app.run()


if __name__ == '__main__':
    run()

print('tool done running')
