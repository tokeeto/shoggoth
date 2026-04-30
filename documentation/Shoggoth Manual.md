# Shoggoth Manual

## Table of Contents

- [What is Shoggoth?](#what-is-shoggoth)
- [Installation](#installation)
- [General Concepts](#general-concepts)
- [The User Interface](#the-user-interface)
  - [The Project Tree](#the-project-tree)
  - [The Editing Area](#the-editing-area)
  - [The Card Preview](#the-card-preview)
  - [The Command Palette](#the-command-palette)
- [Creating a Project](#creating-a-project)
- [Player Cards](#player-cards)
  - [Asset](#asset)
  - [Event](#event)
  - [Skill](#skill)
  - [Investigator](#investigator)
  - [Customizable](#customizable)
- [Scenario Cards](#scenario-cards)
  - [Enemy](#enemy)
  - [Treachery](#treachery)
  - [Location](#location)
  - [Act & Agenda](#act--agenda)
  - [Story](#story)
  - [Chaos Bag Reference Card](#chaos-bag-reference-card)
- [Writing Card Text](#writing-card-text)
- [Working with Images](#working-with-images)
- [Guides](#guides)
- [Exporting Your Cards](#exporting-your-cards)
- [Translating a Project](#translating-a-project)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [File Organization and Sharing](#file-organization-and-sharing)
- [Advanced: Editing JSON Directly](advanced-json.md)

---

## What is Shoggoth?

Shoggoth is a desktop application for creating custom cards and related content for **Arkham Horror: The Card Game** by Fantasy Flight Games.

Shoggoth is not affiliated with, nor endorsed by Fantasy Flight Games.

![Shoggoth main window](screenshots/main_window.jpg)

---

## Installation

Download the latest release for your platform from the [releases page](link-to-releases). No installation is required — just extract and run the executable.

### Building from Source

If you want to build Shoggoth yourself or contribute to development:

1. Install [uv](https://docs.astral.sh/uv/)
2. Clone this repository
3. Run `uv run shoggoth`

Shoggoth downloads its asset pack (card templates, fonts, icons) automatically on first launch from the [shoggoth-assets](https://github.com/tokeeto/shoggoth_assets) repository. You only need to clone that repo if you want to modify the assets themselves.

---

## General Concepts

Shoggoth organizes content the same way Arkham Horror products are structured:

| Concept | What it means |
|---|---|
| **Project** | An "expansion" — a campaign box, investigator pack, or any grouped product. Stored as a single `.json` file. |
| **Encounter Set** | A named group of encounter cards sharing an icon and sequential numbering. |
| **Card** | A single card with a front and a back **Face**. |
| **Face** | One side of a card. Each face has a **type** that determines its default artwork and layout. |
| **Type** | A set of default values for a face (images, fields, layout). Built-in types include `investigator`, `asset`, `location`, `enemy`, etc. Types can also point to custom templates. |

Because everything is just a card with typed faces, Shoggoth doesn't enforce rigid categories. You can always override any field or point to a custom template to create something entirely unique.

---

## The User Interface

Shoggoth's window is divided into three areas:

![UI overview](screenshots/ui_overview.jpg)

1. **Menu bar** — access all commands
2. **Project Tree** (left panel) — navigate cards and encounter sets
3. **Editing area** (right) — edit the selected card or project element

You can toggle the Project Tree with **Ctrl+K** and the card preview panel from **View → Show Preview**.

### The Project Tree

The tree shows your entire project hierarchy. Player cards are grouped by class (Guardian, Seeker, etc.). Encounter cards are grouped by encounter set.

- **Click** an item to open its editor.
- **Right-click** any item to see context-specific actions (rename, duplicate, delete, add child, etc.).
- **Drag and drop** cards to move them between encounter sets or class groups.

The tree has two display modes switchable from the View menu:
- **Tree view** — hierarchical, showing encounter sets as folders
- **List view** — flat list of all cards, sortable by name or type

### The Editing Area

Most items in the tree open a dedicated editor when selected:

- **Project editor** — project-wide settings, encounter sets, and guides
- **Card editor** — tabbed front/back editing for a single card
- **Encounter set editor** — thumbnail grid of all cards in a set
- **Guide editor** — Markdown-based rulebook editor (see [Guides](#guides))
- **Translation editor** — field-by-field translation overlay (see [Translations](#translating-a-project))

### The Card Preview

Enable the preview panel from **View → Show Preview** (or press **Ctrl+Shift+P** if bound). The preview renders the card exactly as it will look when exported. Click the card image to switch between front and back faces.

### The Command Palette

Press **Ctrl+P** to open the command palette. It lists every menu action and most settings toggles, searchable by name. This is the fastest way to reach any command without remembering where it lives in the menus.

---

## Creating a Project

**File → New Project** (or **File → Open Project** to open an existing one).

When creating a new project, you'll set:

- **Name** — used for display and as the default export filename
- **Save location** — the project `.json` file will be created here; all relative image paths are resolved from this folder
- **Encounter set icon** — an image used for the default encounter set (you can change it later)

After creation, the project editor opens. From here you can rename encounter sets, add new ones, add guides, or jump straight to creating cards.

![New project dialog](screenshots/new_project_dialog.jpg)

### Project Templates

**Project → Add Scenario**, **Add Campaign**, **Add Investigator**, or **Add Investigator Expansion** pre-populate your project with the right encounter sets and card skeletons for that format, so you don't have to set them up from scratch.

---

## Player Cards

Create a new player card via **File → New Card** (**Ctrl+N**) or by right-clicking in the Project Tree and selecting **New Card**.

In the New Card dialog, choose:

- **Template** — the card face type (see below)
- **Name** — the card's name
- **Encounter set** — which encounter set or player card pool to add it to

Player cards live under the class-grouped section of the Project Tree (Guardian, Seeker, Rogue, Mystic, Survivor, or Other).

### Asset

Assets are the most common player card type: weapons, tomes, allies, and other items you put into play.

**Front fields:**
- Name, subname (flavour subheading)
- Class(es)
- Cost (resource cost; use `X` for variable)
- Level (0–5)
- Traits
- Slot(s)
- Willpower / Intellect / Combat / Agility skill icons
- Body text (supports [Arkham text syntax](text-formatting.md))
- Flavor text
- Health / Sanity (for ally assets)
- Illustration

**Back:** Generic player card back by default; customizable.

### Event

One-use cards that are played and discarded.

**Front fields:** Same as Asset minus slot and health/sanity.

### Skill

Skill cards committed to skill tests.

**Front fields:**
- Name, subname
- Class(es)
- Level
- Traits
- Skill icons (the icons committed to tests)
- Body text, flavor text
- Illustration

### Investigator

A full two-sided investigator card.

**Front fields:**
- Name, subname (title)
- Class(es)
- Willpower / Intellect / Combat / Agility stats
- Health / Sanity
- Traits
- Elder Sign ability text
- Illustration
- Signature card / weakness card names

**Back fields:**
- Class(es)
- Deck-building restrictions / special rules text
- Flavor / quote text
- Deckbuilding options and requirements

### Customizable

Customizable cards have upgrade boxes on the front.

The **Customizable** editor adds an upgrade table where each row has a checkbox count, XP cost, and upgrade text. The **Customizable Back** type is a plain player card back used for the separate level-0 version.

---

## Scenario Cards

Scenario cards follow the same **File → New Card** / right-click flow. They're added to Encounter Sets.

### Enemy

**Fields:** Fight, Health, Evade, damage, horror, class/keyword traits, body text, victory points, flavor text, illustration.

### Treachery

**Fields:** Class, traits, body text, flavor text, illustration.

### Location

Locations have a **front** (the unrevealed side) and a **back** (the revealed side).

**Front:** Shroud value, connection dots (directions), location icon, flavor text, illustration.  
**Back:** Clues, connection arrows, traits, body text, victory points, flavor text, illustration.

The location view (**View → Location View**) arranges all locations in your project on a canvas so you can check connection layouts visually.

### Act & Agenda

Acts and Agendas have matching front and back types (`act` / `act_back`, `agenda` / `agenda_back`).

**Front:** Act/Agenda number and letter (e.g. "1a"), title, body text, flavor text.  
**Back:** Act/Agenda number and letter (e.g. "1b"), title, doom/clue threshold, body text, resolution text.

### Story

A catch-all card type for interlude/story cards, scenario reference cards, etc.

### Chaos Bag Reference Card

The `chaos` type renders a chaos bag odds reference card.

---

## Writing Card Text

Shoggoth uses a lightweight tag syntax for card body text. Tags are rendered directly in the card preview as you type.

For a full reference of every tag, see **[Text Formatting Reference](text-formatting.md)** or open **Help → Text Options** inside Shoggoth.

**Quick reference:**

| Tag | Effect |
|---|---|
| `<b>...</b>` | Bold |
| `<i>...</i>` | Italic |
| `[[...]]` | Bold italic (trait/flavor emphasis) |
| `<action>` or `[action]` | Action symbol |
| `<fast>` or `[fast]` | Fast (free trigger) symbol |
| `<reaction>` | Reaction symbol |
| `<resource>` | Resource symbol |
| `<skull>`, `<cultist>`, `<tablet>`, `<elder_thing>` | Chaos token icons |
| `<elder_sign>`, `<auto_fail>` | Special chaos token icons |
| `[willpower]`, `[intellect]`, `[combat]`, `[agility]` | Stat icons |
| `<damage>`, `<horror>` | Damage / horror icons |
| `<for>` | Expands to **Forced –** |
| `<rev>` | Expands to **Revelation –** |
| `<prey>` | Expands to **Prey –** |
| `<center>...</center>` | Center-align text |
| `<br>` | Line break |
| `--` | En dash (–) |
| `---` | Em dash (—) |

---

## Working with Images

Every Face has an **Illustration** field that accepts a file path to an image. Paths can be:

- **Absolute** — points to a specific file anywhere on your system
- **Relative** — resolved from the project's `.json` file location (recommended for portability)

Supported formats: JPEG, PNG, WebP, and most other common image formats.

### Gather Images

**File → Gather Images** copies all referenced images into a subfolder next to the project file and rewrites all paths to relative ones. Use this before sharing your project to ensure all images travel with the project file.

**File → Gather and Update Images** does the same but also pulls in any updated versions of images that have changed on disk.

---

## Guides

A Guide is a Markdown-formatted document attached to your project — useful for scenario rules, campaign logs, or reference sheets. Guides can also incorporate a PDF as a front page.

**Project → Add Guide** opens the guide creation dialog.

The guide editor provides:
- A Markdown editor with syntax highlighting
- A section list for organizing content
- A PDF viewer for any attached front page

Guides are exported alongside your cards as part of the PDF export workflow.

---

## Exporting Your Cards

Shoggoth offers several export paths. See **[Exporting Reference](exporting.md)** for full details.

**Quick export (Ctrl+E)** — saves the current card's front and back as images to the project folder immediately, no dialog.

**Export → Export to Images (Ctrl+Shift+E)** — batch export with control over:
- Scope (all cards, player cards only, or campaign cards only)
- File format (PNG / JPEG / WebP) and quality
- Image size (print, screen, or thumbnail)
- Filename format
- Optional card backs and bleed border

**Export → Export to PDF** — generates a print-ready PDF via the Prince XML renderer. Requires [Prince](https://www.princexml.com/) to be installed (available free for non-commercial use). Also supports **MBprint** format for Make Playing Cards compatible files.

**Export → Export to Tabletop Simulator** — generates a TTS deck JSON with card sheet images ready to import into Tabletop Simulator.

**Export → Export to arkham.build** — generates a JSON file compatible with the arkham.build deckbuilder, with an optional image URL pattern so your hosted images load automatically.

---

## Translating a Project

Shoggoth supports layered translations: the original text is never modified; translated text is stored in a separate overlay file.

1. **Project → Add Translation** — creates a new translation (set language and file path).
2. Select any card in the tree — the editor will show both original and translated fields side by side.
3. Type into the translated fields; changes save automatically.
4. **Project → Load Translation** — load an existing translation file created by someone else.

When exporting with a translation active, the exported images use the translated text.

See **[Translation Guide](translations.md)** for details on sharing and managing translation files.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open project |
| `Ctrl+S` | Save |
| `Ctrl+N` | New card |
| `Ctrl+R` | Go to card (search by name) |
| `Ctrl+M` | Auto-enumerate cards |
| `Ctrl+E` | Quick export current card |
| `Ctrl+Shift+E` | Export to images dialog |
| `Ctrl+P` | Command palette |
| `Ctrl+K` | Toggle project tree |

---

## File Organization and Sharing

A Shoggoth project is a single `.json` file. Card images are referenced by path — they're not embedded in the project file.

**Recommended layout for a shareable project:**

```
My Campaign/
  My Campaign.json        ← project file
  My Campaign images/     ← created by File → Gather Images
    art_location_1.jpg
    art_enemy_boss.png
    ...
```

After running **Gather Images**, all paths in the project file are relative, so the entire folder can be zipped and shared. Recipients open `My Campaign.json` in Shoggoth directly.

### Working with a Text Editor

The `.json` format is designed to be human-readable and hand-editable. You can open the project file in any text editor to make bulk changes (find-and-replace, batch field updates, etc.). Shoggoth detects external changes and reloads automatically in viewer mode (`uv run shoggoth -v project.json`).

For an explanation of the JSON schema, see **[Advanced: Editing JSON Directly](advanced-json.md)**.
