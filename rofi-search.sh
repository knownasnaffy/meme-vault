#!/usr/bin/env bash

if [[ -n "$1" ]]; then
    # User selected an entry

    selected="$1"

    echo "SELECTED: $selected" >> /tmp/rofi-meme.log

    feh "$selected" &
    exit 0
fi

output="$(./.venv/bin/python search.py)"

echo "$output" | awk '
BEGIN {
    path=""
    caption=""
    tags=""
}

/^\[[0-9]+\]/ {
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

    label = caption " [" tags "]"

    printf "%s\0icon\x1f%s\x1fmeta\x1f%s\n",
        label,
        path,
        path
}
'
