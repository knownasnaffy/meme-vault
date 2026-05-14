#!/usr/bin/env bash

if [[ -z "$1" ]]; then
    exit 0
fi

output="$(./.venv/bin/python search.py "$1")"

echo "$output" | awk '
/^\[[0-9]+\]/ {
    sub(/^\[[0-9]+\] /, "")
    path=$0
    printf "%s\0icon\x1f%s\n", path, path
}
'
