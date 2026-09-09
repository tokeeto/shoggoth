# Shoggoth
## Card creation software for Arkham Horror: The Card Game

## Status
Under development. We're getting close to a 1.0.0 release though. Most things work, many advanced features has been implemented, and many nice-to-have's are coming together.

Shoggoth allows you to create homebrew cards for Arkham Horror: The Card Game. It features a sensible templating system with inheritance, that makes it easy to define new cards in very few rules.

Shoggoth has been translated into multiple languages by the community.

## Installation:
The easiest way is to head to [releases](https://github.com/tokeeto/shoggoth/releases/latest) and grab the file for your system.

If you're on linux, or are comfortable around python, you can install Shoggoth as a python tool, using `pipx install shoggoth` (or `uvx shoggoth` if you use uv).

**Security and false positives in virus detection**
Windows defender has on occasionally reported Shoggoth as being harmful.
Shoggoth is not malware, but it does a lot of the same things as malware - it downloads files from the internet without asking you (asset files), unpacks them, and parse arbitrary files (projects/cards) on your system.
All of this is intended and expected. That being said, Shoggoth is not reviewed for security, and you shouldn't try to run files from people you don't trust. I can't give you any guarantee that the standard python json module doesn't have some exploit that will allow someone take over your system. Most software can't make that guarantee.

## Usage
Simply start Shoggothe.
You'll be presented with an experience similar to other card designers, where the UI will help guide you along to create cards similar to official cards.
If you installed Shoggoth via Python you can also use shoggoth as a cli tool. Run `shoggoth --help` for more information.

See also the [documentation](documentation/manual.md)

## Development
### Application development

Install python and uv. Clone this repo. Then you should be good to go.

To run Shoggoth in dev mode:
```bash
uv run shoggoth
```
but I personally prefer to use jurigged
```bash
uv run jurigged ./shoggoth/tool.py
```
this will reload all non-UI changes on the fly, as you change them.

To build a standalone `.app` (macOS) or executable (Windows/Linux):
```bash
uv run pyinstaller ShoggothStandalone.spec
```
The built app will be in `dist/Shoggoth.app` (macOS) or `dist/Shoggoth` (Windows/Linux).

### Asset development
(Changes to card layouts, font sizes, etc.)

While not technically this repo, the asset repo is best tested running Shoggoth.
To avoid overwriting your local changes, place a .env file in the shoggoth directory
```
SHOGGOTH_ASSET_DIR="/path/to/shoggoth_assets/"
SHOGGOTH_UNMANAGED_ASSETS=1
```
This will make it so Shoggoth doesn't try to download the newest updates automatically, and will point it towards your cloned asset repo, instead of using the default location for installed applications.

You can incentivise the further development of Shoggoth (and other AH:TCG software and content) by donating on [Patreon](https://patreon.com/tokeeto) or [Ko-Fi](https://ko-fi.com/tokeeto).
