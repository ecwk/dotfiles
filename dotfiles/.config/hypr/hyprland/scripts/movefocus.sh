#!/bin/bash

direction=$1

if [[ "$#" -lt 1 ]]; then
  echo "Must pass direction"
  exit 1
fi

hyprctl dispatch hy3:movefocus $1

while true; do
  read -s -n 1 -t 5 key

  if [[ "$key" == "h" || "$key" == "j" || "$key" == "k" || "$key" == "l" ]]; then
    continue
  else
    hyprctl dispatch submap reset
    break
  fi
done

