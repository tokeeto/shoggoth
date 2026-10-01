# Controlling card numbering

[← Back to the manual](manual.md)

Official cards carry two numbers at the bottom:

- The **collection number** is the card's number in the whole product, next to the product's icon. Example: `147`.
- The **encounter set number** is the card's position within its encounter set, out of the set's total. Example: `4-6/20` for a treachery with three copies.

Shoggoth works both out for you. This chapter explains how, and how to change the result.

## Numbering the project

Choose **Project → Enumerate all cards** (**Ctrl+M**). Shoggoth numbers every card in the project. Numbers aren't updated on every edit, so run it again whenever you add, remove or reorder cards. The *Collection #* and *Encounter Set #* fields in a card's *Basic info* show the result.

The order Shoggoth numbers in is:

1. **Encounter sets**, first those with an **Order** (scenarios, by their number), then the rest alphabetically. Within each set, cards are sorted by type: scenario reference card, agendas, acts, locations, story cards, treacheries, enemies, then anything else. Cards of the same type are sorted by their index (`1a`, `2a`...), then by name.
2. **Player cards** come after all encounter sets. They're sorted by class, card type and level, with each investigator's signature cards and weakness right after the investigator, and bonded cards next to the card they belong to.

**Amount in set** matters for encounter set numbers. A card with 3 copies takes up three numbers, so it's numbered `4-6`. The set's total (`/20`) counts every copy.

To check the result, switch the sidebar to **Card List** and sort by *Project Number* (see [Finding your way in a big project](organizing.md)).

## Taking control of individual cards

Each card has a **Numbering** setting in *Basic info*:

| Setting | What happens |
|---|---|
| **Automatic** | Shoggoth numbers the card (the default). |
| **Manual** | You type the card's numbers yourself, and Shoggoth leaves them alone. Automatic numbering **skips** the numbers you've taken, so they aren't used twice. |
| **Ignored** | The card isn't numbered, and takes up no number. Use it for cards that aren't part of the product, like promo cards or proxies for cards from another product. |

Manual is how you handle "this card has to be number 1" or "these numbers are reserved for an expansion". Manual numbers can be ranges too, like `12-14`. If you switch a card from *Manual* back to *Automatic*, Shoggoth warns you that its numbers will be recalculated the next time you enumerate.

## Changing what's printed

The numbers are printed through three fields that every card side has. You can override them on the card's **JSON** tab, or in [your own card type](custom-card-types.md):

| Field | Default | Prints |
|---|---|---|
| `collection_number` | `<exn>` | The collection number |
| `collection_icon` | `<exi>` | The project's icon |
| `collection_total` | `<esn>/<est>` on encounter cards | The encounter set number and total |

(See [Advanced text](advanced-text.md#dynamic-values) for what these tags mean.)

For example, to print a card with the number it has in a *different* product, set `"collection_number": "042"` and `"collection_icon": "<image src=\"icons/other_product.png\">"` on its front. To leave off the encounter set numbering, set `"collection_total": ""`.

## Every copy as its own file

When you export with **Separate versions** on, each copy of a multi-copy card gets its own image with its own number (`4/20`, `5/20`, `6/20`) instead of one image numbered `4-6/20`. See [Exporting card images](exporting.md).

---

Next: **[Making your own card types →](custom-card-types.md)**
