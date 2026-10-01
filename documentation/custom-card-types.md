# Making your own card types

[← Back to the manual](manual.md)

Every card type in Shoggoth, including asset, enemy, location and act, is defined by a small JSON file: the **type**, also called the *defaults*. It says which template image to draw, where each piece of text goes, and in what font and size. Nothing about the built-in types is hard-coded, so you can make your own just as well: a new card frame for your campaign's special mechanic, a variant layout of an existing card, or something entirely new.

This chapter assumes you're comfortable editing JSON files in a text editor.

## How a type works

To see the built-in types, open **Help → Asset file location** and look in the `defaults` folder. Here's a shortened piece of `asset.json`:

```json
{
    "template": "chapter_1/asset_<class><subtitle>",
    "name": "<name>",
    "name_region": { "x": 340, "y": 115, "width": 940, "height": 94 },
    "name_font": { "font": "title", "size": 94, "alignment": "center" },

    "traits": "",
    "traits_region": { "x": 158, "y": 1330, "width": 1346, "height": 64 },
    "traits_font": { "font": "bolditalic", "size": 64, "alignment": "center" },

    "illustration_region": { "x": 0, "y": 232, "width": 1644, "height": 1032 }
}
```

The pattern is the same for every field:

- **`field`** is the default value. A card's own value replaces it.
- **`field_region`** is where it's drawn: `x`, `y`, `width` and `height` in pixels. A standard vertical card is **1644 × 2244** pixels, bleed included.
- **`field_font`** sets how it looks: `font` (a [built-in style name](fonts.md)), `size`, `min_size` (how far it may shrink to fit; half the size by default), `color`, `outline` and `outline_color`, `alignment` (`left`, `center`, `right`), `valignment` (`top`, `center`, `bottom`) and `rotation` (in degrees).
- **`field_polygon`** is an optional list of `[x, y]` points, for text that should flow inside a non-rectangular shape.

When Shoggoth draws a card side, it takes the side's own values and fills in everything else from its type. So a card only stores what's special about it.

Turn on **Settings → Display → Show layout regions** to see every region drawn as a colored box on the preview. It's very useful while you work on a layout.

## Making a type

Create a JSON file in your project folder, for example `types/ritual.json`. Start from an existing type with `parent`, and list only what's different:

```json
{
    "parent": "event",
    "editor": "event",
    "template": "types/ritual_frame.png",
    "label": "RITUAL",
    "text_region": { "x": 158, "y": 1500, "width": 1346, "height": 420 }
}
```

- **`parent`** inherits everything from another type, either a built-in name like `event`, or another file of yours. Parents can have parents.
- **`card_type`** is the role the card plays in the game: `asset`, `event`, `enemy`, `location` and so on. It decides where the card is grouped in the project tree, how it's sorted, how exports treat it, and which editor form it gets. It's inherited from `parent`, so here the ritual is an `event` without saying so. A type that blends roles can list them all in `card_types`, most important first, the way the built-in `enemy_location` is `["location", "enemy"]`.
- **`editor`** overrides the editor form, for a type whose fields match a different built-in type than its `card_type`. A type with neither a known `card_type` nor an `editor` gets a generic editor.
- **`template`** is the card frame image. It's either a path relative to the project, or the name of a template in the asset pack (without `.png`). A template name can contain `<class>` (the card's class, or `multi`), `<subtitle>` (`_subtitle` if the card has a subtitle) and `<class_length>` (the number of classes), so one type can pick the right frame for every class.

To use the type, open a card's **JSON** tab and set the side's type to the file:

```json
"front": { "type": "types/ritual.json", ... }
```

Save the type file, and the preview updates immediately. You can keep a type file open in your text editor and watch the card change as you edit.

## Adding new text fields

Any `something_region` in a type creates a new text field called `something`. It's drawn like any other text field, and it shows up in the editor's **Additional text fields** section, ready to be filled in:

```json
"ritual_cost": "",
"ritual_cost_region": { "x": 1200, "y": 330, "width": 300, "height": 60 },
"ritual_cost_font": { "font": "bold", "size": 50, "alignment": "right" }
```

Up to five extra images can be placed with `image1` to `image5` and their `imageN_region`.

## Different looks for different classes: variants

A type can change values depending on the card's class, with a list of **variants**:

```json
"variants": [
    { "when": ["weakness", "basic weakness"],
      "set": { "label": "%:WEAKNESS", "template": "types/ritual_weakness.png" } },
    { "when": "basic weakness",
      "set": { "label": "%:BASIC WEAKNESS" } },
    { "when": "encounter & !story",
      "set": { "collection_total": "<esn>/<est>" } }
]
```

- **`when`** is matched against the card's class. A card with one class matches that class's name. A multi-class card matches `multi`, and also `multi2`, `multi3`, or `multi2+` style patterns, but *not* its individual class names. `encounter` matches cards in an encounter set.
- Combine conditions with `&`, and negate one with `!`. A list matches if *any* of its entries match.
- **Later variants win** over earlier ones, and a child type's variants win over its parent's.

`%:WEAKNESS` looks up the translated word from the asset pack's translation files, so the label follows the card's language.

## Other useful settings

| Setting | Effect |
|---|---|
| `"orientation": "horizontal"` | A landscape card, like acts and agendas |
| `"card_size": "mini"` | Mini card size (like mini investigator cards) |
| `"template_bleed": true` | The template image already includes the bleed area |
| `"field_overlay"` + `"field_overlay_region"` | An image drawn behind a field, but only when the field has a value (like the cost circle) |

The best way to learn more is to look at the built-in types that resemble what you want.

## Sharing custom types

Keep type files and their images in the project folder and refer to them with relative paths. Then the types travel with the project. **Gather images** doesn't collect them, so keep them in the project folder from the start.

## Editing the asset pack

To improve the built-in types themselves, for example to fix a layout or contribute a new template to Shoggoth, work on a copy of the [asset pack repository](https://github.com/tokeeto/shoggoth_assets), not the managed asset folder (Shoggoth updates that folder, and asks before overwriting your changes). Point Shoggoth at your copy with two environment variables:

```
SHOGGOTH_ASSET_DIR="/path/to/shoggoth_assets/"
SHOGGOTH_UNMANAGED_ASSETS=1
```

The first makes Shoggoth use your folder, and the second stops it from updating that folder. You can put both lines in a file named `.env` next to the Shoggoth program (or in the repository folder when running from source) instead of setting them system-wide. Remove them to go back to the normal, automatically updated assets.

---

Next: **[Working with the project file directly →](project-files.md)**
