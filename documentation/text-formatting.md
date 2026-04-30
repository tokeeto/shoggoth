# Text Formatting Reference

Card body text in Shoggoth supports a tag-based syntax for inline formatting, symbols, and layout control. Tags are rendered live in the card preview as you type.

Open **Help → Text Options** inside Shoggoth to see this reference at any time.

---

## Formatting Tags

| Tag | Effect |
|---|---|
| `<b>` / `</b>` | Bold |
| `<i>` / `</i>` | Italic |
| `<bi>` / `</bi>` | Bold italic |
| `<t>` / `</t>` | Trait emphasis (bold italic) |
| `[[` / `]]` | Trait emphasis shorthand (bold italic) |
| `<center>` / `</center>` | Center-align the enclosed text |
| `<left>` / `</left>` | Left-align (default) |
| `<right>` / `</right>` | Right-align |
| `<story>` / `</story>` | Indented story/flavor block |
| `<blockquote>` / `</blockquote>` | Block quote formatting |
| `<br>` | Explicit line break |
| `</indent>` | End an active indent |

---

## Symbol Tags

### Action Icons

| Tag | Symbol |
|---|---|
| `<action>` or `[action]` | Action (arrow in circle) |
| `<fast>` or `[fast]` | Fast / free trigger (lightning bolt) |
| `<reaction>` | Reaction (lightning bolt with arc) |

### Stat Icons

| Tag | Symbol |
|---|---|
| `[willpower]` or `<willpower>` or `<wil>` | Willpower |
| `[intellect]` or `<intellect>` or `<int>` | Intellect |
| `[combat]` or `<combat>` or `<com>` | Combat |
| `[agility]` or `<agility>` or `<agi>` | Agility |
| `[per_investigator]` or `<per>` | Per investigator |

### Damage & Resources

| Tag | Symbol |
|---|---|
| `<damage>` | Damage |
| `<horror>` | Horror |
| `<resource>` | Resource |

### Chaos Token Icons

| Tag | Symbol |
|---|---|
| `<skull>` | Skull |
| `<cultist>` | Cultist |
| `<tablet>` | Tablet |
| `<elder_thing>` | Elder Thing |
| `<elder_sign>` | Elder Sign |
| `<auto_fail>` | Auto-fail (tentacle) |

### Class Icons

| Tag | Symbol |
|---|---|
| `<guardian>` | Guardian |
| `<seeker>` | Seeker |
| `<rogue>` | Rogue |
| `<mystic>` | Mystic |
| `<survivor>` | Survivor |

### Miscellaneous Icons

| Tag | Symbol |
|---|---|
| `<unique>` | Unique (diamond) |
| `<bullet>` | Bullet point |
| `<blessing>` | Bless token |
| `<curse>` | Curse token |
| `<frost>` | Frost token |
| `<resolution>` | Resolution |
| `<codex>` | Codex |
| `<day>` | Day |
| `<night>` | Night |

---

## Keyword Shorthand Tags

These expand to bold labeled text in the current translation language:

| Tag | Expands to |
|---|---|
| `<rev>` | **Revelation –** |
| `<for>` | **Forced –** |
| `<prey>` | **Prey –** |
| `<spawn>` | **Spawn –** |
| `<obj>` or `<objective>` | **Objective –** |

---

## Typography Replacements

| Tag | Result |
|---|---|
| `--` | En dash (–) |
| `---` | Em dash (—) |
| `<quote>` | Left single quote (') |
| `<quoteend>` | Right single quote (') |
| `<dquote>` | Left double quote (") |
| `<dquoteend>` | Right double quote (") |

---

## Examples

```
<b>Fight.</b> You get +2 <combat> for this attack.

<rev> Test <intellect> (3). On a fail, take 1 <horror>.

<for> After you draw this card: Discard it.

This card costs 1 less resource for each [[Blessed]] card in your hand.

<center><i>"I have seen things that cannot be unseen."</i></center>
```
