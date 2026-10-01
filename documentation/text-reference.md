# Text tag reference

[← Back to the manual](manual.md)

Every tag you can use in card text. For explanations and examples, see [Writing card text](writing-text.md) and [Advanced text](advanced-text.md). Inside Shoggoth, **Help → Text options** shows this list too. Tags aren't case-sensitive.

## Formatting

| Tag | Effect |
|---|---|
| `<b>` … `</b>` | Bold |
| `<i>` … `</i>` | Italic |
| `<bi>` … `</bi>` | Bold italic |
| `<t>` … `</t>`, `[[` … `]]` | Trait style (bold italic) |
| `<u>` … `</u>` | Underline |
| `<dbl>` … `</dbl>` | Double underline (headings) |
| `<center>`, `<left>`, `<right>` (and closing tags) | Alignment |
| `<blockquote>` … `</blockquote>` | Story text style |
| `<size N>` … `</size>` | Font size in card pixels |
| `<font "name">` … `</font>` | Another font. See [Using your own fonts](fonts.md). |
| `<indent N>` … `</indent>` | Indent by N pixels |
| `<margin N>` | N pixels of vertical space |
| `<spacing X>` | Letter spacing (1 is normal) |
| `<valign>` | Vertically center the text from this line on |
| `<br>` | Line break |
| `<hr>` | Horizontal rule |
| `<image src="path" color="…">` | An inline image. `color` is optional: `inverted` or a color. |
| `- ` at the start of a line | Bulleted list item |

## Keywords

These are translated with the card language.

| Tag | Result |
|---|---|
| `<rev>` | **Revelation –** |
| `<for>` | **Forced –** |
| `<prey>` | **Prey –** |
| `<spawn>` | **Spawn –** |
| `<obj>`, `<objective>` | **Objective –** |

## Typography

| Tag | Result |
|---|---|
| `--` | – (en dash) |
| `---` | — (em dash) |
| `<quote>`, `<quoteend>` | ‘ ’ |
| `<dquote>`, `<dquoteend>` | “ ” |
| `"` and `'` | Curled automatically. Write `\"` or `\'` for a straight quote. |
| Shift+Space (in the editor) | Non-breaking space |

## Icons

| Tag | Icon |
|---|---|
| `<action>`, `<act>`, `[action]` | Action |
| `<free>`, `[fast]` | Fast |
| `<reaction>` | Reaction |
| `<willpower>`, `<wil>`, `[willpower]` | Willpower |
| `<intellect>`, `<int>`, `[intellect]` | Intellect |
| `<combat>`, `<com>`, `[combat]` | Combat |
| `<agility>`, `<agi>`, `[agility]` | Agility |
| `<wild>` | Wild |
| `<skull>` | Skull |
| `<cultist>` | Cultist |
| `<tablet>` | Tablet |
| `<elder_thing>` | Elder Thing |
| `<elder_sign>` | Elder Sign |
| `<auto_fail>` | Auto-fail |
| `<blessing>` | Bless |
| `<curse>` | Curse |
| `<frost>` | Frost |
| `<guardian>`, `<seeker>`, `<rogue>`, `<mystic>`, `<survivor>` | Class symbols |
| `<per>`, `[per_investigator]` | Per investigator |
| `<investigator>`, `<per_large>` | Investigator (large) |
| `<unique>` | Unique |
| `<damage>`, `<horror>` | Damage, Horror |
| `<resource>` | Resource |
| `<bullet>` | Bullet |
| `<resolution>` | Resolution |
| `<codex>` | Codex |
| `<day>`, `<night>` | Day, Night |
| `<entry>`, `<open>` | Entry, Open |
| `<blood>` | Blood |
| `<fleur>` | Fleur |
| `<star>`, `<dash>` | Star, Dash |
| `<sign_1>` … `<sign_5>` | Numbered signs |

## Dynamic values

| Tag | Becomes |
|---|---|
| `<name>` | The card's name |
| `<copy>` | The same field on the other side |
| `<exn>` | Collection number |
| `<exi>` | Project icon |
| `<esn>` | Encounter set number |
| `<est>` | Encounter set total |
| `<esi>` | Encounter set icon |
| `<copyright>` | The card's copyright |
| `<:id field>` | A field from another card, set or project (**Ctrl+L**). Leave out the id for this card. |
| `%:KEY` | A translated word from the asset pack (in card types) |

## Campaign guides

Guides use Markdown plus some extras. See [Writing a campaign guide](campaign-guides.md).

| Syntax | Effect |
|---|---|
| `[[Trait]]` | Trait |
| `:::story`, `:::resolution`, `:::codex`, `:::toc`, `:::center`, `:::right`, `:::indent` … `:::` | Blocks |
| `:::image-top` / `-bottom` / `-column` / `-block` / `-free` | Image placements |
| `:::image-fade-top` / `-bottom` / `-column` / `-block` | Faded image placements |
| `[card:id:name]`, `[card:id:front:field]` | Card references |
| `[encounter:id:name]`, `[encounter:id:icon]`, `[encounter:id:number_of_locations]`, `[encounter:id:location_overview:N]` | Encounter set references |
| `[enc:Set Name]` | An encounter set's icon, by name |
| `[project:name]`, `[project:icon]`, `[project:number_of_scenarios]`, `[project:scenario_names]` | Project references |
| `[pagebreak]` | New page |
| `{./path}` in HTML | A path relative to the project folder |
