# State and recovery

[Back to the README](../README.md) · [Usage and restoration behavior](usage.md)

## Location and backups

State lives at:

```text
$XDG_STATE_HOME/hypr-chrome-resurrect/layout.json
```

If `XDG_STATE_HOME` is unset or empty, use
`~/.local/state/hypr-chrome-resurrect/layout.json`. The daemon alone writes it.
Each replacement is written and synced to a temporary file, then renamed
atomically. The previous valid file is backed up as `layout.json.bak`; directory
metadata is synced too. State files use mode `0600` and newly created state
directories use `0700`.

## File format

```json
{
  "version": 2,
  "records": [
    {"title": "Example - Google Chrome", "workspace": {"kind": "numeric", "value": 10}},
    {"title": "Project - Google Chrome", "workspace": {"kind": "numeric", "value": 10}},
    {"title": "Other - Google Chrome", "workspace": {"kind": "named", "value": "dev"}}
  ],
  "groups": [[0, 1]]
}
```

`groups` contains record indices in tab order, never saved window addresses.
Indices must be valid and unique, and all members of a group share a workspace.

Regular positive numbered workspaces and named workspaces are supported. Special
workspaces and names containing commas or line breaks are unsupported and
reported rather than saved or moved incorrectly.

Malformed JSON, unsupported versions, or invalid destinations are reported and
left untouched. The daemon refuses startup with invalid state and also validates
the existing file before every write. To recover, stop the daemon, inspect both
files, and restore the backup or move the invalid file aside before restarting.
Do not edit state while the daemon is running. Titles can contain private
information; the JSON and backup contain the titles you saved.

## Runtime files

CLI IPC uses `$XDG_RUNTIME_DIR/hypr-chrome-resurrect/service.sock`. The directory
has mode `0700`, the socket `0600`, and an advisory lock rejects duplicate
daemons. Requests are newline-terminated JSON with size and read-time limits.
The lock is released by the OS when the process exits; keep its lock file in
place. `hyprctl` subprocesses have a three-second timeout.

## Quitting Chrome and shutting down

Closing a window removes its live tracking identity, not its saved record.
Closing every Chrome window leaves the saved layout intact and makes the daemon
wait for the next launch. Only an explicit `save` prunes closed-window records;
an empty `save` is refused.

The saved layout survives shutdown and is loaded at the next daemon start.
There is no final save-on-shutdown handler, so a title or workspace change made
immediately before shutdown may not be captured. The last successfully written
layout and its previous-state backup remain on disk.

## If restoration does not work

- Run `status` to inspect missing or ambiguous titles, failed moves, and connection
  or persistence errors. A successful `restore` command starts the cycle; it does
  not guarantee every window or group was restored.
- Give windows distinct active-tab titles. Place unresolved windows and groups
  manually, then use `save` if you want that current layout to replace old records.
- For delayed Chrome session restoration, run `restore` to start a fresh cycle.
- If the service is unavailable, start the daemon inside your Hyprland session.
  After installing an updated binary, stop and restart the existing daemon.
- If grouping was interrupted, inspect any `hcr-restore-…` workspace, then retry
  restoration. Grouping rules or locks can prevent a group from being assembled.

The commands above use `~/.local/bin/hypr-chrome-resurrect` if the installation
folder is not on your `PATH`.
