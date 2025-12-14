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
        if not f.read().startswith('0.4.1'):
            return False
    return True


def run():
    os.environ["KIVY_NO_ARGS"] = "1"
    os.environ["KIVY_IMAGE"] = "sdl2, pil"

    parser = argparse.ArgumentParser(description='Shoggoth Card Creator')
    parser.add_argument('-v', '--view', metavar='FILE', help='Open in viewer mode with specified file')
    parser.add_argument('-r', '--render', metavar='FILE', help='Render a specific file directly')
    parser.add_argument('-id', '--card_id', metavar='STRING', help='Only render the card with the given ID.')
    parser.add_argument('-o', '--out', metavar='FOLDER', help='Overwrite the default output folder for --render option.')
    parser.add_argument('-b', '--bleed', metavar='BOOL', help='--render mode option. If set, render will output with bleed.')
    parser.add_argument('-f', '--format', metavar='STRING', help='--render mode option. Should be one of jpeg, png or webp. Other formats might be supported, as per PIL documentation.', default='jpeg')
    parser.add_argument('-re', '--refresh', metavar='FLAG', help='Re-downloads the asset files. Use in case of corrupt asset folder, or in case of new version.')
    args = parser.parse_args()

    # ensure directories exist
    root_dir.mkdir(parents=True, exist_ok=True)

    # ensure assets directory exists
    if args.refresh or not asset_dir.is_dir() or not version_is_up_to_date():
        print("Asset pack not found. Downloading assets...")
        # download assets
        url = 'https://www.dropbox.com/scl/fi/5df6umq75ueexvisgfbr7/assets-0-4-1.zip?rlkey=42nio7o6dssbnis99ul19flhe&st=sqk00lrd&dl=1'
        filehandle, _ = urllib.request.urlretrieve(url)
        with zipfile.ZipFile(filehandle, 'r') as file:
            file.extractall(root_dir)
        print("Assets downloaded successfully.")
    else:
        print("Asset pack up to date.")

    if args.view and args.render:
        print('--view and --render are not compatible options.')

    if args.view:
        # Start in viewer mode
        from shoggoth.viewer import ViewerApp
        app = ViewerApp(args.view)
    elif args.render:
        from time import time
        t = time()
        from shoggoth.renderer import CardRenderer
        from shoggoth.project import Project

        p = Project.load(args.render)
        r = CardRenderer()
        if args.card_id:
            cards = [p.get_card(args.card_id)]
        else:
            cards = p.get_all_cards()

        target_folder = args.out or p.folder
        for card in cards:
            r.export_card_images(card, target_folder, False, bleed=bool(args.bleed), format=args.format, quality=100)
        print(f'Took {time()-t} seconds.')
        return
    else:
        # Start in normal mode
        from shoggoth.main import ShoggothApp
        app = ShoggothApp()
    app.run()


if __name__ == '__main__':
    run()
    print('tool done running')

