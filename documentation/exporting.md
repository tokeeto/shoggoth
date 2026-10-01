# Exporting card images

[← Back to the manual](manual.md)

Card images are the starting point for almost everything else: printing, Tabletop Simulator, sharing online. Shoggoth has several ways to get them, from a single card to a saved export setup that runs your whole pipeline.

Exports go to a folder called `Export of <project name>` next to your project file, unless you choose another folder.

## One card, right now

**Export → Quick Export Current Card** (**Ctrl+E**) saves the front and back of the card you're looking at. There's no dialog. It uses the size and format from **File → Settings → Export**.

To export a single encounter set, right-click it and choose **Export Set** (or use the *Export Set* button in the encounter set editor). That opens a one-time image export already limited to that set.

## The whole project: export setups

**Export → Export Project** (**Ctrl+Shift+E**) opens the export dialog. It's built around **export setups**: named, saved recipes such as "Print shop", "TTS playtest" or "Everything". They're saved *inside the project*, so they're there next time, and they travel with the project if you share it.

A setup is a list of **entries** that run from top to bottom. Each entry is one kind of export:

| Entry | What it makes |
|---|---|
| **Images** | Card image files |
| **PDF** | A printable PDF (see [Printing your cards](printing.md)) |
| **Tabletop Simulator** | A TTS deck/bag (see [Playing digitally](playing-digitally.md)) |
| **arkham.build** | A JSON file for the arkham.build deck builder |
| **Guides** | PDF and/or HTML versions of your campaign guides |
| **Submit to cloud** | Uploads what the earlier entries produced (see [Sharing your project](sharing.md)) |

To make one:

1. Click **Add New...** next to *Export setup* and give it a name.
2. Click **Add Entry** for each export you want, and set its options. Use ▲ and ▼ to reorder entries.
3. For images, PDF and TTS, choose the **scope**: all cards, player cards, campaign cards, specific encounter sets, or specific hand-picked cards.
4. Click **Export**. The setup is saved and run.

Once saved, a setup can be run straight from **Export → Setups** without opening the dialog. Change something on a card, then run "Print shop" again.

For a one-off export that you don't want to keep as a setup, use **Export → One-Time Export**. It's the same dialog, and its button is *Export (Don't Save)*.

## Image options

| Option | What it does |
|---|---|
| **Destination folder** | Where the files go. Relative paths are relative to the project folder. |
| **Size** | Three resolutions, in both **FFG** trim (the official card size, 61.5×88 mm) and **MTG** trim (63.5×88 mm, which most print shops use). The largest is print quality, the middle one is fine for screens and TTS, and the smallest is for thumbnails. |
| **Format** | **PNG** is lossless, with the best quality and the biggest files. **JPEG** gives small files, and 90–95% quality looks great. **WebP** is small and lossless at 100%, but not every program opens it. |
| **Bleed** | Adds the extra margin around the card that print shops cut off. Turn it on for printing, off for screens. |
| **Rounded corners** | Cuts the corners round, like a real card. Only applies without bleed. |
| **Include backs** | Exports every card's back. Without it, the shared player and encounter backs are exported only once. |
| **Separate versions** | Exports one image per copy. A treachery with 3 copies becomes three files numbered `4/20`, `5/20` and `6/20`, instead of one file numbered `4-6/20`. Use it for print-and-play and anything that needs every physical card. |
| **Rotate** | Turns horizontal cards (acts, agendas, some investigators) upright, which makes print layouts simpler. Leave it off for digital use. |
| **File name format** | See below. |

### File names

| Format | Example | Good for |
|---|---|---|
| UUID | `3f2a…_ghoul_priest_front_0.png` | Default. Names never clash, even between projects. |
| Code + name | `tdl_mm_12_front.png` | Readable names built from the project and encounter set codes. |
| Order number | `012-card-a.png` | Print services that want files numbered in order, with `a`/`b` for front/back. |
| Name only | `12_ghoul_priest_front.png` | Browsing the folder by hand. |

## Default settings

**File → Settings → Export** sets the size, format, quality and options for quick exports. The command palette has toggles for the most common ones ("Toggle: Export Bleed", "Set Export Size...").

---

Next: **[Printing your cards →](printing.md)**
