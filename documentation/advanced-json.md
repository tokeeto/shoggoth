# Advanced: Editing JSON Directly

Shoggoth project files are plain JSON. Most things can be done through the UI, but sometimes it's faster or necessary to edit the file directly — for bulk changes, scripting, or features the UI doesn't expose yet.

---

## Project File Structure

```json
{
  "name": "My Campaign",
  "encounter_sets": [ ... ],
  "player_cards": [ ... ],
  "guides": [ ... ],
  "translations": [ ... ]
}
```

### Encounter Set

```json
{
  "id": "abc123",
  "name": "The Dread Cellar",
  "icon": "my_icon.png",
  "cards": [ ... ]
}
```

### Card

```json
{
  "id": "card_001",
  "name": "The Lurker",
  "front": { ... },
  "back": { ... }
}
```

### Face

A face has a `type` field that sets the template, and then any number of overriding fields:

```json
{
  "type": "enemy",
  "name": "The Lurker",
  "subname": "Agent of Chaos",
  "traits": "Monster. Cultist.",
  "fight": "3",
  "health": "4",
  "evade": "2",
  "damage": "1",
  "horror": "2",
  "text": "<b>Hunter.</b>\n<for> Move The Lurker toward the nearest investigator.",
  "flavor": "It does not sleep.",
  "illustration": "images/lurker.jpg",
  "victory": "1"
}
```

Any field not specified inherits the value from the type template, which in turn inherits from the global defaults. You only need to include fields you want to override.

---

## Template Inheritance

When Shoggoth renders a face, it resolves fields in this order (first match wins):

1. The face itself
2. The face's type template (e.g. `enemy.json` from the asset pack)
3. Class-specific overrides (if the card has a class)
4. Global defaults

This means you can make a minimal face with just `type` and `name` set and get a fully rendered card with correct background art and layout.

---

## Common Fields by Card Type

### All Player Cards
`type`, `name`, `subname`, `traits`, `text`, `flavor`, `illustration`, `classes`, `level`, `cost`

### Asset (additional)
`health`, `sanity`, `slots`, `willpower`, `intellect`, `combat`, `agility`

### Enemy
`fight`, `health`, `evade`, `damage`, `horror`, `victory`, `text`, `flavor`

### Location
**Front:** `shroud`, `clue_type`, `connections`, `flavor`, `illustration`  
**Back:** `clues`, `connections`, `traits`, `text`, `victory`, `flavor`, `illustration`

### Investigator
**Front:** `willpower`, `intellect`, `combat`, `agility`, `health`, `sanity`, `elder_sign`  
**Back:** `deck_options`, `deck_requirements`, `text`

### Act / Agenda
`sequence` (e.g. `"1a"`), `title`, `text`, `doom` or `clues`, `resolution`

---

## Editing Tips

- **Viewer mode** (`uv run shoggoth -v project.json`) watches the file for changes and reloads automatically. Open the project in Shoggoth's viewer, edit the JSON in your text editor, and see changes rendered live.
- **Card IDs** are stable identifiers — don't change them, especially if you have translation overlays that reference them.
- **Paths** in image fields can be relative (resolved from the project file location) or absolute. Relative paths are more portable.
- **Field names** are case-sensitive and must match exactly (e.g. `"willpower"` not `"Willpower"`).
- Invalid JSON will cause the project to fail to load. Use a JSON linter before saving.

---

## Custom Templates

You can point a face's `type` field to any `.json` file on disk to use a fully custom template. This is how you create card types that don't exist in the official game — custom layout, custom background art, and custom default field values.

Custom template files follow the same face JSON schema. Place them next to your project file (or in a `templates/` subfolder) and reference them by relative path:

```json
{
  "type": "templates/my_unique_card.json",
  "name": "The Dreamer"
}
```
