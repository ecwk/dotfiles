import { Action, ActionPanel, List, Icon, showToast, Toast, closeMainWindow } from "@vicinae/api";
import { useEffect, useRef, useState } from "react";
import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";
import { homedir } from "node:os";
import { join } from "node:path";
import { createConnection } from "node:net";
import { randomUUID } from "node:crypto";
import { openSync, closeSync, mkdirSync } from "node:fs";
import { pathToFileURL } from "node:url";

import { cli, Mode, Palette } from "./backend";
export { cli, command, Mode, Palette, Entry, Collection } from "./backend";
const execute = promisify(execFile);
export async function fail(error: unknown) {
  await showToast({ style: Toast.Style.Failure, title: "Wallpaper", message: error instanceof Error ? error.message : String(error) });
}
const pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));

export class PreviewClient {
  token = randomUUID();
  socket = "";
  ended = false;
  async start() {
    const result = await execute(cli, ["socket"]);
    this.socket = result.stdout.trim();
    const logdir = join(process.env.XDG_STATE_HOME || join(homedir(), ".local/state"), "walltheme");
    mkdirSync(logdir, { recursive: true });
    const log = openSync(join(logdir, "preview.log"), "a", 0o600);
    const child = spawn(cli, ["serve", this.token], { detached: true, stdio: ["ignore", log, log] });
    closeSync(log);
    child.unref();
    let last: unknown;
    for (let i = 0; i < 40; i++) {
      try { await this.send("status"); return; }
      catch (e) { last = e; await pause(100); }
    }
    throw last;
  }
  send<T = any>(op: string, fields: Record<string, unknown> = {}): Promise<T> {
    if (this.ended && op !== "cancel") return Promise.reject(new Error("Preview session ended"));
    return new Promise((resolve, reject) => {
      const socket = createConnection(this.socket);
      let body = "";
      socket.setTimeout(120000);
      socket.on("connect", () => socket.write(JSON.stringify({ token: this.token, op, ...fields }) + "\n"));
      socket.on("data", data => {
        body += data;
        if (body.includes("\n")) {
          socket.end();
          try {
            const reply = JSON.parse(body.split("\n")[0]);
            if (reply.ok) resolve(reply.value); else reject(new Error(reply.error));
          } catch (error) { reject(error); }
        }
      });
      socket.on("timeout", () => socket.destroy(new Error("Wallpaper helper timed out")));
      socket.on("error", reject);
      socket.on("end", () => { if (!body.includes("\n")) reject(new Error("Wallpaper helper disconnected")); });
    });
  }
  async cancel() { this.ended = true; await this.send("cancel").catch(() => {}); }
}

export function usePreview() {
  const client = useRef<PreviewClient | undefined>(undefined);
  const starting = useRef<Promise<PreviewClient> | undefined>(undefined);
  const alive = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const version = useRef(0);
  const [previewing, setPreviewing] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const get = async () => {
    if (client.current && !client.current.ended) return client.current;
    if (!starting.current) starting.current = (async () => {
      const next = new PreviewClient();
      await next.start();
      if (!alive.current) { await next.cancel(); throw new Error("Picker closed"); }
      client.current = next;
      return next;
    })().finally(() => { starting.current = undefined; });
    return starting.current;
  };
  useEffect(() => {
    alive.current = true;
    const heartbeat = setInterval(() => {
      const current = client.current;
      if (current && !current.ended) current.send("heartbeat").catch(() => {
        current.ended = true;
        if (alive.current) setPreviewing(undefined);
      });
    }, 750);
    return () => {
      alive.current = false;
      version.current++;
      clearTimeout(timer.current);
      clearInterval(heartbeat);
      void client.current?.cancel();
    };
  }, []);
  const preview = (image: string, immediate = false) => {
    clearTimeout(timer.current);
    const request = ++version.current;
    const apply = async () => {
      try {
        const session = await get();
        if (request !== version.current || !alive.current) return;
        const result = await session.send("preview", { image });
        if (alive.current && request === version.current && !result.skipped) { setPreviewing(image); setError(undefined); }
      } catch (e) { if (alive.current) { setError(String(e)); void fail(e); } }
    };
    if (immediate) return apply();
    timer.current = setTimeout(() => void apply(), 150);
  };
  const commit = async (image: string, mode: Mode) => {
    clearTimeout(timer.current);
    version.current++;
    setBusy(true);
    try {
      const session = await get();
      const result = await session.send<{ active: Record<string, string> }>("commit", { image, mode });
      setPreviewing(undefined);
      await showToast({ style: Toast.Style.Success, title: "Wallpaper and colors saved" });
      return result.active;
    } finally { if (alive.current) setBusy(false); }
  };
  const cancel = async () => {
    clearTimeout(timer.current); version.current++;
    await client.current?.cancel(); client.current = undefined;
    if (alive.current) setPreviewing(undefined);
  };
  return { preview, commit, cancel, previewing, busy, error };
}

export function ModePicker({ mode, onChange }: { mode: Mode; onChange: (mode: Mode) => void }) {
  return <List.Dropdown tooltip="Palette mode" value={mode} onChange={value => onChange(value as Mode)} storeValue={false}>
    <List.Dropdown.Item title="Dark colors" value="dark" />
    <List.Dropdown.Item title="Light colors" value="light" />
  </List.Dropdown>;
}
const labels: Record<string, string> = { background: "Background", surface: "Surface", foreground: "Text", muted: "Muted text", border: "Border", accent: "Accent", on_accent: "Text on accent" };
export function WallpaperDetail({ image, palette, mode, estimated, note }: { image?: string; palette?: Palette; mode: Mode; estimated?: boolean; note?: string }) {
  const markdown = image ? `![Wallpaper](<${image.startsWith("https:") ? image : pathToFileURL(image).href}>)` : "Loading preview…";
  return <List.Item.Detail markdown={markdown} metadata={<List.Item.Detail.Metadata>
    <List.Item.Detail.Metadata.Label title="Palette" text={`${mode === "dark" ? "Dark" : "Light"}${estimated ? " · Estimated from thumbnail" : ""}`} />
    {note && <List.Item.Detail.Metadata.Label title="Status" text={note} />}
    {palette ? Object.entries(palette.palettes[mode]).map(([role, hex]) =>
      <List.Item.Detail.Metadata.Label key={role} title={labels[role] || role} text={hex} icon={palette.swatches?.[mode]?.[role]} />
    ) : <List.Item.Detail.Metadata.Label title="Colors" text="Generating…" />}
  </List.Item.Detail.Metadata>} />;
}
export function CancelAction({ cancel }: { cancel: () => Promise<void> }) {
  return <Action title="Cancel Preview" icon={Icon.XMarkCircle} onAction={async () => { await cancel(); await closeMainWindow(); }} />;
}
export { Action, ActionPanel, List, Icon };
