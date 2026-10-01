# Using your own fonts

[← Back to the manual](manual.md)

Shoggoth draws cards with the fonts from the official cards, which come with its asset pack. You can use any other font, for a character's handwritten note, an eldritch script, or a whole custom card type, with the `<font>` tag.

## The `<font>` tag

Wrap text in `<font "...">` and `</font>`:

```
The note reads: <font "fonts/Handwriting.ttf">Don't open the door.</font>
```

The name in quotes can be:

1. **A font file** (`.ttf` or `.otf`), relative to the project file, like `fonts/Handwriting.ttf`, or a full path. This is the recommended way: keep the font in the project folder and the project stays portable.
2. **An installed font's file name**, without the extension. `<font "Garamond">` finds `Garamond.ttf` or `Garamond.otf` in your system's font folders. Note that this is the *file* name, which isn't always the name font menus show.
3. **One of Shoggoth's built-in styles**:

| Name | Font | Used for |
|---|---|---|
| `regular`, `italic`, `bold`, `bolditalic`, `semibold` | Arno Pro | Rules text |
| `caption`, `display`, `displaybold` | Arno Pro variants | Small print, labels |
| `title` | Arkhamic | Card titles |
| `cost` | Arkhamic | Costs and numbers |
| `skill` | Bolton | Skill values |
| `icon` | Arkham symbol font | Icons |

If Shoggoth can't find a font, it draws the text **struck through** in the normal font, so a missing font never goes unnoticed.

**Help → Text options** lists the built-in font names too.

## Fonts and sharing

- A font you refer to by a **relative path** travels with the project folder. **Gather images** doesn't collect fonts, so keep font files in the project folder yourself.
- A font you refer to by an **installed name** only works on computers where it's installed.
- In a **cloud project**, add font files with **Cloud → Upload New File...** so your collaborators get them.
- Check the font's license before you share or print it.

If you edit a font file while Shoggoth is running, the preview updates immediately.

## Fonts in PDFs

When you export a PDF with **Export text as vector PDF text** turned on, the card text, including your custom fonts, is embedded in the PDF as real text. It stays sharp at any print size.

## A custom font for a whole field

To use a font for a whole field, such as every title of a custom card type, put the `<font>` tag in that field's default value in [your own card type](custom-card-types.md):

```json
"name": "<font \"fonts/MyTitleFont.ttf\"><name>"
```

The style setting of a field (`"name_font": {"font": "title", ...}`) only accepts the built-in style names from the table above.

---

Next: **[Controlling card numbering →](numbering.md)**
