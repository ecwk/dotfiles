#!/bin/zsh
case "$1" in
    up)
        wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+
        volume=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ | awk '{print $2}')
        volume=$(($volume * 100))
        # notify-send -e -t 2000 $(printf "%.0f" "$volume")
    ;;
    down)
        wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%-
        volume=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ | awk '{print $2}')
        volume=$(($volume * 100))
        # notify-send -e -t 2000 $(printf "%.0f" "$volume")
    ;;
    mute)
        wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle
        # muted=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ | awk '{print $3}')
        # if [[ -z "$muted" ]]; then
        #     notify-send -e -t 2000 "Unmuted"
        # else
        #     notify-send -e -t 2000 "Muted"
        # fi
    ;;
esac
