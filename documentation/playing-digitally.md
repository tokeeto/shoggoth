# Playing digitally

[← Back to the manual](manual.md)

## Tabletop Simulator

Add a **Tabletop Simulator** entry to an export setup (see [Exporting card images](exporting.md)). Shoggoth renders the card images and builds a TTS saved object:

- **All cards** or **Campaign cards** make a bag with one deck per encounter set.
- **Player cards**, specific encounter sets, or specific cards make a single bag of those cards.

If Shoggoth finds your Tabletop Simulator folder, the object is saved straight into TTS's **Saved Objects**, so it shows up in the game's *Objects → Saved Objects* menu. Otherwise it's saved in the project's export folder, and Shoggoth tells you where.

Cards are exported with the metadata the **SCED** mod (the community Arkham Horror mod for TTS) uses, so they're recognized as player cards, enemies, locations and so on.

### Live updates while you playtest

Tick **Send to TTS?** and keep Tabletop Simulator running. Every time you run the export, Shoggoth sends the updated cards into your open game, **replacing the cards where they are on the table**. Fix a typo, run the export setup from **Export → Setups**, and the card on the table updates. You don't need to reload anything.

If TTS isn't running, the export still works and the live update is skipped.

### Updating an existing TTS object

If you've already set up a TTS object you're happy with, choose it under **Update an existing TTS export**. Shoggoth updates the card images and data in that file instead of creating a new one.

### Sharing a TTS object with other players

The exported object points to the card images *on your computer*, so other players won't see them. To share it, the images must be online. [Submitting your project to the Library of Celaeno](sharing.md#publishing-to-the-library-of-celaeno) uploads the images and rewrites the TTS object to use the online copies.

## arkham.build

> **Work in progress.** The arkham.build export is not finished, which is why the entry is labelled **arkham.build (WIP)** and Shoggoth reminds you after each export. If something in the exported file is wrong or missing, report it to the Shoggoth team, not to the arkham.build team.

[arkham.build](https://arkham.build) is a popular deck builder that supports fan-made content. An **arkham.build (WIP)** entry creates `<project name>_arkham_build.json` in your project folder, describing every card in the arkham.build format: types, classes, costs, traits, text, deckbuilding requirements and signature cards.

For card images to show up in arkham.build, they must be hosted online. Enter an **Image URL pattern** with `{code}` where the card's code goes:

```
https://example.com/my-project/{code}.jpg
```

Back images use `{code}_back`. Leave the pattern empty to leave out image links: images are never embedded in the file itself.

To get your content listed on arkham.build, contact the arkham.build team.

---

Next: **[Writing a campaign guide →](campaign-guides.md)**
