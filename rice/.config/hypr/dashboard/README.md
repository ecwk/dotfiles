# Glass Dashboard

A native, interactive desktop dashboard for Hyprland. Four GTK4 layer-shell panels sit above the wallpaper and below application windows on every workspace. Source lives in this Hyprland repository; the launcher, systemd unit and application entry are symlinks, not copied configurations.

## Use

- **Super + Shift + D** opens Vicinae Dashboard Controls. Select a fixed layout there; widgets cannot be dragged or resized manually.
- Click **btop** to interact with it. `q` quits only btop. The program automatically relaunches in the same panel when it exits. Repeated fast exits use an increasing delay to avoid a restart loop. Regular btop settings are unaffected. Process termination actions inside btop are real actions, just as in a normal terminal.
- Music controls use existing MPRIS players. **Automatic** prefers a currently playing player; the dropdown in settings allows an explicit choice. Missing capabilities are disabled. Progress is read-only. CAVA visualises all system output, not only the selected player.

- **Fastfetch** runs directly inside a terminal, with a small Arch logo and nine aligned lowercase keys: `os`, `wm`, `up`, `cpu`, `gpu`, `ram`, `swap`, `disk`, `bat`. Only the root partition is shown. Fastfetch runs every 30 seconds and its native ANSI output is rendered directly in a fitted, non-interactive terminal. The final newline is removed before rendering to prevent the Arch logo tip from scrolling away. Edit `data/fastfetch.jsonc` to customise this layout.

## Install / reproduce

Verified on Arch Linux, Hyprland 0.56.2 with its existing `.conf` configuration, GTK4 4.24.1 and gtk4-layer-shell 1.3.0. `VERSIONS.txt` records the actual dependency inventory. No framework upgrades are needed.

```sh
sudo pacman -S --needed python python-gobject python-cairo gtk4 gtk4-layer-shell vte4 btop fastfetch cava
/usr/bin/python ~/.config/hypr/dashboard/install.py
```

The installer refuses to replace unrelated files. It adds one include to `hyprland.conf`, checks compositor configuration errors, then enables the user service. It is deliberately version-gated to Hyprland 0.56 and does not migrate your desktop configuration. GTK must use Wayland and preload layer-shell; **always run `launch` / `glass-dashboard` rather than `python app.py`**.

| Expected location | Single source in this repository |
|---|---|
| `~/.local/bin/glass-dashboard` | `dashboard/launch` |
| `~/.config/systemd/user/glass-dashboard.service` | `dashboard/integration/glass-dashboard.service` |
| `~/.local/share/applications/io.github.ecwk.GlassDashboard.desktop` | `dashboard/integration/io.github.ecwk.GlassDashboard.desktop` |
| Include in `hyprland.conf` | `dashboard/integration/hyprland.conf` |

No nested Git repository is created. Commit this directory and the include in the parent Hyprland repository when ready. No remote publishing is performed. If you move/clone the repository, uninstall the old links before running the installer from the new location.

## Configuration and recovery

- `style.css`: shared glass appearance. Background blur uses existing compositor blur settings, scoped to `glass-dashboard-*`. This is frosted transparency, not optical refraction. The launcher disables GTK 4.24’s empty `ext_background_effect_manager_v1` region for this application only, allowing Hyprland’s scoped blur rule to apply. This behavior was verified against [GTK 4.24.1 source](https://github.com/GNOME/gtk/blob/4.24.1/gdk/wayland/gdkdisplay-wayland.c) and [Hyprland 0.56.2 rendering](https://github.com/hyprwm/Hyprland/blob/v0.56.2/src/render/Renderer.cpp).
- `data/layouts.json`: eight fixed layouts in logical pixels. Balanced center is centered on both axes. Bottom command deck is anchored 32 pixels above the bottom; other presets are centered. Selection is remembered per display. Layouts shrink as a group when needed; very small displays may not support the terminals’ minimum readable size.
- `data/btop.conf`, `data/fastfetch.jsonc` and `data/cava.conf`: dashboard-only terminal and visualiser presets.
- `~/.local/state/glass-dashboard/settings.json`: chosen display, per-display layout/visibility. Mode 0600, not tracked by Git. Terminal and runtime files are also under this state directory.

```sh
systemctl --user status glass-dashboard
journalctl --user -u glass-dashboard -n 60
systemctl --user restart glass-dashboard
glass-dashboard --restart-terminal
glass-dashboard --reset-layout
```

Disconnecting the preferred monitor moves panels to an available monitor; reconnecting restores the preferred output and its saved layout. GTK layer-shell surfaces remain on all workspaces and are covered by fullscreen windows. The user service restarts after crashes, cleans up its child processes on exit, and stops with the graphical session. It does not run at the lock/login screen.


## Remove

```sh
/usr/bin/python ~/.config/hypr/dashboard/install.py --uninstall
```

This stops/disables the service, removes only its own symlinks and include, and reloads Hyprland. Source and personal state are preserved. A pre-install copy of the main configuration is kept in the local state directory for reference; uninstall removes the include instead of restoring an old file over later edits.

## Verification

```sh
/usr/bin/python -m unittest discover -s ~/.config/hypr/dashboard/tests -v
```

`tests/live_check.py` is an opt-in desktop integration check. Stop the installed dashboard first; run it with `GDK_BACKEND=wayland`, `LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so` and an isolated `GLASS_DASHBOARD_STATE` directory. It opens real panels, sends `q` to its btop child, checks recovery. It never sends terminal input to another application. `probe.py` is the minimal layer-shell/VTE feasibility example.

## Upstream references

- [GTK4 Layer Shell](https://wmww.github.io/gtk4-layer-shell/gtk4-layer-shell-GTK4-Layer-Shell.html); installed 1.3.0 GIR used for exact signatures.
- [VTE GTK4 spawn API](https://gnome.pages.gitlab.gnome.org/vte/gtk4/method.Terminal.spawn_async.html); installed 0.84.1 introspection used for Python callback arguments.
- [Hyprland 0.56.2 config selection](https://github.com/hyprwm/Hyprland/blob/v0.56.2/src/config/ConfigManager.cpp).
- [CAVA 1.0.0 configuration](https://github.com/karlstav/cava/blob/1.0.0/example_files/config).
- [MPRIS Player interface](https://specifications.freedesktop.org/mpris-spec/latest/Player_Interface.html).


The panel theme is neutral black/grey. Btop uses its original Default theme unless opted into Full theme. The panel background remains neutral black. [VTE child-exited](https://gnome.pages.gitlab.gnome.org/vte/gtk4/signal.Terminal.child-exited.html) triggers terminal recovery.

- [Fastfetch 2.69.0 schema](https://raw.githubusercontent.com/fastfetch-cli/fastfetch/2.69.0/doc/json_schema.json); exact module formats and native `--watch` usage verified against the installed binary’s help.

Fastfetch framing uses [VTE feed](https://gnome.pages.gitlab.gnome.org/vte/gtk4/method.Terminal.feed.html), with character metrics and input handling checked against the installed VTE 0.84.1 introspection.

## Wallpaper theme modes

Vicinae’s **Dashboard Controls** command has **Full theme**, **Accents only**, and **Original** appearance modes.
Full theme is the initial default and follows the committed walltheme mode (dark or light).
Accents only applies the wallpaper accent to playback, progress, visualizer bars, Fastfetch keys/logo,
and focus/selection highlights, keeping neutral glass and Default btop colors.
Original restores the previous neutral glass, blue Fastfetch accent, and Default btop colors.
Music artwork retains its original colors in every mode.

Btop has independent **Style TUI** and **Style background** switches, available in Full theme.
Style TUI recolors the actual terminal text/graphs; Style background changes only the glass panel.
With both off, btop keeps its Default theme and neutral dark glass. Background changes do not restart btop.
Changing its effective theme restarts btop.
The choice is remembered when switching modes. Appearance settings persist in local settings.json.

Colors come from the seven semantic roles in `${XDG_STATE_HOME:-$HOME/.local/state}/walltheme/current.json`,
following the dotfiles AGENTS.md contract. The containing directory is watched for atomic replacement;
committing another wallpaper theme reloads colors automatically. Invalid updates retain the last valid
palette; when none is available, the dashboard falls back to Original and shows a settings notice.
Generated btop themes/configs stay in the dashboard state directory; normal application configs are untouched.

Implementation references: [Gio directory monitoring](https://docs.gtk.org/gio/method.File.monitor_directory.html)
and [VTE palette API](https://gnome.pages.gitlab.gnome.org/vte/gtk4/method.Terminal.set_colors.html),
checked against installed GLib 2.90.1 and VTE 0.84.1 GIR signatures (online docs use different minor versions).
Btop role names/path loading follow [btop 1.4.7 source](https://github.com/aristocratos/btop/blob/v1.4.7/src/btop_theme.cpp)
and its installed theme examples. Fastfetch 2.69.0 accepts generated config through stdin (`--config -`).

Fastfetch GPU detection uses PCI enumeration with `hideType: integrated`; when none is detected, the GPU row says “Dedicated GPU unavailable”. Swap usage appears directly below RAM. Bluetooth and weather widgets have been removed; installed system packages are left in place.

The GPU field first queries `nvidia-smi --query-gpu=name --format=csv,noheader` (NVIDIA utilities 615.78.08). A successful name is cached locally. When the driver is unavailable, `data/gpu.json` supplies an explicit fixed name, then the last detected name is tried. With neither available, native Fastfetch PCI detection remains the fallback. The field widens to fit long GPU names. Reference: [NVIDIA SMI query documentation](https://docs.nvidia.com/deploy/nvidia-smi/index.html).

Btop is launched with `--themes-dir` pointing to the generated theme directory. Btop 1.4.7 only resolves `color_theme` against its scanned theme list, even for absolute paths. `tests/btop_palette_check.py` checks real ANSI foreground/accent output in a temporary PTY to catch silent fallback to Default.

## Vicinae controls

Open Vicinae and search **Dashboard Controls**, or press Super+Shift+D. The Layout section offers:
Balanced center, Compact bento, Floating corners, Bottom command deck, System monitor first,
Staggered editorial, Wide terrace, and Stacked canopy. The last two reproduce the unnamed references.
The picker applies immediately and remembers the selection per display. Drag/edit/export actions
have been removed. `--reset-layout` selects Balanced center. The same controls include independent
btop styling, visibility, monitor/player selection and recovery. Appearance is under Theme Settings.


The native extension source is in `vicinae/`, pinned to @vicinae/api 0.20.5. Build with `npm ci`,
`npm run typecheck`, and `npm run build -- --out dist` from that directory. Copy the built dist
contents to `rice/.local/share/vicinae/extensions/glass-dashboard` in this dotfiles repository;
`~/.local/share/vicinae/extensions/glass-dashboard` links to that directory. Remove that link to
uninstall the Vicinae command. The dashboard's validated `--control` JSON interface keeps the
running application in charge of its state; the extension does not edit state files behind it.
Reference: [Vicinae native extension API](https://docs.vicinae.com/extensions/introduction), checked
against the pinned SDK's installed TypeScript declarations.

The user service uses `Type=dbus` with the application BusName so launcher commands wait for a ready command endpoint; verified against the installed systemd.service(5) manual. Open directly with `vicinae deeplink vicinae://extensions/ecwk/glass-dashboard/dashboard`.

### Artwork-colored music player

Dashboard Controls → Music Player → **Music appearance** contains the **iOS album art colors**
checkbox. It defaults on, applies immediately, and persists as `ios_album_art` in settings.
The `--control` interface exposes `iosAlbumArt` in status and accepts
`{"action":"iosAlbumArt","value":true}` (a boolean is required).

The player follows the reference's artwork/title row, elapsed/remaining timeline and centered
transport controls, omitting the corner icons. It fits the existing layout presets; narrow
allocations hide artwork/time labels and place progress below the controls. Artwork colors
remain while paused. Missing or invalid artwork and disconnected players fall back to the
current dashboard theme. Turning the checkbox off also restores that theme.

The background is enlarged, heavily blurred artwork under a dark neutral veil, clipped to
the rounded card. It is an approximation of the iOS look, not Apple's private algorithm.
The original thumbnail remains unmodified. Scoped music CSS takes precedence over wallpaper
colors only when valid artwork is active. No new packages are required.

Rendering follows [GTK 4.24.1 Snapshot blur](https://docs.gtk.org/gtk4/method.Snapshot.push_blur.html)
and installed GTK/GSK GIR signatures. The settings checkbox uses the pinned Vicinae 0.20.5
`Form.Checkbox` declarations (the online form documentation was unavailable).
Run `GDK_BACKEND=wayland LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so /usr/bin/python tests/music_live_check.py`
for an isolated visual/state check; it saves `/tmp/music-preview.png` and does not control a real player.

Music appearance also has **Dark mode darkness**, a 0–100% selector in 5% steps
(default 65%). It applies immediately, persists as `music_darkness`, and affects
only dark mode. The control API exposes `musicDarkness` and accepts the same
integer percentage through `{"action":"musicDarkness","value":65}`.
Vicinae SDK 0.20.5 has no slider component; this uses its supported `Form.Dropdown`
interface, verified against the installed version's declarations.
