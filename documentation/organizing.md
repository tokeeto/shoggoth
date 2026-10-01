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
