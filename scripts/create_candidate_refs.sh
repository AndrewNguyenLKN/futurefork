#!/usr/bin/env bash
# Create the `coupled` and `modular` Git refs from examples/pocketcart/candidates/.
#
# Each ref is a parentless commit whose tree is exactly that candidate directory
# (so `git archive coupled` yields a self-contained project). Built with Git
# plumbing: the working tree, index, HEAD, and current branch are never touched.
# Refuses to overwrite an existing ref. Only the repo is written; nothing is pushed.
#
# usage: scripts/create_candidate_refs.sh [repo-dir]   (default: repository root)
set -euo pipefail

REPO="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
SRC="$REPO/examples/pocketcart/candidates"
TMP_INDEX="$(mktemp -d)/index"
trap 'rm -rf "$(dirname "$TMP_INDEX")"' EXIT

for name in coupled modular; do
  if git -C "$REPO" show-ref --verify --quiet "refs/heads/$name"; then
    echo "refs/heads/$name already exists; refusing to overwrite" >&2
    exit 1
  fi
done

for name in coupled modular; do
  rm -f "$TMP_INDEX"
  # Stage the candidate's files (excluding caches) into a throwaway index.
  (cd "$SRC/$name" && find . -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -not -path './.pytest_cache/*' \
     | sed 's|^\./||' | sort \
     | while read -r f; do
         blob="$(git -C "$REPO" hash-object -w "$SRC/$name/$f")"
         mode=100644; [ -x "$SRC/$name/$f" ] && mode=100755
         printf '%s %s\t%s\n' "$mode" "$blob" "$f"
       done \
     | GIT_INDEX_FILE="$TMP_INDEX" git -C "$REPO" update-index --add --index-info)
  tree="$(GIT_INDEX_FILE="$TMP_INDEX" git -C "$REPO" write-tree)"
  commit="$(git -C "$REPO" commit-tree "$tree" -m "PocketCart candidate: $name (behavior contract v1)")"
  git -C "$REPO" update-ref "refs/heads/$name" "$commit"
  echo "created refs/heads/$name -> $commit"
done
