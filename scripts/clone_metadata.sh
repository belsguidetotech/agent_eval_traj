#!/usr/bin/env bash

set -u

repo="$1"
dest="data/cache/repo_metadata/$repo"

if [ -d "$dest/.git" ]; then
    echo "[SKIP] $repo"
    exit 0
fi

mkdir -p "$(dirname "$dest")"

echo "[CLONE] $repo"

git clone \
    --depth 1 \
    --filter=blob:none \
    --no-checkout \
    "git@github.com:Hypogenic-AI/${repo}.git" \
    "$dest" \
    >/tmp/"${repo}".clone.log 2>&1

status=$?

if [ $status -ne 0 ]; then
    echo "[FAIL] $repo"
    exit $status
fi

echo "[OK] $repo"
