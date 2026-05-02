# Shoggoth
## Card creation software for Arkham Horror: The Card Game

## Status
Under development. We're getting close to a 1.0.0 release though. Most things work, many advanced features has been implemented, and many nice-to-have's are coming together.

Shoggoth allows you to create homebrew cards for Arkham Horror: The Card Game. It features a sensible templating system with inheritance, that makes it easy to define new cards in very few rules.

Shoggoth has been translated into multiple languages by the community.

## Installation:
The easiest way is to head to [releases](https://github.com/tokeeto/shoggoth/releases/latest) and grab the file for your system.

If you're on linux, or are comfortable around python, you can install Shoggoth as a python tool, using `pipx install shoggoth` (or `uvx shoggoth` if you use uv).

Note, that due to this being a hobby project, I'm not going to spend resources on obtaining a Apple developer license, and as such, Mac will complain about the application being unsigned, insecure or unknown. That is expected.

**Security and false positives in virus detection**
Windows defender has on ocassion reported Shoggoth as being harmful.
Shoggoth is not malware, but it does a lot of the same things as malware - it downloads files from the internet without asking you (asset files), unpacks them, and parse arbitrary files (projects/cards) on your system.
All of this is intended and expected. That being said, Shoggoth is not reviewed for security, and you shouldn't try to run files from people you don't trust. I can't give you any guarantee that the standard python json module doesn't have some exploit that will allow someone take over your system. Most software can't make that guarantee.

## Usage
Simply start Shoggoth for the UI mode.
In UI mode, you'll have an experience similar to other card designers, where the UI will help guide you along to create cards similar to official cards.
If you installed Shoggoth via Python you can also use shoggoth as a cli tool. Run `shoggoth --help` for more information.

See also the [documentation](documentation/Shoggoth Manual.md)

## Development

To run Shoggoth in dev mode:
```bash
uv run shoggoth
```

To build a standalone `.app` (macOS) or executable (Windows/Linux):
```bash
uv run pyinstaller ShoggothStandalone.spec
```

The built app will be in `dist/Shoggoth.app` (macOS) or `dist/Shoggoth` (Windows/Linux).

You can incentivise the further development of Shoggoth (and other AH:TCG software and content) by donating on [Patreon](https://patreon.com/tokeeto) or [Ko-Fi](https://ko-fi.com/tokeeto).
