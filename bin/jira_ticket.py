#!/usr/bin/env python3
"""
jira_ticket - read a Jira Cloud ticket into AI-friendly Markdown.

Usage:

  jira_ticket setup \
    --site https://turniere.atlassian.net \
    --email chatgpt@schaedler.rocks \
    --auth-mode scoped \
    --cloud-id <cloud-id>

  jira_ticket PLAN-83
  jira_ticket PLAN-83 --brief
  jira_ticket PLAN-83 --json

Config is stored at:

  ~/.config/jira-ticket-reader/config.json

Token storage:

  macOS default: Keychain
  Linux/default fallback: config file with mode 0600
  alternative: environment variable via --store env

Security note:

  This avoids storing the token in dotfiles and avoids printing it.
  It does not fully hide the token from an AI agent that can run arbitrary
  shell commands as your same OS user while your Keychain/session is unlocked.
  The important safety boundary is using a scoped/read-only Jira token.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


APP_NAME = "jira-ticket-reader"
CONFIG_PATH = Path.home() / ".config" / APP_NAME / "config.json"
KEYCHAIN_SERVICE = APP_NAME
DEFAULT_SITE = "https://turniere.atlassian.net"

SYSTEM_FIELDS = [
    "summary",
    "issuetype",
    "priority",
    "description",
    "environment",
    "components",
    "attachment",
    "issuelinks",
    "parent",
    "subtasks",
    "labels",
]

INTERESTING_CUSTOM_FIELD_NAMES = {
    "epic link",
    "epic name",
    "sprint",
    "story points",
    "story point estimate",
    "acceptance criteria",
    "flagged",
    "start date",
    "target start",
    "target end",
    "team",
    "rank",
}

TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "application/javascript",
    "application/x-javascript",
    "application/x-sh",
    "application/sql",
}
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".csv",
    ".log",
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".sql",
    ".html",
    ".css",
}


class JiraError(RuntimeError):
    pass


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def require_ticket_key(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", value):
        raise argparse.ArgumentTypeError(f"not a Jira issue key: {value!r}")
    return value


def normalize_site(site: str) -> str:
    site = site.strip().rstrip("/")
    if not site.startswith(("https://", "http://")):
        site = "https://" + site
    return site


def secure_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    try:
        os.chmod(path.parent, 0o700)
    except PermissionError:
        pass

    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")

    os.replace(tmp, path)

    try:
        os.chmod(path, 0o600)
    except PermissionError:
        pass


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise SystemExit(
            f"No config found at {config_path}\n"
            f"Run: {Path(sys.argv[0]).name} setup --site {DEFAULT_SITE}"
        )

    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def macos_keychain_available() -> bool:
    return platform.system() == "Darwin" and shutil.which("security") is not None


def keychain_account(email: str, site: str) -> str:
    host = urllib.parse.urlparse(site).netloc or site
    return f"{email}@{host}"


def store_token_keychain(service: str, account: str, token: str) -> None:
    if not macos_keychain_available():
        raise SystemExit("macOS Keychain is not available. Use --store file or --store env.")

    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
            token,
            "-U",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def load_token_keychain(service: str, account: str) -> str:
    if not macos_keychain_available():
        raise SystemExit("macOS Keychain is not available on this machine.")

    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise SystemExit(
            f"Could not read Jira API token from macOS Keychain "
            f"service={service!r} account={account!r}."
        )

    return result.stdout.strip()


def resolve_token(config: dict[str, Any]) -> str:
    token_env = config.get("token_env")

    if token_env and os.environ.get(token_env):
        return os.environ[token_env]

    storage = config.get("token_storage", "keychain")

    if storage == "env":
        raise SystemExit(f"Set {token_env or 'JIRA_API_TOKEN'} in the environment.")

    if storage == "keychain":
        return load_token_keychain(
            config.get("keychain_service", KEYCHAIN_SERVICE),
            config["keychain_account"],
        )

    if storage == "file":
        token = config.get("token")
        if not token:
            raise SystemExit(f"No token stored in {CONFIG_PATH}")
        return token

    raise SystemExit(f"Unknown token_storage in config: {storage!r}")


class JiraClient:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.site = normalize_site(config["site"])
        self.email = config["email"]
        self.token = resolve_token(config)
        self.api_root = config["api_root"].rstrip("/")
        self.auth_header_type = config.get("auth_header_type", "basic")

    def _auth_header(self) -> str:
        if self.auth_header_type == "bearer":
            return f"Bearer {self.token}"

        raw = f"{self.email}:{self.token}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _url(self, path_or_url: str, params: dict[str, Any] | None = None) -> str:
        if path_or_url.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(path_or_url)

            if self.config.get("auth_mode") == "scoped":
                marker = "/rest/api/3/"
                alt_marker = "/jira/rest/api/3/"

                if alt_marker in parsed.path:
                    path_or_url = "/rest/api/3/" + parsed.path.split(alt_marker, 1)[1]
                elif marker in parsed.path:
                    path_or_url = "/rest/api/3/" + parsed.path.split(marker, 1)[1]
                else:
                    url = path_or_url
                    if params:
                        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
                            params,
                            doseq=True,
                        )
                    return url
            else:
                url = path_or_url
                if params:
                    url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
                        params,
                        doseq=True,
                    )
                return url

        if not path_or_url.startswith("/"):
            path_or_url = "/" + path_or_url

        clean_params: dict[str, Any] = {}
        if params:
            clean_params = {
                key: value
                for key, value in params.items()
                if value is not None and value != "" and value != []
            }

        url = self.api_root + path_or_url

        if clean_params:
            url += "?" + urllib.parse.urlencode(clean_params, doseq=True)

        return url

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": self._auth_header(),
            "User-Agent": f"{APP_NAME}/1.0",
        }

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            self._url(path_or_url, params),
            data=data,
            headers=headers,
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()

                if not expect_json:
                    return raw

                if not raw:
                    return None

                return json.loads(raw.decode("utf-8"))

        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")

            hint = ""
            if exc.code in {401, 403}:
                hint = (
                    "\nAuth hint: scoped tokens usually use --auth-header-type bearer "
                    "and api.atlassian.com/ex/jira/<cloudId>. "
                    "Classic site tokens usually use --auth-header-type basic "
                    "and your *.atlassian.net site URL."
                )

            raise JiraError(
                f"Jira API {method.upper()} {path_or_url} failed with HTTP {exc.code}: "
                f"{details[:2000]}{hint}"
            ) from exc

        except urllib.error.URLError as exc:
            raise JiraError(f"Could not reach Jira API: {exc}") from exc

    def get(
        self,
        path_or_url: str,
        params: dict[str, Any] | None = None,
        *,
        expect_json: bool = True,
    ) -> Any:
        return self.request("GET", path_or_url, params=params, expect_json=expect_json)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self.request("POST", path, body=body)


def display_user(user: Any) -> str:
    if not user:
        return "Unassigned"

    if isinstance(user, str):
        return user

    return (
        user.get("displayName")
        or user.get("emailAddress")
        or user.get("accountId")
        or "-"
    )


def compact_ws(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.strip())


def adf_to_text(node: Any, *, indent: int = 0) -> str:
    if node is None:
        return ""

    if isinstance(node, str):
        return node

    if isinstance(node, (int, float, bool)):
        return str(node)

    if isinstance(node, list):
        return compact_ws(
            "\n".join(adf_to_text(item, indent=indent) for item in node if item is not None)
        )

    if not isinstance(node, dict):
        return str(node)

    node_type = node.get("type")
    content = node.get("content", [])

    if node_type == "doc":
        return adf_to_text(content, indent=indent)

    if node_type == "text":
        text = node.get("text", "")

        for mark in node.get("marks", []) or []:
            mark_type = mark.get("type")
            attrs = mark.get("attrs") or {}

            if mark_type == "link" and attrs.get("href"):
                text = f"{text} ({attrs['href']})"
            elif mark_type == "code":
                text = f"`{text}`"
            elif mark_type == "strong":
                text = f"**{text}**"
            elif mark_type == "em":
                text = f"*{text}*"

        return text

    if node_type == "hardBreak":
        return "\n"

    if node_type == "paragraph":
        return "".join(adf_to_text(item, indent=indent) for item in content).strip()

    if node_type == "heading":
        level = int((node.get("attrs") or {}).get("level", 2))
        level = max(2, min(level + 1, 6))
        return "#" * level + " " + "".join(
            adf_to_text(item, indent=indent) for item in content
        ).strip()

    if node_type == "bulletList":
        lines: list[str] = []

        for item in content:
            item_text = adf_to_text(item, indent=indent + 2).strip()
            if item_text:
                lines.append(
                    " " * indent
                    + "- "
                    + item_text.replace("\n", "\n" + " " * (indent + 2))
                )

        return "\n".join(lines)

    if node_type == "orderedList":
        lines = []
        start = int((node.get("attrs") or {}).get("order", 1))

        for idx, item in enumerate(content, start=start):
            item_text = adf_to_text(item, indent=indent + 3).strip()
            if item_text:
                prefix = f"{idx}. "
                lines.append(
                    " " * indent
                    + prefix
                    + item_text.replace("\n", "\n" + " " * (indent + len(prefix)))
                )

        return "\n".join(lines)

    if node_type == "listItem":
        return adf_to_text(content, indent=indent)

    if node_type == "codeBlock":
        language = (node.get("attrs") or {}).get("language") or ""
        code = adf_to_text(content, indent=0)
        return f"```{language}\n{code}\n```"

    if node_type == "blockquote":
        text = adf_to_text(content, indent=indent).strip()
        return "\n".join("> " + line for line in text.splitlines())

    if node_type == "mention":
        return (
            (node.get("attrs") or {}).get("text")
            or (node.get("attrs") or {}).get("id")
            or "@mention"
        )

    if node_type in {"inlineCard", "blockCard", "embedCard"}:
        return (node.get("attrs") or {}).get("url") or ""

    if node_type == "rule":
        return "---"

    if node_type == "media":
        attrs = node.get("attrs") or {}
        return f"[media: {attrs.get('id') or attrs.get('alt') or 'attachment'}]"

    if node_type == "table":
        rows = [adf_to_text(row, indent=indent) for row in content]
        return "\n".join(row for row in rows if row.strip())

    if node_type == "tableRow":
        cells = [adf_to_text(cell, indent=indent).replace("\n", " ") for cell in content]
        return "| " + " | ".join(cell.strip() for cell in cells) + " |"

    if node_type in {"tableCell", "tableHeader"}:
        return adf_to_text(content, indent=indent)

    return adf_to_text(content, indent=indent)


def first_non_empty_line(text: str, max_chars: int = 500) -> str:
    text = compact_ws(text or "")

    if not text:
        return "-"

    for line in text.splitlines():
        line = line.strip()
        if line:
            if len(line) > max_chars:
                return line[:max_chars].rstrip() + "..."
            return line

    return "-"


def format_value(value: Any) -> str:
    if value is None or value == "":
        return "-"

    if isinstance(value, (str, int, float, bool)):
        return str(value)

    if isinstance(value, list):
        rendered = [format_value(item) for item in value]
        return ", ".join(item for item in rendered if item and item != "-") or "-"

    if isinstance(value, dict):
        if value.get("type") == "doc":
            return adf_to_text(value)

        for key in ("displayName", "name", "value", "key", "filename"):
            if value.get(key):
                return str(value[key])

        if "fields" in value and "key" in value:
            fields = value.get("fields") or {}
            return f"{value['key']} — {fields.get('summary', '')}".strip()

        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    return str(value)


def get_field_catalog(client: JiraClient) -> dict[str, dict[str, Any]]:
    fields = client.get("/rest/api/3/field")
    return {field["id"]: field for field in fields if field.get("id")}


def interesting_custom_fields(field_catalog: dict[str, dict[str, Any]]) -> list[str]:
    result: list[str] = []

    for field_id, meta in field_catalog.items():
        name = (meta.get("name") or "").strip().lower()

        if field_id.startswith("customfield_") and name in INTERESTING_CUSTOM_FIELD_NAMES:
            result.append(field_id)

    return result


def get_issue(client: JiraClient, key: str, custom_fields: list[str]) -> dict[str, Any]:
    fields = SYSTEM_FIELDS + custom_fields

    return client.get(
        f"/rest/api/3/issue/{urllib.parse.quote(key)}",
        {
            "fields": ",".join(fields),
            "expand": "names,schema",
        },
    )


def get_comments(client: JiraClient, key: str, max_comments: int) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    start_at = 0
    page_size = min(100, max_comments)

    if max_comments <= 0:
        return []

    while len(comments) < max_comments:
        page = client.get(
            f"/rest/api/3/issue/{urllib.parse.quote(key)}/comment",
            {
                "startAt": start_at,
                "maxResults": page_size,
                "orderBy": "created",
            },
        )

        batch = page.get("comments") or page.get("values") or []
        comments.extend(batch)

        total = page.get("total", len(comments))
        start_at += len(batch)

        if not batch or start_at >= total:
            break

    return comments[:max_comments]


def get_changelog(client: JiraClient, key: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    page = client.get(
        f"/rest/api/3/issue/{urllib.parse.quote(key)}/changelog",
        {
            "startAt": 0,
            "maxResults": min(max(limit, 1), 100),
        },
    )

    values = page.get("values") or []
    return values[-limit:]


def get_remote_links(client: JiraClient, key: str) -> list[dict[str, Any]]:
    try:
        links = client.get(f"/rest/api/3/issue/{urllib.parse.quote(key)}/remotelink")
        return links if isinstance(links, list) else []
    except JiraError:
        return []


def search_children(client: JiraClient, key: str, max_results: int) -> list[dict[str, Any]]:
    if max_results <= 0:
        return []

    fields = ["summary", "issuetype"]

    jqls = [
        f'parent = {key} OR "Epic Link" = {key} ORDER BY Rank ASC',
        f"parent = {key} ORDER BY Rank ASC",
    ]

    for jql in jqls:
        body = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields,
        }

        for search_endpoint in ("/rest/api/3/search/jql", "/rest/api/3/search"):
            try:
                result = client.post(search_endpoint, body)
                return result.get("issues", [])
            except JiraError:
                continue

    return []


def is_text_attachment(att: dict[str, Any]) -> bool:
    mime = (att.get("mimeType") or "").lower()
    filename = (att.get("filename") or "").lower()
    suffix = Path(filename).suffix

    return (
        mime.startswith(TEXT_MIME_PREFIXES)
        or mime in TEXT_MIME_TYPES
        or suffix in TEXT_EXTENSIONS
    )


def preview_attachment(client: JiraClient, att: dict[str, Any], max_bytes: int) -> str | None:
    if max_bytes <= 0 or not is_text_attachment(att):
        return None

    content_url = att.get("content")
    if not content_url:
        return None

    try:
        raw = client.get(content_url, expect_json=False)
    except JiraError as exc:
        return f"[could not read attachment: {exc}]"

    if len(raw) > max_bytes:
        raw = raw[:max_bytes] + b"\n...[truncated]\n"

    return raw.decode("utf-8", errors="replace")


def issue_url(site: str, key: str) -> str:
    return f"{normalize_site(site)}/browse/{key}"


def linked_issue_summary(link: dict[str, Any]) -> str:
    link_type = link.get("type") or {}

    if link.get("outwardIssue"):
        direction = link_type.get("outward") or link_type.get("name") or "links to"
        issue = link["outwardIssue"]
    elif link.get("inwardIssue"):
        direction = link_type.get("inward") or link_type.get("name") or "linked from"
        issue = link["inwardIssue"]
    else:
        return "- unknown link"

    fields = issue.get("fields") or {}
    summary = fields.get("summary") or ""

    return f"- {direction}: {issue.get('key')} {summary}".strip()


def linked_compact(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    issue_type = ((fields.get("issuetype") or {}).get("name")) or "-"

    return (
        f"- {issue.get('key')} "
        f"({issue_type}) {fields.get('summary') or ''}"
    ).strip()


def render_brief_markdown(
    *,
    config: dict[str, Any],
    issue: dict[str, Any],
    comments: list[dict[str, Any]],
    children: list[dict[str, Any]],
) -> str:
    key = issue["key"]
    fields = issue.get("fields") or {}

    lines: list[str] = []

    lines.append(f"# {key} — {fields.get('summary') or ''}".rstrip())
    lines.append("")
    lines.append(f"URL: {issue_url(config['site'], key)}")
    lines.append("")

    issue_type = format_value(fields.get("issuetype"))
    priority = format_value(fields.get("priority"))
    components = format_value(fields.get("components"))
    labels = format_value(fields.get("labels"))

    compact_meta = []

    if issue_type != "-":
        compact_meta.append(f"Type: {issue_type}")

    if priority != "-":
        compact_meta.append(f"Priority: {priority}")

    if components != "-":
        compact_meta.append(f"Components: {components}")

    if labels != "-":
        compact_meta.append(f"Labels: {labels}")

    if compact_meta:
        lines.append("## Metadata")
        for item in compact_meta:
            lines.append(f"- {item}")
        lines.append("")

    description = adf_to_text(fields.get("description"))
    lines.append("## Description")
    lines.append(first_non_empty_line(description, max_chars=1200))
    lines.append("")

    parent = fields.get("parent")
    if parent:
        lines.append("## Parent / Epic")
        lines.append(f"- {format_value(parent)}")
        lines.append("")

    links = fields.get("issuelinks") or []
    subtasks = fields.get("subtasks") or []

    if links or subtasks or children:
        lines.append("## Related tickets")

        for link in links[:10]:
            lines.append(linked_issue_summary(link))

        for subtask in subtasks[:10]:
            lines.append(linked_compact(subtask))

        for child in children[:10]:
            lines.append(linked_compact(child))

        total_related = len(links) + len(subtasks) + len(children)
        if total_related > 30:
            lines.append("- ...truncated")

        lines.append("")

    attachments = fields.get("attachment") or []

    if attachments:
        lines.append("## Attachments")
        for att in attachments[:10]:
            lines.append(f"- {att.get('filename')} ({att.get('mimeType') or 'unknown mime'})")

        if len(attachments) > 10:
            lines.append(f"- ...and {len(attachments) - 10} more")

        lines.append("")

    if comments:
        lines.append("## Latest comments")

        for comment in comments[-3:]:
            author = display_user(comment.get("author"))
            created = comment.get("created") or "unknown date"
            body = first_non_empty_line(adf_to_text(comment.get("body")), max_chars=800)

            lines.append(f"### {author}, {created}")
            lines.append(body)
            lines.append("")

    return compact_ws("\n".join(lines)) + "\n"


def render_markdown(
    *,
    config: dict[str, Any],
    issue: dict[str, Any],
    field_catalog: dict[str, dict[str, Any]],
    comments: list[dict[str, Any]],
    changelog: list[dict[str, Any]],
    remote_links: list[dict[str, Any]],
    children: list[dict[str, Any]],
    attachment_previews: dict[str, str | None],
) -> str:
    key = issue["key"]
    fields = issue.get("fields") or {}
    names = issue.get("names") or {}

    def name_of(field_id: str) -> str:
        return names.get(field_id) or (field_catalog.get(field_id) or {}).get("name") or field_id

    lines: list[str] = []

    lines.append(f"# {key} — {fields.get('summary') or ''}".rstrip())
    lines.append("")
    lines.append(f"URL: {issue_url(config['site'], key)}")
    lines.append("")

    lines.append("## Metadata")

    meta_rows = [
        ("Type", format_value(fields.get("issuetype"))),
        ("Priority", format_value(fields.get("priority"))),
        ("Components", format_value(fields.get("components"))),
        ("Labels", format_value(fields.get("labels"))),
    ]

    for label, value in meta_rows:
        if value and value != "-":
            lines.append(f"- **{label}:** {value}")

    parent = fields.get("parent")
    if parent:
        lines.append(f"- **Parent/Epic:** {format_value(parent)}")

    custom_lines = []

    for field_id, value in fields.items():
        if not field_id.startswith("customfield_") or value in (None, "", []):
            continue

        display = format_value(value)

        if display and display != "-":
            custom_lines.append(f"- **{name_of(field_id)}:** {display}")

    if custom_lines:
        lines.append("")
        lines.append("## Interesting custom fields")
        lines.extend(custom_lines)

    description = adf_to_text(fields.get("description"))
    if description:
        lines.append("")
        lines.append("## Description")
        lines.append(description)

    environment = adf_to_text(fields.get("environment"))
    if environment:
        lines.append("")
        lines.append("## Environment")
        lines.append(environment)

    attachments = fields.get("attachment") or []
    lines.append("")
    lines.append(f"## Attachments ({len(attachments)})")

    if attachments:
        for att in attachments:
            size = att.get("size")
            size_text = f"{size} bytes" if size is not None else "unknown size"

            lines.append(
                f"- {att.get('filename')} "
                f"({att.get('mimeType') or 'unknown mime'}, {size_text}, "
                f"by {display_user(att.get('author'))}, "
                f"{att.get('created') or 'unknown date'})"
            )

            preview = attachment_previews.get(str(att.get("id")))

            if preview:
                lines.append("")
                lines.append(f"  Preview of `{att.get('filename')}`:")
                lines.append("")
                lines.append(textwrap.indent("```text\n" + preview.rstrip() + "\n```", "  "))
                lines.append("")
    else:
        lines.append("- none")

    links = fields.get("issuelinks") or []
    lines.append("")
    lines.append(f"## Linked issues ({len(links)})")

    if links:
        lines.extend(linked_issue_summary(link) for link in links)
    else:
        lines.append("- none")

    subtasks = fields.get("subtasks") or []
    lines.append("")
    lines.append(f"## Subtasks ({len(subtasks)})")

    if subtasks:
        for subtask in subtasks:
            lines.append(linked_compact(subtask))
    else:
        lines.append("- none")

    lines.append("")
    lines.append(f"## Children / issues in epic ({len(children)})")

    if children:
        lines.extend(linked_compact(child) for child in children)
    else:
        lines.append("- none found or not applicable")

    lines.append("")
    lines.append(f"## Remote links ({len(remote_links)})")

    if remote_links:
        for link in remote_links:
            obj = link.get("object") or {}
            title = obj.get("title") or link.get("globalId") or "remote link"
            url = obj.get("url") or "-"
            lines.append(f"- {title}: {url}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append(f"## Comments ({len(comments)})")

    if comments:
        for idx, comment in enumerate(comments, start=1):
            author = display_user(comment.get("author"))
            created = comment.get("created") or "unknown date"
            updated = comment.get("updated")
            suffix = f", updated {updated}" if updated and updated != created else ""
            body = adf_to_text(comment.get("body"))

            lines.append("")
            lines.append(f"### Comment {idx} — {author}, {created}{suffix}")
            lines.append(body or "-")
    else:
        lines.append("- none")

    lines.append("")
    lines.append(f"## Recent changelog ({len(changelog)})")

    if changelog:
        for change in changelog:
            author = display_user(change.get("author"))
            created = change.get("created") or "unknown date"

            lines.append(f"- {created} — {author}")

            for item in change.get("items") or []:
                field = item.get("field") or item.get("fieldId") or "field"
                old = item.get("fromString") or "-"
                new = item.get("toString") or "-"
                lines.append(f"  - {field}: {old} → {new}")
    else:
        lines.append("- none requested or no visible changelog")

    return compact_ws("\n".join(lines)) + "\n"


def build_payload(
    client: JiraClient,
    key: str,
    *,
    max_comments: int,
    changelog_limit: int,
    child_limit: int,
    attachment_preview_bytes: int,
) -> dict[str, Any]:
    field_catalog = get_field_catalog(client)
    issue = get_issue(client, key, interesting_custom_fields(field_catalog))
    comments = get_comments(client, issue["key"], max_comments)
    changelog = get_changelog(client, issue["key"], changelog_limit)
    remote_links = get_remote_links(client, issue["key"]) if changelog_limit > 0 else []
    children = search_children(client, issue["key"], child_limit)

    attachment_previews: dict[str, str | None] = {}

    for att in (issue.get("fields") or {}).get("attachment") or []:
        attachment_previews[str(att.get("id"))] = preview_attachment(
            client,
            att,
            attachment_preview_bytes,
        )

    return {
        "issue": issue,
        "field_catalog": field_catalog,
        "comments": comments,
        "changelog": changelog,
        "remote_links": remote_links,
        "children": children,
        "attachment_previews": attachment_previews,
    }


def cmd_setup(args: argparse.Namespace) -> int:
    site = normalize_site(
        args.site or input(f"Jira site [{DEFAULT_SITE}]: ").strip() or DEFAULT_SITE
    )

    email = args.email or input("Atlassian account email: ").strip()

    if not email:
        raise SystemExit("email is required")

    auth_mode = args.auth_mode

    if not auth_mode:
        auth_mode = (
            input(
                "Auth mode: scoped read-only token or direct site token? "
                "[scoped/direct, default scoped]: "
            )
            .strip()
            .lower()
            or "scoped"
        )

    if auth_mode not in {"scoped", "direct"}:
        raise SystemExit("--auth-mode must be scoped or direct")

    cloud_id = args.cloud_id

    if auth_mode == "scoped" and not cloud_id:
        cloud_id = input(
            "Jira cloudId for scoped tokens "
            "(try: curl https://turniere.atlassian.net/_edge/tenant_info): "
        ).strip()

        if not cloud_id:
            raise SystemExit("cloudId is required for scoped API tokens")

    auth_header_type = args.auth_header_type

    if not auth_header_type:
        auth_header_type = "bearer" if auth_mode == "scoped" else "basic"

    store = args.store

    if store == "keychain" and not macos_keychain_available():
        eprint("macOS Keychain not available; falling back to --store file.")
        store = "file"

    token = None

    if store != "env":
        if args.token_stdin:
            token = sys.stdin.read().strip()
        else:
            token = getpass.getpass("Jira API token (input hidden): ").strip()

        if not token:
            raise SystemExit("token is required")

    if auth_mode == "scoped":
        api_root = f"https://api.atlassian.com/ex/jira/{cloud_id}"
    else:
        api_root = site

    config: dict[str, Any] = {
        "site": site,
        "api_root": api_root,
        "email": email,
        "auth_mode": auth_mode,
        "auth_header_type": auth_header_type,
        "cloud_id": cloud_id,
        "token_storage": store,
    }

    if store == "keychain":
        account = keychain_account(email, site)
        store_token_keychain(KEYCHAIN_SERVICE, account, token or "")
        config["keychain_service"] = KEYCHAIN_SERVICE
        config["keychain_account"] = account

    elif store == "env":
        config["token_env"] = args.token_env

    elif store == "file":
        config["token"] = token

    secure_write_json(args.config, config)

    print(f"Wrote config to {args.config}")

    if store == "keychain":
        print("Stored token in macOS Keychain; the config file contains only the keychain lookup key.")
    elif store == "env":
        print(f"Token is not stored. Export it before use: export {args.token_env}=...")
    else:
        print("Stored token in the config file. File permissions were set to 0600.")

    return 0


def cmd_show_config(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    redacted = dict(config)

    if "token" in redacted:
        redacted["token"] = "<redacted>"

    print(json.dumps(redacted, indent=2, sort_keys=True))

    return 0


def cmd_read(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    client = JiraClient(config)

    payload = build_payload(
        client,
        args.ticket,
        max_comments=10 if args.brief else args.max_comments,
        changelog_limit=0 if args.brief else args.changelog,
        child_limit=20 if args.brief else args.children,
        attachment_preview_bytes=0 if args.brief else args.attachment_preview_bytes,
    )

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    if args.brief:
        print(
            render_brief_markdown(
                config=config,
                issue=payload["issue"],
                comments=payload["comments"],
                children=payload["children"],
            )
        )
        return 0

    print(
        render_markdown(
            config=config,
            issue=payload["issue"],
            field_catalog=payload["field_catalog"],
            comments=payload["comments"],
            changelog=payload["changelog"],
            remote_links=payload["remote_links"],
            children=payload["children"],
            attachment_previews=payload["attachment_previews"],
        )
    )

    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Read a Jira Cloud issue into AI-friendly Markdown.",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help=f"config path, default: {CONFIG_PATH}",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="configure Jira credentials")
    setup.add_argument("--site", default=DEFAULT_SITE, help=f"Jira site URL, default: {DEFAULT_SITE}")
    setup.add_argument("--email", help="Atlassian account email")
    setup.add_argument("--auth-mode", choices=["scoped", "direct"], default=None)
    setup.add_argument("--cloud-id", help="required for scoped API tokens")
    setup.add_argument(
        "--auth-header-type",
        choices=["basic", "bearer"],
        default=None,
        help="default: bearer for scoped, basic for direct",
    )
    setup.add_argument(
        "--store",
        choices=["keychain", "env", "file"],
        default="keychain" if macos_keychain_available() else "file",
        help="where to keep the API token",
    )
    setup.add_argument("--token-env", default="JIRA_API_TOKEN", help="env var name for --store env")
    setup.add_argument("--token-stdin", action="store_true", help="read token from stdin instead of prompting")
    setup.set_defaults(func=cmd_setup)

    show_config = sub.add_parser("show-config", help="print config with secrets redacted")
    show_config.set_defaults(func=cmd_show_config)

    read = sub.add_parser("read", help="read one issue")
    read.add_argument("ticket", type=require_ticket_key, help="Jira issue key, e.g. PLAN-83")
    read.add_argument("--brief", action="store_true", help="emit a short hardcoded summary")
    read.add_argument("--json", action="store_true", help="emit raw JSON payload instead of Markdown")
    read.add_argument("--max-comments", type=int, default=100, help="maximum comments to read")
    read.add_argument("--children", type=int, default=50, help="maximum child issues / epic issues to list")
    read.add_argument("--changelog", type=int, default=20, help="recent changelog entries to include; 0 disables")
    read.add_argument(
        "--attachment-preview-bytes",
        type=int,
        default=16_384,
        help="preview text-like attachments up to this many bytes; 0 disables",
    )
    read.set_defaults(func=cmd_read)

    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv

    commands = {"setup", "show-config", "read", "-h", "--help"}

    # Convenience call:
    #
    #   jira_ticket PLAN-83
    #
    # instead of:
    #
    #   jira_ticket read PLAN-83
    if argv[0] not in commands and not argv[0].startswith("-"):
        return ["read", *argv]

    return argv


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(normalize_argv(list(sys.argv[1:] if argv is None else argv)))

    try:
        return args.func(args)
    except JiraError as exc:
        eprint(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
