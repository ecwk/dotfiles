# dotfiles

Canonical Linux configuration, organized as GNU Stow packages. The working checkout lives at `~/Documents/Repos/dotfiles`; it can live elsewhere as long as Stow receives an explicit home target. There are no submodules or nested repositories.

## Packages

| Package | Contents | Target |
| --- | --- | --- |
| `rice` | Hyprland/Hyprlock/Hyprpaper, wallpapers, dashboard, Waybar, SwayNC, Vicinae and wallpaper extension, AGS, Ghostty, UWSM, Waypaper, Fontconfig, custom scripts, launchers and user-service definitions | `$HOME` |
| `tools` | Neovim, Zed, mise, tmux, Git, clang-format, IdeaVim and ripgrep | `$HOME` |
| `shell` | Zsh, Powerlevel10k, login environment and Bash fallback files | `$HOME` |
| `desktop` | Fcitx5, MIME defaults and selected GIMP preferences/tool options | `$HOME` |
| `machine` | ASUS ROG/NVIDIA user preferences and XDG home-directory settings | `$HOME` (optional on other machines) |
| `system` | Reviewed `/etc` snapshots, including boot, NVIDIA, locale, pacman and custom system-service configuration | Manual review/copy only |
| `snapshots` | Sanitized TeXstudio/MuseScore preferences and desktop-interface dconf export | Manual import only |
| `extras` | Editable source for the Vicinae wallpaper extension, Hyprpaper patch, and Chrome layout restoration daemon | Source only |

The layout mirrors actual config paths. In particular tmux stays at `tools/.tmux.conf`, matching the existing setup. Shell, tools and desktop packages can be used independently of the rice. The dashboard, wallpaper backend and compiled Vicinae extension are included so their integrations are not lost.

The lock shortcut (`Super+Alt+L`) and Hypridle launch Hyprlock directly. Bright text and dark shadows keep labels readable over the blurred desktop without extra background sampling or preprocessing.

## Apply on a machine

These instructions apply configuration only. Install the programs you intend to use separately. GNU Stow **2.4.1** was used to verify this layout.

1. Clone this repository, or copy its checkout, to `~/Documents/Repos/dotfiles`.
2. Close preference editors and inspect machine-specific paths, monitor names, keybindings and commands before applying the rice. This is a personal configuration, not a hardware-detection layer. Some original configs/scripts contain `/home/ecwk` paths; change those for a different username/home. Shell configuration expects the existing Oh My Zsh/Powerlevel10k/plugins and language-tool environment.
3. Preview the links with an explicit target. This matters because the checkout is not directly under `$HOME`:

   ```sh
   cd ~/Documents/Repos/dotfiles
   stow --simulate --verbose --target="$HOME" rice tools shell desktop
   ```

4. If Stow reports existing configs, move **only the conflicting paths** into a backup outside the repository, then rerun the preview. For example, if `~/.config/hypr` conflicts:

   ```sh
   backup="$HOME/.local/state/dotfiles-backups/$(date +%Y%m%d-%H%M%S)"
   mkdir -p "$backup/.config"
   mv "$HOME/.config/hypr" "$backup/.config/hypr"
   ```

   Repeat for the paths Stow actually reports; do not replace all of `~/.config`. Preserve any credentials, histories or app state separately. Avoid `--adopt` on a fresh machine: it can replace repository files with that machine's existing settings.

5. Create the links:

   ```sh
   stow --verbose --target="$HOME" rice tools shell desktop
   # Only when these laptop/user-directory settings fit this machine:
   stow --simulate --verbose --target="$HOME" machine
   stow --verbose --target="$HOME" machine
   ```

Stow uses normal directory folding. Application config directories become symlinks where possible, so applications that save via atomic file replacement continue writing inside the repository. Shared directories such as `~/.config`, `~/.local/bin` and the existing user-service tree remain shared. A file that was linked individually can still be replaced by an application's save operation; check `git status` and the live path if changes stop appearing.

Do not move this checkout after stowing. Unstow first, move it, then stow again.

## Updating and removing links

Edit configs through their usual home paths or inside this repository, then review and commit the diff. Watch for applications adding history or generated state before committing.

```sh
cd ~/Documents/Repos/dotfiles
# Preview and reconcile links after adding/removing config files:
stow --simulate --verbose --restow --target="$HOME" rice tools shell desktop machine
stow --verbose --restow --target="$HOME" rice tools shell desktop machine
# Remove this repository's links; repository files remain intact:
stow --verbose --delete --target="$HOME" rice tools shell desktop machine
```

Only include packages you actually applied. Unstowing does not restore pre-existing files; restore those from your backup afterward. Add another category by creating a package directory containing its intended home-relative paths, then stow that package with the same explicit target. Keep a target path owned by one package only.

## Desktop integrations

The Chrome layout restoration daemon's Rust source is in
[`extras/hypr-chrome-resurrect`](extras/hypr-chrome-resurrect/README.md).
Build and install it from that directory using its README. Hyprland autostart
launches `~/.local/bin/hypr-chrome-resurrect daemon`; the executable is installed
separately. The project is maintained as ordinary files in this repository.

The dashboard launcher, desktop entry and user-service definition use relative links within `rice`. The SwayNC user-service override is included. Stow applies the definitions but does not restart programs or enable units.

The original machine had `waybar.service`, `swaync.service` and `glass-dashboard.service` enabled for the graphical session, `pipewire-pulse.service/socket` enabled, and `mako.service` masked. Review `snapshots/systemd-user-links.txt` if reproducing those choices. After reviewing definitions, `systemctl --user daemon-reload` makes unit changes visible; use your normal session-management commands to enable the desired services. Hyprpaper already starts from Hyprland autostart. The old user-service tree also contained a **broken** `hyprpaper.service` enablement link; that broken link is not reproduced by this repository.

The wallpaper backend is at `rice/.local/share/walltheme/lib/walltheme.py`. Its existing code expects a Matugen **4.2.0** executable at `rice/.local/share/walltheme/lib/tools/matugen` and the Waypaper launcher at `~/.local/bin/waypaper`. Executables installed by software managers are not committed. This machine's existing Matugen executable is retained locally at the expected location and ignored by Git. On another machine, point that location at your matching existing executable before using wallpaper generation:

```sh
mkdir -p rice/.local/share/walltheme/lib/tools
ln -s "$(command -v matugen)" rice/.local/share/walltheme/lib/tools/matugen
```

Check the version first. The installed Vicinae extension files are in `rice/.local/share/vicinae/extensions/walltheme`; their editable sources are in `extras/vicinae-wallpapers`. The source project's installer assumes a standalone deployment and copies files; avoid rerunning it over Stow-managed files. Keep the source and deployed extension/backend in sync when changing them. Palette indexes, swatches and cache data are regenerated and excluded.

## System and preference snapshots

`system/` is **not a home Stow package** and was not applied during migration. Compare each file with the destination machine's config and copy/merge only deliberate changes. Boot/initramfs, driver, pacman mirror and locale files are machine-specific. Systemd enablement links and root-owned files are not activated automatically. Do not stow `system` against `/`: that could redirect critical boot/system files into a home checkout. The Waybar `impala` sudoers example is stored under `system/etc/sudoers.d/` for separate review with `visudo`.

TeXstudio and MuseScore store preferences alongside personal identity, credentials and recent-file data. Their sanitized copies under `snapshots/.config/` omit those fields; merge preferences with the apps closed. Their active files remain unchanged and are not symlinked. The original keys are preserved only in the app's original local files, outside Git.

To apply the saved desktop interface preferences explicitly:

```sh
dconf load /org/gnome/desktop/interface/ < snapshots/dconf/org-gnome-desktop-interface.ini
```

Do not symlink the live binary dconf database.

## What is intentionally excluded

- Secrets, authentication/session data, private keys, browser profiles and clipboard databases.
- Backup files, old Neovim configs, shell histories, caches, generated bindings and dependency trees.
- Downloaded program binaries, third-party shell/tmux plugin checkouts and fonts; existing installations stay in place.
- Generated game/browser launchers and personal GTK bookmarks. The customized ChatGPT/Zed launchers are included.
- Empty btop config and stock Cava shader/theme assets. The dashboard's actual btop/Cava/fastfetch presets are included under its `data/` directory.
- Flameshot config: it was present during the earlier scan but absent during this final scan.

Original Git histories are not imported into this repository. The migration backup retains the previous local config directories and their Git metadata for recovery. No old remotes are inherited.

## References

Layout and symlink behavior follow the [GNU Stow 2.4.1 manual](https://www.gnu.org/software/stow/manual/stow.html), including [invocation and adoption](https://www.gnu.org/software/stow/manual/html_node/Invoking-Stow.html) and [package ignore lists](https://www.gnu.org/software/stow/manual/html_node/Types-And-Syntax-Of-Ignore-Lists.html).
