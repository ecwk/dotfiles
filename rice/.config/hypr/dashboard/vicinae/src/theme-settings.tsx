import { useEffect, useState } from "react";
import { Action, ActionPanel, List, showToast, Toast } from "@vicinae/api";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { homedir } from "node:os";
const exec = promisify(execFile);
type Settings = { style: string; mode: string; available: boolean };
export default function ThemeSettings() {
  const [state, setState] = useState<Settings>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function update(args: string[] = []) {
    setBusy(true);
    try {
      const result = await exec(`${homedir()}/.local/bin/walltheme`, ["settings", ...args], { timeout: 10000 });
      setState(JSON.parse(result.stdout)); setError("");
    } catch (e) {
      setError(String(e));
      await showToast({ style: Toast.Style.Failure, title: "Theme update failed", message: String(e) });
    } finally { setBusy(false); }
  }
  useEffect(() => { void update(); }, []);
  return <List isLoading={busy} navigationTitle="Theme Settings" searchBarPlaceholder="Theme colors and light mode…">
    {!state && <List.EmptyView title={error ? "Theme unavailable" : "Loading theme…"} description={error} actions={<ActionPanel><Action title="Retry" onAction={() => update()} /></ActionPanel>} />}
    {state && <>
      <List.Section title="Appearance" subtitle="Applies to Waybar and dashboard widgets">
        {[["full", "Full Theme", "Wallpaper backgrounds, text and accents"], ["accents", "Accents Only", "Wallpaper accents with original backgrounds"], ["original", "Application Defaults", "Each application's original colors"]].map(([value, title, subtitle]) =>
          <List.Item key={value} title={title} subtitle={subtitle} accessories={[{ text: state.style === value ? "✓ Selected" : "" }]} actions={<ActionPanel><Action title={`Use ${title}`} onAction={() => update(["--style", value])} /></ActionPanel>} />)}
      </List.Section>
      <List.Section title="Color Mode" subtitle={state.available ? "Full Theme uses light or dark surfaces; Accents Only changes accent colors" : "Apply a wallpaper to enable light/dark mode"}>
        <List.Item title="Light Mode" accessories={[{ text: state.mode === "light" ? "On" : "Off" }]} actions={state.available ? <ActionPanel><Action title={state.mode === "light" ? "Switch to Dark Mode" : "Switch to Light Mode"} onAction={() => update(["--mode", state.mode === "light" ? "dark" : "light"])} /></ActionPanel> : undefined} />
      </List.Section>
      <List.Section title="Other Controls"><List.Item title="Btop styling" subtitle="Configure separately in Dashboard Controls" /></List.Section>
    </>}
  </List>;
}
