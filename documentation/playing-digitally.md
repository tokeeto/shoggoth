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

[arkham.build](https://arkham.build) is a popular deck builder that supports fan-made content. An **arkham.build** entry saves card data to
`Export of <project name>/arkham-build/<project ID>.json` inside the project folder.

The export automatically infers card text and attributes, investigator <-> signature links, numeric deck size requirements and bonded card relations. It does not yet infer the investigator's deckbuilding options and customizable sheets for customizable cards. You can set these explicitly as outlined below.

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

Explicit values replace generated values for the same field. Fields inside `back` apply only to the separate back record linked by the generated `back_link` should there be one.

### Card images and icons

Enter a **URL prefix** for the server where you will host the images:

```
https://example.com/cards
```

With a prefix set, the export saves images, thumbnails and icons in
`Export of <project name>/arkham-build/<project ID>/` inside the project folder.

The export copies the project icon, encounter set icons, and inline images
from card text into the `assets/` subfolder. These files keep their original
format and content. The export does not convert or recolor them. Shared images
are copied only once.

Pack and encounter set `icon_url` fields use the same URL prefix. Inline
`<image src="…">`, `<exi>`, `<esi>`, `<project.icon>`, and `<encounter.icon>` tags
become HTML images with hosted URLs.
If an image file is missing, the export logs a warning and omits its reference.

Upload the project ID folder to that URL. Shoggoth does not upload images for you.

To get your content listed on arkham.build, contact the arkham.build team.

---

Next: **[Writing a campaign guide →](campaign-guides.md)**
