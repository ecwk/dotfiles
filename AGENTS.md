# Agent instructions

## Accessing wallpaper theme colors

The `walltheme` CLI exposes the theme committed by the Vicinae wallpaper picker.
Use its semantic color roles when integrating applications; do not hardcode the
current wallpaper's hex values.

```sh
walltheme get accent
walltheme get background --mode light
walltheme get accent --image /path/to/wallpaper.jpg
walltheme export --format json
```

The seven roles are `background`, `surface`, `foreground`, `muted`, `border`,
`accent`, and `on_accent`. Values are `#RRGGBB`. Both dark and light palettes are
available; the committed mode determines the default returned by the CLI.

For shell scripts that need environment variables:

```sh
eval "$(walltheme export --format shell)"
printf '%s\n' "$WALLTHEME_ACCENT"
```

The exports are `WALLTHEME_BACKGROUND`, `WALLTHEME_SURFACE`,
`WALLTHEME_FOREGROUND`, `WALLTHEME_MUTED`, `WALLTHEME_BORDER`,
`WALLTHEME_ACCENT`, and `WALLTHEME_ON_ACCENT`. These affect the current shell and
future child processes. Already-running applications must reread the JSON file
or use an application-specific reload mechanism.

### JSON interface for applications

Read `${XDG_STATE_HOME:-$HOME/.local/state}/walltheme/current.json`.
Use `.colors.<role>` for the committed mode, `.mode` for its name, and
`.palettes.dark.<role>` or `.palettes.light.<role>` for an explicit variant.
The document also contains `schemaVersion`, wallpaper identity, and generator
metadata. Ignore unknown fields.

```sh
jq -r '.colors.accent' "${XDG_STATE_HOME:-$HOME/.local/state}/walltheme/current.json"
jq '.palettes.light' "${XDG_STATE_HOME:-$HOME/.local/state}/walltheme/current.json"
```

Publication replaces the file atomically. Watch its containing directory for
changes and reopen the JSON file, rather than keeping its old inode open.
Temporary wallpaper previews do not update the committed theme file or saved
wallpaper settings. Only an explicit Apply publishes a new selection.

### Per-wallpaper palettes and documentation

Generated palettes and the wallpaper-path index are stored under
`${XDG_DATA_HOME:-$HOME/.local/share}/walltheme/`. Use the CLI to retrieve a
specific image's palette rather than depending on internal hashed filenames.
`walltheme extract IMAGE` generates/stores both variants without applying them;
`walltheme scan` refreshes palettes for the configured wallpaper collection.

The maintained source and detailed usage/rebuild documentation are in
[`extras/vicinae-wallpapers/README.md`](extras/vicinae-wallpapers/README.md).
The deployed extension and backend are in the `rice/.local/share/vicinae/extensions/walltheme/`
and `rice/.local/share/walltheme/lib/` directories, linked into the home directory.
