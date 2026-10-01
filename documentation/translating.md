# Translating a project

[← Back to the manual](manual.md)

You can translate a project, yours or someone else's, **without copying it**. A translation is a small separate file that stores only what you changed. The original project is never touched. When its author fixes a typo or changes a card, the translation picks up the change automatically.

The same mechanism works for other changes too, like replacement art, different templates, or house-rule tweaks. Shoggoth calls all of these **modifications**. A translation is just the most common kind.

## Starting a translation

1. Open the original project.
2. Choose **Project → New Modification / Translation...**.
3. Choose **Translation** as the kind and pick (or type) the **language**. Choosing a language also sets the card language, so the text Shoggoth prints by itself, such as "ENEMY" or "Revelation –", is translated too.
4. Choose where to save the translation's file. Keep it next to the original project if you can.

The translation appears in the tree as *Project name [language]*. The original project must stay where it is, because the translation looks it up every time it's opened.

To continue later, open the original project and choose **Project → Open Modification / Translation...**. You can also open the translation file directly with **File → Open Project**.

## Translating cards

Select a card. In the **Translation View** (**View → Translation View**, the default for translations), you see each text field twice: the **original** on the left (read-only) and **your translation** on the right. It covers the name, subtitle, traits, rules text, flavor text, victory text and so on, for both sides of the card.

- Fields you haven't translated yet are marked, and a counter shows how many fields of the card you've changed.
- The reset button next to a field puts the original text back.
- In the preview, the **Original** toggle switches between your translated card and the original, for comparison.

For changes beyond text, like art, stats or templates, switch to **View → Modification View**. It shows the full card editor for your version next to a locked editor showing the original.

Encounter set names, the project name and campaign guides can be translated the same way. Select them in the tree as usual.

## What you can't do in a modification

A modification changes what's *in* the original. It can't add or remove cards, encounter sets or guides. If your translation needs an extra card, ask the original author, or make a copy of the project instead.

## Replacement art

In a modification, image paths are looked up in the modification's own folder first, then in the original project's folder. To replace an image, for example art with text painted into it, put a file with the same relative path next to your translation file.

## Exporting a translation

Every export works on a translation exactly as on a normal project: images, PDFs, Tabletop Simulator and export setups. The exported cards contain the translated text, the translated automatic labels, and any replaced art.

Because a translation only stores text, the translator doesn't even need the original art. The original author can open your translation file next to their own project and export it with all their images.

## Sharing a translation

Send the translation file, and any replacement images, to people who have the original project. They open it next to their copy of the original.

To publish a translation to the Library of Celaeno, use a *Submit to cloud* export entry from the translation, like any other project (see [Sharing your project](sharing.md#publishing-to-the-library-of-celaeno)). The original project has to be published first. The translation is then listed on the original's page.

> Older versions of Shoggoth stored translations in a different format. Those files still open, and are converted to the new format the next time you save them.

---

Next: **[Advanced text →](advanced-text.md)**
