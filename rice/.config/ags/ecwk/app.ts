import app from "ags/gtk4/app";
import style from "./style.scss";
import Volume from "./widget/Volume";

app.start({
	css: style,
	main: () => {
		app.get_monitors().map(Volume);
	},
});
