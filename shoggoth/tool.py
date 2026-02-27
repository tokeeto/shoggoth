import logging
import argparse
import multiprocessing
from shoggoth.files import asset_dir, root_dir
from shoggoth.settings import EXPORT_SIZES
from shoggoth import updater
from os import makedirs


logger = logging.getLogger('shoggoth')
log_file = root_dir / 'session.log'
if not log_file.exists():
    makedirs(root_dir, exist_ok=True)
logging.basicConfig(filename=log_file, level=logging.INFO)


def run():
    # Required for multiprocessing to work with frozen executables (PyInstaller on Windows)
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description='Shoggoth Card Creator')
    parser.add_argument('-r', '--render', metavar='FILE', help='Render a specific file directly')
    parser.add_argument('-id', '--card_id', metavar='STRING', help='Only render the card with the given ID.')
    parser.add_argument('-o', '--out', metavar='FOLDER', help='Overwrite the default output folder for --render option.')
    parser.add_argument('-b', '--bleed', metavar='BOOL', help='--render mode option. If set, render will output with bleed.')
    parser.add_argument('-f', '--format', metavar='STRING', help='--render mode option. Should be one of jpeg, png or webp. Other formats might be supported, as per PIL documentation.', default='jpeg')
    parser.add_argument('-s', '--size', metavar='INT', type=int, help='--render mode option. Should be one of 0, 1 or 2, for either full, half or quater resolution.', default=0)
    parser.add_argument('-re', '--refresh', metavar='FLAG', help='Re-downloads the asset files. Use in case of corrupt asset folder, or in case of new version.')
    parser.add_argument('--test', help='Runs the test case, and exports the text project.', action='store_true')
    args = parser.parse_args()

    # ensure directories exist
    root_dir.mkdir(parents=True, exist_ok=True)

    # ensure assets directory exists
    if args.refresh:
        (asset_dir / updater.ASSETS_STATE_FILE).unlink(missing_ok=True)
    updater.ensure_assets_current()

    # flag for using shoggoth as a cli tool
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
            r.export_card_images(
                card,
                target_folder,
                EXPORT_SIZES[args.size][1],
                False,
                bleed=bool(args.bleed),
                format=args.format,
                quality=100
            )
        logger.info(f'Tool.render took {time()-t} seconds.')
        return

    # run the test cases
    if args.test:
        from time import time
        t = time()
        from shoggoth.renderer import CardRenderer
        from shoggoth.project import Project

        p = Project.load('./test_case/test_case.json')
        r = CardRenderer()
        if args.card_id:
            cards = [p.get_card(args.card_id)]
        else:
            cards = p.get_all_cards()

        target_folder = args.out or p.folder

        import threading
        threads = []
        for card in cards:
            # Export in thread
            thread = threading.Thread(
                target=r.export_card_images,
                args=(
                    card,
                    target_folder,
                    EXPORT_SIZES[args.size][1],
                    False,
                ),
                kwargs={
                    'bleed': bool(args.bleed),
                    'format': args.format,
                    'quality': 100,
                }
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        print(f'Tool.test took {time()-t} seconds.')
        return

    # Start in normal mode
    from shoggoth.main_qt import main
    main()


if __name__ == '__main__':
    logger.debug('tool main starting')
    run()
    logger.debug('tool main ending')