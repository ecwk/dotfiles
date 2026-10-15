use crate::{
    engine::Engine,
    hypr::{self, RealHyprland},
    model::{Hyprland, Layout},
    storage,
};
use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    env,
    fs::{self, File, OpenOptions},
    io::{BufRead, BufReader, Read, Write},
    os::{
        fd::AsRawFd,
        unix::{
            fs::{DirBuilderExt, MetadataExt, OpenOptionsExt, PermissionsExt},
            net::{UnixListener, UnixStream},
        },
    },
    path::{Path, PathBuf},
    sync::mpsc::{self, Receiver, SyncSender},
    thread,
    time::{Duration, Instant},
};

const MAX_REQUEST: u64 = 4096;
const POLL: Duration = Duration::from_secs(2);
const DEBOUNCE: Duration = Duration::from_millis(200);
#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "command", rename_all = "snake_case")]
pub enum Request {
    Save,
    Restore { dry_run: bool },
    Status,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Response {
    pub ok: bool,
    pub data: Value,
    pub error: Option<String>,
}
impl Response {
    fn success(data: Value) -> Self {
        Self {
            ok: true,
            data,
            error: None,
        }
    }
    fn failure(error: anyhow::Error) -> Self {
        Self {
            ok: false,
            data: Value::Null,
            error: Some(format!("{error:#}")),
        }
    }
}
enum Message {
    Request(Request, UnixStream),
    Event,
    Closed(String),
    Connection(Option<String>),
}

pub fn socket_path() -> Result<PathBuf> {
    let runtime = env::var_os("XDG_RUNTIME_DIR")
        .filter(|s| !s.is_empty())
        .context("XDG_RUNTIME_DIR is not set")?;
    Ok(PathBuf::from(runtime).join("hypr-chrome-resurrect/service.sock"))
}
pub fn send(request: &Request) -> Result<Response> {
    let mut stream = UnixStream::connect(socket_path()?)
        .context("connecting to daemon; start `hypr-chrome-resurrect daemon` first")?;
    stream.set_read_timeout(Some(Duration::from_secs(30)))?;
    stream.set_write_timeout(Some(Duration::from_secs(3)))?;
    serde_json::to_writer(&mut stream, request)?;
    stream.write_all(b"\n")?;
    let mut line = String::new();
    BufReader::new(stream)
        .take(16 * 1024 * 1024)
        .read_line(&mut line)?;
    serde_json::from_str(&line).context("decoding daemon reply")
}

// Linux advisory locking releases the lock even after SIGKILL. The lock file stays
// in place so two starters can never lock different inodes after a stale cleanup.
unsafe extern "C" {
    fn flock(fd: std::ffi::c_int, operation: std::ffi::c_int) -> std::ffi::c_int;
    fn getuid() -> u32;
}
fn bind(path: &Path) -> Result<(UnixListener, File)> {
    let directory = path.parent().context("socket path has no parent")?;
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(directory)?;
    let metadata = fs::symlink_metadata(directory)?;
    // SAFETY: getuid has no arguments and no memory side effects.
    if !metadata.is_dir() || metadata.uid() != unsafe { getuid() } {
        bail!("runtime service directory must be owned by this user and must not be a symlink");
    }
    fs::set_permissions(directory, fs::Permissions::from_mode(0o700))?;
    let lock = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .mode(0o600)
        .open(directory.join("daemon.lock"))?;
    // SAFETY: the descriptor belongs to the live File; LOCK_EX | LOCK_NB never blocks.
    if unsafe { flock(lock.as_raw_fd(), 2 | 4) } != 0 {
        bail!(
            "another daemon owns the service lock: {}",
            std::io::Error::last_os_error()
        );
    }
    match fs::remove_file(path) {
        Ok(()) => (),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(e) => return Err(e.into()),
    }
    let listener = UnixListener::bind(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    Ok((listener, lock))
}
fn reply(stream: &mut UnixStream, response: &Response) -> Result<()> {
    let mut bytes = serde_json::to_vec(response)?;
    bytes.push(b'\n');
    stream.write_all(&bytes)?;
    Ok(())
}
fn listen(listener: UnixListener, tx: SyncSender<Message>) {
    thread::spawn(move || {
        for incoming in listener.incoming() {
            let mut stream = match incoming {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("accept: {e}");
                    continue;
                }
            };
            let parsed = (|| -> Result<Request> {
                stream.set_read_timeout(Some(Duration::from_secs(2)))?;
                stream.set_write_timeout(Some(Duration::from_secs(2)))?;
                let mut line = String::new();
                BufReader::new(&stream)
                    .take(MAX_REQUEST)
                    .read_line(&mut line)?;
                if !line.ends_with('\n') {
                    bail!("request must be a newline-terminated JSON object under 4096 bytes");
                }
                Ok(serde_json::from_str(&line)?)
            })();
            match parsed {
                Ok(request) => {
                    if tx.send(Message::Request(request, stream)).is_err() {
                        break;
                    }
                }
                Err(error) => {
                    let _ = reply(&mut stream, &Response::failure(error));
                }
            }
        }
    });
}
fn events(tx: SyncSender<Message>) {
    thread::spawn(move || {
        loop {
            let result = (|| -> Result<()> {
                let stream = UnixStream::connect(hypr::event_socket()?)
                    .context("connecting to Hyprland event socket")?;
                let _ = tx.send(Message::Connection(None));
                for line in BufReader::new(stream).lines() {
                    let line = line?;
                    let event = line.split_once(">>").map(|(name, _)| name).unwrap_or("");
                    if event == "closewindow" {
                        if let Some((_, address)) = line.split_once(">>") {
                            let address = if address.starts_with("0x") {
                                address.to_owned()
                            } else {
                                format!("0x{address}")
                            };
                            let _ = tx.try_send(Message::Closed(address));
                        }
                        continue;
                    }
                    if matches!(
                        event,
                        "openwindow"
                            | "closewindow"
                            | "windowtitle"
                            | "windowtitlev2"
                            | "movewindow"
                            | "movewindowv2"
                            | "togglegroup"
                            | "moveintogroup"
                            | "moveoutofgroup"
                            | "lockgroups"
                            | "renameworkspace"
                            | "configreloaded"
                    ) {
                        // A full channel already guarantees a pending refresh. Never hold up IPC event draining.
                        let _ = tx.try_send(Message::Event);
                    }
                }
                bail!("Hyprland event socket disconnected")
            })();
            if let Err(error) = result {
                if tx
                    .send(Message::Connection(Some(format!("{error:#}"))))
                    .is_err()
                {
                    break;
                }
            }
            thread::sleep(Duration::from_secs(2));
        }
    });
}
fn handle(
    request: Request,
    engine: &mut Engine,
    hypr: &mut impl Hyprland,
    path: &Path,
    now: u64,
    health: &Health,
) -> Result<Value> {
    match request {
        Request::Status => Ok(json!({
            "service": "running", "phase": engine.phase(), "state_path": path,
            "saved": engine.layout, "unresolved": engine.unresolved,
            "failed_moves": engine.errors, "hyprland_error": health.refresh_error,
            "event_connection_error": health.event_error, "persistence_error": health.persistence_error,
        })),
        Request::Save => {
            let windows = hypr.clients()?;
            if windows.is_empty() {
                bail!("refusing to save an empty Chrome layout");
            }
            let layout = Layout::capture(&windows)?;
            storage::store(path, &layout)?; // Only commit the new engine baseline after durable persistence.
            engine.save(&windows)?;
            Ok(json!({ "saved_records": engine.layout.records.len() }))
        }
        Request::Restore { dry_run: true } => {
            Ok(serde_json::to_value(engine.preview(&hypr.clients()?))?)
        }
        Request::Restore { dry_run: false } => {
            // Check connectivity before clearing a running cycle's bindings.
            hypr.clients()?;
            engine.retry();
            engine.refresh(hypr, now)?;
            Ok(
                json!({ "phase": engine.phase(), "unresolved": engine.unresolved, "failed_moves": engine.errors }),
            )
        }
    }
}
#[derive(Default)]
struct Health {
    refresh_error: Option<String>,
    event_error: Option<String>,
    persistence_error: Option<String>,
}

pub fn daemon(class: String) -> Result<()> {
    let path = storage::state_path()?;
    let socket = socket_path()?;
    let (listener, _lock) = bind(&socket)?;
    let mut engine = Engine::new(storage::load(&path)?);
    let (tx, rx): (SyncSender<Message>, Receiver<Message>) = mpsc::sync_channel(64);
    listen(listener, tx.clone());
    events(tx);
    let mut hypr = RealHyprland { class };
    let epoch = Instant::now();
    let mut next_poll = Instant::now();
    let mut debounce = None;
    let mut persisted = engine.layout.clone();
    let mut health = Health::default();
    eprintln!(
        "daemon listening at {}; state at {}",
        socket.display(),
        path.display()
    );
    loop {
        let deadline = debounce.map_or(next_poll, |d: Instant| d.min(next_poll));
        match rx.recv_timeout(deadline.saturating_duration_since(Instant::now())) {
            Ok(Message::Request(request, mut stream)) => {
                let is_save = matches!(request, Request::Save);
                let response = match handle(
                    request,
                    &mut engine,
                    &mut hypr,
                    &path,
                    epoch.elapsed().as_secs(),
                    &health,
                ) {
                    Ok(data) => {
                        if is_save {
                            persisted = engine.layout.clone();
                            health.persistence_error = None;
                        }
                        Response::success(data)
                    }
                    Err(error) => Response::failure(error),
                };
                if let Err(error) = reply(&mut stream, &response) {
                    eprintln!("reply failed: {error:#}");
                }
            }
            Ok(Message::Event) => {
                debounce = Some(Instant::now() + DEBOUNCE);
            }
            Ok(Message::Closed(address)) => {
                engine.closed(&address);
                debounce = Some(Instant::now() + DEBOUNCE);
            }
            Ok(Message::Connection(error)) => {
                health.event_error = error;
                debounce = Some(Instant::now() + DEBOUNCE);
            }
            Err(mpsc::RecvTimeoutError::Timeout) => (),
            Err(mpsc::RecvTimeoutError::Disconnected) => bail!("service channel disconnected"),
        }
        let now = Instant::now();
        if now >= next_poll || debounce.is_some_and(|d| now >= d) {
            let previous_errors = engine.errors.len();
            match engine.refresh(&mut hypr, epoch.elapsed().as_secs()) {
                Ok(_) => health.refresh_error = None,
                Err(error) => {
                    let message = format!("{error:#}");
                    if health.refresh_error.as_ref() != Some(&message) {
                        eprintln!("Hyprland refresh failed: {message}");
                    }
                    health.refresh_error = Some(message);
                }
            }
            for error in &engine.errors[previous_errors.min(engine.errors.len())..] {
                eprintln!("{error}");
            }
            if engine.layout != persisted {
                match storage::store(&path, &engine.layout) {
                    Ok(()) => {
                        persisted = engine.layout.clone();
                        health.persistence_error = None;
                    }
                    Err(error) => {
                        let message = format!("{error:#}");
                        if health.persistence_error.as_ref() != Some(&message) {
                            eprintln!("state save failed: {message}");
                        }
                        health.persistence_error = Some(message);
                    }
                }
            }
            next_poll = Instant::now() + POLL;
            debounce = None;
        }
    }
}
