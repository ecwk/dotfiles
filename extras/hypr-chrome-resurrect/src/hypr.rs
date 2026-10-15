use crate::model::{Hyprland, Window, Workspace};
use anyhow::{Context, Result, bail};
use serde::Deserialize;
use std::{
    env,
    io::Read,
    path::PathBuf,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

pub struct RealHyprland {
    pub class: String,
}
#[derive(Deserialize)]
struct Client {
    address: String,
    class: String,
    title: String,
    workspace: ClientWorkspace,
    #[serde(default = "default_mapped")]
    mapped: bool,
    #[serde(default)]
    grouped: Vec<String>,
}
fn default_mapped() -> bool {
    true
}
#[derive(Deserialize)]
struct ClientWorkspace {
    id: i64,
    name: String,
}

fn run(args: &[&str]) -> Result<String> {
    let mut child = Command::new("hyprctl")
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("starting hyprctl (is it installed?)")?;
    let mut stdout = child.stdout.take().context("missing stdout")?;
    let mut stderr = child.stderr.take().context("missing stderr")?;
    let out = thread::spawn(move || {
        let mut bytes = Vec::new();
        stdout.read_to_end(&mut bytes).map(|_| bytes)
    });
    let err = thread::spawn(move || {
        let mut bytes = Vec::new();
        stderr.read_to_end(&mut bytes).map(|_| bytes)
    });
    let start = Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if start.elapsed() >= Duration::from_secs(3) {
            let _ = child.kill();
            let _ = child.wait();
            bail!("hyprctl timed out after 3 seconds");
        }
        thread::sleep(Duration::from_millis(10));
    };
    let output = out
        .join()
        .map_err(|_| anyhow::anyhow!("stdout reader panicked"))??;
    let error = err
        .join()
        .map_err(|_| anyhow::anyhow!("stderr reader panicked"))??;
    if !status.success() {
        bail!("hyprctl failed: {}", String::from_utf8_lossy(&error));
    }
    String::from_utf8(output).context("hyprctl returned non-UTF-8 data")
}
impl Hyprland for RealHyprland {
    fn clients(&mut self) -> Result<Vec<Window>> {
        let clients: Vec<Client> =
            serde_json::from_str(&run(&["-j", "clients"])?).context("decoding hyprctl clients")?;
        clients
            .into_iter()
            .filter(|c| c.class == self.class && c.mapped)
            .map(|c| {
                // A numeric workspace has its ID as its name. Custom names use name: selectors.
                let workspace = if c.workspace.name == c.workspace.id.to_string() {
                    Workspace::Numeric(c.workspace.id)
                } else {
                    Workspace::Named(c.workspace.name)
                };
                workspace.validate()?;
                Ok(Window {
                    address: c.address,
                    title: c.title,
                    workspace,
                    grouped: c.grouped,
                })
            })
            .collect()
    }
    fn move_window(&mut self, address: &str, workspace: &Workspace) -> Result<()> {
        workspace.validate()?;
        validate_address(address)?;
        let argument = format!("{},address:{address}", workspace.selector());
        let reply = run(&["dispatch", "movetoworkspacesilent", &argument])?;
        if reply.trim() != "ok" {
            bail!("Hyprland rejected move: {}", reply.trim());
        }
        Ok(())
    }
    fn detach_window(&mut self, address: &str) -> Result<()> {
        validate_address(address)?;
        with_focus_restored(|| dispatch("moveoutofgroup", &format!("address:{address}")))
    }
    fn restore_group(&mut self, addresses: &[String], workspace: &Workspace) -> Result<()> {
        if addresses.is_empty() {
            bail!("empty group");
        }
        for address in addresses {
            validate_address(address)?;
        }
        workspace.validate()?;
        let clients: Vec<Client> = serde_json::from_str(&run(&["-j", "clients"])?)?;
        for address in addresses {
            let window = clients
                .iter()
                .find(|w| &w.address == address && w.mapped && w.class == self.class)
                .context("group member disappeared or changed class")?;
            if window.grouped.iter().any(|a| !addresses.contains(a)) {
                bail!("current group contains windows outside the saved group");
            }
        }
        // Pick a workspace absent from Hyprland's list. Only one new member is
        // introduced at a time, so directional grouping has exactly one target.
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let workspaces: Vec<serde_json::Value> =
            serde_json::from_str(&run(&["-j", "workspaces"])?)?;
        let staging = loop {
            let name = format!(
                "hcr-restore-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            );
            if !workspaces.iter().any(|w| w["name"].as_str() == Some(&name)) {
                break Workspace::Named(name);
            }
        };
        with_focus_restored(|| {
            let operation = (|| -> Result<()> {
                // Rebuild from independent windows, including a pre-existing
                // group in the wrong order. We never issue unlock commands.
                for address in addresses {
                    let current = self.clients()?;
                    if current
                        .iter()
                        .any(|w| &w.address == address && !w.grouped.is_empty())
                    {
                        dispatch("moveoutofgroup", &format!("address:{address}"))?;
                        if self
                            .clients()?
                            .iter()
                            .any(|w| &w.address == address && !w.grouped.is_empty())
                        {
                            bail!("could not detach locked group member");
                        }
                    }
                }
                self.move_window(&addresses[0], &staging)?;
                dispatch("focuswindow", &format!("address:{}", addresses[0]))?;
                dispatch("togglegroup", "")?;
                if !self
                    .clients()?
                    .iter()
                    .any(|w| w.address == addresses[0] && w.grouped == addresses[..1])
                {
                    bail!("could not create anchor group");
                }
                for address in &addresses[1..] {
                    self.move_window(address, &staging)?;
                    dispatch("focuswindow", &format!("address:{address}"))?;
                    let mut joined = false;
                    for direction in ["l", "r", "u", "d"] {
                        let all_clients: Vec<Client> =
                            serde_json::from_str(&run(&["-j", "clients"])?)?;
                        if all_clients.iter().any(|w| {
                            w.mapped
                                && w.workspace.name
                                    == match &staging {
                                        Workspace::Named(name) => name.as_str(),
                                        _ => unreachable!(),
                                    }
                                && !addresses.contains(&w.address)
                        }) {
                            bail!(
                                "another window appeared on the temporary workspace; refusing to guess a group target"
                            );
                        }
                        dispatch("moveintogroup", direction)?;
                        let snapshot = self.clients()?;
                        let member = snapshot
                            .iter()
                            .find(|w| &w.address == address)
                            .context("group member disappeared")?;
                        if member.grouped.iter().any(|a| !addresses.contains(a)) {
                            bail!("unexpected group members appeared during restoration");
                        }
                        if member.grouped.contains(&addresses[0]) {
                            joined = true;
                            break;
                        }
                    }
                    if !joined {
                        bail!("could not join saved group (check group locks/rules)");
                    }
                }
                // Joining can insert after the active tab or at the head,
                // depending on group configuration. Reorder explicitly.
                for (index, address) in addresses.iter().enumerate() {
                    dispatch("focuswindow", &format!("address:{address}"))?;
                    for _ in 0..addresses.len() {
                        let snapshot = self.clients()?;
                        let member = snapshot
                            .iter()
                            .find(|w| &w.address == address)
                            .context("group member disappeared")?;
                        if member.grouped.get(index) == Some(address) {
                            break;
                        }
                        dispatch("movegroupwindow", "b")?;
                    }
                }
                Ok(())
            })();
            // Always return surviving members, including after a partial failure.
            let mut cleanup_errors = Vec::new();
            for address in addresses {
                match self.clients() {
                    Ok(windows) if windows.iter().any(|w| &w.address == address) => {
                        let returned = (|| -> Result<()> {
                            if windows.iter().any(|w| {
                                &w.address == address
                                    && w.grouped.iter().any(|a| !addresses.contains(a))
                            }) {
                                dispatch("moveoutofgroup", &format!("address:{address}"))?;
                                if self
                                    .clients()?
                                    .iter()
                                    .any(|w| &w.address == address && !w.grouped.is_empty())
                                {
                                    bail!(
                                        "refusing to move unrelated group members during cleanup"
                                    );
                                }
                            }
                            self.move_window(address, workspace)
                        })();
                        if let Err(error) = returned {
                            cleanup_errors.push(format!("{error:#}"));
                        }
                    }
                    Ok(_) => (),
                    Err(error) => cleanup_errors.push(format!("{error:#}")),
                }
            }
            if !cleanup_errors.is_empty() {
                bail!(
                    "group result: {operation:?}; returning windows failed: {}",
                    cleanup_errors.join("; ")
                );
            }
            operation
        })
    }
}
pub fn event_socket() -> Result<PathBuf> {
    let runtime = env::var_os("XDG_RUNTIME_DIR").context("XDG_RUNTIME_DIR is not set")?;
    let signature = env::var("HYPRLAND_INSTANCE_SIGNATURE")
        .context("HYPRLAND_INSTANCE_SIGNATURE is not set")?;
    if signature.is_empty() || signature.contains('/') {
        bail!("invalid Hyprland instance signature");
    }
    Ok(PathBuf::from(runtime)
        .join("hypr")
        .join(signature)
        .join(".socket2.sock"))
}

fn validate_address(address: &str) -> Result<()> {
    if !address
        .strip_prefix("0x")
        .is_some_and(|s| !s.is_empty() && s.bytes().all(|c| c.is_ascii_hexdigit()))
    {
        bail!("invalid window address {address:?}");
    }
    Ok(())
}
fn dispatch(name: &str, argument: &str) -> Result<()> {
    let reply = run(&["dispatch", name, argument])?;
    if reply.trim() != "ok" {
        bail!("Hyprland rejected {name}: {}", reply.trim());
    }
    Ok(())
}
fn with_focus_restored(operation: impl FnOnce() -> Result<()>) -> Result<()> {
    let window: serde_json::Value = serde_json::from_str(&run(&["-j", "activewindow"])?)?;
    let workspace: serde_json::Value = serde_json::from_str(&run(&["-j", "activeworkspace"])?)?;
    let cursor: serde_json::Value = serde_json::from_str(&run(&["-j", "cursorpos"])?)?;
    let result = operation();
    let restored = (|| -> Result<()> {
        if let Some(address) = window["address"].as_str().filter(|a| !a.is_empty()) {
            validate_address(address)?;
            dispatch("focuswindow", &format!("address:{address}"))?;
        } else if let Some(name) = workspace["name"].as_str() {
            let selector = if name.parse::<i64>().is_ok() || name.starts_with("special") {
                name.to_owned()
            } else {
                format!("name:{name}")
            };
            dispatch("workspace", &selector)?;
        }
        if let (Some(x), Some(y)) = (cursor["x"].as_i64(), cursor["y"].as_i64()) {
            dispatch("movecursor", &format!("{x} {y}"))?;
        }
        Ok(())
    })();
    match (result, restored) {
        (Ok(()), Ok(())) => Ok(()),
        (Err(error), Ok(())) => Err(error),
        (result, Err(error)) => {
            bail!("group operation: {result:?}; restoring focus failed: {error:#}")
        }
    }
}
