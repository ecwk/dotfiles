use crate::model::Layout;
use anyhow::{Context, Result};
use std::{
    env,
    fs::{self, File, OpenOptions},
    io::Write,
    os::unix::fs::{DirBuilderExt, OpenOptionsExt},
    path::{Path, PathBuf},
};

pub fn state_path() -> Result<PathBuf> {
    let base = match env::var_os("XDG_STATE_HOME").filter(|s| !s.is_empty()) {
        Some(base) => PathBuf::from(base),
        None => PathBuf::from(env::var_os("HOME").context("HOME is not set")?).join(".local/state"),
    };
    Ok(base.join("hypr-chrome-resurrect/layout.json"))
}
pub fn load(path: &Path) -> Result<Option<Layout>> {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error).context("reading saved layout"),
    };
    let layout: Layout = serde_json::from_slice(&bytes)
        .with_context(|| format!("malformed state at {}; left untouched", path.display()))?;
    layout
        .validate()
        .with_context(|| format!("invalid state at {}; left untouched", path.display()))?;
    Ok(Some(layout))
}
fn replace(path: &Path, bytes: &[u8]) -> Result<()> {
    let temporary = path.with_extension(format!("tmp-{}", std::process::id()));
    // Remove only our own abandoned temp file; never follow a pre-existing symlink.
    match fs::remove_file(&temporary) {
        Ok(()) => (),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
        Err(e) => return Err(e.into()),
    }
    let result = (|| -> Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temporary)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        fs::rename(&temporary, path)?;
        File::open(path.parent().context("state path has no parent")?)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(temporary);
    }
    result
}
pub fn store(path: &Path, layout: &Layout) -> Result<()> {
    layout.validate()?;
    let parent = path.parent().context("state path has no parent")?;
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(parent)?;
    // Validate the existing file again before any write, even if it changed since startup.
    if load(path)?.is_some() {
        replace(&path.with_extension("json.bak"), &fs::read(path)?)?;
    }
    let mut bytes = serde_json::to_vec_pretty(layout)?;
    bytes.push(b'\n');
    replace(path, &bytes).context("atomically saving layout")
}
