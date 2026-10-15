use crate::{
    engine::Engine,
    model::{Hyprland, Layout, Record, Window, Workspace},
    storage,
};
use anyhow::{Result, bail};
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};

#[derive(Default)]
struct FakeHyprland {
    windows: Vec<Window>,
    moves: Vec<(String, Workspace)>,
    fail: bool,
    ignore: bool,
    disconnected: bool,
    group_calls: Vec<Vec<String>>,
    group_fail: bool,
    group_ignore: bool,
}
impl Hyprland for FakeHyprland {
    fn clients(&mut self) -> Result<Vec<Window>> {
        if self.disconnected {
            bail!("offline");
        }
        Ok(self.windows.clone())
    }
    fn move_window(&mut self, address: &str, workspace: &Workspace) -> Result<()> {
        self.moves.push((address.into(), workspace.clone()));
        if self.fail {
            bail!("move failed");
        }
        if !self.ignore {
            self.windows
                .iter_mut()
                .find(|w| w.address == address)
                .unwrap()
                .workspace = workspace.clone();
        }
        Ok(())
    }
    fn detach_window(&mut self, address: &str) -> Result<()> {
        for window in &mut self.windows {
            window.grouped.retain(|a| a != address);
            if window.address == address {
                window.grouped.clear();
            }
        }
        Ok(())
    }
    fn restore_group(&mut self, addresses: &[String], workspace: &Workspace) -> Result<()> {
        self.group_calls.push(addresses.to_vec());
        if self.group_fail {
            bail!("group failed");
        }
        if !self.group_ignore {
            for window in &mut self.windows {
                if addresses.contains(&window.address) {
                    window.grouped = addresses.to_vec();
                    window.workspace = workspace.clone();
                }
            }
        }
        Ok(())
    }
}
fn window(address: &str, title: &str, workspace: i64) -> Window {
    Window {
        address: address.into(),
        title: title.into(),
        workspace: Workspace::Numeric(workspace),
        grouped: Vec::new(),
    }
}
fn layout(records: &[(&str, i64)]) -> Layout {
    Layout {
        version: 1,
        groups: None,
        records: records
            .iter()
            .map(|(title, id)| Record {
                title: (*title).into(),
                workspace: Workspace::Numeric(*id),
            })
            .collect(),
    }
}
fn fake(windows: Vec<Window>) -> FakeHyprland {
    FakeHyprland {
        windows,
        ..Default::default()
    }
}

#[test]
fn unique_titles_restore_once_across_1_2_and_10() {
    let saved = layout(&[("A", 1), ("B", 2), ("C", 10)]);
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(vec![
        window("a", "A", 3),
        window("b", "B", 3),
        window("c", "C", 3),
    ]);
    engine.refresh(&mut hypr, 0).unwrap();
    assert_eq!(hypr.moves.len(), 3);
    for time in [1, 2, 30, 59] {
        assert!(!engine.refresh(&mut hypr, time).unwrap());
    }
    assert_eq!(hypr.moves.len(), 3);
    assert_eq!(engine.layout, saved);
    assert_eq!(hypr.windows[2].workspace, Workspace::Numeric(10));
}
#[test]
fn duplicate_saved_or_live_titles_and_empty_titles_are_untouched() {
    for (saved, windows) in [
        (layout(&[("A", 1), ("A", 2)]), vec![window("a", "A", 3)]),
        (
            layout(&[("A", 1)]),
            vec![window("a", "A", 3), window("b", "A", 4)],
        ),
        (layout(&[("", 1)]), vec![window("a", "", 3)]),
    ] {
        let mut engine = Engine::new(Some(saved));
        let mut hypr = fake(windows);
        engine.refresh(&mut hypr, 0).unwrap();
        assert!(hypr.moves.is_empty());
        assert!(!engine.unresolved.is_empty());
    }
}
#[test]
fn changed_and_delayed_titles_do_not_overwrite_frozen_baseline() {
    let saved = layout(&[("A", 10)]);
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(Vec::new());
    engine.refresh(&mut hypr, 500).unwrap();
    assert_eq!(engine.phase(), "waiting_for_chrome");
    hypr.windows.push(window("a", "loading", 1));
    engine.refresh(&mut hypr, 1000).unwrap();
    assert!(hypr.moves.is_empty());
    hypr.windows[0].title = "A".into();
    engine.refresh(&mut hypr, 1059).unwrap();
    assert_eq!(hypr.moves.len(), 1);
    hypr.windows[0].title = "new tab".into();
    hypr.windows[0].workspace = Workspace::Numeric(2);
    engine.refresh(&mut hypr, 1059).unwrap();
    assert_eq!(engine.layout, saved);
    engine.refresh(&mut hypr, 1060).unwrap();
    assert_eq!(engine.layout.records[0], hypr.windows[0].record());
}
#[test]
fn each_record_and_window_is_consumed_once() {
    let mut engine = Engine::new(Some(layout(&[("A", 10), ("B", 2)])));
    let mut hypr = fake(vec![window("a", "A", 1)]);
    engine.refresh(&mut hypr, 0).unwrap();
    hypr.windows[0].title = "B".into();
    engine.refresh(&mut hypr, 1).unwrap();
    hypr.windows.push(window("b", "A", 1));
    engine.refresh(&mut hypr, 2).unwrap();
    assert_eq!(hypr.moves.len(), 1);
}
#[test]
fn startup_and_generated_move_events_cannot_change_state() {
    let saved = layout(&[("A", 10), ("B", 2)]);
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(vec![window("a", "A", 1)]);
    engine.refresh(&mut hypr, 0).unwrap();
    for time in 1..60 {
        engine.refresh(&mut hypr, time).unwrap();
        assert_eq!(engine.layout, saved);
    }
    engine.refresh(&mut hypr, 60).unwrap();
    assert_eq!(engine.layout, saved);
}
#[test]
fn unmatched_records_retained_and_live_windows_adopted_after_deadline() {
    let saved = layout(&[("old", 10)]);
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(vec![window("a", "new", 2)]);
    engine.refresh(&mut hypr, 0).unwrap();
    assert_eq!(engine.layout, saved);
    engine.refresh(&mut hypr, 60).unwrap();
    assert_eq!(engine.layout.records.len(), 2);
    assert_eq!(engine.layout.records[0], saved.records[0]);
    hypr.windows.clear();
    engine.refresh(&mut hypr, 61).unwrap();
    assert_eq!(engine.layout.records.len(), 2);
    assert_eq!(engine.phase(), "waiting_for_chrome");
}
#[test]
fn closed_records_retained_save_prunes_and_empty_save_refused() {
    let mut engine = Engine::new(None);
    let mut hypr = fake(vec![window("a", "A", 1), window("b", "B", 2)]);
    engine.refresh(&mut hypr, 0).unwrap();
    hypr.windows.remove(1);
    hypr.windows[0].title = "updated".into();
    hypr.windows[0].workspace = Workspace::Numeric(10);
    engine.refresh(&mut hypr, 1).unwrap();
    assert_eq!(engine.layout.records.len(), 2);
    assert_eq!(engine.layout.records[0], hypr.windows[0].record());
    let retained = engine.layout.clone();
    assert!(engine.save(&[]).is_err());
    assert_eq!(engine.layout, retained);
    engine.save(&hypr.windows).unwrap();
    assert_eq!(engine.layout.records.len(), 1);
}
#[test]
fn reopening_chrome_and_manual_retry_start_new_cycles() {
    let mut engine = Engine::new(Some(layout(&[("A", 10)])));
    let mut hypr = fake(vec![window("a", "A", 1)]);
    engine.refresh(&mut hypr, 0).unwrap();
    engine.refresh(&mut hypr, 60).unwrap();
    hypr.windows.clear();
    engine.refresh(&mut hypr, 61).unwrap();
    hypr.windows.push(window("new-address", "A", 1));
    engine.refresh(&mut hypr, 62).unwrap();
    assert_eq!(hypr.moves.len(), 2);
    engine.refresh(&mut hypr, 122).unwrap();
    hypr.windows[0].workspace = Workspace::Numeric(1);
    engine.retry();
    engine.refresh(&mut hypr, 123).unwrap();
    assert_eq!(hypr.moves.len(), 3);
}
#[test]
fn failure_or_unverified_move_keeps_saved_destination_even_after_tracking() {
    for ignore in [false, true] {
        let saved = layout(&[("A", 10)]);
        let mut engine = Engine::new(Some(saved.clone()));
        let mut hypr = fake(vec![window("a", "A", 1)]);
        hypr.fail = !ignore;
        hypr.ignore = ignore;
        engine.refresh(&mut hypr, 0).unwrap();
        engine.refresh(&mut hypr, 1).unwrap();
        engine.refresh(&mut hypr, 60).unwrap();
        assert_eq!(engine.layout, saved);
        assert_eq!(hypr.moves.len(), 1);
        assert_eq!(engine.errors.len(), 1);
    }
}
#[test]
fn disconnection_does_not_reset_cycle_or_discard_state() {
    let saved = layout(&[("A", 10)]);
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(vec![window("a", "A", 1)]);
    engine.refresh(&mut hypr, 0).unwrap();
    hypr.disconnected = true;
    assert!(engine.refresh(&mut hypr, 1).is_err());
    assert_eq!(engine.layout, saved);
    assert_eq!(engine.phase(), "restoring");
    hypr.disconnected = false;
    engine.refresh(&mut hypr, 2).unwrap();
    assert_eq!(hypr.moves.len(), 1);
}
#[test]
fn dry_run_does_not_consume_matches_or_change_state() {
    let saved = layout(&[("A", 10)]);
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(vec![window("a", "A", 1)]);
    assert_eq!(engine.preview(&hypr.windows).moves.len(), 1);
    assert_eq!(engine.preview(&hypr.windows).moves.len(), 1);
    assert_eq!(engine.layout, saved);
    engine.refresh(&mut hypr, 0).unwrap();
    assert_eq!(hypr.moves.len(), 1);
}
struct Temp(PathBuf);
impl Temp {
    fn new() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let path = std::env::temp_dir().join(format!(
            "hcr-test-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn state(&self) -> PathBuf {
        self.0.join("layout.json")
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
#[test]
fn atomic_state_round_trip_previous_backup_and_no_temporary_files() {
    let temp = Temp::new();
    let path = temp.state();
    assert!(storage::load(&path).unwrap().is_none());
    let first = layout(&[("A", 10)]);
    let mut second = layout(&[("B", 2)]);
    second.records.push(Record {
        title: "named".into(),
        workspace: Workspace::Named("dev".into()),
    });
    storage::store(&path, &first).unwrap();
    storage::store(&path, &second).unwrap();
    assert_eq!(storage::load(&path).unwrap(), Some(second));
    assert_eq!(
        storage::load(&path.with_extension("json.bak")).unwrap(),
        Some(first)
    );
    assert_eq!(fs::read_dir(&temp.0).unwrap().count(), 2);
}
#[test]
fn malformed_or_future_state_is_never_overwritten() {
    for bytes in [
        "broken",
        "{\"version\":3,\"records\":[]}",
        "{\"version\":1,\"records\":[{\"title\":\"A\",\"workspace\":{\"kind\":\"numeric\",\"value\":0}}]}",
    ] {
        let temp = Temp::new();
        let path = temp.state();
        fs::write(&path, bytes).unwrap();
        assert!(storage::load(&path).is_err());
        assert!(storage::store(&path, &layout(&[("A", 1)])).is_err());
        assert_eq!(fs::read_to_string(path).unwrap(), bytes);
        assert!(!temp.0.join("layout.json.bak").exists());
    }
}

#[test]
fn close_events_detect_a_restart_between_client_polls() {
    let mut engine = Engine::new(Some(layout(&[("A", 10)])));
    let mut hypr = fake(vec![window("0xa", "A", 1)]);
    engine.refresh(&mut hypr, 0).unwrap();
    engine.refresh(&mut hypr, 60).unwrap();
    engine.closed("0xa");
    assert_eq!(engine.phase(), "waiting_for_chrome");
    hypr.windows = vec![window("0xb", "A", 1)];
    engine.refresh(&mut hypr, 61).unwrap();
    assert_eq!(hypr.moves.len(), 2);
}

#[test]
fn named_destination_is_restored_and_invalid_destinations_rejected() {
    let named = Workspace::Named("development".into());
    let saved = Layout {
        version: 1,
        groups: None,
        records: vec![Record {
            title: "A".into(),
            workspace: named.clone(),
        }],
    };
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(vec![window("a", "A", 1)]);
    engine.refresh(&mut hypr, 0).unwrap();
    assert_eq!(hypr.moves, vec![("a".into(), named.clone())]);
    assert_eq!(hypr.windows[0].workspace, named);
    engine.refresh(&mut hypr, 60).unwrap();
    assert_eq!(engine.layout, saved);
    for workspace in [
        Workspace::Numeric(0),
        Workspace::Named("special".into()),
        Workspace::Named("special:scratch".into()),
        Workspace::Named("a,address:0x1".into()),
    ] {
        assert!(workspace.validate().is_err());
    }
}

fn grouped_layout(records: &[(&str, i64)], groups: Vec<Vec<usize>>) -> Layout {
    let mut saved = layout(records);
    saved.version = 2;
    saved.groups = Some(groups);
    saved.validate().unwrap();
    saved
}
fn set_group(hypr: &mut FakeHyprland, addresses: &[&str]) {
    let addresses: Vec<String> = addresses.iter().map(|a| (*a).into()).collect();
    for window in &mut hypr.windows {
        if addresses.contains(&window.address) {
            window.grouped = addresses.clone();
        }
    }
}
#[test]
fn two_groups_on_one_workspace_restore_members_and_order_once() {
    let saved = grouped_layout(
        &[("A", 2), ("B", 2), ("C", 2), ("D", 2)],
        vec![vec![1, 0], vec![3, 2]],
    );
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(vec![
        window("a", "A", 1),
        window("b", "B", 1),
        window("c", "C", 1),
        window("d", "D", 1),
    ]);
    assert_eq!(
        engine.preview(&hypr.windows).groups,
        vec![vec!["b", "a"], vec!["d", "c"]]
    );
    engine.refresh(&mut hypr, 0).unwrap();
    engine.refresh(&mut hypr, 1).unwrap();
    assert_eq!(hypr.group_calls, vec![vec!["b", "a"], vec!["d", "c"]]);
    assert_eq!(hypr.windows[0].grouped, vec!["b", "a"]);
    assert_eq!(hypr.windows[2].grouped, vec!["d", "c"]);
    assert_eq!(engine.layout, saved);
}
#[test]
fn delayed_group_member_is_waited_for_before_grouping() {
    let saved = grouped_layout(&[("A", 2), ("B", 2)], vec![vec![0, 1]]);
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(vec![window("a", "A", 1), window("b", "loading", 1)]);
    assert!(engine.preview(&hypr.windows).groups.is_empty());
    engine.refresh(&mut hypr, 0).unwrap();
    assert!(hypr.group_calls.is_empty());
    hypr.windows[1].title = "B".into();
    engine.refresh(&mut hypr, 59).unwrap();
    assert_eq!(hypr.group_calls.len(), 1);
    engine.refresh(&mut hypr, 60).unwrap();
    assert_eq!(engine.layout, saved);
}
#[test]
fn ambiguous_group_is_skipped_and_saved_group_protected_after_deadline() {
    let saved = grouped_layout(&[("A", 2), ("B", 2)], vec![vec![0, 1]]);
    let mut engine = Engine::new(Some(saved.clone()));
    let mut hypr = fake(vec![
        window("a", "A", 1),
        window("b", "B", 1),
        window("c", "B", 1),
    ]);
    engine.refresh(&mut hypr, 0).unwrap();
    engine.refresh(&mut hypr, 60).unwrap();
    assert!(hypr.group_calls.is_empty());
    assert_eq!(engine.layout.groups, saved.groups);
    assert_eq!(&engine.layout.records[..2], &saved.records);
    assert!(engine.unresolved.iter().any(|m| m.contains("group")));
}
#[test]
fn wrong_groups_are_detached_and_regrouped_and_saved_ungrouped_stays_separate() {
    let saved = grouped_layout(&[("A", 2), ("B", 2), ("C", 2)], vec![vec![0, 1]]);
    let mut engine = Engine::new(Some(saved));
    let mut hypr = fake(vec![
        window("a", "A", 2),
        window("b", "B", 2),
        window("c", "C", 2),
    ]);
    set_group(&mut hypr, &["a", "c", "b"]);
    engine.refresh(&mut hypr, 0).unwrap();
    assert_eq!(hypr.windows[0].grouped, vec!["a", "b"]);
    assert!(hypr.windows[2].grouped.is_empty());
}
#[test]
fn untracked_current_group_member_prevents_destructive_detachment() {
    let saved = grouped_layout(&[("A", 2)], vec![vec![0]]);
    let mut engine = Engine::new(Some(saved));
    let mut hypr = fake(vec![window("a", "A", 1)]);
    hypr.windows[0].grouped = vec!["a".into(), "foreign".into()];
    assert!(engine.preview(&hypr.windows).groups.is_empty());
    engine.refresh(&mut hypr, 0).unwrap();
    assert!(hypr.moves.is_empty());
    assert!(hypr.group_calls.is_empty());
    assert_eq!(hypr.windows[0].grouped, vec!["a", "foreign"]);
}
#[test]
fn failed_and_unverified_group_restore_keeps_saved_group_and_reports_failure() {
    for ignore in [false, true] {
        let saved = grouped_layout(&[("A", 2), ("B", 2)], vec![vec![0, 1]]);
        let mut engine = Engine::new(Some(saved.clone()));
        let mut hypr = fake(vec![window("a", "A", 1), window("b", "B", 1)]);
        hypr.group_fail = !ignore;
        hypr.group_ignore = ignore;
        engine.refresh(&mut hypr, 0).unwrap();
        engine.refresh(&mut hypr, 1).unwrap();
        engine.refresh(&mut hypr, 60).unwrap();
        assert_eq!(engine.layout, saved);
        assert_eq!(hypr.group_calls.len(), 1);
        assert!(engine.errors[0].contains("group 0"));
    }
}
#[test]
fn tracking_captures_order_changes_ungrouping_and_retains_closed_group_members() {
    let mut engine = Engine::new(None);
    let mut hypr = fake(vec![window("a", "A", 2), window("b", "B", 2)]);
    set_group(&mut hypr, &["b", "a"]);
    engine.refresh(&mut hypr, 0).unwrap();
    assert_eq!(engine.layout.groups, Some(vec![vec![1, 0]]));
    set_group(&mut hypr, &["a", "b"]);
    engine.refresh(&mut hypr, 1).unwrap();
    assert_eq!(engine.layout.groups, Some(vec![vec![0, 1]]));
    hypr.detach_window("b").unwrap();
    hypr.windows.pop();
    engine.refresh(&mut hypr, 2).unwrap();
    assert_eq!(engine.layout.groups, Some(vec![vec![0, 1]]));
    engine.save(&hypr.windows).unwrap();
    assert_eq!(engine.layout.groups, Some(vec![vec![0]]));
    hypr.detach_window("a").unwrap();
    engine.refresh(&mut hypr, 3).unwrap();
    assert_eq!(engine.layout.groups, Some(Vec::new()));
}
#[test]
fn group_state_validation_and_legacy_migration() {
    let temp = Temp::new();
    let path = temp.state();
    let legacy = layout(&[("A", 2), ("B", 2)]);
    storage::store(&path, &legacy).unwrap();
    let mut engine = Engine::new(storage::load(&path).unwrap());
    let mut hypr = fake(vec![window("a", "A", 2), window("b", "B", 2)]);
    set_group(&mut hypr, &["a", "b"]);
    engine.refresh(&mut hypr, 0).unwrap();
    assert_eq!(engine.layout, legacy);
    engine.refresh(&mut hypr, 60).unwrap();
    assert_eq!(engine.layout.version, 2);
    assert_eq!(engine.layout.groups, Some(vec![vec![0, 1]]));
    storage::store(&path, &engine.layout).unwrap();
    assert_eq!(storage::load(&path).unwrap().unwrap(), engine.layout);
    assert_eq!(
        storage::load(&path.with_extension("json.bak")).unwrap(),
        Some(legacy)
    );
    for groups in [
        vec![vec![]],
        vec![vec![0, 9]],
        vec![vec![0, 0]],
        vec![vec![0], vec![0]],
    ] {
        let mut invalid = engine.layout.clone();
        invalid.groups = Some(groups);
        assert!(invalid.validate().is_err());
    }
    let mut mixed = fake(vec![window("a", "A", 2)]);
    mixed.windows[0].grouped = vec!["a".into(), "foreign".into()];
    let before = engine.layout.clone();
    assert!(engine.save(&mixed.windows).is_err());
    assert_eq!(engine.layout, before);
}

#[test]
fn resolved_current_group_conflict_resumes_tracking_for_an_ungrouped_record() {
    let saved = grouped_layout(&[("A", 2)], vec![]);
    let mut engine = Engine::new(Some(saved));
    let mut hypr = fake(vec![window("a", "A", 1)]);
    hypr.windows[0].grouped = vec!["a".into(), "foreign".into()];
    engine.refresh(&mut hypr, 0).unwrap();
    hypr.windows[0].grouped.clear();
    engine.refresh(&mut hypr, 1).unwrap();
    engine.refresh(&mut hypr, 60).unwrap();
    hypr.windows[0].title = "updated".into();
    engine.refresh(&mut hypr, 61).unwrap();
    assert_eq!(engine.layout.records[0].title, "updated");
}
