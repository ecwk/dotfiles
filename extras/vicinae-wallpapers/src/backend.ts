import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { homedir } from "node:os";
import { join } from "node:path";

export type Mode = "dark" | "light";
export type Palette = { id: string; wallpaper?: string; palettes: Record<Mode, Record<string, string>>; swatches?: Record<Mode, Record<string, string>> };
export type Entry = { path: string; name: string; activeOn: string[]; palette?: Palette };
export type Collection = { entries: Entry[]; active: Record<string, string>; selected?: string; mode: Mode; folder: string };
export const cli = join(homedir(), ".local/bin/walltheme");
const execute = promisify(execFile);
export async function command<T>(...args: string[]): Promise<T> {
  const { stdout } = await execute(cli, args, { timeout: 120000, maxBuffer: 8 * 1024 * 1024 });
  return JSON.parse(stdout);
}
