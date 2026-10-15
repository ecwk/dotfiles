import { useEffect, useRef, useState } from "react";
import { showToast, Toast } from "@vicinae/api";
import { Action, ActionPanel, List, Icon, command, Collection, Palette, Mode, ModePicker, WallpaperDetail, usePreview, fail, CancelAction } from "./common";
import { search, image, save, Wallpaper } from "./online";

export default function SearchWallpapers() {
  const [query, setQuery] = useState("");
  const [retry, setRetry] = useState(0);
  const [items, setItems] = useState<Wallpaper[]>([]);
  const [mode, setMode] = useState<Mode>("dark");
  const [resolution, setResolution] = useState("");
  const [ratio, setRatio] = useState("");
  const [page, setPage] = useState(1);
  const [lastPage, setLastPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string>();
  const [selected, setSelected] = useState<string>();
  const [assets, setAssets] = useState<Record<string, { path: string; palette: Palette; full: boolean }>>({});
  const [saved, setSaved] = useState<Record<string, string>>({});
  const [activeId, setActiveId] = useState<string>();
  const [previewId, setPreviewId] = useState<string>();
  const folder = useRef("");
  const operation = useRef<AbortController | undefined>(undefined);
  const preview = usePreview();
  useEffect(() => {
    void command<Collection>("list").then(data => { folder.current = data.folder; setMode(data.mode); }).catch(fail);
    return () => operation.current?.abort();
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true); setError(undefined);
    const timer = setTimeout(() => {
      void search(query, page, resolution, ratio, abort.signal).then(data => {
        if (abort.signal.aborted) return;
        setItems(old => page === 1 ? data.data : [...old, ...data.data.filter(item => !old.some(other => other.id === item.id))]);
        setLastPage(data.meta.last_page);
        if (page === 1) setSelected(data.data[0]?.id);
      }).catch(e => { if (!abort.signal.aborted) { setError(String(e)); if (page === 1) setItems([]); } })
        .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    }, 400);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [query, page, resolution, ratio, retry]);
  useEffect(() => {
    const item = items.find(item => item.id === selected);
    if (!item || assets[item.id]) return;
    const abort = new AbortController();
    const timer = setTimeout(() => {
      void image(item, false, abort.signal).then(asset => {
        if (!abort.signal.aborted) setAssets(old => old[item.id]?.full ? old : { ...old, [item.id]: { ...asset, full: false } });
      }).catch(e => { if (!abort.signal.aborted) setError(String(e)); });
    }, 150);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [selected, items]);
  const act = async (item: Wallpaper, action: "try" | "save" | "apply") => {
    if (working || preview.busy) return;
    const controller = new AbortController(); operation.current = controller;
    setWorking(true);
    try {
      if (action === "try") {
        const asset = await image(item, true, controller.signal);
        controller.signal.throwIfAborted();
        setAssets(old => ({ ...old, [item.id]: { ...asset, full: true } }));
        await preview.preview(asset.path, true); setPreviewId(item.id);
      } else {
        if (!folder.current) throw new Error("Wallpaper collection is not ready");
        const asset = await save(item, folder.current, controller.signal);
        controller.signal.throwIfAborted();
        setAssets(old => ({ ...old, [item.id]: { ...asset, full: true } }));
        setSaved(old => ({ ...old, [item.id]: asset.path }));
        if (action === "apply") { await preview.commit(asset.path, mode); setActiveId(item.id); setPreviewId(undefined); }
        else await showToast({ style: Toast.Style.Success, title: "Saved to wallpaper collection" });
      }
    } catch (e) { if (!controller.signal.aborted) void fail(e); }
    finally { setWorking(false); operation.current = undefined; }
  };
  const filters = <ActionPanel.Section title="Search filters">
    <ActionPanel.Submenu title="Minimum Resolution" icon={Icon.MagnifyingGlass}>
      {["", "1920x1080", "2560x1440", "2880x1800", "3840x2160"].map(value => <Action key={value} title={value || "Any resolution"} onAction={() => { setResolution(value); setPage(1); }} />)}
    </ActionPanel.Submenu>
    <ActionPanel.Submenu title="Aspect Ratio" icon={Icon.MagnifyingGlass}>
      {["", "16x9", "16x10", "21x9", "9x16"].map(value => <Action key={value} title={value || "Any ratio"} onAction={() => { setRatio(value); setPage(1); }} />)}
    </ActionPanel.Submenu>
    <Action title="Retry Search" icon={Icon.ArrowClockwise} onAction={() => { setRetry(value => value + 1); setPage(1); }} />
  </ActionPanel.Section>;
  // Reapplying searchText on detail renders resets selection in Vicinae 0.20.5.
  // Let Vicinae own the input; query still drives the remote search.
  return <List isLoading={loading || working || preview.busy} isShowingDetail filtering={false}
    navigationTitle={`Search Wallpapers · ${resolution || "Any size"} · ${ratio || "Any ratio"}`}
    searchBarPlaceholder="Search Wallhaven — Enter to download and try"
    onSearchTextChange={text => { setQuery(text); setPage(1); }} onSelectionChange={setSelected}
    searchBarAccessory={<ModePicker mode={mode} onChange={setMode} />}
    actions={<ActionPanel>{filters}</ActionPanel>}>
    {!items.length && <List.EmptyView title={error || (loading ? "Searching Wallhaven…" : "No wallpapers found")} description="Try different keywords or adjust the search filters in Actions." />}
    {items.map(item => <List.Item id={item.id} key={item.id} title={item.id} subtitle={item.resolution}
      icon={item.thumbs.small} accessories={[
        ...(activeId === item.id ? [{ text: "✓ Active" }] : []),
        ...(preview.previewing && previewId === item.id ? [{ text: "Previewing" }] : []),
        ...(saved[item.id] ? [{ text: "Saved" }] : []),
      ]}
      detail={<WallpaperDetail image={assets[item.id]?.path || item.thumbs.large} palette={assets[item.id]?.palette} mode={mode}
        estimated={!assets[item.id]?.full} note={error || `${item.resolution} · ${(item.file_size / 1048576).toFixed(1)} MB`} />}
      actions={<ActionPanel>
        <Action title="Try Wallpaper" icon={Icon.Eye} onAction={() => act(item, "try")} />
        <Action title="Save and Apply" icon={Icon.Checkmark} onAction={() => act(item, "apply")} />
        <Action title="Save to Collection" icon={Icon.Download} onAction={() => act(item, "save")} />
        {working && <Action title="Cancel Download" icon={Icon.XMarkCircle} onAction={() => operation.current?.abort()} />}
        <CancelAction cancel={async () => { operation.current?.abort(); await preview.cancel(); }} />
        <Action.OpenInBrowser title="Open Wallpaper Source" url={item.url} />
        {page < lastPage && <Action title="Load More Results" icon={Icon.Plus} onAction={() => !loading && setPage(value => value + 1)} />}
        {filters}
      </ActionPanel>} />)}
  </List>;
}
