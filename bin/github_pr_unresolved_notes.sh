#!/usr/bin/env bash
set -euo pipefail

repo="${1:-}"
pr_number="${2:-}"
mode="${3:-}"

if [ -z "$repo" ] || [ -z "$pr_number" ]; then
  echo "Usage: github_pr_unresolved_notes.sh <owner/repo> <pr_number> [--all]" >&2
  echo "Example: github_pr_unresolved_notes.sh Malaber/planini 66" >&2
  echo "Example: github_pr_unresolved_notes.sh Malaber/planini 66 --all" >&2
  exit 1
fi

if [[ "$repo" != */* ]]; then
  echo "Repository must be in owner/repo format, got: $repo" >&2
  exit 1
fi

owner="${repo%%/*}"
name="${repo#*/}"

show_all="0"
if [ "$mode" = "--all" ]; then
  show_all="1"
elif [ -n "$mode" ]; then
  echo "Unknown option: $mode" >&2
  echo "Only supported option: --all" >&2
  exit 1
fi

pr_json="$(
  gh pr view "$pr_number" \
    --repo "$repo" \
    --json url,baseRefName,headRefName,headRefOid,statusCheckRollup
)"

base_ref="$(
  jq -r '.baseRefName' <<<"$pr_json"
)"

head_sha="$(
  jq -r '.headRefOid' <<<"$pr_json"
)"

compare_json="$(
  gh api "repos/${repo}/compare/${base_ref}...${head_sha}"
)"

notes_json="$(
  gh api graphql \
    -F owner="$owner" \
    -F name="$name" \
    -F number="$pr_number" \
    -f query='
      query($owner: String!, $name: String!, $number: Int!) {
        repository(owner: $owner, name: $name) {
          pullRequest(number: $number) {
            comments(first: 100) {
              nodes {
                id
                databaseId
                author {
                  login
                }
                body
                createdAt
                url
                reactionGroups {
                  content
                  users {
                    totalCount
                  }
                }
              }
            }

            reviewThreads(first: 100) {
              nodes {
                id
                isResolved
                isOutdated
                path
                line
                originalLine
                comments(first: 100) {
                  nodes {
                    id
                    databaseId
                    author {
                      login
                    }
                    body
                    createdAt
                    url
                    path
                    line
                    originalLine
                    reactionGroups {
                      content
                      users {
                        totalCount
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    '
)"

jq -n \
  --argjson pr "$pr_json" \
  --argjson compare "$compare_json" \
  --argjson notes_json "$notes_json" \
  --arg show_all "$show_all" '
    def thumbs_up_count:
      (
        .reactionGroups
        // []
        | map(select(.content == "THUMBS_UP") | .users.totalCount)
        | add
      ) // 0;

    def resolved_by_thumbs_up:
      thumbs_up_count > 0;

    def check_name:
      if .__typename == "CheckRun" then
        .name
      elif .__typename == "StatusContext" then
        .context
      else
        (.name // .context // null)
      end;

    def check_status:
      if .__typename == "CheckRun" then
        .status
      elif .__typename == "StatusContext" then
        .state
      else
        (.status // .state // null)
      end;

    def check_conclusion:
      if .__typename == "CheckRun" then
        .conclusion
      elif .__typename == "StatusContext" then
        .state
      else
        (.conclusion // .state // null)
      end;

    def check_details_url:
      if .__typename == "CheckRun" then
        .detailsUrl
      elif .__typename == "StatusContext" then
        .targetUrl
      else
        (.detailsUrl // .targetUrl // null)
      end;

    def is_failed_check:
      if .__typename == "CheckRun" then
        (
          .status == "COMPLETED"
          and
          (.conclusion != null)
          and
          (.conclusion != "")
          and
          (.conclusion != "SUCCESS")
          and
          (.conclusion != "SKIPPED")
          and
          (.conclusion != "NEUTRAL")
        )
      elif .__typename == "StatusContext" then
        (
          (.state != null)
          and
          (.state != "")
          and
          (.state != "SUCCESS")
          and
          (.state != "PENDING")
        )
      else
        false
      end;

    def is_pending_check:
      if .__typename == "CheckRun" then
        (.status != "COMPLETED")
      elif .__typename == "StatusContext" then
        (.state == "PENDING")
      else
        false
      end;

    def compact_check:
      {
        type: (.__typename // null),
        name: check_name,
        status: check_status,
        conclusion: check_conclusion,
        workflowName: (.workflowName // null),
        detailsUrl: check_details_url,
        startedAt: (.startedAt // null),
        completedAt: (.completedAt // null),
        description: (.description // null)
      };

    ($notes_json.data.repository.pullRequest // {}) as $notes
    | ($pr.statusCheckRollup // []) as $checks
    | ($checks | map(select(is_failed_check))) as $failed
    | ($checks | map(select(is_pending_check))) as $pending
    | {
        pull_request: {
          url: $pr.url,
          base: $pr.baseRefName,
          head: $pr.headRefName,
          head_sha: $pr.headRefOid
        },
        branch: {
          up_to_date_with_base: (($compare.behind_by // 0) == 0),
          compare_status: ($compare.status // "unknown"),
          ahead_by: ($compare.ahead_by // null),
          behind_by: ($compare.behind_by // null),
          base_branch: $pr.baseRefName,
          head_branch: $pr.headRefName,
          base_url: ($compare.base_commit.html_url // null),
          compare_url: ($compare.html_url // null)
        },
        ci: {
          state: (
            if ($failed | length) > 0 then
              "FAILURE"
            elif ($pending | length) > 0 then
              "PENDING"
            elif ($checks | length) == 0 then
              "UNKNOWN"
            else
              "SUCCESS"
            end
          ),
          failed: ($failed | map(compact_check)),
          pending: ($pending | map(compact_check))
        },
        unresolved_notes: (
          [
            ($notes.comments.nodes // [])[]
            | select(.author.login == "Malaber")
            | {
                kind: "pr_comment",
                comment_id: .id,
                database_id: .databaseId,
                created_at: .createdAt,
                resolved: resolved_by_thumbs_up,
                thumbs_up_count: thumbs_up_count,
                note: .body,
                url: .url
              }
          ]
          +
          [
            ($notes.reviewThreads.nodes // [])[]
            as $thread
            | ($thread.comments.nodes // [])[]
            | select(.author.login == "Malaber")
            | {
                kind: "review_thread_comment",
                thread_id: $thread.id,
                thread_is_resolved_by_github: $thread.isResolved,
                thread_is_outdated: $thread.isOutdated,
                comment_id: .id,
                database_id: .databaseId,
                created_at: .createdAt,
                resolved: resolved_by_thumbs_up,
                thumbs_up_count: thumbs_up_count,
                path: (.path // $thread.path),
                line: (.line // $thread.line),
                original_line: (.originalLine // $thread.originalLine),
                note: .body,
                url: .url
              }
          ]
          | map(select($show_all == "1" or (.resolved | not)))
        )
      }
  '
