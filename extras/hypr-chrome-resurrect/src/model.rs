use anyhow::{Result, bail};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum Workspace {
    Numeric(i64),
    Named(String),
}
impl Workspace {
    pub fn validate(&self) -> Result<()> {
        match self {
            Self::Numeric(id) if *id > 0 => Ok(()),
            Self::Named(name)
                if !name.is_empty()
                    && !name.contains([',', '\n', '\r', '\0'])
                    && name != "special"
                    && !name.starts_with("special:") =>
            {
                Ok(())
            }
            _ => bail!("unsupported workspace destination: {self:?}"),
        }
    }
    pub fn selector(&self) -> String {
        match self {
            Self::Numeric(id) => id.to_string(),
            Self::Named(name) => format!("name:{name}"),
        }
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Record {
    pub title: String,
    pub workspace: Workspace,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Layout {
    pub version: u32,
    pub records: Vec<Record>,
    /// Record indices in tab order. None means legacy state with unknown groups.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub groups: Option<Vec<Vec<usize>>>,
}
impl Default for Layout {
    fn default() -> Self {
        Self {
            version: 1,
            records: Vec::new(),
            groups: None,
        }
    }
}
impl Layout {
    pub fn validate(&self) -> Result<()> {
        if !matches!(self.version, 1 | 2) {
            bail!("unsupported state version {}", self.version);
        }
        for record in &self.records {
            record.workspace.validate()?;
        }
        if self.version == 1 && self.groups.is_some() {
            bail!("version 1 cannot contain groups");
        }
        if self.version == 2 && self.groups.is_none() {
            bail!("version 2 requires groups");
        }
        let mut seen = std::collections::HashSet::new();
        for group in self.groups.iter().flatten() {
            if group.is_empty() {
                bail!("saved group cannot be empty");
            }
            let mut workspace = None;
            for &index in group {
                let record = self
                    .records
                    .get(index)
                    .ok_or_else(|| anyhow::anyhow!("group references missing record {index}"))?;
                if !seen.insert(index) {
                    bail!("record {index} belongs to multiple group positions");
                }
                if workspace.is_some_and(|w| w != &record.workspace) {
                    bail!("group members must share a workspace");
                }
                workspace = Some(&record.workspace);
            }
        }
        Ok(())
    }
    pub fn capture(windows: &[Window]) -> Result<Self> {
        let layout = Self {
            version: 2,
            records: windows.iter().map(Window::record).collect(),
            groups: Some(capture_groups(windows)?),
        };
        layout.validate()?;
        Ok(layout)
    }
}
pub fn capture_groups(windows: &[Window]) -> Result<Vec<Vec<usize>>> {
    let lookup: std::collections::HashMap<_, _> = windows
        .iter()
        .enumerate()
        .map(|(i, w)| (w.address.as_str(), i))
        .collect();
    let mut groups = Vec::new();
    for window in windows {
        if window.grouped.is_empty() {
            continue;
        }
        let indices: Vec<usize> = window
            .grouped
            .iter()
            .map(|address| {
                lookup.get(address.as_str()).copied().ok_or_else(|| {
                    anyhow::anyhow!("cannot capture group containing an untracked window {address}")
                })
            })
            .collect::<Result<_>>()?;
        if !indices.contains(&lookup[window.address.as_str()]) {
            bail!("inconsistent group membership");
        }
        for &i in &indices {
            if windows[i].grouped != window.grouped {
                bail!("inconsistent group order in client snapshot");
            }
        }
        if !groups.contains(&indices) {
            groups.push(indices);
        }
    }
    Ok(groups)
}
#[derive(Clone, Debug)]
pub struct Window {
    pub address: String,
    pub title: String,
    pub workspace: Workspace,
    pub grouped: Vec<String>,
}
impl Window {
    pub fn record(&self) -> Record {
        Record {
            title: self.title.clone(),
            workspace: self.workspace.clone(),
        }
    }
}

pub trait Hyprland {
    fn clients(&mut self) -> Result<Vec<Window>>;
    fn move_window(&mut self, address: &str, workspace: &Workspace) -> Result<()>;
    fn detach_window(&mut self, address: &str) -> Result<()>;
    fn restore_group(&mut self, addresses: &[String], workspace: &Workspace) -> Result<()>;
}
