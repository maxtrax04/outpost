#!/usr/bin/env bash
# Turns the published pre-releases that a stable version replaces into drafts: its own betas and
# release candidates, and every pre-release of an earlier version. Run by the release workflow.
#
#   scripts/draft_prereleases.sh 2026.12.0            needs gh and GH_TOKEN
#   scripts/draft_prereleases.sh --list 2026.12.0     reads tags from stdin, prints the ones to draft
set -euo pipefail

list_only=false
if [ "${1:-}" = "--list" ]; then
    list_only=true
    shift
fi
released="$1"

# True when version $1 comes before $2 (both without a suffix), by number in each part
older() {
    [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | head -n1)" = "$1" ]
}

replaced() {
    while read -r tag; do
        version="${tag#v}"
        case "$version" in
            *-*) ;;
            *) continue ;;  # only pre-releases
        esac
        base="${version%%-*}"
        if [ "$base" = "$released" ] || older "$base" "$released"; then
            echo "$tag"
        fi
    done
}

if $list_only; then
    replaced
    exit 0
fi

gh release list --limit 200 --json tagName,isDraft,isPrerelease \
    --jq '.[] | select((.isDraft | not) and .isPrerelease) | .tagName' |
replaced |
while read -r tag; do
    gh release edit "$tag" --draft > /dev/null
    echo "$tag is now a draft"
done
