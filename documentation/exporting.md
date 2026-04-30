# Exporting Reference

Shoggoth provides several export formats depending on how you intend to use your cards.

---

## Quick Export (Ctrl+E)

**Export → Quick Export Current Card**

Instantly saves the front and back of the currently selected card as images to the project folder. No dialog, no options — good for a fast check or when you want one card quickly.

---

## Export to Images

**Export → Export to Images (Ctrl+Shift+E)**

Batch-exports cards as individual image files.

![Export to Images dialog](screenshots/export_images_dialog.jpg)

### Scope

Choose which cards to export:
- **All** — every card in the project
- **Player cards** — Guardian, Seeker, Rogue, Mystic, Survivor, and neutral player cards
- **Campaign cards** — encounter set cards (enemies, treacheries, locations, acts/agendas)

### Format

| Option | Details |
|---|---|
| **Size** | Print (standard), large, or thumbnail |
| **Format** | PNG (lossless), JPEG, or WebP |
| **Quality** | Compression quality for JPEG and WebP (1–100%) |

### Filename Format

Controls how exported files are named. Options include card name, card index, or encounter set + index combinations. Choose a naming scheme that matches how your print service or playtest group expects files.

### Options

| Option | Effect |
|---|---|
| **Include backs** | Exports the back face of each card alongside the front |
| **Include bleed** | Adds a bleed border for print services that require it (recommended for printing) |
| **Rotate** | Rotates the exported images 90° (useful for landscape-format cards) |
| **Separate versions** | Exports each version of a multi-version card as a separate file |

---

## Export to PDF

**Export → Export Card/Campaign/Player to PDF**

Generates a print-ready PDF. Requires [Prince XML](https://www.princexml.com/) to be installed — Prince is free for non-commercial use. Shoggoth will prompt you to install it if it isn't found.

Use **Export → Install Prince** if you need to set it up.

### Scope

Choose to export a single card, all campaign cards, or all player cards.

### PDF Options

| Option | Details |
|---|---|
| **Image folder** | Where to render card images before assembling the PDF (next to project or custom path) |
| **Format** | PNG, JPEG, or WebP for the intermediate images |
| **Size** | Card image resolution |
| **Quality** | Compression for lossy formats |
| **Include backs** | Whether to include card backs in the PDF |
| **Output path** | Where to save the final PDF |

---

## Export to MBPrint PDF

**Export → Export Card/Campaign/Player to MBPrint PDF**

Same as PDF export but uses a fixed size and format optimized for uploading to [Make Playing Cards](https://www.makeplayingcards.com/) (MBPrint format). Intermediate images are rendered at the exact resolution MPC expects.

---

## Export to Tabletop Simulator

**Export → Export to Tabletop Simulator**

Generates a TTS-compatible deck configuration.

![TTS Export dialog](screenshots/tts_export_dialog.jpg)

### Scope

- **Campaign** — encounter set cards
- **Player** — player cards
- **All** — everything

### Images

By default Shoggoth renders and exports the card images alongside the TTS JSON. You can point the image folder to the project folder or a custom location.

If you uncheck **Export images**, the TTS JSON will reference images by name only (useful if you've already uploaded images somewhere and are just regenerating the deck data).

### Sync to TTS

With **Send to Tabletop Simulator** checked, Shoggoth will write the deck JSON directly to TTS's `Saved Objects` folder so it appears immediately in the game — no manual file copying needed.

---

## Export to arkham.build

**Export → Export to arkham.build**

Generates a JSON file compatible with the [arkham.build](https://arkham.build) deckbuilder, allowing players to browse and add your custom cards to decks.

### Image URL Pattern

If you host your card images somewhere publicly accessible (e.g. GitHub Pages, Dropbox, Imgur), enter the URL pattern here. Use `{filename}` as a placeholder for the image filename:

```
https://mysite.com/cards/{filename}
```

The generated JSON will reference the full URL for each card image.

If you leave this blank, the JSON will contain local image paths, which only works if you also send the image files separately.

---

## Tips

- Run **File → Gather Images** before exporting to ensure all image paths are relative and portable.
- For print-on-demand services, use **Include bleed** in the image export settings. Most services require 3mm of bleed.
- PDF export with Prince produces the most accurate, print-ready output and handles multi-page layouts correctly.
