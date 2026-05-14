#!/usr/bin/env bash

# Usage: rofi -show memes -modi memes:$PWD/rofi-search.sh -theme fullscreen-preview.rasi

if [[ -n "$1" ]]; then
    id="$(grep -oP '^\[\K[0-9]+(?=\])' <<< "$1")"

    result="$(./.venv/bin/python search.py --id "$id")"

    path="$(awk '
    /^\[[0-9]+\]/ {
        sub(/^\[[0-9]+\] /, "")
        print
    }
    ' <<< "$result")"

    mime="$(file --mime-type -b "$path")"

    i3-msg exec "xclip -selection clipboard -t \"$mime\" -i \"$path\"" >/dev/null
    notify-send "Image copied" "$(basename "$path")"
    exit 0
fi

output="$(./.venv/bin/python search.py)"

echo "$output" | awk '
BEGIN {
    id=""
    path=""
    caption=""
    tags=""
}

/^\[[0-9]+\]/ {
    match($0, /^\[([0-9]+)\]/, m)
    id=m[1]

    sub(/^\[[0-9]+\] /, "")
    path=$0
}

/^  caption:/ {
    sub(/^  caption: /, "")
    caption=$0
}

/^  tags:/ {
    sub(/^  tags: /, "")
    tags=$0

    label = "[" id "] " caption " [" tags "]"

    printf "%s\0icon\x1f%s\n",
        label,
        path
}
'
