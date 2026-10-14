import type GLib from "gi://GLib?version=2.0";
import type { Gdk } from "ags/gtk4";
import { Astal, Gtk } from "ags/gtk4";
import { subprocess } from "ags/process";
import { createComputed, createState } from "gnim";
import { Observable } from "rxjs";

const volumeIcons = ["", "", ""];

function getVolume() {
	return new Promise<{ volume: number; muted: boolean }>((resolve, reject) => {
		subprocess("wpctl get-volume @DEFAULT_AUDIO_SINK@", (out) => {
			const isMuted = out.match(/MUTED/);

			const volume = out.match(/Volume: ([\d.]+)/)?.[1];
			if (!volume) {
				reject(new Error("Could not parse volume from output: " + out));
				return;
			}

			resolve({
				volume: parseFloat(volume),
				muted: !!isMuted,
			});
		});
	});
}

const volume$ = new Observable<{ volume: number; muted: boolean }>(
	(subscriber) => {
		subprocess("pactl subscribe", (out) => {
			const isSinkChange = !!out.match(/Event 'change' on sink #\d+/);

			if (!isSinkChange) return;

			getVolume()
				.then((volume) => {
					subscriber.next(volume);
				})
				.catch((err) => {
					subscriber.error(err);
				});
		});
	},
);

export default function Volume(gdkmonitor: Gdk.Monitor) {
	const [volume, setVolume] = createState<number>(-1);
	const [muted, setMuted] = createState<boolean>(false);
	const [isVisible, setIsVisible] = createState(false);
	const [timeoutId, setTimeoutId] = createState<GLib.Source | null>(null);
	const volumeIcon = createComputed(() => {
		if (muted()) {
			return "";
		}

		const v = volume();
		if (v < 0.35) return volumeIcons[0];
		if (v < 0.7) return volumeIcons[1];
		return volumeIcons[2];
	});
	const volumeFraction = createComputed(() =>
		Math.min(Math.max(volume(), 0), 1),
	);
	const volumeLabel = createComputed(() => `${Math.round(volume() * 100)}%`);

	if (volume() === -1) {
		getVolume()
			.then((v) => {
				setVolume(v.volume);
                setMuted(v.muted);
			})
			.catch((err) => {
				console.error("Error getting initial volume:", err);
			});
	}
	volume$.subscribe((v) => {
		setVolume(v.volume);
        setMuted(v.muted);
		setIsVisible(true);

		const existingTimeoutId = timeoutId();
		if (existingTimeoutId) {
			clearTimeout(existingTimeoutId);
		}
		const newTimeoutId = setTimeout(() => {
			setIsVisible(false);
		}, 2000) as unknown as GLib.Source;
		setTimeoutId(newTimeoutId);
	});

	return (
		<window
			class="Volume"
			gdkmonitor={gdkmonitor}
			layer={Astal.Layer.OVERLAY}
			anchor={Astal.WindowAnchor.BOTTOM}
			visible={isVisible}
		>
			<box spacing={16}>
				<label label={volumeIcon} />
				<Gtk.ProgressBar fraction={volumeFraction} valign={Gtk.Align.CENTER} />
				<label label={volumeLabel} widthChars={4} />
			</box>
		</window>
	);
}
