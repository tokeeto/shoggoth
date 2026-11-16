# Finding your way in a big project

[← Back to the manual](manual.md)

A full campaign easily has 300 cards. Here's how to get around one quickly, and how to move cards around once you're there.

## Jumping to a card

- **Go to** (**Ctrl+R**): start typing a card's name, pick it from the list with the arrow keys, and press Enter. It searches cards, encounter sets, guides and projects, and shows a thumbnail of the selected card. You don't need to type the exact name: `ghoulpr` finds *Ghoul Priest*.
- **Back and forward**: the back and forward buttons on your mouse move through the cards and pages you've viewed, like in a web browser.
- **Command palette** (**Ctrl+P**): finds *commands* rather than cards.

## The tree, the folders and the card list

The sidebar has three modes, which you can switch under **View → Sidebar View**:

- **Tree View** groups everything: projects, then encounter sets (each split into *Story*, *Locations* and *Encounter* cards), player cards by class, and guides. The grouping is always the same, decided by what each card is.
- **Folder View** starts out looking exactly like the tree, but lets you put cards in folders of your own. See [Your own folders](#your-own-folders) below.
- **Card List** is a flat list of every card. You can **sort** it by collection number or name, **filter** it by card type, and **search** by name. It's useful for questions like "show me all the treacheries" or "which card is number 147?"

In the tree and folders, acts and agendas are labelled with their index, like *Act 1a: Trapped* and *Agenda 2a: Rise of the Ghouls*. That keeps acts and agendas sorted in order and easy to match up.

### Reading through a scenario: the story view

Click an encounter set's **Story** group (in the Tree View or the Folder View) to see all its story cards at once, so you can read the scenario from start to finish:

- **Agenda** and **Act** columns show each agenda and act with its front directly above its back, in order, with a gap before the next card.
- Scenarios with **several agenda or act lines** (1a/1b → 2a/2b next to 1c/1d → 2c/2d, or a split into 3a, 3d and 3e) are shown side by side: every agenda (or act) with the same number goes in one row, ordered by letter, and a lone card is centered. This is decided by the **index** number alone, so cards without an index each get their own row at the end. How the lines connect differs from scenario to scenario, so check the layout against your own scenario. With several lines, the doom and clue totals still add up every card, so they won't match a single path through the scenario.
- Under the **Agenda** and **Act** headers you'll see the total doom and clue thresholds, like *15 doom* or *6 + 7<per> clues*. The color tells you how the scenario's length compares to a standard one, counting each <per> as 3 (a three-player game):
  - **Doom**: white at exactly 15, yellow at 16–18, red at anything else.
  - **Clues**, compared with the total doom: white at 0.6–0.75<per> clues per doom (15 doom = 9<per> clues), yellow up to 1<per> per doom, red above or below that.
- **Other** shows the rest of the Story group (scenario reference cards, story cards and so on), front side up. Press **F** to flip the card under the mouse, or **Shift+F** to flip them all.

Zoom with the mouse wheel and drag to pan. **Double-click** a card to open it in the editor. The story view is for reading: cards can't be moved or edited there.

### Balancing the encounter deck: the encounter view

Click an encounter set's **Encounter** group to see its encounter deck laid out like the story view, in **Enemies**, **Treacheries** and **Other** columns. Every copy of an enemy or treachery is dealt out separately, overlapping the previous copy like a hand of playing cards, so you can see at a glance how many copies there are.

Above the columns, everything is counted per copy:

- **Enemies**: the total health of all enemy copies (like *14 + 5<per>*), how much of the encounter deck is enemies (enemies divided by enemies plus treacheries), and bar charts of the **Combat** and **Evade** values, from *X* (anything that isn't a plain number, like *X*, *?* or a dash) through *1* to *6+*, with their median and mean. A value of 0 is counted as 1.
- **Treacheries**: a chart of the skill tests in the treacheries' text by difficulty, colored by skill, and how many tests of each skill there are, like *Willpower: 16 (44%)*. The percentage is out of all treachery copies. Tests are found by looking for text like `Test <willpower> (3)`, so a test written differently (for example *Test <willpower> or <agility> (3)*) isn't counted.
  - Under **Deals**, how many treachery copies deal **damage** and how many deal **horror**, with their percentage of all treachery copies. A treachery counts when its text has a number right before the word, like *take 2 horror*, so *heal all damage* or *the enemy with the most damage* don't count. When the player gets to choose, as in *take 1 damage or horror* or *take 1 damage or 1 horror*, it counts under **Damage or horror** instead. A treachery that deals several kinds counts for each, but only once for each, however many times it mentions them. Wordings like *take X damage* aren't counted either.

The view works the same way as the story view: zoom, pan, double-click to open a card, and **F** / **Shift+F** to flip cards in the *Other* column.

If an encounter set only has encounter cards, the tree shows them directly under the set without an *Encounter* group, so there's nothing to click. Add a story or location card to get the groups.

Toggle the sidebar with **Ctrl+K** when you need the space.

When you have several projects open, the **active** project is the one that menu commands like *New Card* and *Export* act on. Clicking anything in a project makes it active, and you can also right-click a project and choose **Set as Active**.

## Your own folders

The Tree View decides where every card goes. When you'd rather decide yourself (all the bosses together, a folder per act, a *Needs art* pile), switch to **Folder View**.

Every card has a **Folder** on its **Meta** tab, and that's where it's listed. Until you change it, the field shows the card's default place, which is the same place the tree would put it. Type a path with `/` between the folders, and the folders appear as soon as a card is in them:

```
Bosses/Act 1
```

The names in braces in the default stand for the built-in groups. They follow the card, so `{encounter_set}` is always the set the card is in right now:

| Name | Stands for |
|---|---|
| `{campaign_cards}`, `{player_cards}` | The two top-level groups |
| `{encounter_set}` | The card's encounter set |
| `{story}`, `{locations}`, `{encounter}` | The three groups within an encounter set |
| `{investigators}`, `{investigator}` | The Investigators group, and the investigator the card belongs to |
| `{class}` | The card's class |
| `{card_type}` | The card's type: *Asset*, *Enemy*, and so on |

You can mix them with your own folders. `{campaign_cards}/{encounter_set}/Bosses` gives every encounter set its own *Bosses* folder, and `Review/{card_type}` sorts a review pile by type.

To put a card back where it belongs by default, clear the field.

A folder exists only as long as a card is in it, so there's nothing to create or delete. Folders are a way of looking at the project and don't change the cards: you can switch back to Tree View at any time, which is handy when you're working in someone else's project and want the standard layout.

### Dragging cards into folders

In Folder View you can drag cards onto any folder. Shoggoth looks at the folder and everything above it to work out what the card should become:

- A folder inside an **encounter set** makes the card part of that set.
- A folder inside **Player Cards**, a **class** or an **investigator** makes it a player card. It leaves its encounter set, and takes the class or investigator if there is one.
- A folder that's inside neither just changes where the card is listed. The card stays what it was.

If the folder doesn't say enough, the drop isn't allowed and the cursor shows it. That's the case when you drag a player card onto *Campaign Cards* or a folder directly inside it: Shoggoth can't tell which encounter set you mean.

Dropping a card on a built-in group it would belong in anyway, such as its encounter set or *Player Cards*, clears its own folder and puts it back in its default place.

### Adding cards to a folder

Right-click one of your own folders to add a card straight into it. Inside an encounter set you get the encounter card types (act, agenda, story, enemy, treachery, location), inside player cards you get asset, event and skill, and anywhere else a plain **New Card**. **Paste Card** works the same way.

## Reorganizing

- **Drag and drop** cards onto another encounter set or class group to move them. Select several cards with Shift-click or Ctrl-click to move them together. In Folder View you can also drop them on [your own folders](#dragging-cards-into-folders).
- **Right-click** a card for *Duplicate*, *Copy*, *Delete* and *Transfer*. Right-click an encounter set or group to *Paste Card* there.
- To **reorder encounter sets**, give scenarios an **Order** number in the encounter set editor. Sets without one are sorted alphabetically after them.
- **Cards within a set** are always sorted automatically: scenario reference card, agendas, acts, locations, story cards, treacheries, then enemies. That's also the order they're numbered in. To change it, see [Controlling card numbering](numbering.md).

## Moving cards between projects

**Project → Transfer Cards** moves or copies many cards from one open project to another at once:

1. Choose the **source** and **destination** projects, and whether to **move** or **copy**.
2. Tick the cards you want. The filter box narrows the list down.
3. Choose what happens to their encounter sets: copy each card's encounter set into the destination, turn the cards into player cards, or put them all into one specific encounter set.

If you select cards in the tree first, they're already ticked when the dialog opens. It's the easy way to split a big project in two, or to pull your best cards into a "collected" project.

For just one or two cards, **Copy** and **Paste Card** across projects works too.

## Closing projects

Right-click a project and choose **Close Project**, or use **File → Close Project**. Shoggoth asks if there are unsaved changes. **Open Containing Folder** on the same menu opens the project's folder in your file manager.

---

Next: **[Exporting card images →](exporting.md)**
