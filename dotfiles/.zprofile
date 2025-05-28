if uwsm check may-start -q && uwsm select; then
	exec systemd-cat -t uwsm_start uwsm start default
fi

# Created by `pipx` on 2025-05-10 18:00:47
export PATH="$PATH:/home/ecwk/.local/bin"
