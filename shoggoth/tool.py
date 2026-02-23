import logging
import argparse
import multiprocessing
from shoggoth.files import asset_dir, root_dir
import urllib.request
import zipfile
from os import makedirs


logger = logging.getLogger('shoggoth')
log_file = root_dir / 'session.log'
if not log_file.exists():
    makedirs(root_dir, exist_ok=True)
logging.basicConfig(filename=log_file, level=logging.INFO)


def version_is_up_to_date() -> bool:
    """ Parses the asset pack version """
    if not (asset_dir / 'version.txt').exists():
        return False
    with (asset_dir / 'version.txt').open('r') as f:
        if not f.read().startswith('1.0.0'):
            return False
    return True


def run():
    # Required for multiprocessing to work with frozen executables (PyInstaller on Windows)
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description='Shoggoth Card Creator')
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
        logger.info("Asset pack not found. Downloading assets...")
        # download assets
        url = 'https://www.dropbox.com/scl/fi/6430x09x1ex7oh05qsr9j/assets-1-0-0.zip?rlkey=un15ovgndos0xf0z6bw53etc0&st=3cqmhex5&dl=1'
        filehandle, _ = urllib.request.urlretrieve(url)
        with zipfile.ZipFile(filehandle, 'r') as file:
            file.extractall(root_dir)
        logger.info("Assets downloaded successfully.")
    else:
        logger.info("Asset pack up to date.")

    if args.render:
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
        logger.info(f'Tool.render took {time()-t} seconds.')
        return
    else:
        # Start in normal mode
        from shoggoth.main_qt import main
        main()


if __name__ == '__main__':
    logger.debug('tool main starting')
    run()
    logger.debug('tool main ending')