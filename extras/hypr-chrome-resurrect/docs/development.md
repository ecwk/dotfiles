# Development and testing

[Back to the README](../README.md) · [Usage and restoration behavior](usage.md)

Run all commands from `extras/hypr-chrome-resurrect` in the dotfiles repository.
The project uses Rust edition 2024
and has been built with Rust 1.87.

## Automated checks

```sh
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
cargo build
python3 tests/cli.py
```

The Rust tests use a fake Hyprland interface and a simulated clock: exact and
duplicate matching, empty and delayed titles, consumption, startup freezing,
tracking, closed-record retention, explicit pruning, empty-save refusal,
restarts, dry-run, disconnections, failed or unverified moves, version validation,
atomic persistence, backups, legacy-state migration, delayed/ambiguous groups,
multiple groups per workspace, tab order, ungrouping, and closed-tab retention.

The Python smoke test runs the actual daemon and CLI with fake `hyprctl` and an
isolated Unix event socket. It checks moves
across workspaces 1, 2, and 10, exact class matching, read-only dry-run, IPC errors,
save/refusal, permissions, second-instance rejection, stale socket recovery, and
malformed-state protection, group assembly, head-insertion order correction,
focus restoration, group-lock failures, and cleanup. It does not touch the
desktop's real Chrome windows.

## Desktop acceptance tests

1. Start the daemon, place three Chrome windows with distinct active-tab titles
   on workspaces 1, 2, and 10, and run `save`.
2. Run `restore --dry-run`; check that each title has the intended destination
   and there are no ambiguous records. Check `status` for errors.
3. Exit Chrome completely, reopen it normally, and confirm restored windows
   return to 1, 2, and 10. Workspace-only moves leave the active workspace
   unchanged. Allow up to 60 seconds for restored titles; use `restore` if Chrome
   needs more time.
4. Create two Chrome tabbed groups on the same workspace, with at least three
   distinct titles in one group. Run `save`, restart Chrome, and verify membership
   and tab order. Test delayed/duplicate titles and group locks; unresolved groups
   must be reported, with their saved metadata retained. Expect brief focus
   changes while groups are assembled.
5. Reboot with the `exec-once` entry enabled. Launch Chrome through your normal
   workflow and verify the same assignments. Test a duplicate title separately
   and confirm it is reported and left for manual correction.

Reboot and real Chrome session restoration require a desktop acceptance test;
they are not covered by the automated fake-interface checks.

## Rust concepts in this project

- **Structs**: `Window`, `Record`, and `Layout` group related values. Live windows
  include an address; persisted records include only titles and destinations.
  The layout stores group membership as record indices in tab order.
- **Enums**: `Workspace` represents numbered or named destinations; `Phase`
  separates waiting/restoration from tracking; `Request` represents CLI commands.
  Pattern matching makes each case explicit.
- **Ownership and borrowing**: the daemon owns the `Engine` and its saved layout.
  Threads transfer owned messages over a channel instead of sharing mutable
  state. Temporary borrows inspect records, and clones take independent client
  snapshots for matching and verification.
- **Error handling**: `Result`, `?`, and `anyhow::Context` preserve actionable
  failure messages. Failed reads do not become empty client lists. Failed moves
  do not silently become saved destinations.
- **JSON serialization**: Serde derives encode/decode typed state and IPC;
  `serde_json` handles bytes and values. A schema version rejects unsupported
  future formats. Clap derives define the typed command-line interface.
- **Threads**: standard-library threads accept requests, drain Hyprland events,
  and read subprocess output. A bounded channel feeds one state-owning loop.
  `Instant` supplies monotonic timing; tests inject an integer clock.
- **IPC**: Unix sockets carry local CLI requests and Hyprland event notifications;
  `hyprctl` queries clients and dispatches address-specific moves. A small,
  documented Unix FFI call provides a process-lifetime advisory lock.

## Source map

| File | Responsibility |
| --- | --- |
| [model.rs](../src/model.rs) | Data types and the Hyprland trait. |
| [engine.rs](../src/engine.rs) | Matching, tracking, and restoration lifecycle. |
| [hypr.rs](../src/hypr.rs) | Commands and queries for real Hyprland. |
| [storage.rs](../src/storage.rs) | Atomic persistence and backups. |
| [service.rs](../src/service.rs) | CLI IPC and the daemon loop. |
| [main.rs](../src/main.rs) | Command-line interface. |
| [tests.rs](../src/tests.rs) | Engine and storage tests. |
