# Planning locations and maps

[← Back to the manual](manual.md)

## Connecting locations on the cards

Each location has a **connection symbol** (its own symbol, printed at the top) and a list of symbols it **connects to** (printed at the bottom). In the location's editor, pick its own symbol and use **+ add symbol** to add connections. Symbols already used by another location in the set are dimmed, so it's easy to see which ones are free. Besides the original symbols, there's a set of alternates for when you run out.

## The location view

Each encounter set has a **Locations** entry in the tree. Click it to see all the set's locations laid out as a map, with arrows for their connections. Use it to check that the map makes sense, and to build the map for your campaign guide.

| To... | Do this |
|---|---|
| Move a location | Drag it (turn on **Snap to Grid** for neat rows) |
| Zoom | Mouse wheel |
| Connect two locations | Right-drag from one to the other. Shoggoth updates both cards, and asks for a connection symbol if one of them has none yet. |
| Remove a connection | Right-click the arrow and choose *Remove Connection* |
| See the other side of a location | **F** flips the location under the mouse, **Shift+F** flips all of them. Revealed and unrevealed sides can have different connections. |
| Hide a location temporarily | **H** hides the location under the mouse, and **Shift+H** toggles whether hidden locations are shown. Hidden locations are listed on the side, where you can unhide them. |
| Show symbols instead of cards | The icon toggle shows each location as its connection symbol, which gives a compact overview |

**Simulate** shuffles the locations around automatically, pushing connected locations together and unconnected ones apart. It's a quick way to untangle a messy map. Click it again to stop.

### Several layouts

A scenario sometimes changes its map partway through, or you might want one map per act. The **+** tab adds another **layout** of the same set. Each layout remembers its own positions. You can also add locations from other encounter sets (**Add Locations From Set**) or any single card (**Add Card**), for example when a scenario combines two sets.

### Arrows and decorations

**Show Arrows** turns the connection arrows on and off. **Fixed Length Arrows** draws short, centered arrows between locations like the official guides do. **Add Arrow** adds a free-standing arrow that isn't tied to a connection. Drag it to move it, drag its ends to resize and rotate it, and right-click it to change its color or make it double-headed.

## Using the map in your campaign guide

Click **Export** to save the current layout as an image in the project's export folder. In a campaign guide, `[encounter:<id>:location_overview:0]` shows the first layout of that set (`:1` shows the second, and so on). *Insert → Location Layout* in the guide editor adds this for you. See [Writing a campaign guide](campaign-guides.md).

**Screenshot** copies the view to the clipboard, ready to paste into any other program.

---

Next: **[Sharing your project →](sharing.md)**
