# Glass Dashboard

A native, interactive desktop dashboard for Hyprland. Nine GTK4 layer-shell panels sit above the wallpaper and below application windows on every workspace. Source lives in this Hyprland repository; the launcher, systemd unit and application entry are symlinks, not copied configurations.

## Use

- **Super + Shift + D** toggles layout editing. Use the small top grip to move a panel and the bottom-right corner grip to resize. Click the edit icon again to lock the layout. Both grips appear only in edit mode. This does not bring widgets over application windows: use an empty workspace or move covering windows aside.
- The small gear icon at the lower-left opens settings to select a display, hides/shows widgets, resets the layout, and restarts the dashboard. The control panel always remains accessible on an uncovered desktop. **Save layout to repo** exports your current arrangement/visibility to `data/layout.json` for Git tracking, without exporting weather coordinates. The equivalent command is `glass-dashboard --export-layout`.
- Click **btop** to interact with it. `q` quits only btop. The program automatically relaunches in the same panel when it exits. Repeated fast exits use an increasing delay to avoid a restart loop. Regular btop settings are unaffected. Process termination actions inside btop are real actions, just as in a normal terminal.
- Music controls use existing MPRIS players. **Automatic** prefers a currently playing player; the dropdown in settings allows an explicit choice. Missing capabilities are disabled. Progress is read-only. CAVA visualises all system output, not only the selected player.
- Weather first requests approximate location through the desktop portal. If unavailable or denied, **Choose location** opens a searchable list. Enter a city, press Enter, and select a matching region/country. **Use my location** switches back. **↻** retries. No IP-location fallback is used.
- Location coordinates are sent to Open-Meteo for forecasts; search text is sent to its geocoding API. Weather and approximate coordinates are stored only in local state, outside this repository. Weather refreshes every 15 minutes, retains cached results offline, and always shows the retrieval time.
- The calendar follows the **standard NUS academic year**, not mini-semesters or programme-specific calendars. The clock uses Asia/Singapore. Weekends stay with the preceding teaching week unless an official recess/reading/examination interval begins. Dates outside the bundled calendar show unavailable coverage.
- **Bluetooth** embeds the installed `bluetui` TUI. `Tab` moves between sections; `o` toggles adapter power; `s` starts/stops scanning; Enter connects/disconnects a paired device or pairs a discovered device. `q` exits only bluetui, which automatically relaunches in the same panel. These controls change real Bluetooth state only when you use them.

- **Fastfetch** runs directly inside a terminal, with a small Arch logo and eight aligned lowercase keys: `os`, `wm`, `up`, `cpu`, `gpu`, `ram`, `disk`, `bat`. Only the root partition is shown. Fastfetch refreshes through its native watch mode every 30 seconds and automatically relaunches if terminated. Edit `data/fastfetch.jsonc` to customise this layout.

## Install / reproduce

Verified on Arch Linux, Hyprland 0.56.2 with its existing `.conf` configuration, GTK4 4.24.1 and gtk4-layer-shell 1.3.0. `VERSIONS.txt` records the actual dependency inventory. No framework upgrades are needed.

```sh
sudo pacman -S --needed python python-gobject python-cairo gtk4 gtk4-layer-shell vte4 btop fastfetch cava geoclue bluetui bluez bluez-utils
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
- `data/layout.json`: default panel positions in logical pixels at 1440×900. Defaults scale for other outputs; btop retains a minimum usable terminal size. Smaller outputs can require manually rearranging or hiding panels.
- `data/academic.json`: explicit intervals transcribed from the official AY2026/2027 calendar, including provenance and revision. Update this file for a subsequent academic year.
- `data/btop.conf`, `data/bluetui.toml`, `data/fastfetch.jsonc` and `data/cava.conf`: dashboard-only terminal and visualiser presets.
- `~/.local/state/glass-dashboard/settings.json`: chosen display, per-display layout/visibility and weather location. Mode 0600, not tracked by Git. Terminal and runtime files are also under this state directory.
- `~/.local/state/glass-dashboard/weather.json`: cached forecast and retrieval timestamp.

```sh
systemctl --user status glass-dashboard
journalctl --user -u glass-dashboard -n 60
systemctl --user restart glass-dashboard
glass-dashboard --restart-terminal
glass-dashboard --restart-bluetooth
glass-dashboard --reset-layout
```

Disconnecting the preferred monitor moves panels to an available monitor; reconnecting restores the preferred output and its saved layout. GTK layer-shell surfaces remain on all workspaces and are covered by fullscreen windows. The user service restarts after crashes, cleans up its child processes on exit, and stops with the graphical session. It does not run at the lock/login screen.

Automatic location depends on the portal, its access/permission backend, GeoClue, and the location provider configured by your distribution. Installing GeoClue alone does not guarantee a position. If no result arrives within 40 seconds, use the picker or retry. A visible backend permission prompt must be answered by you. If permission is denied or cancelled, automatic mode is disabled until you choose **Use my location** again. This setup enabled `org.gnome.system.location enabled`; uninstall leaves this system-wide preference unchanged. To disable it yourself: `gsettings set org.gnome.system.location enabled false`.

## Remove

```sh
/usr/bin/python ~/.config/hypr/dashboard/install.py --uninstall
```

This stops/disables the service, removes only its own symlinks and include, and reloads Hyprland. Source and personal state are preserved. A pre-install copy of the main configuration is kept in the local state directory for reference; uninstall removes the include instead of restoring an old file over later edits.

## Verification

```sh
/usr/bin/python -m unittest discover -s ~/.config/hypr/dashboard/tests -v
```

`tests/live_check.py` is an opt-in desktop integration check. Stop the installed dashboard first; run it with `GDK_BACKEND=wayland`, `LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so` and an isolated `GLASS_DASHBOARD_STATE` directory. It opens real panels, sends `q` to its btop and bluetui children, checks recovery, and tests weather error states. It never sends terminal input to another application. `probe.py` is the minimal layer-shell/VTE feasibility example.

## Upstream references

- [GTK4 Layer Shell](https://wmww.github.io/gtk4-layer-shell/gtk4-layer-shell-GTK4-Layer-Shell.html); installed 1.3.0 GIR used for exact signatures.
- [VTE GTK4 spawn API](https://gnome.pages.gitlab.gnome.org/vte/gtk4/method.Terminal.spawn_async.html); installed 0.84.1 introspection used for Python callback arguments.
- [Hyprland 0.56.2 config selection](https://github.com/hyprwm/Hyprland/blob/v0.56.2/src/config/ConfigManager.cpp).
- [CAVA 1.0.0 configuration](https://github.com/karlstav/cava/blob/1.0.0/example_files/config).
- [MPRIS Player interface](https://specifications.freedesktop.org/mpris-spec/latest/Player_Interface.html).
- [Location portal v1](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Location.html).
- [Open-Meteo weather](https://open-meteo.com/en/docs) and [geocoding](https://open-meteo.com/en/docs/geocoding-api).
- [NUS AY2026/2027 calendar](https://nus.edu.sg/registrar/docs/default-source/calendar/ay2026-2027.pdf), revision 30 July 2026.

- [bluetui upstream](https://github.com/pythops/bluetui); controls/configuration verified against the installed 0.8.1 README in `/usr/share/doc/bluetui/Readme.md`.

The panel theme is neutral black/grey. Btop uses its original Default theme; bluetui uses the normal ANSI colour palette. The panel background remains neutral black. [GTK 4.24.1 overlays](https://docs.gtk.org/gtk4/class.Overlay.html) keep edit grips outside the content layout, and [VTE child-exited](https://gnome.pages.gitlab.gnome.org/vte/gtk4/signal.Terminal.child-exited.html) triggers terminal recovery.

- [Fastfetch 2.69.0 schema](https://raw.githubusercontent.com/fastfetch-cli/fastfetch/2.69.0/doc/json_schema.json); exact module formats and native `--watch` usage verified against the installed binary’s help.
