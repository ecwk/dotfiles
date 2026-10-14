import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { command, Palette } from "./backend";

export type Wallpaper = { id: string; url: string; source?: string; path: string; resolution: string; file_size: number; file_type: string; thumbs: { small: string; large: string } };
export type Results = { data: Wallpaper[]; meta: { current_page: number; last_page: number } };
const cache = join(process.env.XDG_CACHE_HOME || join(homedir(), ".cache"), "walltheme");
async function response(url: string, signal: AbortSignal) {
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" || !(parsed.hostname === "wallhaven.cc" || parsed.hostname.endsWith(".wallhaven.cc"))) throw new Error("Unexpected wallpaper host");
  const reply = await fetch(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]), redirect: "error", headers: { "User-Agent": "Walltheme/1.0 (Vicinae wallpaper picker)" } });
  if (reply.status === 429) throw new Error("Wallhaven rate limit reached. Wait a minute before retrying.");
  if (!reply.ok) throw new Error(`Wallhaven returned HTTP ${reply.status}`);
  return reply;
}
export async function search(query: string, page: number, resolution: string, ratio: string, signal: AbortSignal): Promise<Results> {
  const params = new URLSearchParams({ q: query, page: String(page), purity: "100", categories: "111", sorting: query ? "relevance" : "toplist", order: "desc" });
  if (resolution) params.set("atleast", resolution);
  if (ratio) params.set("ratios", ratio);
  const key = createHash("sha256").update(params.toString()).digest("hex");
  const file = join(cache, `search-${key}.json`);
  try { if (Date.now() - (await fs.stat(file)).mtimeMs < 15 * 60000) return JSON.parse(await fs.readFile(file, "utf8")); } catch {}
  const data = await (await response(`https://wallhaven.cc/api/v1/search?${params}`, signal)).json() as Results;
  if (!Array.isArray(data.data) || !data.meta) throw new Error("Invalid Wallhaven search response");
  data.data = data.data.filter(item => /^[a-z0-9]{6}$/.test(item.id) && ["image/jpeg", "image/png"].includes(item.file_type));
  await fs.mkdir(cache, { recursive: true });
  await fs.writeFile(file, JSON.stringify(data));
  return data;
}
export async function image(wallpaper: Wallpaper, full: boolean, signal: AbortSignal): Promise<{ path: string; palette: Palette }> {
  if (!/^[a-z0-9]{6}$/.test(wallpaper.id)) throw new Error("Invalid wallpaper ID");
  const extension = full && wallpaper.file_type === "image/png" ? "png" : "jpg";
  const path = join(cache, `${full ? "full" : "thumb"}-${wallpaper.id}.${extension}`);
  await fs.mkdir(cache, { recursive: true });
  try { await fs.access(path); } catch {
    if (full && wallpaper.file_size > 50 * 1024 * 1024) throw new Error("This wallpaper exceeds the 50 MB download limit");
    const reply = await response(full ? wallpaper.path : wallpaper.thumbs.large, signal);
    const limit = full ? 50 * 1024 * 1024 : 5 * 1024 * 1024;
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (!reply.body) throw new Error("Empty wallpaper download");
    for await (const chunk of reply.body) {
      size += chunk.byteLength;
      if (size > limit) throw new Error("Wallpaper download is too large");
      chunks.push(chunk);
    }
    signal.throwIfAborted();
    const temp = `${path}.${process.pid}.tmp`;
    await fs.writeFile(temp, Buffer.concat(chunks));
    await fs.rename(temp, path);
  }
  signal.throwIfAborted();
  try { return { path, palette: await command<Palette>("extract", path) }; }
  catch (e) { await fs.unlink(path).catch(() => {}); throw e; }
}
export async function save(wallpaper: Wallpaper, folder: string, signal: AbortSignal) {
  const downloaded = await image(wallpaper, true, signal);
  const dir = join(folder, "wallhaven");
  await fs.mkdir(dir, { recursive: true });
  const path = join(dir, `wallhaven-${wallpaper.id}.${wallpaper.file_type === "image/png" ? "png" : "jpg"}`);
  await fs.copyFile(downloaded.path, path, 1).catch((error: NodeJS.ErrnoException) => { if (error.code !== "EEXIST") throw error; });
  await fs.writeFile(`${path}.source.json`, JSON.stringify({ provider: "wallhaven", id: wallpaper.id, url: wallpaper.url, source: wallpaper.source || null }, null, 2));
  const palette = await command<Palette>("extract", path);
  return { path, palette };
}
