# Writing card text

[← Back to the manual](manual.md)

Card text in Shoggoth is plain text with a few **tags** mixed in: short codes in angle brackets, like `<b>` for bold or `<action>` for the action icon. The preview shows the result as you type. This chapter covers what you need for everyday cards. The [text tag reference](text-reference.md) lists everything, and [Advanced text](advanced-text.md) covers the more powerful features.

## Bold, italic and traits

| You type | You get |
|---|---|
| `<b>Fight.</b>` | **Fight.** (bold, used for ability names and keywords) |
| `<i>Some flavor.</i>` | *Some flavor.* (italic) |
| `<t>Ally</t>` or `[[Ally]]` | ***Ally*** (the bold italic style used for traits in rules text) |

In a text field, **Ctrl+B**, **Ctrl+I** and **Ctrl+T** wrap the selected text in bold, italic and trait tags. The button row above text fields inserts the most common tags with one click.

You don't need tags in the **Traits** field. Type `Item. Weapon. Firearm.` and Shoggoth styles it for you.

## Icons

Type the icon's name in angle brackets:

| Kind | Tags |
|---|---|
| Actions | `<action>`, `<free>` (fast), `<reaction>` |
| Skills | `<willpower>`, `<intellect>`, `<combat>`, `<agility>`, `<wild>` |
| Chaos tokens | `<skull>`, `<cultist>`, `<tablet>`, `<elder_thing>`, `<elder_sign>`, `<auto_fail>`, `<blessing>`, `<curse>`, `<frost>` |
| Other | `<per>` (per investigator), `<unique>`, `<damage>`, `<horror>`, `<resource>`, `<bullet>`, `<guardian>`, `<seeker>`... |

When you type `<` in a text field, Shoggoth suggests matching tags. Keep typing to narrow the list down, then press Enter or Tab to insert one.

By default, text fields show icons *as icons* while you edit (**Settings → Display → Ligatures**). Turn that off if you'd rather see the tags as plain text.

## Keywords

These tags expand to the bold keyword with its dash. They're also translated automatically when the project's card language isn't English:

| You type | You get |
|---|---|
| `<rev>` | **Revelation –** |
| `<for>` | **Forced –** |
| `<prey>` | **Prey –** |
| `<spawn>` | **Spawn –** |
| `<obj>` or `<objective>` | **Objective –** |

## Lines and paragraphs

- **Enter** starts a new paragraph, with a little space above it, the way separate abilities are laid out on official cards.
- **Shift+Enter** breaks the line without starting a new paragraph (the same as `<br>`).
- **Shift+Space** inserts a non-breaking space, which keeps two words on the same line, such as a number and its unit: `2 damage`.
- Start lines with `- ` (dash and space) to make a **bulleted list**. Shoggoth indents it and adds bullet icons.

## Punctuation

- **Quotes curl by themselves.** `"Hello"` becomes “Hello” and `don't` becomes don’t. To keep a straight quote, write `\"`.
- **Dashes:** `--` becomes an en dash (–) and `---` becomes an em dash (—).

## Flavor text

Most card types have a separate **Flavor** field. Shoggoth places it under the rules text, centered and in italics, like on official cards, so you don't need to format it yourself.

On story cards and act and agenda backs, story passages go in `<blockquote>...</blockquote>`, which gives them the indented story style. The *Story* button above the text field inserts this for you.

## When the text doesn't fit

If there's too much text, Shoggoth shrinks the font until it fits, down to half the normal size. It also avoids leaving a single word alone on the last line. If the text still looks cramped, shorten it, turn on [hyphenation](first-project.md#project-settings) for the project, or see [Advanced text](advanced-text.md#fine-tuning-layout) for manual layout control.

## Quick reference inside Shoggoth

**Help → Text options** lists every tag, icon and font Shoggoth knows about.

---

Next: **[Adding art →](adding-art.md)**
