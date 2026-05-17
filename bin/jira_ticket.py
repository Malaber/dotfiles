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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

APP_NAME = "jira-ticket-reader"
DEFAULT_SITE = "https://turniere.atlassian.net"
CONFIG_PATH = Path.home() / ".config" / APP_NAME / "config.json"
KEYCHAIN_SERVICE = APP_NAME
ISSUE_FIELDS = [
    "summary",
    "issuetype",
    "status",
    "priority",
    "description",
    "components",
    "attachment",
    "issuelinks",
    "parent",
    "subtasks",
    "labels",
]


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
        raise SystemExit(f"No config found at {path}\nRun: {Path(sys.argv[0]).name} setup --site {DEFAULT_SITE}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def store_token_keychain(service: str, account: str, token: str) -> None:
    subprocess.run(
        ["security", "add-generic-password", "-s", service, "-a", account, "-w", token, "-U"],
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
        raise SystemExit(f"Could not read token from Keychain service={service!r} account={account!r}.")
    return result.stdout.strip()


def resolve_token(config: dict[str, Any]) -> str:
    env_name = config.get("token_env")
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    storage = config.get("token_storage", "keychain")
    if storage == "keychain":
        return load_token_keychain(config.get("keychain_service", KEYCHAIN_SERVICE), config["keychain_account"])
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
        # Atlassian scoped API tokens still use Basic auth: email:token.
        raw = f"{self.email}:{self.token}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def url(self, path: str, params: dict[str, Any] | None = None) -> str:
        if path.startswith(("http://", "https://")) and self.config.get("auth_mode") == "scoped":
            parsed = urllib.parse.urlparse(path)
            marker = "/rest/api/3/"
            if marker in parsed.path:
                path = "/rest/api/3/" + parsed.path.split(marker, 1)[1]
        elif path.startswith(("http://", "https://")):
            url = path
            if params:
                url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
            return url
        if not path.startswith("/"):
            path = "/" + path
        clean = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
        url = self.api_root + path
        return url + ("?" + urllib.parse.urlencode(clean, doseq=True) if clean else "")

    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None, body: Any = None) -> Any:
        headers = {"Accept": "application/json", "Authorization": self.auth_header(), "User-Agent": f"{APP_NAME}/1.0"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        url = self.url(path, params)
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            hint = ""
            if exc.code in {401, 403}:
                hint = "\nHint: scoped tokens use --auth-mode scoped and Basic email:token against api.atlassian.com/ex/jira/<cloud-id>."
            raise JiraError(f"Jira API {method.upper()} {url} failed with HTTP {exc.code}: {details[:2000]}{hint}") from exc
        except urllib.error.URLError as exc:
            raise JiraError(f"Could not reach Jira API: {exc}") from exc

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)


def compact_ws(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.strip())


def adf_to_text(node: Any, indent: int = 0) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, (int, float, bool)):
        return str(node)
    if isinstance(node, list):
        return compact_ws("\n".join(adf_to_text(item, indent) for item in node if item is not None))
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
            if mark.get("type") == "link" and attrs.get("href"):
                text = f"{text} ({attrs['href']})"
            elif mark.get("type") == "code":
                text = f"`{text}`"
            elif mark.get("type") == "strong":
                text = f"**{text}**"
            elif mark.get("type") == "em":
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
        return "\n".join(" " * indent + "- " + adf_to_text(item, indent + 2).replace("\n", "\n" + " " * (indent + 2)) for item in content)
    if typ == "orderedList":
        start = int((node.get("attrs") or {}).get("order", 1))
        return "\n".join(f"{' ' * indent}{i}. {adf_to_text(item, indent + 3)}" for i, item in enumerate(content, start=start))
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
    return adf_to_text(content, indent)


def display_user(user: Any) -> str:
    if not user:
        return "Unassigned"
    return user if isinstance(user, str) else user.get("displayName") or user.get("emailAddress") or user.get("accountId") or "-"


def format_value(value: Any) -> str:
    if value in (None, "", []):
        return "-"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(v for v in (format_value(item) for item in value) if v != "-") or "-"
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


def issue_line(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    return f"- {issue.get('key')} ({format_value(fields.get('issuetype'))}) {fields.get('summary') or ''}".strip()


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
    return f"- {direction}: {issue.get('key')} {(issue.get('fields') or {}).get('summary') or ''}".strip()


def get_issue(client: JiraClient, key: str) -> dict[str, Any]:
    return client.get(f"/rest/api/3/issue/{urllib.parse.quote(key)}", {"fields": ",".join(ISSUE_FIELDS), "expand": "names,schema"})


def get_comments(client: JiraClient, key: str, max_comments: int) -> list[dict[str, Any]]:
    if max_comments <= 0:
        return []
    page = client.get(f"/rest/api/3/issue/{urllib.parse.quote(key)}/comment", {"startAt": 0, "maxResults": min(max_comments, 100), "orderBy": "created"})
    return (page.get("comments") or page.get("values") or [])[:max_comments]


def search_children(client: JiraClient, key: str, max_results: int) -> list[dict[str, Any]]:
    if max_results <= 0:
        return []
    for jql in (f'parent = {key} OR "Epic Link" = {key} ORDER BY Rank ASC', f"parent = {key} ORDER BY Rank ASC"):
        try:
            result = client.get("/rest/api/3/search/jql", {"jql": jql, "fields": "summary,issuetype", "maxResults": max_results})
            if result.get("issues"):
                return result["issues"]
        except JiraError:
            continue
    return []


def get_changelog(client: JiraClient, key: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    page = client.get(f"/rest/api/3/issue/{urllib.parse.quote(key)}/changelog", {"startAt": 0, "maxResults": min(limit, 100)})
    return (page.get("values") or [])[-limit:]


def get_remote_links(client: JiraClient, key: str) -> list[dict[str, Any]]:
    try:
        links = client.get(f"/rest/api/3/issue/{urllib.parse.quote(key)}/remotelink")
        return links if isinstance(links, list) else []
    except JiraError:
        return []


def build_payload(client: JiraClient, key: str, *, brief: bool, max_comments: int, children: int, changelog: int) -> dict[str, Any]:
    issue = get_issue(client, key)
    key = issue["key"]
    return {
        "issue": issue,
        "comments": get_comments(client, key, 10 if brief else max_comments),
        "children": search_children(client, key, 20 if brief else children),
        "changelog": [] if brief else get_changelog(client, key, changelog),
        "remote_links": [] if brief else get_remote_links(client, key),
    }


def render_brief(config: dict[str, Any], payload: dict[str, Any]) -> str:
    issue = payload["issue"]
    fields = issue.get("fields") or {}
    lines = [f"# {issue['key']} — {fields.get('summary') or ''}".rstrip(), "", f"URL: {issue_url(config['site'], issue['key'])}", "", "## Metadata"]
    for label, value in (("Type", format_value(fields.get("issuetype"))), ("Status", format_value(fields.get("status"))), ("Priority", format_value(fields.get("priority"))), ("Components", format_value(fields.get("components"))), ("Labels", format_value(fields.get("labels")))):
        if value != "-":
            lines.append(f"- {label}: {value}")
    lines.extend(["", "## Description", first_chars(adf_to_text(fields.get("description")), 1200), ""])
    if fields.get("parent"):
        lines.extend(["## Parent / Epic", f"- {format_value(fields['parent'])}", ""])
    related = [link_line(link) for link in (fields.get("issuelinks") or [])[:10]]
    related += [issue_line(item) for item in (fields.get("subtasks") or [])[:10]]
    related += [issue_line(item) for item in payload["children"][:10]]
    if related:
        lines.extend(["## Related tickets", *related, ""])
    attachments = fields.get("attachment") or []
    if attachments:
        lines.append("## Attachments")
        for att in attachments[:10]:
            lines.append(f"- {att.get('filename')} ({att.get('mimeType') or 'unknown mime'})")
        lines.append("")
    if payload["comments"]:
        lines.append("## Latest comments")
        for comment in payload["comments"][-3:]:
            lines.extend([f"### {display_user(comment.get('author'))}, {comment.get('created') or 'unknown date'}", first_chars(adf_to_text(comment.get("body")), 800), ""])
    return compact_ws("\n".join(lines)) + "\n"


def render_full(config: dict[str, Any], payload: dict[str, Any]) -> str:
    issue = payload["issue"]
    fields = issue.get("fields") or {}
    lines = [f"# {issue['key']} — {fields.get('summary') or ''}".rstrip(), "", f"URL: {issue_url(config['site'], issue['key'])}", "", "## Metadata"]
    for label, value in (("Type", format_value(fields.get("issuetype"))), ("Status", format_value(fields.get("status"))), ("Priority", format_value(fields.get("priority"))), ("Components", format_value(fields.get("components"))), ("Labels", format_value(fields.get("labels")))):
        if value != "-":
            lines.append(f"- **{label}:** {value}")
    if fields.get("parent"):
        lines.append(f"- **Parent/Epic:** {format_value(fields['parent'])}")
    description = adf_to_text(fields.get("description"))
    if description:
        lines.extend(["", "## Description", description])
    attachments = fields.get("attachment") or []
    lines.extend(["", f"## Attachments ({len(attachments)})"])
    lines.extend([f"- {att.get('filename')} ({att.get('mimeType') or 'unknown mime'}, {att.get('size', 'unknown size')} bytes)" for att in attachments] or ["- none"])
    links = fields.get("issuelinks") or []
    lines.extend(["", f"## Linked issues ({len(links)})"])
    lines.extend([link_line(link) for link in links] or ["- none"])
    subtasks = fields.get("subtasks") or []
    lines.extend(["", f"## Subtasks ({len(subtasks)})"])
    lines.extend([issue_line(item) for item in subtasks] or ["- none"])
    children = payload["children"]
    lines.extend(["", f"## Children / issues in epic ({len(children)})"])
    lines.extend([issue_line(item) for item in children] or ["- none found or not applicable"])
    remote_links = payload["remote_links"]
    lines.extend(["", f"## Remote links ({len(remote_links)})"])
    if remote_links:
        for link in remote_links:
            obj = link.get("object") or {}
            lines.append(f"- {obj.get('title') or link.get('globalId') or 'remote link'}: {obj.get('url') or '-'}")
    else:
        lines.append("- none")
    comments = payload["comments"]
    lines.extend(["", f"## Comments ({len(comments)})"])
    if comments:
        for idx, comment in enumerate(comments, start=1):
            lines.extend(["", f"### Comment {idx} — {display_user(comment.get('author'))}, {comment.get('created') or 'unknown date'}", adf_to_text(comment.get("body")) or "-"])
    else:
        lines.append("- none")
    changelog = payload["changelog"]
    lines.extend(["", f"## Recent changelog ({len(changelog)})"])
    if changelog:
        for change in changelog:
            lines.append(f"- {change.get('created') or 'unknown date'} — {display_user(change.get('author'))}")
            for item in change.get("items") or []:
                lines.append(f"  - {item.get('field') or item.get('fieldId') or 'field'}: {item.get('fromString') or '-'} → {item.get('toString') or '-'}")
    else:
        lines.append("- none")
    return compact_ws("\n".join(lines)) + "\n"


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
        token = sys.stdin.read().strip() if args.token_stdin else getpass.getpass("Jira API token (input hidden): ").strip()
        if not token:
            raise SystemExit("token is required")
    api_root = f"https://api.atlassian.com/ex/jira/{cloud_id}" if auth_mode == "scoped" else site
    config: dict[str, Any] = {"site": site, "api_root": api_root, "email": email, "auth_mode": auth_mode, "cloud_id": cloud_id, "token_storage": store}
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
    config = {**config, "token": "<redacted>"} if "token" in config else config
    print(json.dumps(config, indent=2, sort_keys=True))
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    payload = build_payload(JiraClient(config), args.ticket, brief=args.brief, max_comments=args.max_comments, children=args.children, changelog=args.changelog)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(render_brief(config, payload) if args.brief else render_full(config, payload))
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read a Jira Cloud issue into Markdown.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup")
    setup.add_argument("--site", default=DEFAULT_SITE)
    setup.add_argument("--email")
    setup.add_argument("--auth-mode", choices=["scoped", "direct"], default="scoped")
    setup.add_argument("--cloud-id")
    setup.add_argument("--store", choices=["keychain", "env", "file"], default="keychain" if macos_keychain_available() else "file")
    setup.add_argument("--token-env", default="JIRA_API_TOKEN")
    setup.add_argument("--token-stdin", action="store_true")
    setup.set_defaults(func=cmd_setup)
    show_config = sub.add_parser("show-config")
    show_config.set_defaults(func=cmd_show_config)
    read = sub.add_parser("read")
    read.add_argument("ticket", type=require_ticket_key)
    read.add_argument("--brief", action="store_true")
    read.add_argument("--json", action="store_true")
    read.add_argument("--max-comments", type=int, default=100)
    read.add_argument("--children", type=int, default=50)
    read.add_argument("--changelog", type=int, default=20)
    read.set_defaults(func=cmd_read)
    return parser


def normalize_argv(argv: list[str]) -> list[str]:
    commands = {"setup", "show-config", "read", "-h", "--help"}
    return ["read", *argv] if argv and argv[0] not in commands and not argv[0].startswith("-") else argv


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
