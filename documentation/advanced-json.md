# Advanced: Editing JSON Directly

Shoggoth project files are plain JSON. Most things can be done through the UI, but sometimes it's faster or necessary to edit the file directly — for bulk changes, scripting, or features the UI doesn't expose.

---

## Project File Structure

```json
{
  "name": "My Campaign",
  "encounter_sets": [ ... ],
  "cards": [ ... ],
  "guides": [ ... ],
  "translations": [ ... ]
}
```

### Encounter Set

```json
{
  "id": "abc123",
  "name": "The Dread Cellar",
  "icon": "my_icon.png"
}
```

### Card

```json
{
  "id": "card_001",
  "name": "The Lurker",
  "front": { ... },
  "back": { ... },
  "encounter_set": "abc123" or null
}
```

### Face

A face has a `type` field that sets the template, and then any number of overriding fields:

```json
{
  "type": "enemy",  // A built-in type or a path to the .json template file
  "name": "The Lurker",
  "subtitle": "Agent of Chaos",
  "traits": "Monster. Cultist.",
  "combat": "3",
  "health": "4",
  "evade": "2",
  "damage": 1,
  "horror": 2,
  "text": "<b>Hunter.</b>\n<for> Move The Lurker toward the nearest investigator.",
  "flavor_text": "It does not sleep.",
  "illustration": "./images/lurker.jpg",
  "victory": "Victory 1."
}
```

Any field not specified inherits the value from the type template, which in turn inherits from the global defaults. You only need to include fields you want to override.

---

## Template Inheritance

When Shoggoth renders a face, it resolves fields in this order (first match wins):

1. The face itself
3. Class-specific overrides (if the card has a class)
2. The face's type template (e.g. `enemy.json` from the asset pack)
4. Global defaults

This means you can make a minimal face with just `type`, `name` and `illustration` set and get a fully rendered card with correct background art and layout.

---

## Fields

Any face supports any field. With one or two exceptions, there's no special rules for any card type. Each field follows a general pattern:

1. The renderer will go through the list of known fields.
2. For each field, it will check if there's a value for that field.
3. For each field with a value, it will check if the `<field>_region` is set for that face. This is the location to render the value.
4. For text fields, it will also check for a `<field>_font` value.
5. If the renderer finds everything it needs to render a field, it will render it. Be that health and horror on a treachery, clues on an investigator or location icons on an asset.

## Editing Tips

- **Card IDs** are stable identifiers — don't change them, especially if you have translation overlays that reference them.
- **Paths** in image fields can be relative (resolved from the project file location) or absolute. Relative paths are more portable.
- **Field names** are case-sensitive and must match exactly (e.g. `"willpower"` not `"Willpower"`).
- Invalid JSON will cause the project to fail to load. Use a JSON linter before saving. Look out for trailing commas.

---

## Custom Defaults

You can point a face's `type` field to any `.json` file on disk to use fully custom defaults. This is how you create card types that don't exist in the official game — custom layout, custom templates, and/or custom default field values.

Custom template files follow the same face JSON schema. Place them next to your project file (or in a `templates/` subfolder) and reference them by relative path:

```json
{
  "type": "templates/my_unique_card.json",
  "name": "The Dreamer"
}
```
