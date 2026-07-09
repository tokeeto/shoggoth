# Shoggoth for Sublime Text

Edit a Shoggoth project file (plain JSON) in Sublime Text and preview the card
under your cursor as a rendered image, without leaving the editor.

Place the cursor anywhere inside a card's JSON block and run
**Shoggoth: Preview Card at Cursor** from the command palette. The plugin
finds the enclosing card, invokes the Shoggoth CLI (`-r <project> -id <card>`)
in the background, and shows the rendered front and back in a reusable
scratch tab. Re-running it updates the same tab.

Requires Sublime Text 4.

## Install

Symlink this directory into your Sublime `Packages` folder as `Shoggoth`:

```bash
# Linux
ln -s /path/to/shoggoth/plugins/sublime ~/.config/sublime-text/Packages/Shoggoth

# macOS
ln -s /path/to/shoggoth/plugins/sublime ~/Library/Application\ Support/Sublime\ Text/Packages/Shoggoth
```

(The package name must be `Shoggoth` for the settings entry in the command
palette to resolve.)

## Configure

Open **Preferences: Shoggoth Settings** from the command palette. The one
thing you must decide is how Shoggoth is launched:

```jsonc
// Development checkout:
{
    "command": ["uv", "run", "shoggoth"],
    "working_dir": "~/Workspace/shoggoth"
}

// Installed version:
{
    "command": "uvx shoggoth"        // or "pipx run shoggoth"
}
```

`command` may be a list of arguments or a shell-style string. The plugin
appends `-r <project> -id <card_id> -o <tmpdir> -f png -s <render_size>`.

### Faster previews

Every render normally checks GitHub for asset-pack updates. Once you have the
assets downloaded (run Shoggoth once normally), skip that check:

```jsonc
{
    "env": { "SHOGGOTH_UNMANAGED_ASSETS": "1" }
}
```

Lower `render_size` (`1` = half, `2` = quarter resolution) also speeds things
up considerably; the preview is downscaled anyway.

### All settings

| Setting | Default | Meaning |
|---|---|---|
| `command` | `["uv", "run", "shoggoth"]` | Base command to launch Shoggoth |
| `working_dir` | project file's folder | Directory the command runs in |
| `extra_args` | `[]` | Extra CLI args inserted before the plugin's flags |
| `env` | `{}` | Extra environment variables for the subprocess |
| `render_size` | `1` | 0 = full, 1 = half, 2 = quarter resolution |
| `bleed` | `false` | Render with bleed margins |
| `image_width` | `420` | Display width (px) per face in the preview tab |
| `save_on_render` | `true` | Save the file before rendering |
| `timeout` | `120` | Seconds before the render subprocess is killed |

## Key binding

No binding is installed by default. Add one via
**Preferences → Key Bindings**, e.g.:

```json
{ "keys": ["ctrl+shift+r"], "command": "shoggoth_preview_card" }
```

## Tips

- If you split the window into two groups (`View → Layout → Columns: 2`), the
  preview tab is created in the other group so it sits next to the JSON.
- Render failures open an output panel with the exact command and its
  stdout/stderr.
- The card is read from **disk**, so the file is saved before rendering by
  default (`save_on_render`).
