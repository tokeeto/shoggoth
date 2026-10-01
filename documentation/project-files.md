# Working with the project file directly

[← Back to the manual](manual.md)

A Shoggoth project is a plain, readable JSON file. Most people never need to open it, but when you want to rename 40 traits at once, generate cards from a spreadsheet, keep your project in git, or write cards in your favorite text editor, you can work with the file directly.

## The format

```json
{
  "name": "The Shadow over Innsmouth",
  "code": "TSOI",
  "icon": "icons/tsoi.png",
  "default_copyright": "© Me 2026",
  "encounter_sets": [
    { "id": "…", "name": "Deep Ones", "icon": "icons/deep_ones.png", "order": 1 }
  ],
  "cards": [
    {
      "id": "…",
      "name": "Deep One Hybrid",
      "encounter_set": "…",
      "amount": 3,
      "front": {
        "type": "enemy",
        "traits": "Monster. Deep One.",
        "attack": "3", "health": "3", "evade": "2",
        "damage": 1, "horror": 1,
        "text": "<b>Hunter.</b>",
        "illustration": "art/hybrid.jpg"
      },
      "back": { "type": "encounter" }
    }
  ],
  "guides": [ … ],
  "meta": { … }
}
```

- A card has an **id**, a **name**, an **encounter_set** (the set's id, or missing for player cards), and a **front** and **back**.
- Each side has a **type** and only the fields that differ from that type's defaults. Everything else comes from the type (see [Making your own card types](custom-card-types.md)). You can leave out any field you don't need.
- **Ids** tie everything together: encounter sets, [references](advanced-text.md#referring-to-other-cards), links between investigators and their cards, translations, and cloud sync. Don't change them. When you add cards by hand, give each one a new unique id (any unique string works, and Shoggoth uses UUIDs).
- **Paths** can be relative to the project file (recommended) or absolute.

The quickest way to learn the format is to make a card in Shoggoth and look at its **JSON** tab. The tab shows the card exactly as it's stored, and you can edit it there too.

## Editing the file while Shoggoth is open

You can keep the project open in Shoggoth *and* in a text editor. When you save in the text editor, Shoggoth notices the file changed and offers to **Reload from Disk** (see [Sharing your project](sharing.md#when-someone-else-changes-the-file)). If you have no unsaved changes in Shoggoth, reloading loses nothing.

A mistake in the JSON, like a missing comma, a trailing comma or an unclosed quote, keeps the project from loading. Most text editors highlight these, and online JSON validators help too.

## Previewing cards in the terminal

If you prefer writing cards in a text editor, **display mode** gives you a live preview without the rest of Shoggoth:

```
shoggoth -d my_project.json
```

It watches the project file and, every time you save, shows the card you **last edited** right in your terminal. To pin one card instead, add `-id <card id>`. It needs a terminal that supports the kitty graphics protocol (kitty, WezTerm, Ghostty and others), or the `chafa` program for other terminals.

## Rendering from the command line

Shoggoth can export card images with no window at all, which is useful for scripts and automated builds:

```
shoggoth -r my_project.json -o out/ -f png -b 1
```

| Option | Meaning |
|---|---|
| `-r FILE` | Render every card in the project |
| `-id ID` | Only render the card with this id |
| `-o FOLDER` | Where to put the images (default: next to the project) |
| `-f FORMAT` | `jpeg` (default), `png` or `webp` |
| `-s N` | Size: `0`, `1` or `2` for full, half or quarter resolution (FFG trim). `3`, `4` and `5` are the same in MTG trim. |
| `-b 1` | Include bleed (leave it out for no bleed) |

`shoggoth --help` lists every option. If Shoggoth was installed as a standalone app, run the program file from its folder instead of `shoggoth`.

## Scripting

Because a project is just JSON, any language can read and write it. Common uses are generating a batch of cards from a spreadsheet, renaming a trait everywhere, or checking that every card has an illustration and an artist. Close the project in Shoggoth (or reload it afterwards) when a script changes the file.

---

Next: **[Text tag reference →](text-reference.md)**
