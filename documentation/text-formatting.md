# Text Formatting Reference

Card body text in Shoggoth supports a tag-based syntax for inline formatting, symbols, and layout control. Tags are rendered live in the card preview as you type.

Open **Help → Text Options** inside Shoggoth to see this reference at any time.

---

## Formatting Tags

| Tag | Effect |
|---|---|
| `<b>` / `</b>` | Bold |
| `<i>` / `</i>` | Italic |
| `<t>` / `</t>` | Trait |
| `<center>` / `</center>` | Center-align the paragraph and onward |
| `<left>` / `</left>` | Left-align (default) |
| `<right>` / `</right>` | Right-align |
| `<blockquote>` / `</blockquote>` | Block quote formatting - this matches flavor/story text on Story cards, as well as on Agenda/Act back sides |
| `<br>` | Explicit line break |
| `<indent>` / `</indent>` | Create an indented block. Useful for aligning a couple of lines |

---

## Symbol Tags

### Action Icons

| Tag | Symbol |
|---|---|
| `<action>` | Action (arrow in circle) |
| `<free>` | Fast / free trigger (lightning bolt) |
| `<reaction>` | Reaction (lightning bolt with arc) |

### Stat Icons

| Tag | Symbol |
|---|---|
| `<willpower>` | Willpower |
| `<intellect>` | Intellect |
| `<combat>` | Combat |
| `<agility>` | Agility |
| `<wild>` | Wild icon |

### Damage & Resources (unofficial)

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
| `<curse>` | Curse |
| `<bless>` | Bless |
| `<frost>` | Frost token |
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
| `<unique>` | Unique |
| `<bullet>` | Bullet point |
| `<resolution>` | Resolution |
| `<codex>` | Codex icon |
| `<day>` | Day icon |
| `<night>` | Night icon |

---

## Keyword Shorthand Tags

These expand to bold labeled text in the current translation language:

| Tag | Expands to |
|---|---|
| `<rev>` | **Revelation –** |
| `<for>` | **Forced –** |
| `<prey>` | **Prey –** |
| `<spawn>` | **Spawn –** |
| `<objective>` | **Objective –** |

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

This card costs 1 less resource for each <t>Blessed</t> card in your hand.

<center><i>"I have seen things that cannot be unseen."</i></center>
```
