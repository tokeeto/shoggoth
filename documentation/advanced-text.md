# Advanced text: references, dynamic values and snippets

[← Back to the manual](manual.md)

This chapter is for when basic formatting isn't enough: text that updates itself, typing common phrases in a few keystrokes, and exact control over layout. For basic formatting, see [Writing card text](writing-text.md).

## Referring to other cards

When one card mentions another, like a signature card saying *"Roland Banks deck only."* or a story card naming a location, you can **refer** to the other card instead of typing its name. If you rename the card later, every reference updates.

Press **Ctrl+L** (or **Edit → Insert Link**) in any text field. Pick a card, encounter set or the project from the search list, and Shoggoth inserts a reference like this:

```
<:3f2a9c1e-… >
```

The cursor is placed right before the `>`. Type what you want from the card:

| Reference | Shows |
|---|---|
| `<:id name>` | The card's (or encounter set's, or project's) name |
| `<:id front.traits>` | A field on the card's front |
| `<:id back.victory>` | A field on the card's back |

Leave out the ID to refer to *the card you're writing on*: `<: front.health>`.

References show values that are **set on that card**. They can't show a value the card only gets from its template's defaults.

The **Investigator template** (see [Your first project](first-project.md#getting-a-head-start-with-templates)) uses references this way: the investigator's deckbuilding requirements name the signature cards, and the signature card names its investigator.

## Dynamic values

These tags are replaced with information about the card when it's drawn:

| Tag | Becomes |
|---|---|
| `<name>` | The card's name |
| `<copy>` | The same field's value from the card's *other* side |
| `<exn>` | The card's collection number (its number in the whole project) |
| `<exi>` | The project's icon |
| `<esn>` | The card's number within its encounter set, like `4` or `4-6` |
| `<est>` | The total number of cards in the encounter set |
| `<esi>` | The encounter set's icon |
| `<copyright>` | The card's copyright text |

Most templates already use these. The name field is `<name>`, and the collection line is built from `<esn>/<est>` and `<exn>`. You can also use them in your own text, for example "*Search the encounter deck for a copy of `<name>`*". See also [Controlling card numbering](numbering.md).

## Snippets: whole phrases in a few keystrokes

Arkham cards repeat a lot of phrasing. **Snippets** type it for you. Press **Ctrl+Space** in a text field, and a small box shows which keys are available. Press them one after another:

| Keys | Inserts |
|---|---|
| Ctrl+Space, T, I, 3, F | `test <intellect> (3). If you fail ` |
| Ctrl+Space, U, C, 4 | `Uses (4 charges)` |
| Ctrl+Space, L, O, R, Space | `(Limit once per round.)` |
| Ctrl+Space, A, 1, 1 | `You get +1 <combat> for this attack. This attack deals +1 damage.` |
| Ctrl+Space, C, S, 2 | `Seeker cards (<seeker>) level 0-2.` |

The first key picks a group: **T**est, **C**lass (for deckbuilding), **L**imit, **E**lder sign effect, **A**ttack, **U**ses, **F**ast, **O**bjective, **P**ut into play, or **R**eminder (a collection of common phrases). You don't need to memorize anything, because the box always shows the next options.

### Your own snippets

**Tools → Show Snippet File** opens `snippets.py`, your personal snippet file. It comes with an example. Each snippet is a key sequence and a small Python function that returns the text to insert:

```python
def hello_world(face, card, project):
    """Hello world"""
    return "Hello, world! "

SNIPPETS = [
    (("z", "h"), hello_world),   # Ctrl+Space, Z, H
]
```

The function gets the side, card and project you're editing, so a snippet can insert text based on the card, like its name or its traits. It can even change the card directly. The first line of the docstring is the label shown in the key box. Your snippets are added to the built-in ones, and a snippet with the same keys as a built-in one replaces it.

> The snippet file is ordinary Python and runs with full access to your computer. Only put code in it that you understand, and don't paste in snippet files from people you don't trust.

## Fine-tuning layout

For when the automatic layout isn't quite right:

| Tag | Effect |
|---|---|
| `<center>`, `<right>`, `<left>` | Alignment from here on (close with `</center>` etc.) |
| `<size 60>` ... `</size>` | Font size for part of the text |
| `<indent 40>` ... `</indent>` | Indent a block of lines by that many pixels |
| `<margin 20>` | Add that much vertical space |
| `<spacing 1.1>` | Letter spacing. Values above 1 spread letters apart, below 1 squeeze them together. |
| `<valign>` | Vertically center the text from this line on, in the rest of the text box |
| `<hr>` | A horizontal rule across the text box |
| `<u>` ... `</u>` | Underline |
| `<dbl>` ... `</dbl>` | Double underline, as used for headings on some story cards |
| `<blockquote>` ... `</blockquote>` | Story text style, as on story cards and act/agenda backs |
| `<br>` | Line break within a paragraph |

Pixel values are in card pixels. A card is about 1500 pixels wide, and normal rules text is around 70 pixels tall. To see the exact text box a field is drawn in, turn on **Settings → Display → Show layout regions**.

Text boxes aren't always rectangles. Many templates wrap text around the art or around icons, and Shoggoth follows those shapes automatically.

## Images in text

```
Place 1 <image src="icons/key.png"> on this location.
```

The image is scaled to the height of the text. The path works like any other image path: relative to the project file, or absolute. Add `color="inverted"` to invert a black icon to white, or any color, like `color="#8b0000"` or `color="red"`, to tint a grayscale icon. The *Image* button above text fields inserts the tag for you.

For custom fonts in text, see [Using your own fonts](fonts.md).

## Language-dependent text

- **Card language** is set per project (see [Your first project](first-project.md#project-settings)), and can be overridden for a single card with **Language Override** in the card's *Basic info*.
- **Hyphenation** and **French punctuation** are set per project, in the project editor.
- In [your own card types](custom-card-types.md), `%:KEY` looks up a translated word, like `%:ENEMY`, from the asset pack's translation files. That's how the built-in templates print "ENEMY" in the card's language.

---

Next: **[Using your own fonts →](fonts.md)**
