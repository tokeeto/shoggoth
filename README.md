# Shoggoth
## Card creation software for Arkham Horror: The Card Game

## Status
Under development. Not stable, nor feature complete yet. While Viewermode works, UI mode is still largely unfinished. Lots of dead buttons, weird exceptions, missing functionality and so on.

Shoggoth allows you to create homebrew cards for Arkham Horror: The Card Game. It features a sensible templating system with inheritance, that makes it easy to define new cards in very few rules.

## Installation:
It's recommended to install Shoggoth as a tool, using `pipx install shoggoth` or `uvx install shoggoth`. If you don't know what any of that means, simply use `pip install shoggoth` as normal.

## Usage
You can either start Shoggoth in UI mode using `shoggoth`, or you can run it in "viewer mode" using `shoggoth -v path/to/project_file.json`.
In UI mode, you'll have an experience similar to other card designers, where the UI will help guide you along to create cards similar to official cards.
In viewer mode, you can use your favorite json/text editor to edit the project file, and the viewer will refresh on each and every file save, while jumping straight to first detected change - effectively showing you the card you're working on, live while you write it.

## Planned Features
* Easy exporting: With a very simple data structure, comes very simple exporting. Export to PDF for TTS, Arkham.build or ArkhamCards in a single click.
* Easy sharing: Have shoggoth move all required images, along with all the data, into a single zip folder for easy sharing with your publisher.

You can incentivise the further development of Shoggoth (and other AH:TCG software and content) by donating on [Patreon](https://patreon.com/tokeeto) or [Ko-Fi](https://ko-fi.com/tokeeto).
