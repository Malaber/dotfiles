#!/usr/bin/env python3
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
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


APP_NAME = "jira-ticket-reader"
DEFAULT_SITE = "https://turniere.atlassian.net"
CONFIG_PATH = Path.home() / ".config" / APP_NAME / "config.json"
KEYCHAIN_SERVICE = APP_NAME

BASE_ISSUE_FIELDS = [
    "summary",
    "issuetype",
    "status",
    "description",
    "components",
    "attachment",
    "issuelinks",
    "parent",
    "subtasks",
    "labels",
]

EPIC_FIELD_NAMES = {
    "epic link",
    "epic name",
    "parent link",
}


class JiraError(RuntimeError):
    pass


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def normalize_site(site: str) -> str:
    site = site.strip().rstrip("/")
    return site if site.startswith(("https://", "http://")) else f"https://{site}"


def require_ticket_key(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", value):
        raise argparse.ArgumentTypeError(f"not a Jira issue key: {value!r}")
    return value


def macos_keychain_available() -> bool:
    return platform.system() == "Darwin" and shutil.which("security") is not None


def keychain_account(email: str, site: str) -> str:
    host = urllib.parse.urlparse(site).netloc or site
    return f"{email}@{host}"


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


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"No config found at {path}\n"
            f"Run: {Path(sys.argv[0]).name} setup --site {DEFAULT_SITE}"
        )

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def store_token_keychain(service: str, account: str, token: str) -> None:
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
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise SystemExit(
            f"Could not read token from Keychain "
            f"service={service!r} account={account!r}."
        )

    return result.stdout.strip()


def resolve_token(config: dict[str, Any]) -> str:
    env_name = config.get("token_env")

    if env_name and os.environ.get(env_name):
        return os.environ[env_name]

    storage = config.get("token_storage", "keychain")

    if storage == "keychain":
        return load_token_keychain(
            config.get("keychain_service", KEYCHAIN_SERVICE),
            config["keychain_account"],
        )

    if storage == "file" and config.get("token"):
        return config["token"]

    if storage == "env":
        raise SystemExit(f"Set {env_name or 'JIRA_API_TOKEN'} in the environment.")

    raise SystemExit(f"Could not resolve token from storage={storage!r}.")


class JiraClient:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.site = normalize_site(config["site"])
        self.email = config["email"]
        self.token = resolve_token(config)
        self.api_root = config["api_root"].rstrip("/")

    def auth_header(self) -> str:
        # Atlassian API tokens with scopes still use Basic auth:
        # Authorization: Basic base64(email:token)
        raw = f"{self.email}:{self.token}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def url(self, path_or_url: str, params: dict[str, Any] | None = None) -> str:
        if path_or_url.startswith(("http://", "https://")):
            if self.config.get("auth_mode") == "scoped":
                parsed = urllib.parse.urlparse(path_or_url)
                marker = "/rest/api/3/"

                if marker in parsed.path:
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

        clean_params = {
            key: value
            for key, value in (params or {}).items()
            if value not in (None, "", [])
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
        body: Any = None,
        expect_json: bool = True,
    ) -> Any:
        headers = {
            "Accept": "application/json",
            "Authorization": self.auth_header(),
            "User-Agent": f"{APP_NAME}/1.0",
        }

        data = None

        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        url = self.url(path_or_url, params)
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = response.read()

                if not expect_json:
                    return raw

                return json.loads(raw.decode("utf-8")) if raw else None

        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            hint = ""

            if exc.code in {401, 403}:
                hint = (
                    "\nHint: scoped Atlassian API tokens use Basic email:token "
                    "against https://api.atlassian.com/ex/jira/<cloud-id>."
                )

            raise JiraError(
                f"Jira API {method.upper()} {url} failed with HTTP {exc.code}: "
                f"{details[:2000]}{hint}"
            ) from exc

        except urllib.error.URLError as exc:
            raise JiraError(f"Could not reach Jira API: {exc}") from exc

    def get(self, path_or_url: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path_or_url, params=params)

    def get_bytes(self, path_or_url: str, params: dict[str, Any] | None = None) -> bytes:
        return self.request(
            "GET",
            path_or_url,
            params=params,
            expect_json=False,
        )


def compact_ws(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", (text or "").strip())


def adf_to_text(node: Any, indent: int = 0) -> str:
    if node is None:
        return ""

    if isinstance(node, str):
        return node

    if isinstance(node, (int, float, bool)):
        return str(node)

    if isinstance(node, list):
        return compact_ws(
            "\n".join(adf_to_text(item, indent) for item in node if item is not None)
        )

    if not isinstance(node, dict):
        return str(node)

    typ = node.get("type")
    content = node.get("content", [])

    if typ == "doc":
        return adf_to_text(content, indent)

    if typ == "text":
        text = node.get("text", "")

        for mark in node.get("marks", []) or []:
            attrs = mark.get("attrs") or {}
            mark_type = mark.get("type")

            if mark_type == "link" and attrs.get("href"):
                text = f"{text} ({attrs['href']})"
            elif mark_type == "code":
                text = f"`{text}`"
            elif mark_type == "strong":
                text = f"**{text}**"
            elif mark_type == "em":
                text = f"*{text}*"

        return text

    if typ == "hardBreak":
        return "\n"

    if typ == "paragraph":
        return "".join(adf_to_text(item, indent) for item in content).strip()

    if typ == "heading":
        level = max(2, min(int((node.get("attrs") or {}).get("level", 2)) + 1, 6))
        return "#" * level + " " + adf_to_text(content, indent).strip()

    if typ == "bulletList":
        lines = []

        for item in content:
            item_text = adf_to_text(item, indent + 2).strip()
            if item_text:
                lines.append(
                    " " * indent
                    + "- "
                    + item_text.replace("\n", "\n" + " " * (indent + 2))
                )

        return "\n".join(lines)

    if typ == "orderedList":
        lines = []
        start = int((node.get("attrs") or {}).get("order", 1))

        for idx, item in enumerate(content, start=start):
            item_text = adf_to_text(item, indent + 3).strip()
            if item_text:
                prefix = f"{idx}. "
                lines.append(
                    " " * indent
                    + prefix
                    + item_text.replace("\n", "\n" + " " * (indent + len(prefix)))
                )

        return "\n".join(lines)

    if typ == "listItem":
        return adf_to_text(content, indent)

    if typ == "codeBlock":
        language = (node.get("attrs") or {}).get("language") or ""
        return f"```{language}\n{adf_to_text(content)}\n```"

    if typ == "blockquote":
        return "\n".join("> " + line for line in adf_to_text(content).splitlines())

    if typ == "mention":
        return (node.get("attrs") or {}).get("text") or "@mention"

    if typ in {"inlineCard", "blockCard", "embedCard"}:
        return (node.get("attrs") or {}).get("url") or ""

    if typ == "media":
        attrs = node.get("attrs") or {}
        return f"[media: {attrs.get('alt') or attrs.get('id') or 'attachment'}]"

    if typ == "table":
        return "\n".join(adf_to_text(row, indent) for row in content)

    if typ == "tableRow":
        cells = [
            adf_to_text(cell, indent).replace("\n", " ").strip()
            for cell in content
        ]
        return "| " + " | ".join(cells) + " |"

    if typ in {"tableCell", "tableHeader"}:
        return adf_to_text(content, indent)

    return adf_to_text(content, indent)


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


def format_value(value: Any) -> str:
    if value in (None, "", []):
        return "-"

    if isinstance(value, (str, int, float, bool)):
        return str(value)

    if isinstance(value, list):
        return ", ".join(
            item for item in (format_value(entry) for entry in value) if item != "-"
        ) or "-"

    if isinstance(value, dict):
        if value.get("type") == "doc":
            return adf_to_text(value)

        for key in ("displayName", "name", "value", "key", "filename"):
            if value.get(key):
                return str(value[key])

        if "fields" in value and "key" in value:
            return f"{value['key']} — {(value.get('fields') or {}).get('summary', '')}".strip()

    return str(value)


def first_chars(text: str, limit: int) -> str:
    text = compact_ws(text or "")
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def issue_url(site: str, key: str) -> str:
    return f"{normalize_site(site)}/browse/{key}"


def safe_filename(name: str) -> str:
    name = name.strip() or "attachment"
    name = re.sub(r"[/\\:\0]", "_", name)
    return name


def api_url_to_browser_url(config: dict[str, Any], url: str) -> str:
    if not url:
        return "-"

    if config.get("auth_mode") != "scoped":
        return url

    parsed = urllib.parse.urlparse(url)
    marker = "/rest/api/3/"

    if marker not in parsed.path:
        return url

    suffix = parsed.path.split(marker, 1)[1]
    site = normalize_site(config["site"])

    return f"{site}/rest/api/3/{suffix}"


def issue_line(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    issue_type = format_value(fields.get("issuetype"))
    summary = fields.get("summary") or ""

    if issue_type != "-":
        return f"- {issue.get('key')} ({issue_type}) {summary}".strip()

    return f"- {issue.get('key')} {summary}".strip()


def link_line(link: dict[str, Any]) -> str:
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
    return f"- {direction}: {issue.get('key')} {fields.get('summary') or ''}".strip()


def get_field_catalog(client: JiraClient) -> dict[str, dict[str, Any]]:
    try:
        fields = client.get("/rest/api/3/field")
    except JiraError:
        return {}

    return {
        field["id"]: field
        for field in fields
        if isinstance(field, dict) and field.get("id")
    }


def epic_custom_field_ids(field_catalog: dict[str, dict[str, Any]]) -> list[str]:
    result = []

    for field_id, meta in field_catalog.items():
        name = (meta.get("name") or "").strip().lower()

        if field_id.startswith("customfield_") and name in EPIC_FIELD_NAMES:
            result.append(field_id)

    return result


def get_issue(
    client: JiraClient,
    key: str,
    extra_fields: list[str] | None = None,
) -> dict[str, Any]:
    fields = list(dict.fromkeys(BASE_ISSUE_FIELDS + (extra_fields or [])))

    return client.get(
        f"/rest/api/3/issue/{urllib.parse.quote(key)}",
        {
            "fields": ",".join(fields),
            "expand": "names,schema",
        },
    )


def get_comments(
    client: JiraClient,
    key: str,
    max_comments: int,
) -> list[dict[str, Any]]:
    if max_comments <= 0:
        return []

    comments: list[dict[str, Any]] = []
    start_at = 0
    page_size = min(max_comments, 100)

    while len(comments) < max_comments:
        page = client.get(
            f"/rest/api/3/issue/{urllib.parse.quote(key)}/comment",
            {
                "startAt": start_at,
                "maxResults": min(page_size, max_comments - len(comments)),
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


def search_children(
    client: JiraClient,
    key: str,
    max_results: int,
) -> list[dict[str, Any]]:
    if max_results <= 0:
        return []

    fields = "summary,issuetype"

    jqls = [
        f'parent = {key} OR "Epic Link" = {key} ORDER BY Rank ASC',
        f"parent = {key} ORDER BY Rank ASC",
    ]

    for jql in jqls:
        try:
            result = client.get(
                "/rest/api/3/search/jql",
                {
                    "jql": jql,
                    "fields": fields,
                    "maxResults": max_results,
                },
            )
            issues = result.get("issues") or []
            if issues:
                return issues
        except JiraError:
            continue

    return []


def get_remote_links(
    client: JiraClient,
    key: str,
) -> list[dict[str, Any]]:
    try:
        links = client.get(f"/rest/api/3/issue/{urllib.parse.quote(key)}/remotelink")
        return links if isinstance(links, list) else []
    except JiraError:
        return []


def build_payload(
    client: JiraClient,
    key: str,
    *,
    max_comments: int,
    max_children: int,
) -> dict[str, Any]:
    field_catalog = get_field_catalog(client)
    issue = get_issue(client, key, epic_custom_field_ids(field_catalog))
    key = issue["key"]

    return {
        "issue": issue,
        "field_catalog": field_catalog,
        "comments": get_comments(client, key, max_comments),
        "children": search_children(client, key, max_children),
        "remote_links": get_remote_links(client, key),
    }


def epic_lines(payload: dict[str, Any]) -> list[str]:
    issue = payload["issue"]
    fields = issue.get("fields") or {}
    names = issue.get("names") or {}
    field_catalog = payload.get("field_catalog") or {}
    lines = []

    parent = fields.get("parent")
    if parent:
        lines.append(f"- Parent/Epic: {format_value(parent)}")

    for field_id, value in fields.items():
        if not field_id.startswith("customfield_") or value in (None, "", []):
            continue

        name = (
            names.get(field_id)
            or (field_catalog.get(field_id) or {}).get("name")
            or field_id
        )
        name_l = name.strip().lower()

        if name_l in EPIC_FIELD_NAMES:
            lines.append(f"- {name}: {format_value(value)}")

    return lines


def render_ticket(config: dict[str, Any], payload: dict[str, Any]) -> str:
    issue = payload["issue"]
    fields = issue.get("fields") or {}

    lines = [
        f"# {issue['key']} — {fields.get('summary') or ''}".rstrip(),
        "",
        f"URL: {issue_url(config['site'], issue['key'])}",
        "",
    ]

    meta = [
        ("Type", format_value(fields.get("issuetype"))),
        ("Status", format_value(fields.get("status"))),
        ("Components", format_value(fields.get("components"))),
        ("Labels", format_value(fields.get("labels"))),
    ]

    visible_meta = [(label, value) for label, value in meta if value != "-"]

    if visible_meta:
        lines.append("## Metadata")
        for label, value in visible_meta:
            lines.append(f"- {label}: {value}")
        lines.append("")

    description = adf_to_text(fields.get("description"))
    lines.extend(
        [
            "## Description",
            description if description else "-",
            "",
        ]
    )

    epic = epic_lines(payload)
    if epic:
        lines.extend(["## Epic / Parent", *epic, ""])

    links = fields.get("issuelinks") or []
    subtasks = fields.get("subtasks") or []
    children = payload["children"]

    if links or subtasks or children:
        lines.append("## Linked issues / subtasks")

        if links:
            lines.append("")
            lines.append("### Linked issues")
            lines.extend(link_line(link) for link in links)

        if subtasks:
            lines.append("")
            lines.append("### Subtasks")
            lines.extend(issue_line(item) for item in subtasks)

        if children:
            lines.append("")
            lines.append("### Children / issues in epic")
            lines.extend(issue_line(item) for item in children)

        lines.append("")

    remote_links = payload["remote_links"]
    if remote_links:
        lines.append("## Remote links")

        for link in remote_links:
            obj = link.get("object") or {}
            title = obj.get("title") or link.get("globalId") or "remote link"
            url = obj.get("url") or "-"
            lines.append(f"- {title}: {url}")

        lines.append("")

    attachments = fields.get("attachment") or []
    if attachments:
        lines.append("## Attachments")

        for att in attachments:
            filename = att.get("filename") or "attachment"
            attachment_id = att.get("id") or "-"
            mime = att.get("mimeType") or "unknown mime"
            size = att.get("size")
            size_text = f", {size} bytes" if size is not None else ""
            content_url = api_url_to_browser_url(config, att.get("content") or "")

            lines.append(
                f"- {filename} "
                f"(id: {attachment_id}, {mime}{size_text})"
            )
            lines.append(f"  - link: {content_url}")
            lines.append(
                f"  - download: {Path(sys.argv[0]).name} get-attachment "
                f"{issue['key']} {attachment_id}"
            )

        lines.append("")

    comments = payload["comments"]
    if comments:
        lines.append("## Comments")

        for idx, comment in enumerate(comments, start=1):
            author = display_user(comment.get("author"))
            created = comment.get("created") or "unknown date"
            body = first_chars(adf_to_text(comment.get("body")), 1000)

            lines.append("")
            lines.append(f"### Comment {idx} — {author}, {created}")
            lines.append(body or "-")

        lines.append("")

    return compact_ws("\n".join(lines)) + "\n"


def find_attachment(
    issue: dict[str, Any],
    needle: str,
) -> dict[str, Any]:
    attachments = (issue.get("fields") or {}).get("attachment") or []
    needle_l = needle.lower()

    for att in attachments:
        if str(att.get("id")) == needle:
            return att

    exact = [
        att
        for att in attachments
        if (att.get("filename") or "").lower() == needle_l
    ]

    if len(exact) == 1:
        return exact[0]

    partial = [
        att
        for att in attachments
        if needle_l in (att.get("filename") or "").lower()
    ]

    if len(partial) == 1:
        return partial[0]

    if not attachments:
        raise SystemExit("This issue has no attachments.")

    available = "\n".join(
        f"- {att.get('id')}: {att.get('filename')}"
        for att in attachments
    )

    if exact or partial:
        raise SystemExit(
            f"Attachment name {needle!r} is ambiguous. Use the attachment id.\n"
            f"Available attachments:\n{available}"
        )

    raise SystemExit(
        f"No attachment matching {needle!r} found.\n"
        f"Available attachments:\n{available}"
    )


def cmd_setup(args: argparse.Namespace) -> int:
    site = normalize_site(args.site or DEFAULT_SITE)
    email = args.email or input("Atlassian account email: ").strip()

    if not email:
        raise SystemExit("email is required")

    auth_mode = args.auth_mode
    cloud_id = args.cloud_id

    if auth_mode == "scoped" and not cloud_id:
        cloud_id = input("Jira cloudId: ").strip()
        if not cloud_id:
            raise SystemExit("cloudId is required for scoped tokens")

    store = args.store

    if store == "keychain" and not macos_keychain_available():
        eprint("macOS Keychain not available; falling back to --store file.")
        store = "file"

    token = None

    if store != "env":
        token = (
            sys.stdin.read().strip()
            if args.token_stdin
            else getpass.getpass("Jira API token (input hidden): ").strip()
        )

        if not token:
            raise SystemExit("token is required")

    api_root = (
        f"https://api.atlassian.com/ex/jira/{cloud_id}"
        if auth_mode == "scoped"
        else site
    )

    config: dict[str, Any] = {
        "site": site,
        "api_root": api_root,
        "email": email,
        "auth_mode": auth_mode,
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
    else:
        config["token"] = token

    secure_write_json(args.config, config)

    print(f"Wrote config to {args.config}")
    print(f"API root: {api_root}")
    print("Auth: Basic email:token")

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
        max_comments=args.max_comments,
        max_children=args.children,
    )

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return 0

    print(render_ticket(config, payload))
    return 0


def cmd_get_attachment(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    client = JiraClient(config)

    issue = get_issue(client, args.ticket)
    attachment = find_attachment(issue, args.attachment)

    content_url = attachment.get("content")
    if not content_url:
        raise SystemExit("Attachment has no content URL.")

    raw = client.get_bytes(content_url)

    tmp_base = Path(args.tmpdir) if args.tmpdir else Path(tempfile.gettempdir())
    target_dir = tmp_base / "jira-ticket-attachments" / issue["key"]
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = safe_filename(attachment.get("filename") or f"attachment-{attachment.get('id')}")
    target = target_dir / filename

    if target.exists() and not args.force:
        stem = target.stem
        suffix = target.suffix
        counter = 2

        while True:
            candidate = target.with_name(f"{stem}-{counter}{suffix}")
            if not candidate.exists():
                target = candidate
                break
            counter += 1

    target.write_bytes(raw)

    print(target)
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read Jira Cloud issues into concise Markdown and download attachments."
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)

    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="configure Jira credentials")
    setup.add_argument("--site", default=DEFAULT_SITE)
    setup.add_argument("--email")
    setup.add_argument("--auth-mode", choices=["scoped", "direct"], default="scoped")
    setup.add_argument("--cloud-id")
    setup.add_argument(
        "--store",
        choices=["keychain", "env", "file"],
        default="keychain" if macos_keychain_available() else "file",
    )
    setup.add_argument("--token-env", default="JIRA_API_TOKEN")
    setup.add_argument("--token-stdin", action="store_true")
    setup.set_defaults(func=cmd_setup)

    show_config = sub.add_parser("show-config", help="print config with secrets redacted")
    show_config.set_defaults(func=cmd_show_config)

    read = sub.add_parser("read", help="read one issue")
    read.add_argument("ticket", type=require_ticket_key)
    read.add_argument("--json", action="store_true")
    read.add_argument("--max-comments", type=int, default=50)
    read.add_argument("--children", type=int, default=50)
    read.set_defaults(func=cmd_read)

    get_attachment = sub.add_parser(
        "get-attachment",
        help="download an issue attachment to a tmp directory",
    )
    get_attachment.add_argument("ticket", type=require_ticket_key)
    get_attachment.add_argument(
        "attachment",
        help="attachment id, exact filename, or unique filename substring",
    )
    get_attachment.add_argument(
        "--tmpdir",
        help="base tmp directory; default: system temp dir",
    )
    get_attachment.add_argument(
        "--force",
        action="store_true",
        help="overwrite if target path already exists",
    )
    get_attachment.set_defaults(func=cmd_get_attachment)

    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    commands = {
        "setup",
        "show-config",
        "read",
        "get-attachment",
        "-h",
        "--help",
    }

    if argv and argv[0] not in commands and not argv[0].startswith("-"):
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
