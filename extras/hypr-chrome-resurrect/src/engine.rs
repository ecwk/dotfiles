use crate::model::{Hyprland, Layout, Window, Workspace, capture_groups};
use anyhow::{Result, bail};
use serde::Serialize;
use std::collections::{HashMap, HashSet};

pub const RESTORE_SECONDS: u64 = 60;
#[derive(Debug)]
enum Phase {
    Restoring { started: Option<u64> },
    Tracking,
}
#[derive(Clone, Debug, Serialize)]
pub struct ProposedMove {
    pub address: String,
    pub title: String,
    pub from: Workspace,
    pub to: Workspace,
}
#[derive(Debug, Serialize)]
pub struct Preview {
    pub moves: Vec<ProposedMove>,
    pub unresolved: Vec<String>,
    pub groups: Vec<Vec<String>>,
}

// Count ALL saved records and live windows, including already consumed matches.
// Otherwise a duplicate could become "unique" after its sibling is consumed.
fn candidates(layout: &Layout, windows: &[Window]) -> (Vec<(usize, usize)>, Vec<String>) {
    let mut saved = HashMap::<&str, Vec<usize>>::new();
    let mut live = HashMap::<&str, Vec<usize>>::new();
    for (i, record) in layout.records.iter().enumerate() {
        saved.entry(&record.title).or_default().push(i);
    }
    for (i, window) in windows.iter().enumerate() {
        live.entry(&window.title).or_default().push(i);
    }
    let mut pairs = Vec::new();
    let mut unresolved = Vec::new();
    for (i, record) in layout.records.iter().enumerate() {
        let current = live.get(record.title.as_str());
        if record.title.is_empty() {
            unresolved.push(format!("record {i}: empty title cannot be matched"));
        } else if saved[record.title.as_str()].len() != 1 || current.is_some_and(|v| v.len() > 1) {
            unresolved.push(format!("record {i}: ambiguous title {:?}", record.title));
        } else if let Some(indices) = current {
            pairs.push((i, indices[0]));
        } else {
            unresolved.push(format!(
                "record {i}: no window with title {:?}",
                record.title
            ));
        }
    }
    (pairs, unresolved)
}

pub struct Engine {
    pub layout: Layout,
    baseline: bool,
    phase: Phase,
    bindings: HashMap<String, usize>,
    consumed: HashSet<usize>,
    attempted: HashSet<String>,
    blocked: HashSet<String>,
    had_windows: bool,
    observed: HashSet<String>,
    group_attempted: HashSet<usize>,
    group_protected: HashSet<usize>,
    pub errors: Vec<String>,
    pub unresolved: Vec<String>,
}
impl Engine {
    pub fn new(saved: Option<Layout>) -> Self {
        let baseline = saved.is_some();
        Self {
            layout: saved.unwrap_or_default(),
            baseline,
            phase: Phase::Restoring { started: None },
            bindings: HashMap::new(),
            consumed: HashSet::new(),
            attempted: HashSet::new(),
            blocked: HashSet::new(),
            had_windows: false,
            observed: HashSet::new(),
            group_attempted: HashSet::new(),
            group_protected: HashSet::new(),
            errors: Vec::new(),
            unresolved: Vec::new(),
        }
    }
    pub fn phase(&self) -> &'static str {
        match self.phase {
            Phase::Restoring { started: None } => "waiting_for_chrome",
            Phase::Restoring { .. } => "restoring",
            Phase::Tracking => "tracking",
        }
    }
    pub fn retry(&mut self) {
        self.phase = Phase::Restoring { started: None };
        self.bindings.clear();
        self.consumed.clear();
        self.attempted.clear();
        self.blocked.clear();
        self.group_attempted.clear();
        self.group_protected.clear();
        self.errors.clear();
        self.unresolved.clear();
    }
    pub fn preview(&self, windows: &[Window]) -> Preview {
        let (mut pairs, mut unresolved) = candidates(&self.layout, windows);
        let matched: HashSet<_> = pairs
            .iter()
            .map(|(_, w)| windows[*w].address.as_str())
            .collect();
        if self.layout.groups.is_some() {
            pairs.retain(|(r, w)| {
                let safe = windows[*w]
                    .grouped
                    .iter()
                    .all(|a| matched.contains(a.as_str()));
                if !safe {
                    unresolved.push(format!(
                        "record {r}: current group contains an unresolved or untracked window"
                    ));
                }
                safe
            });
        }
        let lookup: HashMap<_, _> = pairs.iter().copied().collect();
        let mut groups = Vec::new();
        for (id, group) in self.layout.groups.iter().flatten().enumerate() {
            if group.iter().all(|r| lookup.contains_key(r)) {
                groups.push(
                    group
                        .iter()
                        .map(|r| windows[lookup[r]].address.clone())
                        .collect(),
                );
            } else {
                unresolved.push(format!(
                    "group {id}: missing or ambiguous members; grouping skipped"
                ));
            }
        }
        Preview {
            groups,
            moves: pairs
                .into_iter()
                .map(|(r, w)| ProposedMove {
                    address: windows[w].address.clone(),
                    title: windows[w].title.clone(),
                    from: windows[w].workspace.clone(),
                    to: self.layout.records[r].workspace.clone(),
                })
                .collect(),
            unresolved,
        }
    }
    pub fn closed(&mut self, address: &str) {
        self.bindings.remove(address);
        self.blocked.remove(address);
        if self.observed.remove(address) && self.observed.is_empty() && self.had_windows {
            self.retry();
            self.had_windows = false;
        }
    }
    pub fn save(&mut self, windows: &[Window]) -> Result<()> {
        if windows.is_empty() {
            bail!("refusing to save an empty Chrome layout");
        }
        let layout = Layout::capture(windows)?;
        layout.validate()?;
        self.layout = layout;
        self.baseline = true;
        self.retry();
        self.phase = Phase::Tracking;
        self.bindings = windows
            .iter()
            .enumerate()
            .map(|(i, w)| (w.address.clone(), i))
            .collect();
        self.had_windows = true;
        self.observed = windows.iter().map(|w| w.address.clone()).collect();
        Ok(())
    }
    pub fn refresh(&mut self, hypr: &mut impl Hyprland, now: u64) -> Result<bool> {
        let mut windows = hypr.clients()?; // A disconnected compositor must not look like Chrome closing.
        let before = self.layout.clone();
        self.observed = windows.iter().map(|w| w.address.clone()).collect();
        if windows.is_empty() {
            if self.had_windows {
                self.retry();
            }
            self.had_windows = false;
            self.bindings.clear();
            self.unresolved = candidates(&self.layout, &windows).1;
            return Ok(false);
        }
        self.had_windows = true;
        if !self.baseline {
            self.save(&windows)?;
            return Ok(self.layout != before);
        }
        if let Phase::Restoring { started } = &mut self.phase {
            let start = *started.get_or_insert(now);
            if now.saturating_sub(start) >= RESTORE_SECONDS {
                self.phase = Phase::Tracking;
            } else {
                let (pairs, unresolved) = candidates(&self.layout, &windows);
                self.unresolved = unresolved;
                let matched_addresses: HashSet<_> = pairs
                    .iter()
                    .map(|(_, w)| windows[*w].address.clone())
                    .collect();
                let record_addresses: HashMap<_, _> = pairs
                    .iter()
                    .map(|(r, w)| (*r, windows[*w].address.clone()))
                    .collect();
                for (record, window) in pairs {
                    let current = &windows[window];
                    if self.consumed.contains(&record) || self.attempted.contains(&current.address)
                    {
                        continue;
                    }
                    let expected = self
                        .layout
                        .groups
                        .as_ref()
                        .and_then(|groups| groups.iter().find(|g| g.contains(&record)))
                        .and_then(|group| {
                            group
                                .iter()
                                .map(|r| record_addresses.get(r).cloned())
                                .collect::<Option<Vec<_>>>()
                        });
                    if self.layout.groups.is_some()
                        && current
                            .grouped
                            .iter()
                            .any(|a| !matched_addresses.contains(a))
                    {
                        self.unresolved.push(format!("record {record}: current group contains an unresolved or untracked window"));
                        self.group_protected.insert(record);
                        continue;
                    }
                    self.consumed.insert(record);
                    self.attempted.insert(current.address.clone());
                    let destination = &self.layout.records[record].workspace;
                    let result = (|| -> Result<()> {
                        if self.layout.groups.is_some()
                            && !current.grouped.is_empty()
                            && !(expected.as_ref() == Some(&current.grouped)
                                && &current.workspace == destination)
                        {
                            hypr.detach_window(&current.address)?;
                            if hypr
                                .clients()?
                                .iter()
                                .any(|w| w.address == current.address && !w.grouped.is_empty())
                            {
                                bail!("window did not leave its old group");
                            }
                        }
                        if &current.workspace == destination {
                            Ok(())
                        } else {
                            hypr.move_window(&current.address, destination)
                                .and_then(|()| {
                                    let verified = hypr.clients()?;
                                    if verified.iter().any(|w| {
                                        w.address == current.address && &w.workspace == destination
                                    }) {
                                        Ok(())
                                    } else {
                                        bail!("destination not confirmed by client list")
                                    }
                                })
                        }
                    })();
                    match result {
                        Ok(()) => {
                            self.bindings.insert(current.address.clone(), record);
                            if !self
                                .layout
                                .groups
                                .iter()
                                .flatten()
                                .any(|g| g.contains(&record))
                            {
                                self.group_protected.remove(&record);
                            }
                        }
                        Err(error) => {
                            self.blocked.insert(current.address.clone());
                            self.errors.push(format!(
                                "move {:?} ({}) to {} failed: {error:#}",
                                current.title,
                                current.address,
                                destination.selector()
                            ));
                        }
                    }
                }
                self.restore_groups(hypr)?;
                // No saved title or destination changes during this entire phase.
                return Ok(false);
            }
        }
        // Re-read after restoration before tracking to avoid recording stale pre-move workspaces.
        windows = hypr.clients()?;
        Layout::capture(&windows)?;
        let previous_bindings = self.bindings.clone();
        let live: HashSet<_> = windows.iter().map(|w| w.address.as_str()).collect();
        self.bindings
            .retain(|address, _| live.contains(address.as_str()));
        for window in &windows {
            if self.blocked.contains(&window.address)
                || self
                    .bindings
                    .get(&window.address)
                    .is_some_and(|r| self.group_protected.contains(r))
            {
                continue;
            }
            if let Some(&index) = self.bindings.get(&window.address) {
                self.layout.records[index] = window.record();
            } else {
                let index = self.layout.records.len();
                self.layout.records.push(window.record());
                self.bindings.insert(window.address.clone(), index);
            }
        }
        if let Err(error) = self
            .track_groups(&windows)
            .and_then(|()| self.layout.validate())
        {
            self.layout = before;
            self.bindings = previous_bindings;
            return Err(error);
        }
        self.unresolved = candidates(&self.layout, &windows).1;
        for &record in &self.group_protected {
            self.unresolved.push(format!(
                "record {record}: group restoration unresolved; saved grouping retained"
            ));
        }
        Ok(self.layout != before)
    }
    fn restore_groups(&mut self, hypr: &mut impl Hyprland) -> Result<()> {
        let Some(groups) = self.layout.groups.clone() else {
            return Ok(());
        };
        let windows = hypr.clients()?;
        for (id, group) in groups.iter().enumerate() {
            let addresses: Option<Vec<String>> = group
                .iter()
                .map(|r| {
                    self.bindings
                        .iter()
                        .find(|(a, index)| *index == r && windows.iter().any(|w| &w.address == *a))
                        .map(|(a, _)| a.clone())
                })
                .collect();
            let Some(addresses) = addresses else {
                self.group_protected.extend(group);
                self.unresolved.push(format!(
                    "group {id}: missing, ambiguous, or failed members; grouping skipped"
                ));
                continue;
            };
            if self.group_attempted.contains(&id) {
                continue;
            }
            self.group_attempted.insert(id);
            let destination = &self.layout.records[group[0]].workspace;
            let correct = |windows: &[Window]| {
                addresses.iter().all(|address| {
                    windows.iter().any(|w| {
                        &w.address == address
                            && w.grouped == addresses
                            && &w.workspace == destination
                    })
                })
            };
            let result = if correct(&windows) {
                Ok(())
            } else {
                hypr.restore_group(&addresses, destination).and_then(|()| {
                    if correct(&hypr.clients()?) {
                        Ok(())
                    } else {
                        bail!("group membership/order was not confirmed")
                    }
                })
            };
            match result {
                Ok(()) => {
                    for r in group {
                        self.group_protected.remove(r);
                    }
                }
                Err(error) => {
                    self.group_protected.extend(group);
                    self.blocked.extend(addresses);
                    self.errors
                        .push(format!("group {id} restoration failed: {error:#}"));
                }
            }
        }
        Ok(())
    }
    fn track_groups(&mut self, windows: &[Window]) -> Result<()> {
        let captured = capture_groups(windows)?;
        if self.layout.groups.is_none() && captured.is_empty() {
            return Ok(());
        }
        let live: HashSet<_> = windows
            .iter()
            .filter_map(|w| self.bindings.get(&w.address).copied())
            .collect();
        let mut groups: Vec<Vec<usize>> = self
            .layout
            .groups
            .clone()
            .unwrap_or_default()
            .into_iter()
            .filter(|g| {
                g.iter()
                    .any(|r| !live.contains(r) || self.group_protected.contains(r))
            })
            .collect();
        // A closed tab retains its group. Follow the remaining group's workspace.
        for group in &groups {
            if group.iter().any(|r| self.group_protected.contains(r)) {
                continue;
            }
            if let Some(workspace) = group
                .iter()
                .find(|r| live.contains(r))
                .map(|r| self.layout.records[*r].workspace.clone())
            {
                for &r in group {
                    self.layout.records[r].workspace = workspace.clone();
                }
            }
        }
        for group in captured {
            let indices: Vec<usize> = group
                .iter()
                .filter_map(|&i| self.bindings.get(&windows[i].address).copied())
                .collect();
            if indices.len() != group.len()
                || indices.iter().any(|r| self.group_protected.contains(r))
            {
                continue;
            }
            if groups.iter().any(|g| g == &indices) {
                continue;
            }
            if groups.iter().any(|g| {
                indices.iter().all(|r| g.contains(r)) && g.iter().any(|r| !live.contains(r))
            }) {
                continue;
            }
            // Explicitly regrouping a live tab supersedes its old membership while
            // keeping closed siblings and their records.
            for existing in &mut groups {
                existing.retain(|r| !indices.contains(r));
            }
            groups.retain(|g| !g.is_empty());
            groups.push(indices);
        }
        groups.sort_by_key(|g| g.iter().min().copied().unwrap_or(usize::MAX));
        self.layout.groups = Some(groups);
        self.layout.version = 2;
        Ok(())
    }
}
