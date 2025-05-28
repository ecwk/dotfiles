#!/usr/bin/env bash

if ! pgrep -x "hyprpaper" > /dev/null; then
  hyprpaper & disown
fi

hyprctl hyprpaper reload $(grep 'monitors =' ~/.config/waypaper/config.ini | cut -d, -f2),$(grep 'wallpaper =' ~/.config/waypaper/config.ini | cut -d, -f2)

hyprctl hyprpaper reload $(grep 'monitors =' ~/.config/waypaper/config.ini | cut -d, -f3),$(grep 'wallpaper =' ~/.config/waypaper/config.ini | cut -d, -f3)

