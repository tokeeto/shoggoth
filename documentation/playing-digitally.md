# Playing digitally

[← Back to the manual](manual.md)

## Tabletop Simulator

Add a **Tabletop Simulator** entry to an export setup (see [Exporting card images](exporting.md)). Shoggoth renders the card images and builds a TTS saved object:

- **All cards** or **Campaign cards** make a bag with one deck per encounter set.
- **Player cards**, specific encounter sets, or specific cards make a single bag of those cards.

If Shoggoth finds your Tabletop Simulator folder, the object is saved straight into TTS's **Saved Objects**, so it shows up in the game's _Objects → Saved Objects_ menu. Otherwise it's saved in the project's export folder, and Shoggoth tells you where.

Cards are exported with the metadata the **SCED** mod (the community Arkham Horror mod for TTS) uses, so they're recognized as player cards, enemies, locations and so on.

### Live updates while you playtest

Tick **Send to TTS?** and keep Tabletop Simulator running. Every time you run the export, Shoggoth sends the updated cards into your open game, **replacing the cards where they are on the table**. Fix a typo, run the export setup from **Export → Setups**, and the card on the table updates. You don't need to reload anything.

If TTS isn't running, the export still works and the live update is skipped.

### Updating an existing TTS object

If you've already set up a TTS object you're happy with, choose it under **Update an existing TTS export**. Shoggoth updates the card images and data in that file instead of creating a new one.

### Sharing a TTS object with other players

The exported object points to the card images _on your computer_, so other players won't see them. To share it, the images must be online. [Submitting your project to the Library of Celaeno](sharing.md#publishing-to-the-library-of-celaeno) uploads the images and rewrites the TTS object to use the online copies.

## arkham.build

[arkham.build](https://arkham.build) is a popular deck builder that supports fan-made content. Add an **arkham.build** entry to an export setup (see [Exporting card images](exporting.md)) to export your cards as an arkham.build data file. Shoggoth always keeps a local copy at
`Export of <project name>/arkham-build/<project ID>.json` inside the project folder.

### Choosing which cards to export

Like the other entries, the arkham.build entry has an **Export scope**: **All cards**, **Player cards**, **Campaign cards**, **Specific encounter sets** or **Specific cards** (with a filter box to find them by name). Use it to leave out unfinished cards, or to make a player-cards-only file.

A partial export only describes the cards in it:

- Only encounter sets that contain an exported card are listed. **All cards** lists every encounter set, even empty ones.
- Investigators and their signature cards are linked only when both are exported. Export a signature without its investigator, and it's not restricted to that investigator. Export an investigator without its signatures, and its deck requirements leave them out.

The file always describes the whole pack. Uploading a partial export replaces what was there before, so cards you leave out disappear from arkham.build.

### What gets exported

The export works out card text and attributes, links between investigators and their signature cards, numeric deck size requirements (from the back's "Deck Size" entry), and bonded cards. It doesn't yet work out an investigator's deckbuilding options or the upgrade sheets of customizable cards. You can set these yourself, as described below.

- Investigators, acts, agendas, locations and scenario cards become one double-sided record. Other cards with a different back get a separate, hidden back record.
- Generic player and encounter card backs aren't exported as cards. Neither are scanning sheets or enemy decks.
- Text references (`<:id front.traits>` and the like, see [Advanced text](advanced-text.md)) are filled in. A reference to a missing card or field, or one that loops back on itself, stops the export with an error that names it.

Project information comes from the **Meta** tab in the project editor: **Author**, **Description**, **Banner URL**, **Banner Credit**, **Website URL**, **Tags** and **Content Types**. **Status** must be one of `draft`, `alpha`, `beta`, `complete` or `final`. Anything else is exported as `draft`. The language is the project's language.

### Explicit deckbuilding data

Use the card's **JSON** tab to add an `arkham_build` object under the card's
`meta` object:

```json
{
  "meta": {
    "arkham_build": {
      "deck_requirements": "size:30, random:subtype:basicweakness",
      "deck_options": [],
      "starts_in_hand": true,
      "back": {
        "custom_behavior": {}
      }
    }
  }
}
```

Explicit values replace generated values for the same field. Fields inside `back` apply only to the separate back record (linked by the generated `back_link`), if the card has one.

### Card images: uploading

arkham.build needs the card images online. The entry's **Upload** setting decides how they get there.

**Celaeno cloud** uploads everything for you. Sign in to the [Library of Celaeno](sharing.md#publishing-to-the-library-of-celaeno) from the **Cloud** menu first. If the server URL isn't set, set it in **File → Settings → Publishing**. The export uploads card images, thumbnails, icons, images from card text, and the JSON file itself. The JSON contains the public image URLs and an update URL. Run the export again to update it. You don't need a **Submit to cloud** entry for this.

**Manual** leaves the uploading to you. Enter a **URL prefix** for the server where you will host the images:

```
https://example.com/cards
```

The export then saves the images in
`Export of <project name>/arkham-build/<project ID>/` inside the project folder. Upload that `<project ID>` folder to the URL, so the images end up at `https://example.com/cards/<project ID>/…`. Leave the prefix empty to export the card data without any images. Older export setups use **Manual**.

Either way:

- Each card side is saved as a WebP image, with a small square thumbnail cut from the card.
- The project icon, encounter set icons and inline images from card text are copied into the `assets/` subfolder. They keep their original format and content. Shoggoth doesn't convert or recolor them, and an image used several times is copied only once.
- Inline `<image src="…">`, `<exi>`, `<esi>`, `<project.icon>` and `<encounter.icon>` tags become images with online URLs. If an image file can't be found, its image is left out.

To get your content listed on arkham.build, contact the arkham.build team.

---

Next: **[Writing a campaign guide →](campaign-guides.md)**
