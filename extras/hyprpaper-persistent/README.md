# Persistent wallpaper surface for Hyprpaper 0.8.4

Upstream v0.8.4 (`20fc0fa6c2056c388a4cd69cb394a9f989dd27c0`) destroys its
wallpaper target in `CUI::targetChanged` before building the replacement. This
exposes Hyprland's background during Vicinae previews and Apply. A scoped no_anim
rule did not remove the gap and was removed again.

This patch reuses an existing target for single-image updates, rebuilding the
image synchronously through the same API used by Hyprpaper's slideshow timer.
It cancels a prior slideshow timer, retains the mapped layer surface, updates
the active image identity, and notifies IPC observers. Multi-image configuration
updates retain upstream behavior. No system packages are upgraded or replaced.

## Rebuild

Run `./build.sh`. It checks the exact upstream commit, applies the tracked patch,
builds using installed development libraries, and installs the local executable.
Verified with hyprtoolkit 0.6.0, hyprutils 0.14.2, hyprlang 0.6.8, hyprwire 0.3.1,
Wayland 1.26.0 and Hyprland 0.56.2. Rebuild after incompatible library updates.
The distributed patch follows upstream's BSD-3-Clause licensing.

The tracked drop-in at `rice/.config/systemd/user/hyprpaper.service.d/10-persistent-surface.conf`
is symlinked into `~/.config/systemd/user/hyprpaper.service.d/`. It overrides only
ExecStart to `%h/.local/libexec/hyprpaper-persistent`. Keep only this one service;
do not also start Hyprpaper through Hyprland exec-once.

After linking the drop-in: `systemctl --user daemon-reload` then
`systemctl --user restart hyprpaper.service`. Run `walltheme restore` to restore
the saved wallpaper after a manual service restart.

## Rollback

Remove only `~/.config/systemd/user/hyprpaper.service.d/10-persistent-surface.conf`,
then run `systemctl --user daemon-reload`, `systemctl --user restart hyprpaper.service`,
and `walltheme restore`. The packaged `/usr/bin/hyprpaper` is untouched.

## Validation

Before patching, an IPC change produced fully transparent wallpaper samples.
After patching, 126 samples stayed at opacity 1 with no missing surface. Three
preview/cancel transitions retained selections and preserved saved wallpaper/theme
files. `check_switch.py` repeats a temporary live switch, checks the same mapped
surface and its opacity, then restores the original in a finally block.

Source: https://github.com/hyprwm/hyprpaper/blob/v0.8.4/src/ui/UI.cpp
