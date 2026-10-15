mod engine;
mod hypr;
mod model;
mod service;
mod storage;
#[cfg(test)]
mod tests;

use anyhow::{Result, bail};
use clap::{Parser, Subcommand};
use service::Request;

#[derive(Parser)]
#[command(
    version,
    about = "Remember Chrome workspace assignments and restore them in Hyprland"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
enum Command {
    /// Run the background service before Chrome starts.
    Daemon {
        /// Exact Hyprland window class to track.
        #[arg(long, default_value = "google-chrome")]
        class: String,
    },
    /// Replace the layout with current Chrome windows, pruning closed records.
    Save,
    /// Start a new 60-second restoration cycle, or preview without changing anything.
    Restore {
        #[arg(long)]
        dry_run: bool,
    },
    /// Show saved assignments, service health, and unresolved titles.
    Status,
}
fn run() -> Result<()> {
    let request = match Cli::parse().command {
        Command::Daemon { class } => return service::daemon(class),
        Command::Save => Request::Save,
        Command::Restore { dry_run } => Request::Restore { dry_run },
        Command::Status => Request::Status,
    };
    let response = match service::send(&request) {
        Ok(response) => response,
        Err(error) if matches!(request, Request::Status) => {
            let path = storage::state_path()?;
            let layout = storage::load(&path)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "service": "unavailable", "connection_error": format!("{error:#}"),
                    "state_path": path, "saved": layout,
                }))?
            );
            return Ok(());
        }
        Err(error) => return Err(error),
    };
    if !response.ok {
        bail!(
            "{}",
            response
                .error
                .unwrap_or_else(|| "daemon request failed".into())
        );
    }
    println!("{}", serde_json::to_string_pretty(&response.data)?);
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("error: {error:#}");
        std::process::exit(1);
    }
}
