# Wallpapers & Colors

A Vicinae 0.20.5 extension for local wallpaper previews, Wallhaven discovery,
and seven reusable theme colors. Built for Hyprland/Hyprpaper 0.8.4 and Waypaper
2.8. Palette generation uses a pinned, user-local Matugen 4.2.0 binary.

## Using Vicinae

**Select Wallpaper** lists the collection configured in Waypaper, recursively.
The focused monitor's active wallpaper appears first with **✓ Active** and monitor
names. Active images outside the collection are included if their files exist.
Moving selection previews the wallpaper after 150 ms. **Previewing** identifies
the temporary selection; the Active badge stays on the committed wallpaper.

Press Enter to save wallpaper and theme colors. Escape, navigation back, closing
Vicinae, or loss of the extension process restores the original per-monitor
wallpapers. A successful Apply becomes the new baseline for subsequent previews.
A failed rollback retains its recovery journal for retry on the next session.
The helper serializes changes and allows only one preview session per Hyprland
instance. Changes apply to all currently connected monitors.

The detail panel displays an image plus labeled swatches and hex values. Scroll
the details to see all seven colors. The Dark/Light dropdown changes the palette
shown and the mode committed when you apply. It does not theme any applications.

**Search Wallpapers** searches Wallhaven's SFW collection. Its Actions menu
contains minimum-resolution and aspect-ratio filters plus Load More Results.
Browsing downloads thumbnails only; thumbnail-derived colors are labeled
**Estimated**. **Try Wallpaper** explicitly downloads the original and previews
it temporarily. **Save and Apply** saves it under `wallhaven/` in your configured
collection and commits it. **Save to Collection** does not apply it. Source links
are retained in adjacent `.source.json` files. An original is cached after its
first download. Downloads can be cancelled from Actions.

Commands can also be launched with:

```sh
vicinae deeplink vicinae://extensions/ecwk/walltheme/select-wallpaper
vicinae deeplink vicinae://extensions/ecwk/walltheme/search-wallpapers
```

## Accessing the colors

```sh
walltheme get accent
walltheme get background --mode light
walltheme get accent --image /path/to/wallpaper.jpg
walltheme extract /path/to/wallpaper.jpg
walltheme scan
walltheme export --format json

eval "$(walltheme export --format shell)"
printf '%s\n' "$WALLTHEME_ACCENT"
```

Shell exports contain only these fixed variable names and validated hex values:

| JSON key | Shell variable | Meaning |
|---|---|---|
| `background` | `WALLTHEME_BACKGROUND` | Main background |
| `surface` | `WALLTHEME_SURFACE` | Panels |
| `foreground` | `WALLTHEME_FOREGROUND` | Primary text |
| `muted` | `WALLTHEME_MUTED` | Secondary text |
| `border` | `WALLTHEME_BORDER` | Separators |
| `accent` | `WALLTHEME_ACCENT` | Focus and primary actions |
| `on_accent` | `WALLTHEME_ON_ACCENT` | Text on accent backgrounds |

The shared source of truth is:

```text
${XDG_STATE_HOME:-~/.local/state}/walltheme/current.json
```

For the default directories:

```sh
jq -r '.colors.accent' ~/.local/state/walltheme/current.json
jq '.palettes.light' ~/.local/state/walltheme/current.json
```

`current.json` contains `schemaVersion: 1`, image `id` and `sha256`, the absolute
`wallpaper` path, generator metadata, `mode`, active `colors`, and both
`palettes.dark` and `palettes.light`. Hex values are uppercase `#RRGGBB`.
Additional `swatches` paths are used by the picker. Consumers should ignore
unknown fields. Publication uses atomic replacement; file-watch consumers should
watch the **containing directory**, then reopen `current.json` after changes.

Previewing never updates `current.json` or Waypaper's saved configuration.
Shell exports affect the current shell and future child processes only; existing
applications should reread JSON when they need new colors.

Generated palettes and the image-path index live under
`${XDG_DATA_HOME:-~/.local/share}/walltheme/`. Content hashes and the pinned recipe
identify palette records. The picker refreshes the collection and extracts
missing/stale palettes in the background. `walltheme scan` explicitly regenerates
missing records and reports unreadable files without stopping the batch.
Online search caches live under `${XDG_CACHE_HOME:-~/.cache}/walltheme/`; search
responses expire after 15 minutes, while downloaded images are reused.

## Setup and maintenance

From this directory, on x86_64 Linux with Node/npm and system Python installed:

```sh
/usr/bin/python3 bootstrap.py
```

The bootstrap verifies the official Matugen archive against its release SHA-256,
installs locked npm dependencies, checks/builds the extension, installs it, and
scans the collection. It does not upgrade system packages. The built extension
uses the matching Vicinae SDK; npm's build-tool dependencies are not copied into
the installed bundle.

For source changes after dependencies are installed:

```sh
npm run typecheck
npm run build -- --out dist
/usr/bin/python3 install.py
/usr/bin/python3 -m unittest -v test_walltheme.py
```

Installed files:

- CLI: `~/.local/bin/walltheme` → the data directory's `walltheme/lib/walltheme.py`
- Extension: the data directory's `vicinae/extensions/walltheme/`
- Login hook: `exec-once = uwsm app -- ~/.local/bin/walltheme restore`
- Backups: the state directory's `walltheme/backups/<timestamp>/`
- Preview logs: the state directory's `walltheme/preview.log`

The installer removes the original script picker after backing it up, preventing
duplicate commands. If Vicinae was running before its extensions directory first
existed, restart it once to discover the extension. Login restoration waits for
Hyprpaper and recovers an interrupted session before asking Waypaper to restore.

## Validation and current limits

Verified: TypeScript compilation; nine transaction tests (including failure
rollback, competing requests, window closure, lost heartbeat and crash recovery);
live preview/cancel, commit and helper-crash recovery on Hyprpaper; both screens
rendering in Vicinae; real Wallhaven search, thumbnails, original download, cache
reuse and save; cancelled downloads and rate-limit errors; deterministic palette
records and text contrast above 4.5:1 for the generated collection.

A full logout/login was not performed. Per-monitor restoration was tested with
two simulated monitors and the currently connected physical display. Existing
Waypaper `use_xdg_state = False` is required. Paths containing commas or newlines
are rejected by preview because Hyprpaper's command syntax uses commas. Supported
collection extensions are PNG, JPEG, WebP and JPEG XL; actual decoder failures are
reported per image. Wallpapers use Hyprpaper's default cover placement.

No application theme adapters, terminal palettes, or semantic status colors are
installed. Cached originals are limited to 50 MB per download, thumbnails to 5 MB.

References:

- [Vicinae 0.20.5 List API](https://github.com/vicinaehq/vicinae/blob/v0.20.5/src/typescript/api/src/api/components/list.tsx)
- [Vicinae extension installation](https://docs.vicinae.com/install-extensions)
- [Matugen 4.2.0 command options](https://github.com/InioX/matugen/blob/v4.2.0/src/util/arguments.rs)
- [Hyprpaper 0.8.4 IPC](https://github.com/hyprwm/hyprpaper/blob/v0.8.4/src/ipc/IPC.cpp)
- [Wallhaven API](https://www.whvn.cc/help/api)
- [XDG directory specification](https://specifications.freedesktop.org/basedir/latest/)
