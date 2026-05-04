#!/usr/bin/env bash
set -euo pipefail

project="${1:-}"
mr_iid="${2:-}"

if [ -z "$project" ] || [ -z "$mr_iid" ]; then
  echo "Usage: gitlab_merge_request_unresolved_threads.sh <project_path> <mr_iid>" >&2
  echo "Example: gitlab_merge_request_unresolved_threads.sh turniere/turniere-frontend 130" >&2
  exit 1
fi

curl -L -sS \
  "https://gitlab.com/${project}/-/merge_requests/${mr_iid}/discussions.json?notes_filter=0&per_page=100&persist_filter=false" \
  | jq -r '
    .[]
    | select(.resolvable == true)
    | select(.resolved == false)
    | select(.notes[0].author.username == "Malaber")
    | {
        discussion_id: .id,
        note_id: .notes[0].id,
        created_at: .notes[0].created_at,
        note: .notes[0].note,
        url: .notes[0].noteable_note_url
      }
  '
