# hypr-chrome-resurrect

Bring Chrome windows back to their saved **Hyprland workspaces and tabbed groups**,
including group tab order, after restarting Chrome or logging back in.

Chrome restores your windows and tabs; this app restores their placement.

The source is maintained in the dotfiles repository at
`extras/hypr-chrome-resurrect`, without a separate Git repository.

## Install

You need Linux, Hyprland with `hyprctl`, and Rust/Cargo. In Chrome settings, enable
**Continue where you left off**.

From the project directory:

```sh
cargo build --release
install -Dm755 target/release/hypr-chrome-resurrect \
  "$HOME/.local/bin/hypr-chrome-resurrect"
```

## Start

Run this inside your Hyprland session, before launching Chrome:

```sh
~/.local/bin/hypr-chrome-resurrect daemon
```

Leave the terminal running; use another terminal for commands. Stop it with
**Ctrl-C**.

To start automatically at login, add this to `~/.config/hypr/hyprland.conf`, using
your own absolute home path:

```ini
exec-once = /home/YOUR_USER/.local/bin/hypr-chrome-resurrect daemon
```

Keep launching Chrome through your usual workflow. After updating the app,
restart the daemon to use the new binary.

## Everyday use

**Saving is automatic.** The daemon remembers your layout, restores recognized
windows for 60 seconds after Chrome appears, then resumes tracking changes.
Quitting Chrome or shutting down keeps the saved layout. A change immediately
before shutdown may not have been saved yet.

| Command | What it does |
| --- | --- |
| `status` | Show the saved layout and anything that could not be restored. |
| `restore --dry-run` | Preview workspace and group assignments without changing them. |
| `restore` | Retry restoration, including windows that appeared late. |
| `save` | Replace the saved layout with currently open windows, removing old records. |

For example:

```sh
~/.local/bin/hypr-chrome-resurrect status
~/.local/bin/hypr-chrome-resurrect restore --dry-run
```

Manual `save` is optional. Use it after arranging a layout you want to keep or to
prune closed-window records. It refuses an empty layout. Both forms of `restore`
and `save` require the daemon; dry-run leaves normal automatic activity running.

## Things to know

- Matching uses **exact, unique window titles**. Distinct active-tab titles help;
  ambiguous titles are skipped rather than guessed.
- Groups mean **Hyprland window groups**, not tabs inside Chrome. All saved members
  must be recognized before a group is restored. Mixed-app groups are unsupported.
- Group assembly briefly switches focus through a temporary workspace, then
  attempts to restore your previous focus and cursor.
- The default window class is `google-chrome`. Other builds can use
  `daemon --class chromium` or their actual class.
- State normally lives in `~/.local/state/hypr-chrome-resurrect/layout.json`, with
  a previous-state backup. `XDG_STATE_HOME` overrides the base directory.

## More details

- [Commands, automatic tracking, matching, and groups](docs/usage.md)
- [State files, shutdown behavior, and troubleshooting](docs/state-and-recovery.md)
- [Testing, implementation, and Rust concepts](docs/development.md)
