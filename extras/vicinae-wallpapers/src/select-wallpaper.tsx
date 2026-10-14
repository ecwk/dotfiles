import { useEffect, useRef, useState } from "react";
import { basename, dirname } from "node:path";
import { Action, ActionPanel, List, Icon, command, Collection, Entry, Palette, Mode, ModePicker, WallpaperDetail, usePreview, fail, CancelAction } from "./common";

export default function SelectWallpaper() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [mode, setMode] = useState<Mode>("dark");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const first = useRef<string | undefined>(undefined);
  const seenFirst = useRef(false);
  const preview = usePreview();
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const data = await command<Collection>("list");
        if (!alive) return;
        first.current = data.selected;
        data.entries.sort((a, b) => Number(b.path === data.selected) - Number(a.path === data.selected));
        setEntries(data.entries); setMode(data.mode); setLoading(false);
        // Sequential extraction keeps CPU work bounded while the list stays responsive.
        for (const entry of data.entries.filter(item => !item.palette)) {
          if (!alive) break;
          try {
            const palette = await command<Palette>("extract", entry.path);
            if (alive) setEntries(items => items.map(item => item.path === entry.path ? { ...item, palette } : item));
          } catch (e) { if (alive) setError(`Could not extract ${entry.name}: ${String(e)}`); }
        }
      } catch (e) { if (alive) { setError(String(e)); void fail(e); } }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);
  const select = (path: string) => {
    if (!seenFirst.current) {
      seenFirst.current = true;
      if (path === first.current) return;
    }
    if (!preview.busy) preview.preview(path);
  };
  const apply = async (entry: Entry) => {
    try {
      const active = await preview.commit(entry.path, mode);
      setEntries(items => items.map(item => ({ ...item, activeOn: Object.keys(active).filter(name => active[name] === item.path) })));
    } catch (e) { void fail(e); }
  };
  return <List isLoading={loading || preview.busy} isShowingDetail navigationTitle="Select Wallpaper"
    searchBarPlaceholder="Search wallpapers — Enter saves, Escape restores" onSelectionChange={select}
    searchBarAccessory={<ModePicker mode={mode} onChange={setMode} />}>
    {!entries.length && <List.EmptyView title={error || "No wallpapers found"} description="Images are read from your Waypaper wallpaper folders." />}
    {entries.map(entry => <List.Item key={entry.path} id={entry.path} title={entry.name} subtitle={basename(dirname(entry.path))}
      icon={entry.path} keywords={[entry.path]} accessories={[
        ...(entry.activeOn.length ? [{ text: `✓ Active · ${entry.activeOn.join(", ")}` }] : []),
        ...(preview.previewing === entry.path ? [{ text: "Previewing" }] : []),
      ]}
      detail={<WallpaperDetail image={entry.path} palette={entry.palette} mode={mode} note={preview.error || (preview.previewing === entry.path ? "Temporary preview · Enter to save" : error)} />}
      actions={<ActionPanel>
        <Action title="Apply Wallpaper and Colors" icon={Icon.Checkmark} onAction={() => !preview.busy && apply(entry)} />
        <CancelAction cancel={preview.cancel} />
        <Action.CopyToClipboard title="Copy Wallpaper Path" content={entry.path} />
        {entry.palette && <Action.CopyToClipboard title="Copy Palette JSON" content={JSON.stringify(entry.palette.palettes[mode], null, 2)} />}
      </ActionPanel>} />)}
  </List>;
}
