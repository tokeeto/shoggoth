# Sharing your project

[← Back to the manual](manual.md)

There are three ways to share: **send the files**, **work on the project together in the cloud**, or **publish** finished content to the Library of Celaeno for others to find.

## Sending the project files

A project is one `.json` file. Your art is **not** inside it. The project only stores the path to each image. To send someone a project that works on their computer:

1. Run **File → Gather images and update**. It copies the project's images (illustrations, extra card images, encounter set icons and the project icon) into a `<project name> images` folder next to the project file, and changes the project to use those copies through relative paths.
2. Zip the project's folder and send it.

The recipient unzips it and opens the `.json` file with **File → Open Project**. Everything is found, because it's all relative to the project file.

Images inside card text (`<image src="...">`), custom fonts and custom card types aren't gathered. Keep those in the project folder yourself and refer to them with relative paths.

**File → Gather images** (without "and update") only copies the images and leaves the project as it is. Use it to make a backup of your art.

```
My Campaign/
  My Campaign.json          ← the project
  My Campaign images/       ← from "Gather images and update"
  Export of My Campaign/    ← exports
```

> **Moving the project file on its own?** **File → Save Project As** saves under a new name or location. Images with relative paths are still looked up next to the *new* file, so move the images along with it.

### When someone else changes the file

If the project file changes on disk while it's open in Shoggoth, Shoggoth notices. This can happen when you're sharing it through Dropbox or git, or editing it in a text editor. Shoggoth then asks what to do:

- **Reload from Disk**: take the new version. Any unsaved changes you have are lost.
- **Save As...**: keep your version as a separate file, and leave theirs untouched.
- **Keep My Version**: keep working. Your next save overwrites their changes.

Shoggoth only asks when the *content* actually changed, not when the file was just re-saved.

## Working together in the cloud

**Cloud projects** live on the Library of Celaeno's servers and **sync automatically** between everyone working on them. Several people can edit the same project, and each person's changes show up for the others.

To use the cloud, you need a **Library of Celaeno** account with access. Create one at [celaeno.cards](https://celaeno.cards). Access comes with supporting Shoggoth on Patreon (link your Patreon on the website), or can be granted by the maintainers. Then sign in from the **Cloud** menu, or from **File → Settings → Publishing**.

With the **Cloud** menu you can:

- **New Cloud Project...**: start a new project in the cloud.
- **Save Project to Cloud**: make a cloud copy of the project you have open. Your original file stays as it is. From then on you work on the cloud copy.
- **Open Shared Project...**: open a cloud project someone has shared with you.
- **Upload New File...**: add images or fonts to a cloud project. Use this instead of pointing to files on your own disk, so your collaborators get them too.

To invite people, right-click the cloud project in the tree and choose **Share...**. Enter their email and choose a role:

- **Viewer** can open the project and export from it, but not change it.
- **Editor** can change everything.

Sync happens in the background. Opening a cloud project is instant, and changes are pulled in and pushed out as you work. If you and a collaborator change the *same card* at the same time, Shoggoth asks whether to **keep your version** or **use theirs**. Changes to different cards never conflict.

Your own copy is never thrown away because the cloud misbehaves:

- If Shoggoth can't reach the cloud, or the cloud reports an error, it tells you once and keeps your project exactly as it is. Keep working and saving as usual. Your saved changes are sent as soon as the cloud accepts them again, even if you close Shoggoth in the meantime.
- If the cloud copy is missing cards, encounter sets or guides that you still have, Shoggoth asks before removing anything. Choose **Keep and Upload Again** to keep them and send them back up. This is the default. Choose **Remove Here** only if you know a collaborator deleted them.

## Publishing to the Library of Celaeno

The [Library of Celaeno](https://celaeno.cards) is a community library of fan-made Arkham Horror content. When your project is ready for others to play, you can submit it from Shoggoth.

1. Sign in (see above).
2. Open **Export → Export Project** and make an export setup with the things you want to share: **Images**, a **PDF**, a **Tabletop Simulator** object, the **Guides**, and **arkham.build** data.
3. Add a **Submit to cloud** entry *last*. It uploads what the entries above it produced.
4. Fill in the project's **Meta** tab (author, description, banner image) in the project editor. It's shown on your project's page.

Your submission is reviewed before it appears in the public catalogue. Anyone with an account can see it in the meantime. To update it, run the same setup again. The TTS object is automatically changed to use the uploaded images, so it works for everyone.

Translations are published the same way. They're added to the original project's page, which must already be published (see [Translating a project](translating.md)).

---

Next: **[Translating a project →](translating.md)**
