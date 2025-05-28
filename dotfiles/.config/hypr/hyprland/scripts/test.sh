#!/bin/bash


handle() {
  case $1 in
    activewindow*)
      echo 123
      exit 0
    ;;
  esac
}
timeout=5000
while true; do
  sleep 0.1
  timeout=$(($timeout - 100))
echo 123
socket=$(socat -U - UNIX-CONNECT:$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock &)
echo 1235
pid=$!
socat -U - UNIX-CONNECT:$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock | while read -r line; do handle "$line"; done

kill -9 $pid
#$socket=$(socat -U - UNIX-CONNECT:$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock | while read -r line; do handle "$line"; done)

