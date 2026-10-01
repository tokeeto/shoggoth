# Printing your cards

[← Back to the manual](manual.md)

Whether you're printing a playtest copy at home or ordering a finished product from a print shop, you'll use a **PDF** entry in an export setup (see [Exporting card images](exporting.md)). The entry's **PDF flavor** decides the layout.

## Before you start: install Prince

Shoggoth uses a program called **Prince** (free for personal use) to build PDFs. Choose **Export → Install Prince...** and Shoggoth downloads it (about 20 MB) and sets it up. You only need to do this once. If Prince is already installed on your system, you can point Shoggoth at it in **File → Settings → External Applications** instead.

## Printing at home

Use the **Plain PDF** flavor. It lays the cards out on A4 pages, each card followed by its back, with every copy of a card included. Print, cut, and sleeve them. An old card behind each one in the sleeve makes it stiff enough to shuffle.

Useful options:

- **Render rounded card corners**: prints each card at its exact size with rounded corners, so you just cut along the edges. There's no bleed to trim.
- **Export text as vector PDF text** (experimental): the card text is printed as real text instead of pixels, so it's crisp at any size, even from low-resolution card images.
- **Size / Format / Quality**: for home printing, the middle size in JPEG at 90–95% quality looks good and keeps the PDF small. A full campaign at print resolution in PNG can take several minutes and produce a PDF of several gigabytes. At the middle size in JPEG, it takes seconds and makes a few hundred megabytes.

## Ordering from a print shop

Print shops want every card as a separate page, with **bleed**: an extra margin of art around the card that gets cut away, so there are no white slivers if the cut is slightly off. Shoggoth has flavors for two popular shops:

- **MBPrint**: one card per page at the resolution and format MBPrint expects. Upload the PDF as-is.
- **Azao**: two PDFs, one with all the fronts and one with all the backs, one card per page, in matching order. Set both output files.

For other shops, check their requirements for card size, bleed and file type. Often an **Images** entry is all you need, with bleed on, the largest size, and the **Order number** file name format, plus *Separate versions* so every physical copy gets its own file. The **MTG** sizes match the 63.5×88 mm cards most shops print. The **FFG** sizes match official cards exactly.

### Color for professional printing

Screens show color as RGB, and printing presses use CMYK. Home printers handle the conversion themselves, but a professional shop may ask for CMYK files. In **File → Settings → External Applications**, choose a **CMYK output profile** (an ICC file, such as the *Fogra39L* profile many European shops use). All PDF exports are then converted to press-ready CMYK. Leave it empty for home printing.

Always order a single proof copy before a big print run. Colors, text size and cutting tolerances are much easier to judge on paper.

## Checking your cards before printing

- In the preview, turn on **Show bleed** (**Settings → Display**) to see what will be cut off. Keep important text and faces out of the red area.
- The **Trim: FFG / MTG** toggle above the preview shows the card at either width, so you can check that nothing important sits near the edge.

## Printing your campaign guide

Campaign guides are exported as PDF from the guide editor, or with a **Guides** entry in an export setup. See [Writing a campaign guide](campaign-guides.md).

---

Next: **[Playing digitally →](playing-digitally.md)**
