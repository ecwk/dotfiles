# Usage and restoration behavior

[Back to the README](../README.md) · [State and recovery](state-and-recovery.md)

## Running the daemon

The daemon stays in the foreground when started from a terminal. Use another
terminal for CLI commands, and stop the daemon with Ctrl-C.

The daemon inherits `XDG_RUNTIME_DIR` and `HYPRLAND_INSTANCE_SIGNATURE` from
Hyprland. Run one instance as your normal desktop user. A second instance is
rejected; a stale socket after a crash is recovered on the next start.

The default class is exactly `google-chrome`, including case. Check it with
`hyprctl -j clients`. To track a different build, change the daemon entry to
`daemon --class chromium` (or its actual class). CLI commands use the running
daemon's configured class.

## Commands

```sh
hypr-chrome-resurrect status
hypr-chrome-resurrect save
hypr-chrome-resurrect restore --dry-run
hypr-chrome-resurrect restore
```

- `daemon`: automatic restoration and subsequent tracking. Diagnostics go to
  stderr. Stop it with Ctrl-C in the foreground or your normal process manager.
- `save`: immediately replace the layout with currently mapped Chrome windows.
  This explicitly prunes closed records and ends any active restoration cycle.
  An empty layout is refused. Use this after manually correcting ambiguous
  windows or when you want to remove old records.
- `restore --dry-run`: show JSON containing uniquely matched addresses, current
  and saved destinations, ordered group members, and unresolved records. It makes
  no moves and changes neither the saved layout nor the restoration cycle.
- `restore`: reset record consumption and start another restoration cycle.
  Matching starts immediately, or waits for the first Chrome window. Use it for
  a slow or late session restore. Failed moves are included in the response.
- `status`: show saved assignments, restoration phase, unresolved titles, failed
  moves, Hyprland connectivity, event connection health, and persistence errors.
  With no reachable daemon, show the on-disk layout and a connection diagnostic.

`save` and both forms of `restore` require the daemon. Replies are JSON; command
errors go to stderr with a nonzero exit code. A successful `restore` reply means
the cycle started; inspect `failed_moves` and `status` for individual failures.

## Lifecycle

With no state file, the first nonempty Chrome client list becomes the baseline.
Subsequent windows are tracked automatically. With a saved layout, the service
freezes all saved titles and assignments while restoring. It starts matching
existing windows immediately, or waits indefinitely if Chrome is not open.

The restoration period lasts 60 seconds after the first Chrome window appears.
Window creation, closing, title changes, and workspace moves trigger a refresh
after a 200 ms debounce. A two-second poll recovers from missed events; the
event reader reconnects after a disconnection. The service uses Hyprland's
[event socket](https://wiki.hypr.land/IPC/) and
[`movetoworkspacesilent`](https://wiki.hypr.land/0.49.0/Configuring/Dispatchers/)
with an explicit `address:` selector. A post-move client query must confirm the
destination before the window is bound to its saved record.

A title must occur exactly once among **all** saved records and once among all
live Chrome windows. Each record and address can be attempted only once in a
cycle. Empty, changed, or ambiguous titles are left untouched and reported by
`status` or dry-run. A failed move is not retried automatically in that cycle;
its saved destination stays protected during tracking until a new restoration
cycle or an explicit `save`. Failed or incomplete groups retain their saved
membership and order too.

At the deadline, tracking resumes. Bound windows update their saved title and
workspace as you use Chrome. Unmatched live windows are added at their current
workspaces, while unmatched and closed saved records remain. Keeping old
records can eventually produce duplicate titles; `save` replaces them with the
current layout. Closing every Chrome window re-arms restoration for the next
launch. Close events also catch fast restarts between client polls.

Addresses are used only for the current window lifetime; PIDs are not used.
Neither is written to the saved layout or treated as an identity across boots.
Unavailable Hyprland connections never count as an empty Chrome session and do
not delete state. Polling and IPC cannot guarantee that every extremely short
window lifetime will be observed.

## Tabbed groups

The daemon captures Chrome-only Hyprland groups and their left-to-right tab
order. It tracks regrouping, ungrouping, and tab reordering after restoration.
This means Hyprland's window groups, not tabs inside each Chrome window. Multiple
separate groups on the same workspace remain separate; saved ungrouped windows
remain ungrouped.

Every saved group member must first be uniquely recognized and successfully
placed on its workspace. Missing, ambiguous, or failed members leave the group
unresolved. Other recognized windows can still have their workspace restored.
The daemon waits for delayed titles within the existing 60-second period.
`restore --dry-run` includes ordered `groups` of live addresses; `status` includes
group diagnostics in `unresolved` and `failed_moves`.

The group commands in Hyprland's legacy interface insert into a directional
neighbor. To select the correct group reliably, the daemon assembles one group
at a time on an empty temporary named workspace (`hcr-restore-…`), verifies tab
order, and returns the completed group to its saved workspace. This briefly
switches workspaces/focus and moves the pointer; it attempts to restore the
previous focus and cursor even after failure. The service never issues unlock
commands; rebuilt groups use compositor defaults, and local group lock settings
are not restored.

If a command fails, surviving members are returned to the saved workspace and
the failure is reported. If the daemon or compositor is killed during assembly,
windows can remain on the temporary workspace; restarting/restoring retries
from the saved layout. Compositor rules may retain an empty temporary workspace.

Groups containing non-Chrome or otherwise untracked windows are not captured;
`save` refuses such a layout rather than silently forgetting those members.
Restoration skips windows whose current group includes unresolved or untracked
members, so it does not pull those other windows along. Floating mode, geometry,
monitor placement, group lock settings, and the selected tab are not persisted.
Grouping can be prevented by your layout, floating modes, or window/group rules;
inspect diagnostics and retry after correcting them.

Closed tabs retain their saved group membership. As with retained closed-window
records, explicit `save` prunes closed tabs. If you ungroup a remaining tab while
other group members are closed, use `save` to remove that retained relationship.

Existing version-1 files remain readable and restore workspace assignments
without guessing old groups. Live groups are learned automatically when tracking
resumes and the file is upgraded to version 2. To capture your intended groups
immediately, arrange the windows and run `save` (this also prunes closed records).
After upgrading the binary, restart the daemon. The group adapter targets
Hyprland 0.56.2's legacy dispatch interface; no Lua config conversion is needed.
Automated command-sequence checks use a fake compositor. Follow the
[desktop acceptance tests](development.md#desktop-acceptance-tests) to verify
the real session.

## Scope

Tile order, geometry, monitor placement, Chrome launching, extensions, and
Chrome session-file parsing are outside this service.
