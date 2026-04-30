# Translating a Project

Shoggoth supports layered translations. The original card data is never modified — translated text is stored as a separate overlay file, and the two can be shared and applied independently.

---

## Creating a Translation

1. Open your project.
2. Go to **Project → Add Translation**.
3. Enter a language name and choose where to save the translation file (`.json`).

The translation file is created next to the project file by default. It contains only the fields that have been translated — everything else falls back to the original.

---

## Translating Cards

Select any card in the Project Tree. If a translation is active, the card editor shows an extra **Translation** tab (or the editor switches to translation mode). Each translatable field appears as a pair:

- The **original** value (grey, read-only) above
- The **translated** value (editable) below

Type into the translated field and the change saves automatically. You can leave fields blank to inherit the original text.

Fields that appear in the translation editor:

- Card name
- Front face: traits, body text, flavor text, action/keyword text
- Back face: same fields on the back

---

## Switching Between Translations

If you have multiple translation files for a project, load them via **Project → Load Translation**. Only one translation is active at a time.

To return to the original language, close the translation (or reload it with an empty overlay).

---

## Exporting with a Translation

When a translation is active, all export functions (images, PDF, TTS, etc.) use the translated text. Export a translated set just like you would the original — the output files will contain the translated content.

A common workflow:
1. Export the original English cards as one set.
2. Load the German translation.
3. Export again to a different folder — you now have two complete sets.

---

## Sharing Translations

Translation files are plain JSON and can be shared, version-controlled, or edited by hand. Send the `.json` file to collaborators; they load it with **Project → Load Translation** and continue editing.

Because the translation file references cards by ID, it stays in sync even if card names change in the original project — as long as the card IDs remain stable.

---

## Tips

- Keep translation files in the same folder as the project file for easy portability.
- The `documentation/` folder alongside the project is a good place for both.
- If a translator only covers some cards, the untranslated cards will still display correctly in the original language during export.
