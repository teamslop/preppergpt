#!/usr/bin/env python3
import json
import io
import math
import os
import pwd
import re
import shutil
import socket
import struct
import subprocess
import time
import wave
import uuid
import difflib
from datetime import date
from html import escape as html_escape
from copy import deepcopy
from dataclasses import dataclass, asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib import request, parse, error


HOST = os.environ.get("LOCAL_SCHEDULER_HOST", "127.0.0.1")
PORT = int(os.environ.get("LOCAL_SCHEDULER_PORT", "18042"))
PUBLIC_BASE_URL = os.environ.get("LOCAL_SCHEDULER_PUBLIC_BASE_URL", f"http://{HOST}:{PORT}")
STORAGE = Path(os.environ.get("LOCAL_SCHEDULER_STORAGE", "/data"))
DEFAULT_BASE_URL = os.environ.get("LOCAL_SCHEDULER_DEFAULT_BASE_URL", "http://127.0.0.1:18041/v1")
DEFAULT_MODEL = os.environ.get("LOCAL_SCHEDULER_DEFAULT_MODEL", "deep-research-glm52")
DEFAULT_API_KEY = os.environ.get("LOCAL_SCHEDULER_DEFAULT_API_KEY", "")
POLL_SECONDS = int(os.environ.get("LOCAL_SCHEDULER_POLL_SECONDS", "5"))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("LOCAL_SCHEDULER_REQUEST_TIMEOUT_SECONDS", "21600"))

TASKS_FILE = STORAGE / "tasks.json"
RUNS_DIR = STORAGE / "runs"
PULSE_DIR = STORAGE / "pulse"
APPROVALS_DIR = STORAGE / "approvals"
LOCAL_APP_NOTES_DIR = STORAGE / "local-app-notes"
LOCAL_APP_CONNECTIONS_DIR = STORAGE / "local-app-connections"
LOCAL_APP_ACTION_CONTROLS_DIR = STORAGE / "local-app-action-controls"
LOCAL_APP_CALL_LOGS_DIR = STORAGE / "local-app-call-logs"
LOCAL_EMAIL_DRAFTS_DIR = STORAGE / "local-email-drafts"
LOCAL_SECURITY_SESSIONS_DIR = STORAGE / "local-security-sessions"
LOCAL_SITES_DIR = STORAGE / "local-sites"
LOCAL_SHEETS_DIR = STORAGE / "local-sheets"
LOCAL_PRONUNCIATION_DIR = STORAGE / "local-pronunciation"
LOCAL_SPORTS_DIR = STORAGE / "local-sports"
LOCAL_CODE_WORKSPACES_DIR = STORAGE / "local-code-workspaces"
LOCAL_CODE_GIT_WORKTREES_DIR = STORAGE / "local-code-git-worktrees"
LOCAL_BENCHMARKS_DIR = STORAGE / "local-model-benchmarks"
LOCAL_GOALS_DIR = STORAGE / "local-goals"
LOCAL_PARITY_DOCS_DIR = Path(os.environ.get("LOCAL_PARITY_DOCS_DIR", "/app/parity-docs"))
LOCAL_PARITY_SOURCE_MAX_AGE_DAYS = int(os.environ.get("LOCAL_PARITY_SOURCE_MAX_AGE_DAYS", "30"))
LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES = 47
LOCAL_PARITY_EXPECTED_SOURCE_ENTRIES = 78
LOCAL_PARITY_EXPECTED_OFFICIAL_SOURCES = 77
LOCAL_PARITY_EXPECTED_POPULAR_TASKS = 17
LOCAL_PARITY_CURRENT_RELEASE_SOURCE_ID = "chatgpt-release-notes-current"
LOCAL_PARITY_COMPLETION_STATUS = "complete_for_local_functional_parity"
LOCAL_PARITY_HOSTED_SCOPE_STATUS = "excluded_from_local_goal"
LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_FAMILIES = {
    "Core chat and model picker",
    "Chat history management",
    "Projects / organized workspaces",
    "Group chats / collaboration",
    "Message editing, retries, and branches",
    "Search / browsing",
    "Connectors and actions",
    "Interactive visual explanations",
    "Interactive charts in answers",
    "Notes / Library",
    "Pulse / proactive briefings",
    "Scheduled tasks",
    "Voice dictation / STT",
    "File uploads and document Q&A",
    "Image understanding",
    "Job search and resume support",
    "Personal finance analysis",
    "Deep research",
    "Agent mode",
    "Codex / software engineering agent",
    "Skills / reusable workflows",
}
LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_EVIDENCE_TERMS = {
    "pronunciation guidance",
    "World Cup conversational updates",
    "app permission controls",
    "organization and sharing changes",
    "notes from responses",
    "interactive chart",
    "faster image upload",
    "job/resume support",
    "personal finance analysis",
    "scheduled-task monitoring",
    "Slack app/connector support",
    "model picker changes",
    "Pulse migration",
    "Codex Record & Replay",
}
LOCAL_BENCHMARK_FRESH_MAX_AGE_SECONDS = int(
    os.environ.get("LOCAL_BENCHMARK_FRESH_MAX_AGE_SECONDS", str(7 * 24 * 60 * 60))
)
LOCAL_PARITY_LIVE_STATUS_TIMEOUT_SECONDS = int(os.environ.get("LOCAL_PARITY_LIVE_STATUS_TIMEOUT_SECONDS", "3"))
LOCAL_APP_PARITY_SEARCH_CACHE_SECONDS = int(os.environ.get("LOCAL_APP_PARITY_SEARCH_CACHE_SECONDS", "1800"))
LOCAL_CODE_RUNS_DIR = Path(os.environ.get("LOCAL_CODE_RUNS_DIR", "/tmp/openwebui-local-code-runs"))
LOCK = Lock()
LOCAL_APP_PARITY_SEARCH_CACHE_LOCK = Lock()
LOCAL_APP_PARITY_SEARCH_CACHE = {"expires_at": 0.0, "candidates": []}
RUNNING = set()
STORAGE.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)
PULSE_DIR.mkdir(parents=True, exist_ok=True)
APPROVALS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_APP_NOTES_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_APP_CONNECTIONS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_APP_ACTION_CONTROLS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_APP_CALL_LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_EMAIL_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_SECURITY_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_SITES_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_PRONUNCIATION_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_SPORTS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_CODE_WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_CODE_GIT_WORKTREES_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_GOALS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_CODE_RUNS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Task:
    id: str
    title: str
    prompt: str
    enabled: bool
    base_url: str
    model: str
    api_key: str
    interval_seconds: int | None
    run_at: int | None
    next_run_at: int | None
    options: dict
    created_at: int
    updated_at: int
    last_run_at: int | None = None
    last_status: str | None = None
    last_run_id: str | None = None


def now() -> int:
    return int(time.time())


def load_tasks() -> dict[str, Task]:
    if not TASKS_FILE.exists():
        return {}
    try:
        raw = json.loads(TASKS_FILE.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        raw = {}
    tasks = {}
    for task_id, item in raw.items():
        try:
            tasks[task_id] = Task(**item)
        except TypeError:
            continue
    return tasks


def save_tasks(tasks: dict[str, Task]):
    payload = {task_id: asdict(task) for task_id, task in tasks.items()}
    tmp = TASKS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(TASKS_FILE)


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def send_html(handler: BaseHTTPRequestHandler, status: int, html: str):
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def send_bytes(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str):
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def parse_time(value) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        if value.lower() == "now":
            return now()
        if value.isdigit():
            return int(value)
        try:
            from datetime import datetime

            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    return None


def normalize_base_url(base_url: str) -> str:
    base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url[: -len("/chat/completions")]
    return base_url


def chat_completions(task: Task) -> str:
    base_url = normalize_base_url(task.base_url)
    payload = {
        "model": task.model or DEFAULT_MODEL,
        "messages": [{"role": "user", "content": task.prompt}],
        "stream": False,
    }
    payload.update(deepcopy(task.options or {}))
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "openwebui-local-scheduler/0.1"}
    api_key = task.api_key or DEFAULT_API_KEY
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = request.Request(f"{base_url}/chat/completions", data=data, headers=headers)
    with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        result = json.loads(resp.read().decode("utf-8") or "{}")
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")


def chat_content_from_response(data: dict) -> str:
    try:
        message = data.get("choices", [{}])[0].get("message", {})
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                return "\n".join(str(item.get("text") if isinstance(item, dict) else item) for item in content)
            return str(content or "")
    except (IndexError, AttributeError):
        pass
    return ""


def completion_tokens_from_response(data: dict, content: str) -> int:
    usage = data.get("usage") if isinstance(data, dict) else {}
    if isinstance(usage, dict):
        try:
            tokens = int(usage.get("completion_tokens") or 0)
            if tokens > 0:
                return tokens
        except (TypeError, ValueError):
            pass
    return max(1, len(re.findall(r"\S+", content or ""))) if content else 0


def list_runs(task_id: str | None = None) -> list[dict]:
    runs = []
    for path in RUNS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if task_id is None or item.get("task_id") == task_id:
            runs.append(item)
    runs.sort(key=lambda item: item.get("started_at", 0), reverse=True)
    return runs


def write_run(run: dict):
    (RUNS_DIR / f"{run['id']}.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")


def list_pulse_digests() -> list[dict]:
    digests = []
    for path in PULSE_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        digests.append(item)
    digests.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    return digests


def write_pulse_digest(digest: dict):
    (PULSE_DIR / f"{digest['id']}.json").write_text(json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8")


def list_approvals(status: str | None = None) -> list[dict]:
    approvals = []
    for path in APPROVALS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if status is None or item.get("status") == status:
            approvals.append(item)
    approvals.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    return approvals


def approval_path(approval_id: str) -> Path:
    return APPROVALS_DIR / f"{approval_id}.json"


def read_approval(approval_id: str) -> dict | None:
    path = approval_path(approval_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_approval(approval: dict):
    approval_path(approval["id"]).write_text(json.dumps(approval, indent=2, ensure_ascii=False), encoding="utf-8")


def local_app_note_path(note_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", note_id or "")
    return LOCAL_APP_NOTES_DIR / f"{safe_id}.json"


def list_local_app_notes() -> list[dict]:
    notes = []
    for path in LOCAL_APP_NOTES_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        notes.append(item)
    notes.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return notes


def write_local_app_note(note: dict):
    local_app_note_path(note["id"]).write_text(json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8")


def read_local_app_note(note_id: str) -> dict | None:
    path = local_app_note_path(note_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def delete_local_app_note(note_id: str) -> bool:
    path = local_app_note_path(note_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def local_app_connection_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_app_connection_path(connection_id: str) -> Path:
    return LOCAL_APP_CONNECTIONS_DIR / f"{local_app_connection_id(connection_id)}.json"


def local_app_connection_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def local_app_connection_permission(value, default: str = "important_actions") -> str:
    normalized = str(value or default).strip().lower().replace("-", "_")
    aliases = {
        "always": "always_ask",
        "changes": "any_changes",
        "important": "important_actions",
        "never": "never_ask",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"always_ask", "any_changes", "important_actions", "never_ask"}:
        return default
    return normalized


def list_local_app_connections() -> list[dict]:
    connections = []
    for path in LOCAL_APP_CONNECTIONS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        connections.append(item)
    connections.sort(key=lambda item: item.get("updated_at") or item.get("connected_at") or item.get("created_at") or 0, reverse=True)
    return connections


def read_local_app_connection(connection_id: str) -> dict | None:
    path = local_app_connection_path(connection_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_app_connection(connection: dict):
    local_app_connection_path(connection["id"]).write_text(json.dumps(connection, indent=2, ensure_ascii=False), encoding="utf-8")


def local_app_capabilities(payload: dict, existing: dict | None = None) -> dict:
    existing = existing or {}
    raw = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
    existing_raw = existing.get("capabilities") if isinstance(existing.get("capabilities"), dict) else {}
    return {
        "interactive": local_app_connection_bool(raw.get("interactive"), bool(existing_raw.get("interactive", False))),
        "search": local_app_connection_bool(raw.get("search"), bool(existing_raw.get("search", True))),
        "deep_research": local_app_connection_bool(raw.get("deep_research"), bool(existing_raw.get("deep_research", False))),
        "sync": local_app_connection_bool(raw.get("sync"), bool(existing_raw.get("sync", False))),
        "write": local_app_connection_bool(raw.get("write"), bool(existing_raw.get("write", False))),
        "custom_mcp": local_app_connection_bool(raw.get("custom_mcp"), bool(existing_raw.get("custom_mcp", True))),
    }


def create_or_update_local_app_connection(payload: dict) -> dict:
    current = now()
    connection_id = local_app_connection_id(
        str(payload.get("id") or payload.get("slug") or payload.get("app_id") or payload.get("app_name") or f"app-{uuid.uuid4().hex[:8]}")
    )
    existing = read_local_app_connection(connection_id) or {}
    app_name = re.sub(r"\s+", " ", str(payload.get("app_name") or payload.get("name") or existing.get("app_name") or connection_id)).strip()
    if not app_name:
        raise ValueError("app_name or name is required")
    permission = local_app_connection_permission(payload.get("permission_mode") or payload.get("app_permission_mode"), existing.get("permission_mode") or "important_actions")
    status = str(payload.get("status") or existing.get("status") or "connected").strip().lower()
    if status not in {"connected", "disconnected", "disabled"}:
        status = "connected"
    connection = {
        "id": connection_id,
        "source": "local-app-connection",
        "title": str(payload.get("title") or existing.get("title") or f"{app_name} local app connection")[:200],
        "app_name": app_name[:160],
        "provider": str(payload.get("provider") or existing.get("provider") or "local").strip()[:120],
        "account": str(payload.get("account") or existing.get("account") or "local-user").strip()[:180],
        "workspace": str(payload.get("workspace") or existing.get("workspace") or "local-workspace").strip()[:160],
        "status": status,
        "permission_mode": permission,
        "capabilities": local_app_capabilities(payload, existing),
        "sync_enabled": local_app_connection_bool(payload.get("sync_enabled"), bool(existing.get("sync_enabled", False))),
        "workspace_enabled": local_app_connection_bool(payload.get("workspace_enabled"), bool(existing.get("workspace_enabled", True))),
        "created_at": existing.get("created_at") or current,
        "connected_at": existing.get("connected_at") or current,
        "updated_at": current,
        "disconnected_at": existing.get("disconnected_at") if status == "disconnected" else None,
        "url": f"{PUBLIC_BASE_URL}/local-app/connections/{connection_id}",
        "privacy": {
            "local_only": True,
            "external_oauth_performed": False,
            "external_app_connected": False,
            "external_app_disconnected": False,
            "approval_required_for_writes": True,
            "approval_required_for_permission_change": True,
            "approval_required_for_disconnect": True,
            "prompt_bodies_excluded": True,
        },
    }
    write_local_app_connection(connection)
    return connection


def update_local_app_connection_permission(connection_id: str, payload: dict) -> dict:
    connection = read_local_app_connection(connection_id)
    if not connection:
        raise FileNotFoundError(connection_id)
    current = now()
    permission = local_app_connection_permission(
        payload.get("permission_mode") or payload.get("app_permission_mode") or payload.get("ask_permission"),
        connection.get("permission_mode") or "important_actions",
    )
    connection["permission_mode"] = permission
    connection["updated_at"] = current
    connection["permission_receipt"] = {
        "id": f"local-app-permission-{uuid.uuid4().hex[:10]}",
        "created_at": current,
        "approved": True,
        "permission_mode": permission,
        "local_only": True,
        "external_app_permission_changed": False,
        "note": "Recorded as a local app permission preference only; no external OAuth grant, third-party app, or workspace setting was changed.",
    }
    connection["privacy"] = {
        **(connection.get("privacy") or {}),
        "local_only": True,
        "external_app_connected": False,
        "external_app_disconnected": False,
        "approval_required_for_permission_change": True,
    }
    write_local_app_connection(connection)
    return connection


def disconnect_local_app_connection(connection_id: str, payload: dict | None = None) -> dict:
    connection = read_local_app_connection(connection_id)
    if not connection:
        raise FileNotFoundError(connection_id)
    current = now()
    connection["status"] = "disconnected"
    connection["disconnected_at"] = current
    connection["updated_at"] = current
    connection["disconnect_mode"] = "local-ledger-only"
    connection["external_app_disconnected"] = False
    connection["disconnect_receipt"] = {
        "id": f"local-app-disconnect-{uuid.uuid4().hex[:10]}",
        "created_at": current,
        "approved": True,
        "local_only": True,
        "external_app_disconnected": False,
        "note": "Recorded as disconnected in the local app ledger only; no external OAuth grant, third-party app, or workspace app setting was revoked.",
    }
    connection["privacy"] = {
        **(connection.get("privacy") or {}),
        "local_only": True,
        "external_app_connected": False,
        "external_app_disconnected": False,
        "approval_required_for_disconnect": True,
    }
    write_local_app_connection(connection)
    return connection


def delete_local_app_connection(connection_id: str) -> bool:
    path = local_app_connection_path(connection_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def local_app_action_control_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_app_action_control_path(control_id: str) -> Path:
    return LOCAL_APP_ACTION_CONTROLS_DIR / f"{local_app_action_control_id(control_id)}.json"


def list_local_app_action_controls() -> list[dict]:
    controls = []
    for path in LOCAL_APP_ACTION_CONTROLS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        controls.append(item)
    controls.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return controls


def read_local_app_action_control(control_id: str) -> dict | None:
    path = local_app_action_control_path(control_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_app_action_control(control: dict):
    local_app_action_control_path(control["id"]).write_text(json.dumps(control, indent=2, ensure_ascii=False), encoding="utf-8")


def local_app_action_control_list(value) -> list[str]:
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = re.split(r"[,;]", str(value or ""))
    items = []
    for item in raw_values:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if text and text not in items:
            items.append(text[:180])
    return items


def local_app_action_control_mode(value: str, default: str = "custom") -> str:
    normalized = str(value or default).strip().lower().replace("-", "_")
    aliases = {
        "all": "allow_all",
        "allow": "allow_all",
        "read": "read_only",
        "readonly": "read_only",
        "block": "disabled",
        "off": "disabled",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"allow_all", "read_only", "custom", "disabled"}:
        return default
    return normalized


def local_app_new_actions_policy(value: str, default: str = "only_enable_new_read_actions") -> str:
    normalized = str(value or default).strip().lower().replace("-", "_")
    aliases = {
        "enable_all": "enable_all_new_actions",
        "read_only": "only_enable_new_read_actions",
        "disable": "disable_new_actions",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"enable_all_new_actions", "only_enable_new_read_actions", "disable_new_actions"}:
        return default
    return normalized


def create_or_update_local_app_action_control(payload: dict) -> dict:
    current = now()
    control_id = local_app_action_control_id(
        str(payload.get("id") or payload.get("slug") or payload.get("app_id") or payload.get("app_name") or f"action-control-{uuid.uuid4().hex[:8]}")
    )
    existing = read_local_app_action_control(control_id) or {}
    app_name = re.sub(r"\s+", " ", str(payload.get("app_name") or payload.get("name") or existing.get("app_name") or control_id)).strip()
    if not app_name:
        raise ValueError("app_name or name is required")
    constraints = payload.get("parameter_constraints")
    if not isinstance(constraints, dict):
        constraints = existing.get("parameter_constraints") if isinstance(existing.get("parameter_constraints"), dict) else {}
    control = {
        "id": control_id,
        "source": "local-app-action-control",
        "title": str(payload.get("title") or existing.get("title") or f"{app_name} local action control")[:200],
        "app_name": app_name[:160],
        "provider": str(payload.get("provider") or existing.get("provider") or "local-mcp").strip()[:120],
        "mode": local_app_action_control_mode(payload.get("mode") or payload.get("action_mode"), existing.get("mode") or "custom"),
        "allowed_actions": local_app_action_control_list(
            payload.get("allowed_actions") if "allowed_actions" in payload else existing.get("allowed_actions")
        ),
        "blocked_actions": local_app_action_control_list(
            payload.get("blocked_actions") if "blocked_actions" in payload else existing.get("blocked_actions")
        ),
        "new_actions_policy": local_app_new_actions_policy(
            payload.get("new_actions_policy") or existing.get("new_actions_policy") or "only_enable_new_read_actions"
        ),
        "parameter_constraints": constraints,
        "created_at": existing.get("created_at") or current,
        "updated_at": current,
        "url": f"{PUBLIC_BASE_URL}/local-app/action-controls/{control_id}",
        "privacy": {
            "local_only": True,
            "external_app_policy_changed": False,
            "external_workspace_policy_changed": False,
            "approval_required_for_writes": True,
            "approval_required_for_action_control_changes": True,
            "prompt_bodies_excluded": True,
        },
    }
    write_local_app_action_control(control)
    return control


def local_app_constraint_result(parameter: str, constraint: dict, parameters: dict) -> dict | None:
    if not isinstance(constraint, dict):
        return None
    value = parameters.get(parameter)
    if "required" in constraint and bool(constraint.get("required")) and parameter not in parameters:
        return {"parameter": parameter, "reason": "required", "expected": True, "actual": None}
    if parameter not in parameters:
        return None
    if "allowed_values" in constraint and isinstance(constraint.get("allowed_values"), list):
        allowed_values = [str(item) for item in constraint.get("allowed_values")]
        if str(value) not in allowed_values:
            return {"parameter": parameter, "reason": "allowed_values", "expected": allowed_values, "actual": value}
    if "regex" in constraint and str(constraint.get("regex") or ""):
        pattern = str(constraint.get("regex"))
        try:
            matched = re.search(pattern, str(value or "")) is not None
        except re.error:
            matched = False
        if not matched:
            return {"parameter": parameter, "reason": "regex", "expected": pattern, "actual": value}
    if "contains" in constraint and str(constraint.get("contains") or "") not in str(value or ""):
        return {"parameter": parameter, "reason": "contains", "expected": constraint.get("contains"), "actual": value}
    for key, predicate in (("min", lambda actual, expected: actual >= expected), ("max", lambda actual, expected: actual <= expected)):
        if key in constraint:
            try:
                actual_number = float(value)
                expected_number = float(constraint.get(key))
            except (TypeError, ValueError):
                return {"parameter": parameter, "reason": key, "expected": constraint.get(key), "actual": value}
            if not predicate(actual_number, expected_number):
                return {"parameter": parameter, "reason": key, "expected": constraint.get(key), "actual": value}
    return None


def evaluate_local_app_action_control(control_id: str, payload: dict) -> dict:
    control = read_local_app_action_control(control_id)
    if not control:
        raise FileNotFoundError(control_id)
    action_name = re.sub(r"\s+", " ", str(payload.get("action_name") or payload.get("name") or "")).strip()
    action_type = str(payload.get("action_type") or payload.get("type") or "read").strip().lower().replace("-", "_")
    if action_type not in {"read", "write", "important"}:
        action_type = "read"
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    reasons = []
    blocked_constraints = []
    mode = control.get("mode") or "custom"
    allowed_actions = set(control.get("allowed_actions") or [])
    blocked_actions = set(control.get("blocked_actions") or [])
    if not action_name:
        reasons.append({"reason": "missing_action_name"})
    if mode == "disabled":
        reasons.append({"reason": "app_disabled"})
    elif mode == "read_only" and action_type != "read":
        reasons.append({"reason": "read_only_blocks_write", "action_type": action_type})
    elif mode == "custom":
        if action_name in blocked_actions:
            reasons.append({"reason": "blocked_action", "action_name": action_name})
        elif allowed_actions and action_name not in allowed_actions:
            if action_type == "read" and control.get("new_actions_policy") == "only_enable_new_read_actions":
                pass
            elif control.get("new_actions_policy") == "enable_all_new_actions":
                pass
            else:
                reasons.append({"reason": "action_not_allowed", "action_name": action_name})
    constraints = control.get("parameter_constraints") if isinstance(control.get("parameter_constraints"), dict) else {}
    for parameter, constraint in constraints.items():
        result = local_app_constraint_result(parameter, constraint, parameters)
        if result:
            blocked_constraints.append(result)
    if blocked_constraints:
        reasons.append({"reason": "parameter_constraints", "blocked_constraints": blocked_constraints})
    allowed = not reasons
    current = now()
    return {
        "source": "local-app-action-control-evaluation",
        "control_id": control_id,
        "app_name": control.get("app_name"),
        "action_name": action_name,
        "action_type": action_type,
        "allowed": allowed,
        "blocked": not allowed,
        "mode": mode,
        "new_actions_policy": control.get("new_actions_policy"),
        "reasons": reasons,
        "blocked_constraints": blocked_constraints,
        "evaluated_at": current,
        "local_only": True,
        "external_action_executed": False,
        "privacy": {
            "local_only": True,
            "external_action_executed": False,
            "external_app_policy_changed": False,
            "prompt_bodies_excluded": True,
        },
    }


def delete_local_app_action_control(control_id: str) -> bool:
    path = local_app_action_control_path(control_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def local_app_call_log_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_app_call_log_path(log_id: str) -> Path:
    return LOCAL_APP_CALL_LOGS_DIR / f"{local_app_call_log_id(log_id)}.json"


def list_local_app_call_logs() -> list[dict]:
    logs = []
    for path in LOCAL_APP_CALL_LOGS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        logs.append(item)
    logs.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return logs


def read_local_app_call_log(log_id: str) -> dict | None:
    path = local_app_call_log_path(log_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_app_call_log(log: dict):
    local_app_call_log_path(log["id"]).write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


def create_or_update_local_app_call_log(payload: dict) -> dict:
    current = now()
    log_id = local_app_call_log_id(str(payload.get("id") or payload.get("slug") or f"app-call-{uuid.uuid4().hex[:8]}"))
    existing = read_local_app_call_log(log_id) or {}
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    action_type = str(payload.get("action_type") or existing.get("action_type") or "read").strip().lower().replace("-", "_")
    if action_type not in {"read", "write", "important"}:
        action_type = "read"
    status = str(payload.get("status") or existing.get("status") or "recorded").strip().lower()
    if status not in {"recorded", "allowed", "blocked", "completed", "failed"}:
        status = "recorded"
    evaluation = payload.get("evaluation") if isinstance(payload.get("evaluation"), dict) else existing.get("evaluation")
    log = {
        "id": log_id,
        "source": "local-app-call-log",
        "title": str(payload.get("title") or existing.get("title") or f"Local app call log {log_id}")[:200],
        "app_name": str(payload.get("app_name") or existing.get("app_name") or "local-app").strip()[:160],
        "provider": str(payload.get("provider") or existing.get("provider") or "local-mcp").strip()[:120],
        "action_name": str(payload.get("action_name") or existing.get("action_name") or "unknown_action").strip()[:180],
        "action_type": action_type,
        "status": status,
        "approval_id": str(payload.get("approval_id") or existing.get("approval_id") or "").strip()[:160],
        "control_id": str(payload.get("control_id") or existing.get("control_id") or "").strip()[:160],
        "evaluation": evaluation if isinstance(evaluation, dict) else {},
        "parameter_keys": sorted(str(key)[:120] for key in parameters.keys()),
        "parameter_count": len(parameters),
        "prompt_summary": str(payload.get("prompt_summary") or existing.get("prompt_summary") or "")[:500],
        "result_summary": str(payload.get("result_summary") or existing.get("result_summary") or "")[:500],
        "created_at": existing.get("created_at") or current,
        "updated_at": current,
        "url": f"{PUBLIC_BASE_URL}/local-app/call-logs/{log_id}",
        "privacy": {
            "local_only": True,
            "external_action_executed": False,
            "external_compliance_api_written": False,
            "hosted_compliance_api_equivalent": False,
            "prompt_body_stored": False,
            "prompt_bodies_excluded": True,
            "raw_parameter_values_stored": False,
            "parameter_keys_only": True,
            "approval_required_for_writes": True,
        },
    }
    write_local_app_call_log(log)
    return log


def delete_local_app_call_log(log_id: str) -> bool:
    path = local_app_call_log_path(log_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def local_email_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_email_path(draft_id: str) -> Path:
    return LOCAL_EMAIL_DRAFTS_DIR / f"{local_email_id(draft_id)}.json"


def local_email_address_list(value) -> list[str]:
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = re.split(r"[,;]", str(value or ""))
    addresses = []
    for item in raw_values:
        address = re.sub(r"\s+", " ", str(item or "")).strip()
        if address and address not in addresses:
            addresses.append(address[:240])
    return addresses


def list_local_email_drafts() -> list[dict]:
    drafts = []
    for path in LOCAL_EMAIL_DRAFTS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        drafts.append(item)
    drafts.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return drafts


def read_local_email_draft(draft_id: str) -> dict | None:
    path = local_email_path(draft_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_email_draft(draft: dict):
    local_email_path(draft["id"]).write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")


def create_or_update_local_email_draft(payload: dict) -> dict:
    created = now()
    draft_id = local_email_id(str(payload.get("id") or payload.get("slug") or f"email-{uuid.uuid4().hex[:8]}"))
    existing = read_local_email_draft(draft_id) or {}
    body = re.sub(r"\r\n?", "\n", str(payload.get("body") or payload.get("content") or existing.get("body") or "")).strip()
    subject = re.sub(r"\s+", " ", str(payload.get("subject") or existing.get("subject") or "")).strip()
    if not subject:
        raise ValueError("subject is required")
    if not body:
        raise ValueError("body or content is required")
    draft = {
        "id": draft_id,
        "source": "local-email-draft",
        "title": str(payload.get("title") or subject)[:200],
        "provider": str(payload.get("provider") or existing.get("provider") or "local-mailbox").strip()[:80],
        "from": str(payload.get("from") or existing.get("from") or "local-user@example.invalid").strip()[:240],
        "to": local_email_address_list(payload.get("to") if "to" in payload else existing.get("to")),
        "cc": local_email_address_list(payload.get("cc") if "cc" in payload else existing.get("cc")),
        "bcc": local_email_address_list(payload.get("bcc") if "bcc" in payload else existing.get("bcc")),
        "subject": subject[:300],
        "body": body[:20000],
        "attachments": payload.get("attachments") if isinstance(payload.get("attachments"), list) else existing.get("attachments", []),
        "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else existing.get("tags", []),
        "status": existing.get("status") if existing.get("status") == "sent" else "draft",
        "created_at": existing.get("created_at") or created,
        "updated_at": created,
        "sent_at": existing.get("sent_at"),
        "url": f"{PUBLIC_BASE_URL}/local-email/drafts/{draft_id}",
        "privacy": {
            "local_only": True,
            "external_send_performed": False,
            "approval_required_for_writes": True,
            "approval_required_for_send": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": False,
        },
    }
    if not draft["to"]:
        raise ValueError("to is required")
    write_local_email_draft(draft)
    return draft


def send_local_email_draft(draft_id: str, payload: dict | None = None) -> dict:
    draft = read_local_email_draft(draft_id)
    if not draft:
        raise FileNotFoundError(draft_id)
    current = now()
    draft["status"] = "sent"
    draft["sent_at"] = current
    draft["updated_at"] = current
    draft["send_mode"] = "local-ledger-only"
    draft["delivery_status"] = "not_delivered_external"
    draft["send_receipt"] = {
        "id": f"local-send-{uuid.uuid4().hex[:10]}",
        "created_at": current,
        "approved": True,
        "external_send_performed": False,
        "note": "Recorded as sent in the local ledger only; no Gmail, Outlook, SMTP, or external delivery was performed.",
    }
    draft["privacy"] = {
        **(draft.get("privacy") or {}),
        "local_only": True,
        "external_send_performed": False,
        "approval_required_for_send": True,
        "content_bodies_excluded": False,
    }
    write_local_email_draft(draft)
    return draft


def delete_local_email_draft(draft_id: str) -> bool:
    path = local_email_path(draft_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def local_security_session_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_security_session_path(session_id: str) -> Path:
    return LOCAL_SECURITY_SESSIONS_DIR / f"{local_security_session_id(session_id)}.json"


def local_security_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def list_local_security_sessions() -> list[dict]:
    sessions = []
    for path in LOCAL_SECURITY_SESSIONS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        sessions.append(item)
    sessions.sort(key=lambda item: item.get("updated_at") or item.get("sign_in_at") or item.get("created_at") or 0, reverse=True)
    return sessions


def read_local_security_session(session_id: str) -> dict | None:
    path = local_security_session_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_security_session(session: dict):
    local_security_session_path(session["id"]).write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")


def create_or_update_local_security_session(payload: dict) -> dict:
    current = now()
    session_id = local_security_session_id(
        str(payload.get("id") or payload.get("slug") or payload.get("session_id") or f"session-{uuid.uuid4().hex[:8]}")
    )
    existing = read_local_security_session(session_id) or {}
    status = str(payload.get("status") or existing.get("status") or "active").strip().lower()
    if status not in {"active", "revoked"}:
        status = "active"
    sign_in_at = parse_time(payload.get("sign_in_at") or payload.get("signed_in_at")) or existing.get("sign_in_at") or current
    session = {
        "id": session_id,
        "source": "local-security-session",
        "title": str(payload.get("title") or existing.get("title") or payload.get("device") or f"Local security session {session_id}")[:200],
        "app": str(payload.get("app") or existing.get("app") or "OpenWebUI").strip()[:120],
        "device": str(payload.get("device") or existing.get("device") or "local browser").strip()[:160],
        "browser": str(payload.get("browser") or existing.get("browser") or "local").strip()[:120],
        "location": str(payload.get("location") or existing.get("location") or "local network").strip()[:160],
        "trusted_device": local_security_bool(payload.get("trusted_device"), bool(existing.get("trusted_device", False))),
        "current_session": local_security_bool(payload.get("current_session"), bool(existing.get("current_session", False))),
        "sign_in_at": int(sign_in_at),
        "status": status,
        "created_at": existing.get("created_at") or current,
        "updated_at": current,
        "revoked_at": existing.get("revoked_at") if status == "revoked" else None,
        "url": f"{PUBLIC_BASE_URL}/local-security/sessions/{session_id}",
        "privacy": {
            "local_only": True,
            "real_openwebui_session_revoked": False,
            "external_identity_provider_touched": False,
            "third_party_sessions_managed": False,
            "connected_apps_managed": False,
            "approval_required_for_writes": True,
            "approval_required_for_logout": True,
            "prompt_bodies_excluded": True,
        },
    }
    write_local_security_session(session)
    return session


def logout_local_security_session(session_id: str, payload: dict | None = None) -> dict:
    session = read_local_security_session(session_id)
    if not session:
        raise FileNotFoundError(session_id)
    current = now()
    session["status"] = "revoked"
    session["revoked_at"] = current
    session["updated_at"] = current
    session["logout_mode"] = "local-ledger-only"
    session["real_openwebui_session_revoked"] = False
    session["logout_receipt"] = {
        "id": f"local-session-logout-{uuid.uuid4().hex[:10]}",
        "created_at": current,
        "approved": True,
        "local_only": True,
        "real_openwebui_session_revoked": False,
        "note": "Recorded as logged out in the local security ledger only; no browser cookie, OpenWebUI auth token, OpenAI account, or external identity provider session was revoked.",
    }
    session["privacy"] = {
        **(session.get("privacy") or {}),
        "local_only": True,
        "real_openwebui_session_revoked": False,
        "approval_required_for_logout": True,
    }
    write_local_security_session(session)
    return session


def logout_all_local_security_sessions(payload: dict | None = None) -> dict:
    sessions = list_local_security_sessions()
    revoked = []
    for session in sessions:
        if session.get("status") != "revoked":
            revoked.append(logout_local_security_session(session.get("id"), payload))
    current = now()
    return {
        "source": "local-security-session-bulk-logout",
        "status": "completed",
        "logout_mode": "local-ledger-only",
        "total_sessions": len(sessions),
        "revoked_sessions": len(revoked),
        "revoked_session_ids": [item.get("id") for item in revoked],
        "created_at": current,
        "real_openwebui_sessions_revoked": False,
        "privacy": {
            "local_only": True,
            "real_openwebui_sessions_revoked": False,
            "external_identity_provider_touched": False,
            "third_party_sessions_managed": False,
            "connected_apps_managed": False,
            "approval_required_for_logout": True,
            "prompt_bodies_excluded": True,
        },
    }


def delete_local_security_session(session_id: str) -> bool:
    path = local_security_session_path(session_id)
    if not path.exists():
        return False
    path.unlink()
    return True


PRONUNCIATION_PRESETS = {
    "en:quokka": {
        "respelling": "KWOK-uh",
        "syllables": ["kwok", "uh"],
        "tips": ["Stress the first syllable.", "Keep the final vowel short and relaxed."],
    },
    "en:archive": {
        "respelling": "AR-kive",
        "syllables": ["ar", "kive"],
        "tips": ["Stress the first syllable as a noun or general verb in common US usage."],
    },
    "en:gif": {
        "respelling": "gif or jif",
        "syllables": ["gif"],
        "tips": ["Both hard-g and soft-g pronunciations are common; choose the one your audience expects."],
    },
    "es:gracias": {
        "respelling": "GRAH-syahs",
        "syllables": ["grah", "syahs"],
        "tips": ["Keep the first vowel open.", "Let the final syllable glide lightly."],
    },
    "fr:croissant": {
        "respelling": "krwah-SAHN",
        "syllables": ["krwah", "sahn"],
        "tips": ["Stress the final syllable lightly.", "The final consonant is usually not pronounced in isolation."],
    },
}


def local_pronunciation_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_pronunciation_path(guide_id: str) -> Path:
    return LOCAL_PRONUNCIATION_DIR / f"{local_pronunciation_id(guide_id)}.json"


def local_pronunciation_audio_path(guide_id: str) -> Path:
    return LOCAL_PRONUNCIATION_DIR / f"{local_pronunciation_id(guide_id)}.wav"


def read_local_pronunciation(guide_id: str) -> dict | None:
    path = local_pronunciation_path(guide_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_pronunciation(guide: dict):
    local_pronunciation_path(guide["id"]).write_text(json.dumps(guide, indent=2, ensure_ascii=False), encoding="utf-8")


def list_local_pronunciations() -> list[dict]:
    guides = []
    for path in LOCAL_PRONUNCIATION_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        guides.append(item)
    guides.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return guides


def delete_local_pronunciation(guide_id: str) -> bool:
    metadata_path = local_pronunciation_path(guide_id)
    audio_path = local_pronunciation_audio_path(guide_id)
    existed = False
    if metadata_path.exists():
        metadata_path.unlink()
        existed = True
    if audio_path.exists():
        audio_path.unlink()
        existed = True
    return existed


def normalize_pronunciation_word(value: str) -> str:
    word = re.sub(r"\s+", " ", str(value or "")).strip()
    if not word:
        raise ValueError("word is required")
    return word[:120]


def pronunciation_ascii_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def basic_pronunciation_syllables(word: str) -> list[str]:
    normalized = word.lower()
    ascii_word = normalized.encode("ascii", errors="ignore").decode("ascii")
    ascii_word = re.sub(r"[^a-z]+", "", ascii_word)
    if not ascii_word:
        return [word[:24]]
    groups = re.findall(r"[^aeiouy]*[aeiouy]+(?:[^aeiouy](?=[^aeiouy]*[aeiouy])|[^aeiouy]*)?", ascii_word)
    groups = [group.strip() for group in groups if group.strip()]
    if groups:
        return groups[:8]
    return [ascii_word[:24]]


def pronunciation_guide_text(word: str, language: str) -> dict:
    language = re.sub(r"[^A-Za-z0-9_-]", "", str(language or "en").strip()[:24]) or "en"
    preset = PRONUNCIATION_PRESETS.get(f"{language.lower()}:{word.lower()}") or PRONUNCIATION_PRESETS.get(
        f"{language[:2].lower()}:{word.lower()}"
    )
    if preset:
        syllables = list(preset["syllables"])
        respelling = str(preset["respelling"])
        tips = list(preset["tips"])
        method = "local-preset"
    else:
        syllables = basic_pronunciation_syllables(word)
        respelling = "-".join(syllables).upper()
        tips = [
            "Say each syllable separately, then blend them at normal speed.",
            "Ask for a specific dialect or language if you need a more precise guide.",
        ]
        method = "local-heuristic"

    return {
        "language": language,
        "word": word,
        "respelling": respelling,
        "syllables": syllables,
        "stress": "first syllable" if len(syllables) > 1 else "single syllable",
        "tips": tips,
        "method": method,
    }


def build_pronunciation_wav(syllables: list[str]) -> tuple[bytes, float]:
    sample_rate = 16000
    frames = bytearray()

    def append_tone(frequency: float, seconds: float, amplitude: int):
        total = int(sample_rate * seconds)
        for idx in range(total):
            value = int(amplitude * math.sin(2 * math.pi * frequency * (idx / sample_rate)))
            frames.extend(struct.pack("<h", value))

    def append_silence(seconds: float):
        frames.extend(b"\x00\x00" * int(sample_rate * seconds))

    clean_syllables = [str(item or "").strip() for item in syllables if str(item or "").strip()] or ["word"]
    for index, syllable in enumerate(clean_syllables[:8]):
        seed = sum(ord(char) for char in syllable)
        frequency = 360 + (seed % 420)
        append_tone(frequency, 0.24 if index == 0 else 0.18, 8500 if index == 0 else 6500)
        append_silence(0.08)
    append_tone(880, 0.08, 5000)
    append_silence(0.05)

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(frames))
    duration = len(frames) / 2 / sample_rate
    return wav_buffer.getvalue(), round(duration, 3)


def create_local_pronunciation(payload: dict) -> dict:
    created = now()
    word = normalize_pronunciation_word(payload.get("word") or payload.get("text"))
    language = str(payload.get("language") or "en").strip()[:24] or "en"
    guide_id = local_pronunciation_id(str(payload.get("id") or f"{language}-{pronunciation_ascii_key(word)}-{uuid.uuid4().hex[:8]}"))
    guide_text = pronunciation_guide_text(word, language)
    wav_bytes, duration = build_pronunciation_wav(guide_text["syllables"])
    local_pronunciation_audio_path(guide_id).write_bytes(wav_bytes)
    guide = {
        "id": guide_id,
        "source": "local-pronunciation-guide",
        "title": str(payload.get("title") or f"Pronunciation guide: {word}")[:200],
        "word": word,
        "language": guide_text["language"],
        "respelling": guide_text["respelling"],
        "syllables": guide_text["syllables"],
        "stress": guide_text["stress"],
        "tips": guide_text["tips"],
        "method": guide_text["method"],
        "created_at": created,
        "updated_at": created,
        "url": f"{PUBLIC_BASE_URL}/local-pronunciation/guides/{guide_id}",
        "audio": {
            "url": f"{PUBLIC_BASE_URL}/local-pronunciation/audio/{guide_id}.wav",
            "mime_type": "audio/wav",
            "duration_seconds": duration,
            "generator": "python-stdlib-local-tone-fallback",
            "natural_speech_tts": False,
        },
        "privacy": {
            "local_only": True,
            "no_cloud_tts": True,
            "prompt_bodies_excluded": True,
        },
    }
    write_local_pronunciation(guide)
    return guide


LOCAL_SCHEDULER_SEARXNG_URL = os.environ.get("LOCAL_SCHEDULER_SEARXNG_URL", "http://127.0.0.1:18080").rstrip("/")
LOCAL_SPORTS_SEARCH_TIMEOUT_SECONDS = float(os.environ.get("LOCAL_SCHEDULER_SPORTS_SEARCH_TIMEOUT_SECONDS", "5"))
LOCAL_SPORTS_SEARCH_TOTAL_SECONDS = float(os.environ.get("LOCAL_SCHEDULER_SPORTS_SEARCH_TOTAL_SECONDS", "18"))
LOCAL_SPORTS_SEARCH_MAX_QUERIES = int(os.environ.get("LOCAL_SCHEDULER_SPORTS_SEARCH_MAX_QUERIES", "4"))


def local_sports_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_sports_path(briefing_id: str) -> Path:
    return LOCAL_SPORTS_DIR / f"{local_sports_id(briefing_id)}.json"


def read_local_sports_briefing(briefing_id: str) -> dict | None:
    path = local_sports_path(briefing_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_sports_briefing(briefing: dict):
    local_sports_path(briefing["id"]).write_text(json.dumps(briefing, indent=2, ensure_ascii=False), encoding="utf-8")


def list_local_sports_briefings() -> list[dict]:
    briefings = []
    for path in LOCAL_SPORTS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        briefings.append(item)
    briefings.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return briefings


def delete_local_sports_briefing(briefing_id: str) -> bool:
    path = local_sports_path(briefing_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def sports_search_queries(query: str, topic: str, competition: str) -> list[str]:
    candidates: list[str] = []

    def add(value: str):
        value = re.sub(r"\s+", " ", value or "").strip()
        if value and value.lower() not in {item.lower() for item in candidates}:
            candidates.append(value)

    add(query)
    add(topic)
    if competition:
        add(f"{competition} schedule")
        add(competition)

    publisher_stripped = re.sub(
        r"\b(espn|fox sports|cbs sports|nbc sports|bbc sport|sky sports|the athletic)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    publisher_stripped = re.sub(r"\s+", " ", publisher_stripped).strip()
    add(publisher_stripped)

    schedule_stripped = re.sub(r"\b(schedule|fixtures?|results?|standings?)\b", " ", publisher_stripped, flags=re.IGNORECASE)
    schedule_stripped = re.sub(r"\s+", " ", schedule_stripped).strip()
    add(schedule_stripped)

    combined = f"{query} {topic} {competition}".lower()
    if "world cup" in combined or "fifa" in combined:
        add("2026 FIFA World Cup")
        add("FIFA World Cup 2026")
        add("FIFA World Cup 2026 schedule")

    return candidates


def local_sports_curated_sources(query: str, topic: str, competition: str, limit: int) -> list[dict]:
    combined = f"{query} {topic} {competition}".lower()
    if "world cup" not in combined and "fifa" not in combined:
        return []
    candidates = [
        {
            "title": "FIFA World Cup 2026 - official tournament hub",
            "url": "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026",
            "snippet": "Official FIFA tournament hub for the 2026 FIFA World Cup. Use it to verify tournament, schedule, team, venue, and update details.",
            "engine": "local-curated-fallback",
            "score": None,
        },
        {
            "title": "2026 FIFA World Cup schedule - ESPN",
            "url": "https://www.espn.com/soccer/schedule/_/league/fifa.world",
            "snippet": "ESPN schedule page for FIFA World Cup fixtures and match timing. Verify live schedule details before presenting them as current.",
            "engine": "local-curated-fallback",
            "score": None,
        },
        {
            "title": "2026 FIFA World Cup - tournament overview",
            "url": "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup",
            "snippet": "Tournament overview with format, host, and qualification context. Use primary sources for final schedule and live changes.",
            "engine": "local-curated-fallback",
            "score": None,
        },
    ]
    return candidates[: max(1, min(limit, len(candidates)))]


def searxng_sports_search(query: str, limit: int, timeout_seconds: float | None = None) -> list[dict]:
    params = parse.urlencode({"q": query, "format": "json"})
    req = request.Request(
        f"{LOCAL_SCHEDULER_SEARXNG_URL}/search?{params}",
        headers={"User-Agent": "openwebui-local-sports-briefing/0.1"},
    )
    timeout = max(1.0, timeout_seconds or LOCAL_SPORTS_SEARCH_TIMEOUT_SECONDS)
    with request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8") or "{}")
    results = data.get("results") if isinstance(data, dict) else []
    sources = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "").strip()
        title = str(item.get("title") or item.get("name") or "").strip()
        snippet = re.sub(r"\s+", " ", str(item.get("content") or item.get("snippet") or "")).strip()
        if not url.startswith(("http://", "https://")) or not title:
            continue
        sources.append(
            {
                "title": title[:240],
                "url": url,
                "snippet": snippet[:700],
                "engine": item.get("engine"),
                "score": item.get("score"),
            }
        )
        if len(sources) >= limit:
            break
    return sources


def create_local_sports_briefing(payload: dict) -> dict:
    created = now()
    topic = re.sub(r"\s+", " ", str(payload.get("topic") or payload.get("query") or "")).strip()
    if not topic:
        raise ValueError("topic or query is required")
    sport = re.sub(r"\s+", " ", str(payload.get("sport") or "football/soccer")).strip()[:80]
    competition = re.sub(r"\s+", " ", str(payload.get("competition") or "")).strip()[:120]
    query = re.sub(r"\s+", " ", str(payload.get("query") or topic)).strip()
    if competition and competition.lower() not in query.lower():
        query = f"{competition} {query}"
    max_sources = max(1, min(12, int(payload.get("max_sources") or 5)))
    briefing_id = local_sports_id(str(payload.get("id") or f"sports-{uuid.uuid4().hex[:8]}"))
    attempted_queries = sports_search_queries(query, topic, competition)
    search_errors = []
    source_query = None
    source_mode = "local-searxng"
    sources = []
    search_deadline = time.monotonic() + max(1.0, LOCAL_SPORTS_SEARCH_TOTAL_SECONDS)
    search_candidates = attempted_queries[: max(1, LOCAL_SPORTS_SEARCH_MAX_QUERIES)]
    for candidate_query in search_candidates:
        remaining_seconds = search_deadline - time.monotonic()
        if remaining_seconds <= 0:
            search_errors.append(
                f"search budget exhausted after {LOCAL_SPORTS_SEARCH_TOTAL_SECONDS:.1f}s before {candidate_query}"
            )
            break
        try:
            sources = searxng_sports_search(
                candidate_query,
                max_sources,
                timeout_seconds=min(LOCAL_SPORTS_SEARCH_TIMEOUT_SECONDS, remaining_seconds),
            )
        except Exception as exc:
            search_errors.append(f"{candidate_query}: {exc}")
            continue
        if sources:
            source_query = candidate_query
            break
    if not sources:
        sources = local_sports_curated_sources(query, topic, competition, max_sources)
        source_mode = (
            "local-curated-fallback-after-searxng-error-or-timeout"
            if search_errors
            else "local-curated-fallback-after-empty-searxng"
        )
    if not sources:
        attempted = "; ".join(attempted_queries[:6])
        raise RuntimeError(f"local SearXNG returned no sports sources for query variants: {attempted}")
    source_lines = [f"{idx + 1}. {item['title']} - {item['url']}" for idx, item in enumerate(sources[:5])]
    snippet_lines = [item.get("snippet") for item in sources if item.get("snippet")]
    briefing = {
        "id": briefing_id,
        "source": "local-sports-briefing",
        "title": str(payload.get("title") or f"Sports briefing: {topic}")[:200],
        "topic": topic[:240],
        "sport": sport,
        "competition": competition,
        "query": query[:300],
        "resolved_query": (source_query or attempted_queries[0] if attempted_queries else query)[:300],
        "source_mode": source_mode,
        "attempted_queries": attempted_queries[:8],
        "search_errors": search_errors[:5],
        "created_at": created,
        "updated_at": created,
        "url": f"{PUBLIC_BASE_URL}/local-sports/briefings/{briefing_id}",
        "summary": (
            "Local sports/current-event source pack. Use the sources below for schedules, matchups, teams, "
            "players, storylines, and outcome scenarios; verify time-sensitive details on the source sites."
        ),
        "source_highlights": snippet_lines[:5],
        "sources": sources,
        "conversation_starters": [
            f"What is the latest schedule context for {topic}?",
            f"Which matchups or teams should I watch for in {topic}?",
            f"What outcome scenarios matter for {topic}?",
        ],
        "citation_block": "\n".join(source_lines),
        "privacy": {
            "local_only": True,
            "uses_local_searxng": True,
            "searxng_url": LOCAL_SCHEDULER_SEARXNG_URL,
            "source_mode": source_mode,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": False,
        },
    }
    write_local_sports_briefing(briefing)
    return briefing


def local_site_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_site_dir(site_id: str) -> Path:
    return LOCAL_SITES_DIR / local_site_id(site_id)


def local_site_metadata_path(site_id: str) -> Path:
    return local_site_dir(site_id) / "site.json"


def local_site_index_path(site_id: str) -> Path:
    return local_site_dir(site_id) / "index.html"


def normalize_site_html(payload: dict) -> str:
    html = str(payload.get("html") or payload.get("content") or "").strip()
    if not html:
        raise ValueError("html is required")
    if not re.search(r"<html[\s>]", html, flags=re.IGNORECASE):
        title = html_escape(str(payload.get("title") or "Local site").strip()[:200])
        html = (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"  <title>{title}</title>\n"
            "</head>\n"
            f"<body>\n{html}\n</body>\n"
            "</html>\n"
        )
    return html


def list_local_sites() -> list[dict]:
    sites = []
    for path in LOCAL_SITES_DIR.glob("*/site.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        sites.append(item)
    sites.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return sites


def read_local_site(site_id: str) -> dict | None:
    path = local_site_metadata_path(site_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def create_or_update_local_site(payload: dict) -> dict:
    created = now()
    site_id = local_site_id(str(payload.get("id") or payload.get("slug") or uuid.uuid4()))
    existing = read_local_site(site_id) or {}
    title = str(payload.get("title") or existing.get("title") or "Local site").strip()[:200]
    description = str(payload.get("description") or existing.get("description") or "").strip()[:800]
    html = normalize_site_html(payload)
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else existing.get("tags", [])
    tags = [str(tag).strip()[:80] for tag in tags if str(tag).strip()][:12]
    site_path = local_site_dir(site_id)
    site_path.mkdir(parents=True, exist_ok=True)
    (site_path / "index.html").write_text(html, encoding="utf-8")
    site = {
        "id": site_id,
        "title": title,
        "description": description,
        "tags": tags,
        "source": "local-site",
        "created_at": int(existing.get("created_at") or created),
        "updated_at": created,
        "url": f"{PUBLIC_BASE_URL}/local-sites/{site_id}/index.html",
        "metadata_url": f"{PUBLIC_BASE_URL}/local-sites/{site_id}",
        "bytes": len(html.encode("utf-8")),
    }
    local_site_metadata_path(site_id).write_text(json.dumps(site, indent=2, ensure_ascii=False), encoding="utf-8")
    return site


def delete_local_site(site_id: str) -> bool:
    path = local_site_dir(site_id)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def local_sheet_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_sheet_path(workbook_id: str) -> Path:
    return LOCAL_SHEETS_DIR / f"{local_sheet_id(workbook_id)}.json"


def normalize_cell(value):
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)


def normalize_rows(rows) -> list[list]:
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows[:2000]:
        if isinstance(row, dict):
            cells = list(row.values())
        elif isinstance(row, list):
            cells = row
        else:
            cells = [row]
        normalized.append([normalize_cell(cell) for cell in cells[:100]])
    return normalized


def normalize_sheets(payload: dict, existing: dict | None = None) -> list[dict]:
    existing = existing or {}
    raw_sheets = payload.get("sheets")
    sheets = []

    if isinstance(raw_sheets, dict):
        for name, value in raw_sheets.items():
            if isinstance(value, dict):
                rows = value.get("rows")
            else:
                rows = value
            sheets.append({"name": str(name or "Sheet1").strip()[:120] or "Sheet1", "rows": normalize_rows(rows)})
    elif isinstance(raw_sheets, list):
        for idx, item in enumerate(raw_sheets):
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("title") or f"Sheet{idx + 1}").strip()[:120] or f"Sheet{idx + 1}"
                rows = normalize_rows(item.get("rows"))
            else:
                name = f"Sheet{idx + 1}"
                rows = normalize_rows(item)
            sheets.append({"name": name, "rows": rows})
    elif "rows" in payload:
        name = str(payload.get("sheet_name") or "Sheet1").strip()[:120] or "Sheet1"
        sheets.append({"name": name, "rows": normalize_rows(payload.get("rows"))})
    else:
        sheets = deepcopy(existing.get("sheets") or [])

    if not sheets:
        raise ValueError("sheets or rows are required")

    seen = set()
    normalized = []
    for sheet in sheets[:20]:
        base_name = str(sheet.get("name") or "Sheet").strip()[:120] or "Sheet"
        name = base_name
        suffix = 2
        while name.lower() in seen:
            name = f"{base_name[:110]} {suffix}"
            suffix += 1
        seen.add(name.lower())
        rows = normalize_rows(sheet.get("rows"))
        max_cols = max((len(row) for row in rows), default=0)
        normalized.append({"name": name, "rows": rows, "row_count": len(rows), "column_count": max_cols})
    return normalized


def read_local_sheet(workbook_id: str) -> dict | None:
    path = local_sheet_path(workbook_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_sheet(workbook: dict):
    local_sheet_path(workbook["id"]).write_text(json.dumps(workbook, indent=2, ensure_ascii=False), encoding="utf-8")


def list_local_sheets() -> list[dict]:
    workbooks = []
    for path in LOCAL_SHEETS_DIR.glob("*.json"):
        try:
            workbook = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        summary = dict(workbook)
        summary["sheets"] = [
            {
                "name": sheet.get("name"),
                "row_count": sheet.get("row_count", len(sheet.get("rows") or [])),
                "column_count": sheet.get("column_count", max((len(row) for row in sheet.get("rows") or []), default=0)),
            }
            for sheet in workbook.get("sheets") or []
        ]
        workbooks.append(summary)
    workbooks.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return workbooks


def create_or_update_local_sheet(payload: dict) -> dict:
    created = now()
    workbook_id = local_sheet_id(str(payload.get("id") or payload.get("slug") or uuid.uuid4()))
    existing = read_local_sheet(workbook_id) or {}
    title = str(payload.get("title") or existing.get("title") or "Local spreadsheet").strip()[:200]
    description = str(payload.get("description") or existing.get("description") or "").strip()[:800]
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else existing.get("tags", [])
    tags = [str(tag).strip()[:80] for tag in tags if str(tag).strip()][:12]
    workbook = {
        "id": workbook_id,
        "title": title,
        "description": description,
        "tags": tags,
        "source": "local-sheet",
        "sheets": normalize_sheets(payload, existing),
        "created_at": int(existing.get("created_at") or created),
        "updated_at": created,
        "url": f"{PUBLIC_BASE_URL}/local-sheets/{workbook_id}",
    }
    write_local_sheet(workbook)
    return workbook


def find_sheet(workbook: dict, sheet_name: str | None = None) -> dict:
    sheets = workbook.get("sheets") or []
    if not sheets:
        raise ValueError("workbook has no sheets")
    if not sheet_name:
        return sheets[0]
    needle = str(sheet_name).strip().lower()
    for sheet in sheets:
        if str(sheet.get("name") or "").strip().lower() == needle:
            return sheet
    raise KeyError("sheet not found")


def column_index(value) -> int:
    if isinstance(value, int):
        return max(0, value - 1)
    text = str(value or "").strip().upper()
    if text.isdigit():
        return max(0, int(text) - 1)
    if not re.fullmatch(r"[A-Z]+", text):
        raise ValueError(f"invalid column {value!r}")
    idx = 0
    for char in text:
        idx = idx * 26 + (ord(char) - ord("A") + 1)
    return idx - 1


def cell_position(update: dict) -> tuple[int, int]:
    cell = str(update.get("cell") or "").strip().upper()
    if cell:
        match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", cell)
        if not match:
            raise ValueError(f"invalid cell {cell!r}")
        return int(match.group(2)) - 1, column_index(match.group(1))
    row = update.get("row")
    column = update.get("column", update.get("col"))
    if row in (None, "") or column in (None, ""):
        raise ValueError("each update needs either cell or row and column")
    return max(0, int(row) - 1), column_index(column)


def update_local_sheet_cells(workbook_id: str, payload: dict) -> dict:
    workbook = read_local_sheet(workbook_id)
    if not workbook:
        raise KeyError("workbook not found")
    sheet = find_sheet(workbook, payload.get("sheet") or payload.get("sheet_name"))
    rows = sheet.setdefault("rows", [])
    updates = payload.get("updates")
    if not isinstance(updates, list):
        updates = [
            {
                "cell": payload.get("cell"),
                "row": payload.get("row"),
                "column": payload.get("column", payload.get("col")),
                "value": payload.get("value"),
            }
        ]
    changed = []
    for item in updates[:250]:
        if not isinstance(item, dict):
            continue
        row_idx, col_idx = cell_position(item)
        while len(rows) <= row_idx:
            rows.append([])
        while len(rows[row_idx]) <= col_idx:
            rows[row_idx].append("")
        rows[row_idx][col_idx] = normalize_cell(item.get("value"))
        changed.append({"row": row_idx + 1, "column": col_idx + 1, "value": rows[row_idx][col_idx]})
    sheet["row_count"] = len(rows)
    sheet["column_count"] = max((len(row) for row in rows), default=0)
    workbook["updated_at"] = now()
    write_local_sheet(workbook)
    return {"workbook": workbook, "updated_cells": changed, "updated_count": len(changed)}


def local_sheet_explanation(workbook: dict, question: str = "") -> dict:
    terms = [term for term in re.split(r"\s+", (question or "").lower()) if len(term) > 2]
    sheet_summaries = []
    matches = []
    for sheet in workbook.get("sheets") or []:
        rows = sheet.get("rows") or []
        row_count = len(rows)
        column_count = max((len(row) for row in rows), default=0)
        headers = [str(cell) for cell in rows[0][:column_count]] if rows else []
        numeric_totals = {}
        for col_idx in range(column_count):
            values = []
            for row in rows[1:]:
                if col_idx >= len(row):
                    continue
                try:
                    values.append(float(str(row[col_idx]).replace(",", "")))
                except ValueError:
                    continue
            if values:
                label = headers[col_idx] if col_idx < len(headers) and headers[col_idx] else f"Column {col_idx + 1}"
                numeric_totals[label] = {"sum": round(sum(values), 4), "count": len(values)}
        for row_idx, row in enumerate(rows, 1):
            row_text = " | ".join(str(cell) for cell in row)
            haystack = row_text.lower()
            if terms and all(term in haystack for term in terms):
                matches.append({"sheet": sheet.get("name"), "row": row_idx, "text": row_text[:320]})
        sheet_summaries.append(
            {
                "name": sheet.get("name"),
                "row_count": row_count,
                "column_count": column_count,
                "headers": headers[:25],
                "numeric_totals": numeric_totals,
            }
        )
    summary = (
        f"{workbook.get('title') or 'Workbook'} has {len(sheet_summaries)} sheet(s): "
        + ", ".join(f"{item['name']} ({item['row_count']}x{item['column_count']})" for item in sheet_summaries)
    )
    return {
        "id": workbook.get("id"),
        "title": workbook.get("title"),
        "summary": summary,
        "question": question,
        "sheets": sheet_summaries,
        "matches": matches[:20],
        "actions": ["explain", "clean", "update_cells", "export_json"],
        "privacy": {"local_only": True, "approval_required_for_writes": True},
    }


def delete_local_sheet(workbook_id: str) -> bool:
    path = local_sheet_path(workbook_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def local_code_workspace_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip(".-")
    return safe_id[:120] or str(uuid.uuid4())


def local_code_workspace_path(workspace_id: str) -> Path:
    return LOCAL_CODE_WORKSPACES_DIR / f"{local_code_workspace_id(workspace_id)}.json"


def local_code_run_path(run_id: str) -> Path:
    return LOCAL_CODE_RUNS_DIR / local_code_workspace_id(run_id)


def local_code_git_worktree_path(worktree_id: str) -> Path:
    return LOCAL_CODE_GIT_WORKTREES_DIR / local_code_workspace_id(worktree_id)


def local_code_git_worktree_metadata_path(worktree_id: str) -> Path:
    return local_code_git_worktree_path(worktree_id) / ".openwebui" / "metadata.json"


def normalize_code_path(value: str) -> str:
    path = str(value or "").replace("\\", "/").strip()
    if not path or path.startswith("/") or "\x00" in path:
        raise ValueError("file path must be relative")
    parts = [part for part in path.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("file path must stay inside the workspace")
    if any(part in {".git", ".hg", ".svn"} for part in parts):
        raise ValueError("repository metadata paths are not allowed")
    normalized = "/".join(parts)
    if len(normalized) > 240:
        raise ValueError("file path is too long")
    return normalized


def safe_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def language_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".html": "html",
        ".css": "css",
        ".sh": "shell",
    }.get(suffix, suffix.lstrip(".") or "text")


def normalize_code_files(payload: dict, existing: dict | None = None) -> list[dict]:
    existing = existing or {}
    raw_files = payload.get("files")
    if raw_files is None:
        raw_files = existing.get("files") or []

    normalized = []
    if isinstance(raw_files, dict):
        iterable = [{"path": path, "content": content} for path, content in raw_files.items()]
    elif isinstance(raw_files, list):
        iterable = raw_files
    else:
        raise ValueError("files must be an object or list")

    seen = set()
    for item in iterable[:300]:
        if isinstance(item, dict):
            file_path = normalize_code_path(item.get("path") or item.get("name"))
            content = str(item.get("content") if item.get("content") is not None else "")
            language = str(item.get("language") or language_for_path(file_path)).strip()[:80]
        else:
            raise ValueError("each file must be an object")
        if file_path in seen:
            continue
        if len(content.encode("utf-8")) > 1_000_000:
            raise ValueError(f"{file_path} exceeds 1 MiB")
        seen.add(file_path)
        normalized.append(
            {
                "path": file_path,
                "content": content,
                "language": language or language_for_path(file_path),
                "bytes": len(content.encode("utf-8")),
                "updated_at": now(),
            }
        )

    if not normalized:
        raise ValueError("at least one file is required")
    return normalized


def read_local_code_workspace(workspace_id: str) -> dict | None:
    path = local_code_workspace_path(workspace_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_code_workspace(workspace: dict):
    local_code_workspace_path(workspace["id"]).write_text(json.dumps(workspace, indent=2, ensure_ascii=False), encoding="utf-8")


def local_code_workspace_summary(workspace: dict) -> dict:
    files = workspace.get("files") or []
    return {
        "id": workspace.get("id"),
        "title": workspace.get("title"),
        "description": workspace.get("description"),
        "tags": workspace.get("tags") or [],
        "source": "local-code-workspace",
        "created_at": workspace.get("created_at"),
        "updated_at": workspace.get("updated_at"),
        "url": workspace.get("url"),
        "file_count": len(files),
        "files": [
            {
                "path": item.get("path"),
                "language": item.get("language"),
                "bytes": item.get("bytes", len(str(item.get("content") or "").encode("utf-8"))),
            }
            for item in files
        ],
        "last_diff": workspace.get("last_diff", ""),
        "last_check": workspace.get("last_check"),
    }


def list_local_code_workspaces() -> list[dict]:
    workspaces = []
    for path in LOCAL_CODE_WORKSPACES_DIR.glob("*.json"):
        try:
            workspace = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        workspaces.append(local_code_workspace_summary(workspace))
    workspaces.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return workspaces


def create_or_update_local_code_workspace(payload: dict) -> dict:
    created = now()
    workspace_id = local_code_workspace_id(str(payload.get("id") or payload.get("slug") or uuid.uuid4()))
    existing = read_local_code_workspace(workspace_id) or {}
    title = str(payload.get("title") or existing.get("title") or "Local code workspace").strip()[:200]
    description = str(payload.get("description") or existing.get("description") or "").strip()[:800]
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else existing.get("tags", [])
    tags = [str(tag).strip()[:80] for tag in tags if str(tag).strip()][:12]
    workspace = {
        "id": workspace_id,
        "title": title,
        "description": description,
        "tags": tags,
        "source": "local-code-workspace",
        "files": normalize_code_files(payload, existing),
        "history": existing.get("history") if isinstance(existing.get("history"), list) else [],
        "created_at": int(existing.get("created_at") or created),
        "updated_at": created,
        "url": f"{PUBLIC_BASE_URL}/local-code/workspaces/{workspace_id}",
    }
    if existing.get("last_diff"):
        workspace["last_diff"] = existing.get("last_diff")
    if existing.get("last_check"):
        workspace["last_check"] = existing.get("last_check")
    write_local_code_workspace(workspace)
    return workspace


def git_patch_from_unified_diff(diff_text: str) -> str:
    diff_text = str(diff_text or "").strip()
    if not diff_text:
        return ""
    chunks = []
    for chunk in re.split(r"(?m)(?=^--- a/)", diff_text):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.search(r"(?m)^--- a/(.+)\n\+\+\+ b/(.+)$", chunk)
        if match:
            chunks.append(f"diff --git a/{match.group(1)} b/{match.group(2)}\n{chunk}")
        else:
            chunks.append(chunk)
    return "\n\n".join(chunks) + "\n"


def export_local_code_workspace_package(workspace_id: str, payload: dict) -> dict:
    workspace = read_local_code_workspace(workspace_id)
    if not workspace:
        raise KeyError("workspace not found")
    include_history = bool(payload.get("include_history"))
    include_command_output = bool(payload.get("include_command_output"))
    files = [
        {
            "path": item.get("path"),
            "language": item.get("language") or language_for_path(item.get("path") or ""),
            "content": str(item.get("content") or ""),
            "bytes": item.get("bytes", len(str(item.get("content") or "").encode("utf-8"))),
        }
        for item in workspace.get("files") or []
        if isinstance(item, dict)
    ]
    last_diff = str(workspace.get("last_diff") or "")
    patch_text = git_patch_from_unified_diff(last_diff)
    package = {
        "schema_version": "openwebui.local_code_workspace.v1",
        "source": "local-code-workspace-export",
        "exported_at": now(),
        "workspace": {
            "id": workspace.get("id"),
            "title": workspace.get("title"),
            "description": workspace.get("description"),
            "tags": workspace.get("tags") or [],
            "files": files,
            "last_diff": last_diff,
            "last_check": workspace.get("last_check"),
            "last_command": workspace.get("last_command") if include_command_output else None,
            "history": workspace.get("history") if include_history else [],
        },
        "git_patch_bundle": {
            "filename": f"{workspace.get('id') or workspace_id}.patch",
            "format": "git-unified-diff",
            "ready": bool(patch_text.strip()),
            "patch": patch_text,
            "apply_hint": "git apply <patch-file>",
            "privacy": {"local_only": True, "cloud_publish_performed": False},
        },
        "privacy": {
            "local_only": True,
            "host_path_imported": False,
            "cloud_publish_performed": False,
        },
    }
    return package


def import_local_code_workspace_package(payload: dict) -> dict:
    package = payload.get("package") if isinstance(payload.get("package"), dict) else payload
    source_workspace = package.get("workspace") if isinstance(package.get("workspace"), dict) else package
    source_id = str(source_workspace.get("id") or package.get("id") or "imported").strip()
    explicit_id = payload.get("id")
    if explicit_id:
        workspace_id = local_code_workspace_id(str(explicit_id))
        if read_local_code_workspace(workspace_id):
            raise ValueError("import target id already exists; imports are additive by default")
    else:
        workspace_id = local_code_workspace_id(f"{source_id}-import-{uuid.uuid4().hex[:8]}")
    title = str(payload.get("title") or source_workspace.get("title") or "Imported local code workspace").strip()[:200]
    if not payload.get("title") and source_workspace.get("title"):
        title = f"{title} (imported)"[:200]
    description = str(
        payload.get("description") or source_workspace.get("description") or "Imported from a local code workspace package."
    ).strip()[:800]
    tags = payload.get("tags")
    if not isinstance(tags, list):
        tags = list(source_workspace.get("tags") or [])
    tags = [str(tag).strip()[:80] for tag in tags if str(tag).strip()][:10]
    if "imported" not in tags:
        tags.append("imported")
    created = now()
    workspace_payload = {
        "id": workspace_id,
        "title": title,
        "description": description,
        "tags": tags,
        "files": source_workspace.get("files") or package.get("files") or [],
    }
    workspace = {
        "id": workspace_id,
        "title": title,
        "description": description,
        "tags": tags,
        "source": "local-code-workspace",
        "files": normalize_code_files(workspace_payload),
        "history": [
            {
                "id": str(uuid.uuid4()),
                "action": "import_package",
                "summary": "Imported local code workspace package",
                "source_workspace_id": source_id,
                "created_at": created,
            }
        ],
        "created_at": created,
        "updated_at": created,
        "url": f"{PUBLIC_BASE_URL}/local-code/workspaces/{workspace_id}",
        "import": {
            "source": package.get("source") or "local-code-workspace-export",
            "source_workspace_id": source_id,
            "schema_version": package.get("schema_version"),
            "imported_at": created,
            "additive": True,
        },
    }
    if isinstance(package.get("git_patch_bundle"), dict):
        workspace["import"]["git_patch_bundle_ready"] = bool(package["git_patch_bundle"].get("ready"))
    write_local_code_workspace(workspace)
    return workspace


def run_git(args: list[str], cwd: Path, *, check: bool = True, timeout: int = 30) -> dict:
    git_path = shutil.which("git")
    if not git_path:
        raise ValueError("git is not installed in the local scheduler container")
    completed = subprocess.run(
        [git_path, *args],
        cwd=cwd,
        env={
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(cwd),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
        },
        text=True,
        capture_output=True,
        timeout=timeout,
        shell=False,
    )
    result = {
        "command": ["git", *args],
        "returncode": completed.returncode,
        "stdout": safe_text(completed.stdout)[:12000],
        "stderr": safe_text(completed.stderr)[:12000],
    }
    if check and completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result['stderr'] or result['stdout']}")
    return result


def read_local_code_git_worktree(worktree_id: str) -> dict | None:
    metadata_path = local_code_git_worktree_metadata_path(worktree_id)
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def list_local_code_git_worktrees() -> list[dict]:
    worktrees = []
    for path in LOCAL_CODE_GIT_WORKTREES_DIR.iterdir():
        if not path.is_dir():
            continue
        metadata = read_local_code_git_worktree(path.name)
        if metadata:
            worktrees.append(metadata)
    worktrees.sort(key=lambda item: item.get("created_at") or 0, reverse=True)
    return worktrees


def create_local_code_git_worktree(workspace_id: str, payload: dict) -> dict:
    workspace = read_local_code_workspace(workspace_id)
    if not workspace:
        raise KeyError("workspace not found")
    worktree_id = local_code_workspace_id(str(payload.get("id") or f"{workspace_id}-git-{uuid.uuid4().hex[:8]}"))
    worktree_dir = local_code_git_worktree_path(worktree_id)
    if worktree_dir.exists():
        raise ValueError("git worktree id already exists")
    branch = local_code_workspace_id(str(payload.get("branch") or "local-workspace"))[:80] or "local-workspace"
    created = now()
    patch_text = git_patch_from_unified_diff(workspace.get("last_diff", ""))
    git_events = []
    reverse_applied = False
    patch_applied = False
    try:
        write_code_workspace_run_dir(workspace, worktree_dir)
        openwebui_dir = worktree_dir / ".openwebui"
        openwebui_dir.mkdir(parents=True, exist_ok=True)
        patch_path = openwebui_dir / "change.patch"
        patch_path.write_text(patch_text, encoding="utf-8")
        git_events.append(run_git(["init"], worktree_dir))
        exclude_path = worktree_dir / ".git" / "info" / "exclude"
        exclude_path.write_text(exclude_path.read_text(encoding="utf-8") + "\n.openwebui/\n", encoding="utf-8")
        git_events.append(run_git(["config", "user.email", "openwebui-local-code@example.invalid"], worktree_dir))
        git_events.append(run_git(["config", "user.name", "OpenWebUI Local Code"], worktree_dir))
        git_events.append(run_git(["checkout", "-b", "main"], worktree_dir, check=False))
        reverse_check = {"returncode": 1, "stdout": "", "stderr": "no patch"}
        if patch_text.strip():
            reverse_check = run_git(["apply", "--reverse", "--check", str(patch_path)], worktree_dir, check=False)
            if reverse_check.get("returncode") == 0:
                git_events.append(run_git(["apply", "--reverse", str(patch_path)], worktree_dir))
                reverse_applied = True
        git_events.append(run_git(["add", "."], worktree_dir))
        commit = run_git(["commit", "-m", "Base workspace snapshot"], worktree_dir, check=False)
        git_events.append(commit)
        base_commit = run_git(["rev-parse", "HEAD"], worktree_dir, check=False).get("stdout", "").strip()
        if branch != "main":
            git_events.append(run_git(["checkout", "-b", branch], worktree_dir, check=False))
        if patch_text.strip() and reverse_applied:
            git_events.append(run_git(["apply", str(patch_path)], worktree_dir))
            patch_applied = True
        status = run_git(["status", "--short"], worktree_dir, check=False)
        diff = run_git(["diff"], worktree_dir, check=False)
        diff_stat = run_git(["diff", "--stat"], worktree_dir, check=False)
        metadata = {
            "id": worktree_id,
            "workspace_id": workspace_id,
            "source": "local-code-git-worktree",
            "path": str(worktree_dir),
            "branch": branch,
            "base_commit": base_commit,
            "created_at": created,
            "updated_at": now(),
            "status": "ready" if base_commit else "created",
            "status_short": status.get("stdout", ""),
            "diff": diff.get("stdout", ""),
            "diff_stat": diff_stat.get("stdout", ""),
            "patch_applied": patch_applied,
            "reverse_patch_applied_to_base": reverse_applied,
            "patch_check": reverse_check,
            "git_events": [
                {
                    "command": event.get("command"),
                    "returncode": event.get("returncode"),
                    "stdout": event.get("stdout", "")[:1000],
                    "stderr": event.get("stderr", "")[:1000],
                }
                for event in git_events[-12:]
            ],
            "privacy": {
                "local_only": True,
                "isolated_directory": True,
                "host_repo_imported": False,
                "cloud_publish_performed": False,
            },
            "actions": ["inspect_status", "run_approved_command", "export_patch", "delete_worktree"],
        }
        local_code_git_worktree_metadata_path(worktree_id).parent.mkdir(parents=True, exist_ok=True)
        local_code_git_worktree_metadata_path(worktree_id).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        workspace["last_git_worktree"] = metadata
        workspace["updated_at"] = metadata["updated_at"]
        history = workspace.get("history") if isinstance(workspace.get("history"), list) else []
        history.append(
            {
                "id": worktree_id,
                "action": "create_git_worktree",
                "summary": "Created isolated local Git worktree",
                "branch": branch,
                "created_at": metadata["updated_at"],
            }
        )
        workspace["history"] = history[-50:]
        write_local_code_workspace(workspace)
        return metadata
    except Exception:
        if worktree_dir.exists():
            shutil.rmtree(worktree_dir)
        raise


def normalize_github_repository(value: str) -> str:
    repository = str(value or "").strip()
    repository = re.sub(r"^https?://github\.com/", "", repository)
    repository = repository.strip("/")
    if repository.endswith(".git"):
        repository = repository[:-4]
    parts = [part for part in repository.split("/") if part]
    if len(parts) != 2:
        return ""
    owner, repo = parts
    if not re.match(r"^[A-Za-z0-9_.-]{1,100}$", owner):
        return ""
    if not re.match(r"^[A-Za-z0-9_.-]{1,100}$", repo):
        return ""
    return f"{owner}/{repo}"


def sanitize_github_pr_payload(payload: dict) -> tuple[dict, list[str]]:
    safe_payload = {}
    ignored_fields = []
    for key, value in (payload or {}).items():
        key_text = str(key)
        if re.search(r"(authorization|bearer|token|password|secret|api[_-]?key|access[_-]?key)", key_text, re.I):
            ignored_fields.append(key_text)
            continue
        safe_payload[key_text] = value
    return safe_payload, ignored_fields


def changed_files_from_git_worktree(worktree: dict) -> list[str]:
    changed = []
    for line in str(worktree.get("status_short") or "").splitlines():
        path = line[3:].strip() if len(line) >= 4 else line.strip()
        if path:
            changed.append(path)
    if changed:
        return changed[:100]
    for match in re.finditer(r"(?m)^diff --git a/(.+?) b/(.+)$", str(worktree.get("diff") or "")):
        changed.append(match.group(2).strip())
    return changed[:100]


def github_pull_request_body(worktree: dict, workspace: dict | None, title: str, base: str, head: str) -> str:
    changed_files = changed_files_from_git_worktree(worktree)
    diff_stat = str(worktree.get("diff_stat") or "").strip()
    diff = str(worktree.get("diff") or "").strip()
    diff_excerpt = diff[:12000]
    body_lines = [
        f"# {title}",
        "",
        "## Summary",
        f"- Workspace: {(workspace or {}).get('title') or worktree.get('workspace_id')}",
        f"- Worktree: {worktree.get('id')}",
        f"- Base commit: {worktree.get('base_commit') or 'unknown'}",
        f"- Base branch: {base}",
        f"- Head branch: {head}",
        "",
        "## Changed files",
    ]
    if changed_files:
        body_lines.extend(f"- `{path}`" for path in changed_files[:50])
    else:
        body_lines.append("- No changed files were detected.")
    body_lines.extend(
        [
            "",
            "## Verification",
            "- Generated from an isolated local OpenWebUI code worktree.",
            "- Review the diff before publishing or merging.",
            "- GitHub publish requires an explicit approval and environment-configured credentials.",
        ]
    )
    if diff_stat:
        body_lines.extend(["", "## Diff stat", "```text", diff_stat[:4000], "```"])
    if diff_excerpt:
        body_lines.extend(["", "## Diff excerpt", "```diff", diff_excerpt, "```"])
        if len(diff) > len(diff_excerpt):
            body_lines.append("\nDiff excerpt truncated for connector response size.")
    return "\n".join(body_lines)[:20000]


def publish_github_pull_request(repository: str, token: str, payload: dict) -> dict:
    owner, repo = repository.split("/", 1)
    api_url = f"https://api.github.com/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/pulls"
    data = json.dumps(
        {
            "title": payload.get("title"),
            "body": payload.get("body"),
            "base": payload.get("base"),
            "head": payload.get("head"),
            "draft": bool(payload.get("draft", True)),
        }
    ).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "openwebui-local-scheduler/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    req = request.Request(api_url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as resp:
            response = json.loads(resp.read().decode("utf-8") or "{}")
        return {
            "publish_status": "published",
            "publish_performed": True,
            "number": response.get("number"),
            "url": response.get("html_url"),
            "api_url": response.get("url"),
        }
    except error.HTTPError as exc:
        detail = safe_text(exc.read())[:2000]
        return {
            "publish_status": "failed",
            "publish_performed": False,
            "http_status": exc.code,
            "error": detail,
        }
    except (error.URLError, TimeoutError, OSError) as exc:
        return {
            "publish_status": "failed",
            "publish_performed": False,
            "error": safe_text(exc)[:1000],
        }


def prepare_local_code_github_pr(worktree_id: str, payload: dict) -> dict:
    worktree = read_local_code_git_worktree(worktree_id)
    if not worktree:
        raise KeyError("git worktree not found")
    safe_payload, ignored_fields = sanitize_github_pr_payload(payload or {})
    workspace = read_local_code_workspace(str(worktree.get("workspace_id") or ""))
    publish = truthy(safe_payload.get("publish"))
    base = str(safe_payload.get("base") or safe_payload.get("base_branch") or "main").strip()[:100] or "main"
    head = (
        str(safe_payload.get("head") or safe_payload.get("head_branch") or worktree.get("branch") or "local-workspace")
        .strip()[:100]
        or "local-workspace"
    )
    draft = truthy(safe_payload.get("draft")) if "draft" in safe_payload else True
    requested_title = str(safe_payload.get("title") or "").strip()
    workspace_title = (workspace or {}).get("title") or worktree.get("workspace_id") or worktree_id
    title = (requested_title or f"Local code workspace change: {workspace_title}")[:200]
    body = str(safe_payload.get("body") or "").strip()
    if not body:
        body = github_pull_request_body(worktree, workspace, title, base, head)
    else:
        body = body[:20000]

    repository_source = safe_payload.get("repository") if "repository" in safe_payload else os.environ.get("LOCAL_CODE_GITHUB_REPOSITORY", "")
    repository = normalize_github_repository(repository_source)
    token = os.environ.get("LOCAL_CODE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    missing = []
    if not repository:
        missing.append("repository")
    if publish and not token:
        missing.append("token")

    pr_payload = {
        "title": title,
        "body": body,
        "base": base,
        "head": head,
        "draft": draft,
    }
    result = {
        "id": str(uuid.uuid4()),
        "source": "local-code-github-pr-draft",
        "worktree_id": worktree_id,
        "workspace_id": worktree.get("workspace_id"),
        "repository": repository or None,
        "repository_configured": bool(repository),
        "publish_requested": publish,
        "publish_status": "dry_run",
        "publish_performed": False,
        "missing": missing,
        "ignored_sensitive_fields": ignored_fields,
        "pull_request": pr_payload,
        "title": title,
        "body": body,
        "base": base,
        "head": head,
        "draft": draft,
        "changed_files": changed_files_from_git_worktree(worktree),
        "diff_stat": str(worktree.get("diff_stat") or ""),
        "status_short": str(worktree.get("status_short") or ""),
        "privacy": {
            "local_only": True,
            "isolated_directory": True,
            "token_from_environment_only": True,
            "approval_required_for_external_publish": True,
            "cloud_publish_performed": False,
        },
        "created_at": now(),
    }
    if publish:
        if missing:
            result["publish_status"] = "not_configured"
        else:
            publish_result = publish_github_pull_request(repository, token, pr_payload)
            result.update(publish_result)
            result["privacy"]["local_only"] = not bool(publish_result.get("publish_performed"))
            result["privacy"]["cloud_publish_performed"] = bool(publish_result.get("publish_performed"))

    worktree["last_github_pr"] = result
    worktree["updated_at"] = result["created_at"]
    actions = worktree.get("actions") if isinstance(worktree.get("actions"), list) else []
    if "prepare_github_pr" not in actions:
        actions.append("prepare_github_pr")
    worktree["actions"] = actions
    local_code_git_worktree_metadata_path(worktree_id).write_text(
        json.dumps(worktree, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if workspace:
        workspace["last_github_pr"] = result
        workspace["updated_at"] = result["created_at"]
        history = workspace.get("history") if isinstance(workspace.get("history"), list) else []
        history.append(
            {
                "id": result["id"],
                "action": "prepare_github_pr",
                "summary": "Prepared local GitHub PR payload",
                "publish_status": result.get("publish_status"),
                "created_at": result["created_at"],
            }
        )
        workspace["history"] = history[-50:]
        write_local_code_workspace(workspace)
    return result


def delete_local_code_git_worktree(worktree_id: str) -> bool:
    path = local_code_git_worktree_path(worktree_id)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def local_code_analysis(workspace: dict) -> dict:
    language_counts: dict[str, int] = {}
    symbols = []
    todos = []
    for file in workspace.get("files") or []:
        path = file.get("path") or ""
        language = file.get("language") or language_for_path(path)
        language_counts[language] = language_counts.get(language, 0) + 1
        content = str(file.get("content") or "")
        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if "TODO" in stripped or "FIXME" in stripped:
                todos.append({"path": path, "line": lineno, "text": stripped[:240]})
            match = re.match(r"(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", stripped)
            if match:
                symbols.append({"path": path, "line": lineno, "type": "function", "name": match.group(1)})
            match = re.match(r"class\s+([A-Za-z_][A-Za-z0-9_]*)\b", stripped)
            if match:
                symbols.append({"path": path, "line": lineno, "type": "class", "name": match.group(1)})
            match = re.match(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", stripped)
            if match:
                symbols.append({"path": path, "line": lineno, "type": "function", "name": match.group(1)})
    return {
        "id": workspace.get("id"),
        "title": workspace.get("title"),
        "file_count": len(workspace.get("files") or []),
        "language_counts": language_counts,
        "symbols": symbols[:200],
        "todos": todos[:100],
        "actions": ["analyze", "run_static_checks", "run_approved_command", "apply_patch", "review_diff", "prepare_review_package"],
        "privacy": {"local_only": True, "approval_required_for_writes": True},
    }


def find_code_file(workspace: dict, file_path: str) -> dict:
    normalized = normalize_code_path(file_path)
    for file in workspace.get("files") or []:
        if file.get("path") == normalized:
            return file
    raise KeyError("file not found")


def apply_local_code_patch(workspace_id: str, payload: dict) -> dict:
    workspace = read_local_code_workspace(workspace_id)
    if not workspace:
        raise KeyError("workspace not found")
    patches = payload.get("patches")
    if not isinstance(patches, list):
        patches = [
            {
                "path": payload.get("path"),
                "find": payload.get("find"),
                "replace": payload.get("replace"),
                "replace_all": payload.get("replace_all"),
            }
        ]
    changed = []
    diff_parts = []
    for patch in patches[:50]:
        if not isinstance(patch, dict):
            continue
        file = find_code_file(workspace, patch.get("path"))
        old_content = str(file.get("content") or "")
        if "content" in patch:
            new_content = str(patch.get("content") or "")
        else:
            find_text = str(patch.get("find") or "")
            replace_text = str(patch.get("replace") if patch.get("replace") is not None else "")
            if not find_text:
                raise ValueError("patch find text is required")
            if find_text not in old_content:
                raise ValueError(f"find text not found in {file.get('path')}")
            new_content = old_content.replace(find_text, replace_text) if patch.get("replace_all") else old_content.replace(find_text, replace_text, 1)
        if new_content == old_content:
            continue
        file["content"] = new_content
        file["bytes"] = len(new_content.encode("utf-8"))
        file["updated_at"] = now()
        file["language"] = file.get("language") or language_for_path(file.get("path") or "")
        diff = "\n".join(
            difflib.unified_diff(
                old_content.splitlines(),
                new_content.splitlines(),
                fromfile=f"a/{file.get('path')}",
                tofile=f"b/{file.get('path')}",
                lineterm="",
            )
        )
        diff_parts.append(diff)
        changed.append({"path": file.get("path"), "bytes": file["bytes"], "diff": diff})
    workspace["updated_at"] = now()
    workspace["last_diff"] = "\n".join(part for part in diff_parts if part)
    history = workspace.get("history") if isinstance(workspace.get("history"), list) else []
    history.append(
        {
            "id": str(uuid.uuid4()),
            "action": "apply_patch",
            "summary": str(payload.get("summary") or "Local code patch").strip()[:240],
            "changed_files": [item.get("path") for item in changed],
            "diff": workspace.get("last_diff", ""),
            "created_at": workspace["updated_at"],
        }
    )
    workspace["history"] = history[-50:]
    write_local_code_workspace(workspace)
    return {"workspace": workspace, "changed_files": changed, "changed_count": len(changed), "diff": workspace.get("last_diff", "")}


def run_local_code_checks(workspace_id: str) -> dict:
    workspace = read_local_code_workspace(workspace_id)
    if not workspace:
        raise KeyError("workspace not found")
    checks = []
    ok = True
    for file in workspace.get("files") or []:
        path = file.get("path") or ""
        content = str(file.get("content") or "")
        language = file.get("language") or language_for_path(path)
        if path.endswith(".py") or language == "python":
            try:
                compile(content, path, "exec")
                checks.append({"path": path, "kind": "python_compile", "status": "passed"})
            except SyntaxError as exc:
                ok = False
                checks.append({"path": path, "kind": "python_compile", "status": "failed", "error": str(exc)})
        elif path.endswith(".json") or language == "json":
            try:
                json.loads(content or "{}")
                checks.append({"path": path, "kind": "json_parse", "status": "passed"})
            except json.JSONDecodeError as exc:
                ok = False
                checks.append({"path": path, "kind": "json_parse", "status": "failed", "error": str(exc)})
        else:
            checks.append({"path": path, "kind": "static_presence", "status": "passed"})
    result = {
        "id": workspace_id,
        "status": "passed" if ok else "failed",
        "checks": checks,
        "checked_at": now(),
        "note": "Local static checks compile/parse stored files without executing arbitrary project code.",
    }
    workspace["last_check"] = result
    workspace["updated_at"] = result["checked_at"]
    write_local_code_workspace(workspace)
    return result


def normalize_code_command(payload: dict) -> list[str]:
    raw_command = payload.get("command")
    if not isinstance(raw_command, list) or not raw_command:
        raise ValueError("command must be a non-empty array")
    command = []
    for item in raw_command[:20]:
        value = str(item)
        if not value.strip() or "\x00" in value or len(value) > 240:
            raise ValueError("command arguments must be non-empty strings under 240 characters")
        command.append(value)
    executable = command[0]
    if "/" in executable or "\\" in executable or executable.startswith("."):
        raise ValueError("command executable must be a simple program name")
    allowed = {
        item.strip()
        for item in os.environ.get("LOCAL_CODE_ALLOWED_COMMANDS", "python,python3,pytest").split(",")
        if item.strip()
    }
    if executable not in allowed:
        raise ValueError(f"command executable {executable!r} is not allowed")
    if executable in {"python", "python3"} and any(arg == "-c" or arg.startswith("-c") for arg in command[1:]):
        raise ValueError("inline python commands are not allowed; run a workspace file instead")
    if executable in {"python", "python3"} and len(command) >= 3 and command[1] == "-m":
        allowed_modules = {"compileall", "pytest", "unittest"}
        if command[2] not in allowed_modules:
            raise ValueError(f"python module {command[2]!r} is not allowed")
    return command


def write_code_workspace_run_dir(workspace: dict, run_dir: Path):
    run_dir.mkdir(parents=True, exist_ok=False)
    for file in workspace.get("files") or []:
        relative_path = normalize_code_path(file.get("path") or "")
        target = run_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(file.get("content") or ""), encoding="utf-8")


def local_code_run_identity() -> tuple[int | None, int | None, str]:
    if os.name != "posix" or os.geteuid() != 0:
        return None, None, "current-user"
    try:
        user = pwd.getpwnam("nobody")
        return user.pw_uid, user.pw_gid, "nobody"
    except KeyError:
        return None, None, "current-user"


def chown_tree(path: Path, uid: int | None, gid: int | None):
    if uid is None or gid is None:
        return
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, gid)
        for dirname in dirs:
            os.chown(Path(root) / dirname, uid, gid)
        for filename in files:
            os.chown(Path(root) / filename, uid, gid)


def run_local_code_command(workspace_id: str, payload: dict) -> dict:
    workspace = read_local_code_workspace(workspace_id)
    if not workspace:
        raise KeyError("workspace not found")
    command = normalize_code_command(payload)
    executable_path = shutil.which(command[0])
    if not executable_path:
        raise ValueError(f"command executable {command[0]!r} is not installed")
    command[0] = executable_path
    timeout_seconds = min(max(int(payload.get("timeout_seconds") or 10), 1), 30)
    run_id = str(uuid.uuid4())
    run_dir = local_code_run_path(run_id)
    keep_run_dir = bool(payload.get("keep_run_dir"))
    cleaned_up = False
    started_at = now()
    status = "failed"
    returncode = None
    stdout = ""
    stderr = ""
    elapsed_ms = 0
    uid, gid, run_user = local_code_run_identity()
    try:
        write_code_workspace_run_dir(workspace, run_dir)
        chown_tree(run_dir, uid, gid)
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(run_dir),
            "PYTHONPATH": str(run_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        kwargs = {}
        if uid is not None and gid is not None:
            kwargs = {"user": uid, "group": gid, "extra_groups": [], "umask": 0o077}
        before = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=run_dir,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            shell=False,
            **kwargs,
        )
        elapsed_ms = int((time.monotonic() - before) * 1000)
        returncode = completed.returncode
        stdout = safe_text(completed.stdout)[:12000]
        stderr = safe_text(completed.stderr)[:12000]
        status = "passed" if completed.returncode == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = timeout_seconds * 1000
        stdout = safe_text(exc.stdout)[:12000]
        stderr = safe_text(exc.stderr)[:12000]
        status = "timeout"
    finally:
        if not keep_run_dir and run_dir.exists():
            shutil.rmtree(run_dir)
            cleaned_up = True

    result = {
        "id": run_id,
        "workspace_id": workspace_id,
        "status": status,
        "returncode": returncode,
        "command": [Path(command[0]).name, *command[1:]],
        "stdout": stdout,
        "stderr": stderr,
        "timeout_seconds": timeout_seconds,
        "elapsed_ms": elapsed_ms,
        "run_dir": str(run_dir) if keep_run_dir else None,
        "cleaned_up": cleaned_up,
        "started_at": started_at,
        "finished_at": now(),
        "sandbox": {
            "local_temp_workspace": True,
            "no_shell": True,
            "run_user": run_user,
            "allowed_executables": sorted(
                item.strip()
                for item in os.environ.get("LOCAL_CODE_ALLOWED_COMMANDS", "python,python3,pytest").split(",")
                if item.strip()
            ),
            "network_disabled": False,
        },
        "privacy": {"local_only": True, "approval_required": True},
    }
    workspace["last_command"] = result
    workspace["updated_at"] = result["finished_at"]
    history = workspace.get("history") if isinstance(workspace.get("history"), list) else []
    history.append(
        {
            "id": run_id,
            "action": "run_command",
            "summary": "Run approved local code command",
            "command": result["command"],
            "status": status,
            "created_at": result["finished_at"],
        }
    )
    workspace["history"] = history[-50:]
    write_local_code_workspace(workspace)
    return result


def prepare_local_code_review_package(workspace_id: str, payload: dict) -> dict:
    workspace = read_local_code_workspace(workspace_id)
    if not workspace:
        raise KeyError("workspace not found")
    history = workspace.get("history") if isinstance(workspace.get("history"), list) else []
    last_patch = history[-1] if history else {}
    changed_files = [
        str(path)
        for path in (last_patch.get("changed_files") if isinstance(last_patch.get("changed_files"), list) else [])
        if str(path).strip()
    ]
    if not changed_files:
        changed_files = [
            item.get("path")
            for item in workspace.get("files") or []
            if isinstance(item, dict) and item.get("path")
        ][:20]
    diff = str(workspace.get("last_diff") or last_patch.get("diff") or "")
    check = workspace.get("last_check") if isinstance(workspace.get("last_check"), dict) else {}
    check_status = str(check.get("status") or "not_run")
    command = workspace.get("last_command") if isinstance(workspace.get("last_command"), dict) else {}
    command_status = str(command.get("status") or "not_run")
    base_branch = str(payload.get("base_branch") or "local-main").strip()[:80]
    target_branch = str(payload.get("target_branch") or "local-workspace").strip()[:80]
    requested_title = str(payload.get("title") or "").strip()
    patch_summary = str(last_patch.get("summary") or "Local code workspace changes").strip()
    title = (requested_title or f"{patch_summary} ({workspace.get('title') or workspace_id})")[:200]
    analysis = local_code_analysis(workspace)
    todos = analysis.get("todos") or []
    checklist = [
        {"item": "Diff is available for review", "status": "passed" if bool(diff.strip()) else "warning"},
        {"item": "Static checks passed", "status": "passed" if check_status == "passed" else check_status},
        {"item": "Approved command passed", "status": "passed" if command_status == "passed" else command_status},
        {"item": "Changed files are explicit", "status": "passed" if bool(changed_files) else "warning"},
        {"item": "Workspace remains local-only", "status": "passed"},
    ]
    body_lines = [
        f"# {title}",
        "",
        "## Summary",
        f"- Workspace: {workspace.get('title') or workspace_id}",
        f"- Change: {patch_summary}",
        f"- Base: {base_branch}",
        f"- Target: {target_branch}",
        "",
        "## Changed files",
    ]
    body_lines.extend(f"- `{path}`" for path in changed_files[:50])
    body_lines.extend(
        [
            "",
            "## Verification",
            f"- Static checks: {check_status}",
            f"- Approved command: {command_status}",
            "- Review package: local-only; no GitHub, cloud, or external publish action was performed.",
            "",
            "## Reviewer notes",
            f"- Symbols detected: {len(analysis.get('symbols') or [])}",
            f"- TODO/FIXME markers: {len(todos)}",
            "- Apply or publish elsewhere only after reviewing the diff and approving the target system separately.",
        ]
    )
    return {
        "id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "source": "local-code-review-package",
        "title": title,
        "body": "\n".join(body_lines),
        "base_branch": base_branch,
        "target_branch": target_branch,
        "changed_files": changed_files,
        "diff": diff,
        "check_status": check_status,
        "check": check,
        "command_status": command_status,
        "command": command,
        "ready": bool(diff.strip()) and check_status == "passed" and command_status in {"not_run", "passed"},
        "checklist": checklist,
        "analysis": {
            "file_count": analysis.get("file_count"),
            "language_counts": analysis.get("language_counts"),
            "symbols": (analysis.get("symbols") or [])[:50],
            "todos": todos[:20],
        },
        "privacy": {
            "local_only": True,
            "cloud_publish_performed": False,
            "approval_required_for_external_publish": True,
        },
        "created_at": now(),
    }


def delete_local_code_workspace(workspace_id: str) -> bool:
    path = local_code_workspace_path(workspace_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def local_goal_path(goal_id: str) -> Path:
    return LOCAL_GOALS_DIR / f"{local_code_workspace_id(goal_id)}.json"


def read_local_goal(goal_id: str) -> dict | None:
    path = local_goal_path(goal_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_goal(goal: dict):
    local_goal_path(goal["id"]).write_text(json.dumps(goal, indent=2, ensure_ascii=False), encoding="utf-8")


def list_local_goals() -> list[dict]:
    goals = []
    for path in LOCAL_GOALS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        goals.append(item)
    goals.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or 0, reverse=True)
    return goals


def normalize_goal_criteria(values) -> list[str]:
    if isinstance(values, str):
        values = [line.strip() for line in values.splitlines()]
    if not isinstance(values, list):
        values = []
    criteria = []
    for value in values[:40]:
        text = str(value or "").strip()
        if text:
            criteria.append(text[:300])
    if not criteria:
        raise ValueError("success_criteria is required")
    return criteria


def normalize_goal_evidence(values) -> list[dict]:
    if isinstance(values, dict):
        values = [values]
    if not isinstance(values, list):
        values = []
    evidence = []
    for item in values[:40]:
        if isinstance(item, dict):
            summary = str(item.get("summary") or item.get("text") or "").strip()
            criteria = item.get("criteria") if isinstance(item.get("criteria"), list) else item.get("criteria_met")
            criteria_met = [str(value).strip()[:300] for value in (criteria or []) if str(value).strip()]
            verifier = str(item.get("verifier") or item.get("source") or "").strip()[:160]
            status = str(item.get("status") or "passed").strip()[:80]
            url = str(item.get("url") or "").strip()[:500]
        else:
            summary = str(item or "").strip()
            criteria_met = []
            verifier = ""
            status = "noted"
            url = ""
        if not summary:
            continue
        evidence_item = {
            "id": str(uuid.uuid4()),
            "summary": summary[:1000],
            "criteria_met": criteria_met,
            "verifier": verifier,
            "status": status,
            "url": url,
            "created_at": now(),
        }
        evidence.append(evidence_item)
    return evidence


def local_goal_evaluation(goal: dict) -> dict:
    criteria = goal.get("success_criteria") if isinstance(goal.get("success_criteria"), list) else []
    evidence = goal.get("evidence") if isinstance(goal.get("evidence"), list) else []
    met = set()
    evidence_by_criterion = {criterion: [] for criterion in criteria}
    for item in evidence:
        if not isinstance(item, dict):
            continue
        for criterion in item.get("criteria_met") or []:
            if criterion in evidence_by_criterion:
                met.add(criterion)
                evidence_by_criterion[criterion].append(item.get("id"))
    criteria_status = [
        {
            "criterion": criterion,
            "status": "met" if criterion in met else "missing",
            "evidence_ids": evidence_by_criterion.get(criterion, []),
        }
        for criterion in criteria
    ]
    missing = [item["criterion"] for item in criteria_status if item["status"] != "met"]
    return {
        "goal_id": goal.get("id"),
        "source": "local-goal-evaluation",
        "status": "ready_for_completion" if criteria and not missing else "in_progress",
        "criteria": len(criteria),
        "met_criteria": len(criteria) - len(missing),
        "missing_criteria": missing,
        "criteria_status": criteria_status,
        "evidence_count": len(evidence),
        "privacy": {"local_only": True, "prompt_bodies_excluded": True},
    }


def create_or_update_local_goal(payload: dict) -> dict:
    created = now()
    goal_id = local_code_workspace_id(str(payload.get("id") or uuid.uuid4()))
    existing = read_local_goal(goal_id) or {}
    title = str(payload.get("title") or existing.get("title") or "Local goal").strip()[:200]
    objective = str(payload.get("objective") or existing.get("objective") or "").strip()
    if not objective:
        raise ValueError("objective is required")
    success_criteria = normalize_goal_criteria(payload.get("success_criteria") or existing.get("success_criteria"))
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else existing.get("tags", [])
    tags = [str(tag).strip()[:80] for tag in tags if str(tag).strip()][:20]
    goal = {
        "id": goal_id,
        "title": title,
        "objective": objective[:4000],
        "success_criteria": success_criteria,
        "status": str(payload.get("status") or existing.get("status") or "active").strip()[:80],
        "tags": tags,
        "source": "local-goal",
        "evidence": existing.get("evidence") if isinstance(existing.get("evidence"), list) else [],
        "history": existing.get("history") if isinstance(existing.get("history"), list) else [],
        "created_at": int(existing.get("created_at") or created),
        "updated_at": created,
        "url": f"{PUBLIC_BASE_URL}/local-goals/{goal_id}",
        "privacy": {
            "local_only": True,
            "approval_required_for_writes": True,
            "hosted_sync_equivalence": False,
        },
    }
    goal["history"].append(
        {
            "event": "created" if not existing else "updated",
            "summary": "Local goal metadata saved",
            "created_at": created,
        }
    )
    goal["evaluation"] = local_goal_evaluation(goal)
    write_local_goal(goal)
    return goal


def update_local_goal_progress(goal_id: str, payload: dict) -> dict:
    goal = read_local_goal(goal_id)
    if not goal:
        raise KeyError("goal not found")
    evidence = normalize_goal_evidence(payload.get("evidence") or payload.get("progress") or payload)
    if not evidence:
        raise ValueError("progress evidence is required")
    goal.setdefault("evidence", [])
    goal["evidence"].extend(evidence)
    if payload.get("status"):
        goal["status"] = str(payload.get("status")).strip()[:80]
    evaluation = local_goal_evaluation(goal)
    if evaluation.get("status") == "ready_for_completion" and goal.get("status") in {"active", "in_progress"}:
        goal["status"] = "ready_for_completion"
    updated = now()
    goal["updated_at"] = updated
    goal.setdefault("history", [])
    goal["history"].append(
        {
            "event": "progress",
            "summary": f"Added {len(evidence)} local evidence item(s)",
            "evidence_ids": [item.get("id") for item in evidence],
            "created_at": updated,
        }
    )
    goal["evaluation"] = local_goal_evaluation(goal)
    write_local_goal(goal)
    return goal


def delete_local_goal(goal_id: str) -> bool:
    path = local_goal_path(goal_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def create_or_update_local_app_note(payload: dict) -> dict:
    created = now()
    note_id = str(payload.get("id") or uuid.uuid4())
    existing = read_local_app_note(note_id) or {}
    title = str(payload.get("title") or existing.get("title") or "Local app note").strip()[:200]
    content = str(payload.get("content") or existing.get("content") or "").strip()
    if not content:
        raise ValueError("content is required")
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else existing.get("tags", [])
    tags = [str(tag).strip()[:80] for tag in tags if str(tag).strip()][:12]
    note = {
        "id": note_id,
        "title": title,
        "content": content,
        "tags": tags,
        "source": "local-app-note",
        "created_at": int(existing.get("created_at") or created),
        "updated_at": created,
        "url": f"{PUBLIC_BASE_URL}/local-app/notes/{note_id}",
    }
    write_local_app_note(note)
    return note


def searchable_text(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(searchable_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(searchable_text(item) for item in value.values())
    return str(value)


def load_local_parity_doc(filename: str) -> list[dict]:
    path = LOCAL_PARITY_DOCS_DIR / filename
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def local_parity_terms(query: str) -> list[str]:
    return [term for term in re.split(r"\s+", (query or "").strip().lower()) if term]


def local_parity_matches(item: dict, terms: list[str]) -> bool:
    if not terms:
        return True
    haystack = searchable_text(item).lower()
    return all(term in haystack for term in terms)


def local_parity_eval_summary(entry: dict) -> dict:
    return {
        "id": entry.get("id"),
        "catalog_id": entry.get("catalog_id"),
        "feature_family": entry.get("feature_family"),
        "priority": entry.get("priority"),
        "model": entry.get("model"),
        "expected_runtime_model": entry.get("expected_runtime_model"),
        "evaluation_mode": entry.get("evaluation_mode"),
        "quality_tier": entry.get("quality_tier"),
        "verifier_tier": entry.get("verifier_tier"),
        "required_verifiers": entry.get("required_verifiers") if isinstance(entry.get("required_verifiers"), list) else [],
        "expected_signal_count": len(entry.get("expected_signals") or []),
        "failure_signal_count": len(entry.get("failure_signals") or []),
        "max_latency_seconds": entry.get("max_latency_seconds"),
        "max_tokens": entry.get("max_tokens"),
    }


def local_parity_status_counts(items: list[dict], field: str) -> dict:
    counts = {}
    for item in items:
        key = str(item.get(field) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def local_parity_catalog(query: str = "", limit: int = 100) -> dict:
    limit = max(1, min(200, int(limit or 100)))
    terms = local_parity_terms(query)
    use_cases = load_local_parity_doc("chatgpt-local-usecase-catalog.json")
    source_entries = load_local_parity_doc("chatgpt-feature-source-snapshot.json")
    quality_evals = load_local_parity_doc("chatgpt-local-quality-evals.json")

    filtered_use_cases = [item for item in use_cases if local_parity_matches(item, terms)][:limit]
    filtered_sources = [item for item in source_entries if local_parity_matches(item, terms)][:limit]
    filtered_evals = [local_parity_eval_summary(item) for item in quality_evals if local_parity_matches(item, terms)][:limit]

    feature_families = sorted({str(item.get("feature_family")) for item in use_cases if item.get("feature_family")})
    required_verifiers = sorted(
        {
            verifier
            for item in use_cases
            for verifier in (item.get("required_verifiers") or [])
            if isinstance(verifier, str) and verifier.strip()
        }
    )
    optional_verifiers = sorted(
        {
            verifier
            for item in use_cases
            for verifier in (item.get("optional_verifiers") or [])
            if isinstance(verifier, str) and verifier.strip()
        }
    )
    official_sources = [item for item in source_entries if item.get("source_kind") == "official"]
    smoke_evals = [item for item in quality_evals if item.get("evaluation_mode") == "smoke"]
    verifier_evals = [item for item in quality_evals if item.get("evaluation_mode") == "verifier"]
    default_verifier_evals = [
        item for item in verifier_evals if item.get("verifier_tier", "default") == "default"
    ]
    optional_verifier_evals = [
        item for item in verifier_evals if item.get("verifier_tier", "default") == "optional"
    ]
    rubric_evals = [item for item in quality_evals if item.get("evaluation_mode") == "rubric"]
    high_priority_evals = [item for item in quality_evals if item.get("priority") == "high"]

    return {
        "source": "chatgpt-local-parity-catalog",
        "generated_at": now(),
        "query": query or "",
        "counts": {
            "use_cases": len(use_cases),
            "feature_families": len(feature_families),
            "required_verifiers": len(required_verifiers),
            "optional_verifiers": len(optional_verifiers),
            "source_entries": len(source_entries),
            "official_sources": len(official_sources),
            "quality_evals": len(quality_evals),
            "smoke_quality_evals": len(smoke_evals),
            "verifier_quality_evals": len(verifier_evals),
            "default_verifier_quality_evals": len(default_verifier_evals),
            "optional_verifier_quality_evals": len(optional_verifier_evals),
            "executable_quality_evals": len(smoke_evals) + len(verifier_evals),
            "rubric_quality_evals": len(rubric_evals),
            "high_priority_quality_evals": len(high_priority_evals),
        },
        "status_counts": local_parity_status_counts(use_cases, "status"),
        "feature_families": feature_families,
        "use_cases": filtered_use_cases,
        "source_entries": filtered_sources,
        "quality_evals": filtered_evals,
        "docs": {
            "mounted": LOCAL_PARITY_DOCS_DIR.exists(),
            "path": str(LOCAL_PARITY_DOCS_DIR),
            "files": [
                "chatgpt-local-usecase-catalog.json",
                "chatgpt-feature-source-snapshot.json",
                "chatgpt-local-quality-evals.json",
            ],
        },
        "privacy": {
            "local_only": True,
            "prompt_bodies_excluded": True,
            "reads_static_local_docs": True,
        },
    }


def parse_source_retrieved_date(value: str | None) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def local_parity_source_freshness() -> dict:
    source_entries = load_local_parity_doc("chatgpt-feature-source-snapshot.json")
    use_cases = load_local_parity_doc("chatgpt-local-usecase-catalog.json")
    today = date.fromtimestamp(now())
    feature_families = sorted({str(item.get("feature_family")) for item in use_cases if item.get("feature_family")})
    covered_families = sorted(
        {
            str(family)
            for item in source_entries
            for family in (item.get("feature_families") or [])
            if isinstance(family, str) and family.strip()
        }
    )
    missing_families = [family for family in feature_families if family not in set(covered_families)]
    official_sources = [item for item in source_entries if item.get("source_kind") == "official"]
    local_only_sources = [item for item in source_entries if item.get("source_kind") != "official"]
    source_statuses = []
    stale_sources = []
    missing_retrieved_sources = []
    invalid_retrieved_sources = []
    missing_url_sources = []
    missing_evidence_summary_sources = []
    invalid_official_url_sources = []

    for item in source_entries:
        retrieved = item.get("retrieved")
        source_id = item.get("id")
        source_url = str(item.get("url") or "").strip()
        evidence_summary = str(item.get("evidence_summary") or "").strip()
        source_kind = item.get("source_kind")
        if not source_url:
            missing_url_sources.append(source_id)
        if not evidence_summary:
            missing_evidence_summary_sources.append(source_id)
        if source_kind == "official" and not source_url.startswith("https://"):
            invalid_official_url_sources.append(source_id)
        retrieved_date = parse_source_retrieved_date(retrieved)
        if retrieved_date is None:
            age_days = None
            age_status = "missing_retrieved" if not retrieved else "invalid_retrieved"
            if not retrieved:
                missing_retrieved_sources.append(source_id)
            else:
                invalid_retrieved_sources.append(source_id)
        else:
            age_days = max(0, (today - retrieved_date).days)
            age_status = "current" if age_days <= LOCAL_PARITY_SOURCE_MAX_AGE_DAYS else "stale"
            if age_status == "stale":
                stale_sources.append(source_id)
        source_statuses.append(
            {
                "id": source_id,
                "title": item.get("title"),
                "url": source_url,
                "source_kind": source_kind,
                "retrieved": retrieved,
                "age_days": age_days,
                "status": age_status,
                "feature_families": item.get("feature_families") or [],
                "feature_family_count": len(item.get("feature_families") or []),
                "evidence_summary": evidence_summary,
                "has_url": bool(source_url),
                "has_evidence_summary": bool(evidence_summary),
            }
        )

    max_age_days = max([item.get("age_days") or 0 for item in source_statuses], default=0)
    release_notes = next(
        (item for item in source_statuses if item.get("id") == LOCAL_PARITY_CURRENT_RELEASE_SOURCE_ID),
        None,
    )
    release_notes_source_current = bool(release_notes and release_notes.get("status") == "current")
    current_release_family_set = set(release_notes.get("feature_families") or []) if release_notes else set()
    current_release_missing_families = sorted(
        LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_FAMILIES - current_release_family_set
    )
    current_release_summary = str((release_notes or {}).get("evidence_summary") or "").lower()
    current_release_missing_evidence_terms = sorted(
        term
        for term in LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_EVIDENCE_TERMS
        if term.lower() not in current_release_summary
    )
    current_release_coverage_ready = bool(
        release_notes_source_current
        and not current_release_missing_families
        and not current_release_missing_evidence_terms
    )
    freshness_status = (
        "current"
        if len(source_entries) == LOCAL_PARITY_EXPECTED_SOURCE_ENTRIES
        and len(official_sources) == LOCAL_PARITY_EXPECTED_OFFICIAL_SOURCES
        and len(feature_families) == len(covered_families) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        and not missing_families
        and not stale_sources
        and not missing_retrieved_sources
        and not invalid_retrieved_sources
        and not missing_url_sources
        and not missing_evidence_summary_sources
        and not invalid_official_url_sources
        and current_release_coverage_ready
        else "needs_refresh"
    )

    return {
        "source": "chatgpt-feature-source-freshness",
        "generated_at": now(),
        "freshness_status": freshness_status,
        "max_age_days_allowed": LOCAL_PARITY_SOURCE_MAX_AGE_DAYS,
        "summary": {
            "source_entries": len(source_entries),
            "official_sources": len(official_sources),
            "local_only_sources": len(local_only_sources),
            "feature_families": len(feature_families),
            "covered_feature_families": len(covered_families),
            "missing_feature_families": len(missing_families),
            "stale_sources": len(stale_sources),
            "missing_retrieved_sources": len(missing_retrieved_sources),
            "invalid_retrieved_sources": len(invalid_retrieved_sources),
            "sources_with_urls": len(source_entries) - len(missing_url_sources),
            "sources_with_evidence_summaries": len(source_entries) - len(missing_evidence_summary_sources),
            "official_https_sources": len(official_sources) - len(invalid_official_url_sources),
            "missing_url_sources": len(missing_url_sources),
            "missing_evidence_summary_sources": len(missing_evidence_summary_sources),
            "invalid_official_url_sources": len(invalid_official_url_sources),
            "all_sources_have_retrieved": not missing_retrieved_sources and not invalid_retrieved_sources,
            "max_source_age_days": max_age_days,
            "release_notes_source_current": release_notes_source_current,
            "current_release_source_id": LOCAL_PARITY_CURRENT_RELEASE_SOURCE_ID,
            "current_release_coverage_ready": current_release_coverage_ready,
            "current_release_family_count": len(current_release_family_set),
            "current_release_expected_families": len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_FAMILIES),
            "current_release_covered_families": len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_FAMILIES)
            - len(current_release_missing_families),
            "current_release_missing_families": len(current_release_missing_families),
            "current_release_expected_evidence_terms": len(
                LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_EVIDENCE_TERMS
            ),
            "current_release_covered_evidence_terms": len(
                LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_EVIDENCE_TERMS
            )
            - len(current_release_missing_evidence_terms),
            "current_release_missing_evidence_terms": len(current_release_missing_evidence_terms),
        },
        "current_release": {
            "source_id": LOCAL_PARITY_CURRENT_RELEASE_SOURCE_ID,
            "status": "ready" if current_release_coverage_ready else "needs_refresh",
            "source_current": release_notes_source_current,
            "family_count": len(current_release_family_set),
            "expected_families": len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_FAMILIES),
            "covered_families": len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_FAMILIES)
            - len(current_release_missing_families),
            "missing_families": current_release_missing_families,
            "expected_evidence_terms": len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_EVIDENCE_TERMS),
            "covered_evidence_terms": len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_EVIDENCE_TERMS)
            - len(current_release_missing_evidence_terms),
            "missing_evidence_terms": current_release_missing_evidence_terms,
        },
        "missing_feature_families": missing_families,
        "stale_source_ids": [source_id for source_id in stale_sources if source_id],
        "missing_retrieved_source_ids": [source_id for source_id in missing_retrieved_sources if source_id],
        "invalid_retrieved_source_ids": [source_id for source_id in invalid_retrieved_sources if source_id],
        "missing_url_source_ids": [source_id for source_id in missing_url_sources if source_id],
        "missing_evidence_summary_source_ids": [
            source_id for source_id in missing_evidence_summary_sources if source_id
        ],
        "invalid_official_url_source_ids": [source_id for source_id in invalid_official_url_sources if source_id],
        "source_statuses": source_statuses,
        "next_actions": []
        if freshness_status == "current"
        else [
            "Refresh docs/chatgpt-feature-source-snapshot.json from official OpenAI Help/OpenAI sources.",
            "Re-run the source/catalog parity checks after updating retrieved dates and feature-family coverage.",
        ],
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_feature_matrix(query: str = "", limit: int = 100) -> dict:
    limit = max(1, min(200, int(limit or 100)))
    terms = local_parity_terms(query)
    use_cases = load_local_parity_doc("chatgpt-local-usecase-catalog.json")
    source_entries = load_local_parity_doc("chatgpt-feature-source-snapshot.json")
    quality_evals = load_local_parity_doc("chatgpt-local-quality-evals.json")
    source_freshness = local_parity_source_freshness()
    source_status_by_id = {
        item.get("id"): item.get("status")
        for item in source_freshness.get("source_statuses", [])
        if isinstance(item, dict) and item.get("id")
    }

    families = sorted({str(item.get("feature_family")) for item in use_cases if item.get("feature_family")})
    rows = []
    for family in families:
        family_use_cases = [item for item in use_cases if item.get("feature_family") == family]
        family_sources = [item for item in source_entries if family in (item.get("feature_families") or [])]
        family_evals = [item for item in quality_evals if item.get("feature_family") == family]
        required_verifiers = sorted(
            {
                verifier
                for item in family_use_cases
                for verifier in (item.get("required_verifiers") or [])
                if isinstance(verifier, str) and verifier.strip()
            }
        )
        optional_verifiers = sorted(
            {
                verifier
                for item in family_use_cases
                for verifier in (item.get("optional_verifiers") or [])
                if isinstance(verifier, str) and verifier.strip()
            }
        )
        primary_models = sorted(
            {
                model
                for item in family_use_cases
                for model in (item.get("primary_models") or [])
                if isinstance(model, str) and model.strip()
            }
        )
        implemented_use_cases = [item for item in family_use_cases if item.get("status") == "implemented"]
        official_sources = [item for item in family_sources if item.get("source_kind") == "official"]
        local_sources = [item for item in family_sources if item.get("source_kind") != "official"]
        row_ready = bool(family_sources) and bool(implemented_use_cases) and bool(required_verifiers)
        first_use_case = family_use_cases[0] if family_use_cases else {}
        row = {
            "feature_family": family,
            "status": "ready" if row_ready else "needs_attention",
            "use_case_ids": [item.get("id") for item in family_use_cases if item.get("id")],
            "implemented_use_cases": len(implemented_use_cases),
            "sample_use_case": first_use_case.get("sample_use_case"),
            "local_path": first_use_case.get("local_path"),
            "primary_models": primary_models,
            "required_verifier_count": len(required_verifiers),
            "optional_verifier_count": len(optional_verifiers),
            "source_ids": [item.get("id") for item in family_sources if item.get("id")],
            "official_source_count": len(official_sources),
            "local_source_count": len(local_sources),
            "source_statuses": {
                item.get("id"): source_status_by_id.get(item.get("id"), "unknown")
                for item in family_sources
                if item.get("id")
            },
            "quality_eval_ids": [item.get("id") for item in family_evals if item.get("id")],
            "quality_eval_count": len(family_evals),
            "high_priority_quality_eval_count": len([item for item in family_evals if item.get("priority") == "high"]),
            "quality_eval_modes": local_parity_status_counts(family_evals, "evaluation_mode"),
        }
        rows.append(row)

    filtered_rows = [row for row in rows if local_parity_matches(row, terms)][:limit]
    ready_rows = [row for row in rows if row.get("status") == "ready"]
    source_covered_rows = [row for row in rows if row.get("source_ids")]
    implemented_rows = [row for row in rows if row.get("implemented_use_cases", 0) > 0]
    verifier_rows = [row for row in rows if row.get("required_verifier_count", 0) > 0]
    quality_eval_rows = [row for row in rows if row.get("quality_eval_count", 0) > 0]
    high_priority_quality_rows = [row for row in rows if row.get("high_priority_quality_eval_count", 0) > 0]
    matrix_status = (
        "ready"
        if len(rows) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        and len(ready_rows) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        and len(source_covered_rows) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        and len(implemented_rows) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        and len(verifier_rows) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        else "needs_attention"
    )

    return {
        "source": "chatgpt-local-feature-matrix",
        "generated_at": now(),
        "query": query or "",
        "matrix_status": matrix_status,
        "summary": {
            "feature_families": len(rows),
            "ready_feature_families": len(ready_rows),
            "source_covered_feature_families": len(source_covered_rows),
            "official_source_feature_families": len([row for row in rows if row.get("official_source_count", 0) > 0]),
            "local_source_feature_families": len([row for row in rows if row.get("local_source_count", 0) > 0]),
            "implemented_use_case_feature_families": len(implemented_rows),
            "verifier_covered_feature_families": len(verifier_rows),
            "quality_eval_feature_families": len(quality_eval_rows),
            "high_priority_quality_eval_feature_families": len(high_priority_quality_rows),
        },
        "feature_families": filtered_rows,
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_recommended_model(feature_family: str, primary_models: list[str]) -> str | None:
    family = (feature_family or "").lower()
    models = [str(model) for model in primary_models if isinstance(model, str) and model.strip()]
    lowered = {model.lower(): model for model in models}

    def first_available(preferred: list[str]) -> str | None:
        for model in preferred:
            if model.lower() in lowered:
                return lowered[model.lower()]
        return models[0] if models else None

    if "codex" in family or "software" in family or "code" in family:
        return first_available(["slopcode-qwen-coder-local", "local-agent-glm52", "glm52-q8-local", "glm52-q4-local"])
    if "deep research" in family:
        return first_available(["deep-research-glm52", "glm52-q8-local", "glm52-q4-local"])
    if "developer mode" in family or "mcp" in family:
        return first_available(["local-agent-glm52", "local-chatgpt-auto", "glm52-q8-local", "glm52-q4-local"])
    if "image generation" in family:
        return first_available(["flux-2-klein-9b-fp8"])
    if "image editing" in family:
        return first_available(["flux1-dev-kontext_fp8_scaled"])
    if "image understanding" in family:
        return first_available(["local-vision-gemma4-12b", "local-vision-moondream2"])
    if "voice" in family or "record mode" in family:
        return first_available(["whisper-base-bundled", "whisper-large-v3", "local-agent-glm52"])
    if "shopping" in family:
        return first_available(["glm52-shopping-research-local", "glm52-q8-local", "glm52-q4-local"])
    if "job search" in family or "resume" in family or "finance" in family:
        return first_available(["local-agent-glm52", "local-chatgpt-auto", "glm52-q8-local", "glm52-q4-local"])
    if "study" in family:
        return first_available(["glm52-study-coach-local", "glm52-q8-local", "glm52-q4-local"])
    if "advanced reasoning" in family or "long context" in family:
        return first_available(["glm52-q8-local", "glm52-q4-local"])
    if "data analysis" in family or "canvas" in family or "memory" in family or "agent mode" in family:
        return first_available(["local-agent-glm52", "glm52-q8-local", "glm52-q4-local"])
    return first_available(["local-chatgpt-auto", "local-auto-router", "local-instant-gemma4-12b", "glm52-q8-local", "glm52-q4-local"])


def local_parity_route_for_model(feature_family: str, model: str | None, profiles: dict) -> dict:
    family = (feature_family or "").lower()
    model_text = (model or "").lower()
    if "flux" in model_text:
        route_id = "comfyui_flux"
        route_type = "image_workflow"
        action = "Use OpenWebUI Images with the local ComfyUI provider and the selected Flux workflow."
    elif "pronunciation" in model_text:
        route_id = "local_pronunciation"
        route_type = "local_tool"
        action = "Use the Local Scheduler pronunciation guide connector for text guidance and local WAV fallback audio."
    elif "whisper" in model_text:
        route_id = "local_whisper_stt"
        route_type = "speech_to_text"
        action = "Use OpenWebUI voice input with local Whisper STT, then continue in the selected chat route."
    elif "vision" in model_text or "moondream" in model_text:
        route_id = "local_vision"
        route_type = "vision_model"
        action = "Attach an image in OpenWebUI and select the local vision model route."
    elif "deep-research" in model_text:
        route_id = "deep_research"
        route_type = "research_agent"
        action = "Use the deep-research local model route or its OpenAPI report workflow for cited research."
    elif "slopcode" in model_text or "coder" in model_text or "qwen" in model_text:
        route_id = "slopcode_tiny"
        route_type = "benchmarked_chat_route"
        action = "Select the Slopcode/Qwen coding model in OpenWebUI for local software work."
    elif model_text in {"glm52-q8-local", "glm52-q4-local"} or "advanced reasoning" in family or "long context" in family:
        route_id = "glm_tiny"
        route_type = "benchmarked_chat_route"
        action = "Select the best available local GLM 5.2 route in OpenWebUI for private long-context reasoning."
    elif "shopping" in model_text:
        route_id = "glm52_shopping_research_preset"
        route_type = "chat_preset"
        action = "Select the local GLM shopping research preset in OpenWebUI."
    elif "study" in model_text:
        route_id = "glm52_study_coach_preset"
        route_type = "chat_preset"
        action = "Select the local GLM Study Coach preset in OpenWebUI."
    elif "local-agent" in model_text:
        route_id = "local_agent"
        route_type = "tool_agent"
        action = "Select the local agent route in OpenWebUI when tool use, files, or app actions are needed."
    else:
        route_id = "fast_router"
        route_type = "benchmarked_chat_route"
        action = "Select local-chatgpt-auto or local-auto-router in OpenWebUI for the default local ChatGPT-like route."

    profile = profiles.get(route_id) if isinstance(profiles, dict) else None
    profile = profile if isinstance(profile, dict) else {}
    benchmark = profile.get("benchmark") if isinstance(profile.get("benchmark"), dict) else {}
    route_status = profile.get("status") or "ready"
    return {
        "route_id": route_id,
        "route_type": route_type,
        "route_status": route_status,
        "action": action,
        "benchmark_suite": profile.get("benchmark_suite"),
        "target_tps": profile.get("target_tps"),
        "best_tps": benchmark.get("best_tps"),
        "benchmark_freshness_status": profile.get("freshness_status") or benchmark.get("freshness_status"),
        "latest_benchmark_age_seconds": benchmark.get("latest_age_seconds"),
    }


def local_parity_runbook(query: str = "", limit: int = 100) -> dict:
    limit = max(1, min(200, int(limit or 100)))
    terms = local_parity_terms(query)
    feature_matrix = local_parity_feature_matrix()
    route_recommendations = local_model_route_recommendations()
    profiles = route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}

    entries = []
    for row in feature_matrix.get("feature_families", []):
        if not isinstance(row, dict):
            continue
        primary_models = row.get("primary_models") if isinstance(row.get("primary_models"), list) else []
        selected_model = local_parity_recommended_model(str(row.get("feature_family") or ""), primary_models)
        route = local_parity_route_for_model(str(row.get("feature_family") or ""), selected_model, profiles)
        entry_ready = (
            row.get("status") == "ready"
            and bool(selected_model)
            and route.get("route_status") == "ready"
            and row.get("required_verifier_count", 0) > 0
            and bool(row.get("source_ids"))
        )
        entries.append(
            {
                "feature_family": row.get("feature_family"),
                "status": "ready" if entry_ready else "needs_attention",
                "sample_use_case": row.get("sample_use_case"),
                "openwebui_model": selected_model,
                "openwebui_route_id": route.get("route_id"),
                "openwebui_route_type": route.get("route_type"),
                "openwebui_action": route.get("action"),
                "local_path": row.get("local_path"),
                "primary_models": primary_models,
                "route_status": route.get("route_status"),
                "benchmark_suite": route.get("benchmark_suite"),
                "target_tps": route.get("target_tps"),
                "best_tps": route.get("best_tps"),
                "benchmark_freshness_status": route.get("benchmark_freshness_status"),
                "latest_benchmark_age_seconds": route.get("latest_benchmark_age_seconds"),
                "required_verifier_count": row.get("required_verifier_count", 0),
                "optional_verifier_count": row.get("optional_verifier_count", 0),
                "quality_eval_count": row.get("quality_eval_count", 0),
                "source_ids": row.get("source_ids") or [],
                "source_statuses": row.get("source_statuses") or {},
                "verification_commands": [
                    "./scripts/parity-check.py --json",
                    "./scripts/status-parity.sh",
                ],
            }
        )

    filtered_entries = [entry for entry in entries if local_parity_matches(entry, terms)][:limit]
    ready_entries = [entry for entry in entries if entry.get("status") == "ready"]
    route_ready_entries = [entry for entry in entries if entry.get("route_status") == "ready"]
    source_covered_entries = [entry for entry in entries if entry.get("source_ids")]
    verifier_covered_entries = [entry for entry in entries if entry.get("required_verifier_count", 0) > 0]
    benchmarked_entries = [
        entry for entry in entries if entry.get("openwebui_route_type") == "benchmarked_chat_route"
    ]
    runbook_status = (
        "ready"
        if len(entries) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        and len(ready_entries) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        and len(route_ready_entries) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        and len(source_covered_entries) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        and len(verifier_covered_entries) == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
        else "needs_attention"
    )

    return {
        "source": "chatgpt-local-parity-runbook",
        "generated_at": now(),
        "query": query or "",
        "runbook_status": runbook_status,
        "summary": {
            "feature_families": len(entries),
            "ready_entries": len(ready_entries),
            "route_ready_entries": len(route_ready_entries),
            "source_covered_entries": len(source_covered_entries),
            "verifier_covered_entries": len(verifier_covered_entries),
            "benchmarked_chat_route_entries": len(benchmarked_entries),
            "local_tool_route_entries": len(entries) - len(benchmarked_entries),
            "recommended_models": len({entry.get("openwebui_model") for entry in entries if entry.get("openwebui_model")}),
        },
        "entries": filtered_entries,
        "route_recommendation_source": route_recommendations.get("source"),
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_task_recommendations(query: str = "", limit: int = 8) -> dict:
    limit = max(1, min(25, int(limit or 8)))
    runbook = local_parity_runbook(query, limit)
    route_recommendations = local_model_route_recommendations()
    profiles = route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}
    gap_report = local_parity_gap_report()
    entries = runbook.get("entries") if isinstance(runbook.get("entries"), list) else []

    recommendations = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue
        route_id = entry.get("openwebui_route_id")
        profile = profiles.get(route_id) if isinstance(profiles, dict) else None
        profile = profile if isinstance(profile, dict) else {}
        profile_benchmark = profile.get("benchmark") if isinstance(profile.get("benchmark"), dict) else {}
        recommendations.append(
            {
                "feature_family": entry.get("feature_family"),
                "sample_use_case": entry.get("sample_use_case"),
                "openwebui_model": entry.get("openwebui_model"),
                "openwebui_route_id": route_id,
                "openwebui_route_type": entry.get("openwebui_route_type"),
                "openwebui_action": entry.get("openwebui_action"),
                "local_path": entry.get("local_path"),
                "route_status": entry.get("route_status"),
                "route_recommendation": profile.get("recommendation")
                or "Use the listed OpenWebUI action for this local feature route.",
                "best_for": profile.get("best_for") or [],
                "tradeoffs": profile.get("tradeoffs") or [],
                "benchmark_suite": entry.get("benchmark_suite"),
                "target_tps": entry.get("target_tps"),
                "best_tps": entry.get("best_tps") if entry.get("best_tps") is not None else profile_benchmark.get("best_tps"),
                "quality_eval_count": entry.get("quality_eval_count", 0),
                "required_verifier_count": entry.get("required_verifier_count", 0),
                "source_ids": entry.get("source_ids") or [],
                "verification_commands": entry.get("verification_commands") or [],
            }
        )

    ready_matches = [item for item in recommendations if item.get("route_status") == "ready"]
    benchmarked_matches = [
        item for item in recommendations if item.get("openwebui_route_type") == "benchmarked_chat_route"
    ]
    gap_summary = gap_report.get("summary") if isinstance(gap_report.get("summary"), dict) else {}
    task_status = "ready" if recommendations and len(ready_matches) == len(recommendations) else "needs_attention"

    return {
        "source": "chatgpt-local-task-recommendations",
        "generated_at": now(),
        "query": query or "",
        "status": task_status,
        "summary": {
            "matches": len(recommendations),
            "ready_matches": len(ready_matches),
            "benchmarked_chat_route_matches": len(benchmarked_matches),
            "local_tool_route_matches": len(recommendations) - len(benchmarked_matches),
            "open_gaps": gap_summary.get("open_gaps", 0),
            "completion_status": LOCAL_PARITY_COMPLETION_STATUS
            if not gap_summary.get("open_gaps", 0)
            else "needs_attention",
        },
        "recommendations": recommendations,
        "route_recommendation_source": route_recommendations.get("source"),
        "runbook_status": runbook.get("runbook_status"),
        "claim_boundary": gap_report.get("claim"),
        "remaining_gap_ids": [gap.get("id") for gap in gap_report.get("gaps", []) if isinstance(gap, dict)],
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


POPULAR_CHATGPT_TASKS = [
    {
        "id": "everyday-chat",
        "task": "Everyday chat, drafting, summarization, translation, and tutoring",
        "query": "core chat",
        "expected_route_ids": ["fast_router"],
    },
    {
        "id": "private-long-context-reasoning",
        "task": "Private long-context reasoning and architecture review",
        "query": "long context",
        "expected_route_ids": ["glm_tiny"],
    },
    {
        "id": "coding-help",
        "task": "Coding help, code explanation, and local software-engineering work",
        "query": "code",
        "expected_route_ids": ["slopcode_tiny"],
    },
    {
        "id": "deep-research",
        "task": "Deep research, web search, cited reports, and source-backed briefings",
        "query": "research",
        "expected_route_ids": ["deep_research"],
    },
    {
        "id": "file-document-qa",
        "task": "Uploaded-file and document question answering",
        "query": "document Q&A",
        "expected_route_ids": ["glm_tiny"],
    },
    {
        "id": "data-analysis",
        "task": "Data analysis and code-interpreter style workflows",
        "query": "data analysis",
        "expected_route_ids": ["local_agent"],
    },
    {
        "id": "image-generation",
        "task": "Image generation and local Flux workflows",
        "query": "image generation",
        "expected_route_ids": ["comfyui_flux"],
    },
    {
        "id": "image-understanding",
        "task": "Image understanding and visual question answering",
        "query": "image understanding",
        "expected_route_ids": ["local_vision"],
    },
    {
        "id": "voice-dictation",
        "task": "Voice dictation and speech-to-text input",
        "query": "voice dictation",
        "expected_route_ids": ["local_whisper_stt"],
    },
    {
        "id": "memory-personalization",
        "task": "Memory, temporary/private chats, and personalization workflows",
        "query": "memory",
        "expected_route_ids": ["local_agent", "glm_tiny"],
    },
    {
        "id": "study-learning",
        "task": "Study mode, guided learning, and interactive explanations",
        "query": "study",
        "expected_route_ids": ["glm52_study_coach_preset"],
    },
    {
        "id": "shopping-research",
        "task": "Shopping research and product comparison",
        "query": "shopping",
        "expected_route_ids": ["glm52_shopping_research_preset"],
    },
    {
        "id": "job-search-resume",
        "task": "Job search, role-fit comparison, and resume tailoring",
        "query": "job search resume",
        "expected_route_ids": ["local_agent"],
    },
    {
        "id": "personal-finance-analysis",
        "task": "Personal finance analysis over local spending exports",
        "query": "personal finance",
        "expected_route_ids": ["local_agent"],
    },
    {
        "id": "agent-actions",
        "task": "Agent mode, browser/tool use, desktop actions, and calendars",
        "query": "agent",
        "expected_route_ids": ["local_agent"],
    },
    {
        "id": "atlas-browser-chat",
        "task": "Atlas-style browser-native chat, page context, and approved browser actions",
        "query": "browser",
        "expected_route_ids": ["local_agent"],
    },
    {
        "id": "developer-mode-mcp-app",
        "task": "Developer mode, custom MCP app setup, tool discovery, and app governance",
        "query": "mcp",
        "expected_route_ids": ["local_agent"],
    },
]


def local_parity_popular_task_routes() -> dict:
    tasks = []
    for case in POPULAR_CHATGPT_TASKS:
        recommendation = local_parity_task_recommendations(str(case.get("query") or ""), 12)
        recommendations = (
            recommendation.get("recommendations") if isinstance(recommendation.get("recommendations"), list) else []
        )
        route_ids = [
            item.get("openwebui_route_id")
            for item in recommendations
            if isinstance(item, dict) and item.get("openwebui_route_id")
        ]
        expected_route_ids = [str(item) for item in case.get("expected_route_ids", [])]
        matched_expected_route_ids = [route_id for route_id in expected_route_ids if route_id in route_ids]
        ready = (
            recommendation.get("status") == "ready"
            and bool(matched_expected_route_ids)
            and all(item.get("route_status") == "ready" for item in recommendations if isinstance(item, dict))
        )
        selected = next(
            (
                item
                for item in recommendations
                if isinstance(item, dict) and item.get("openwebui_route_id") in matched_expected_route_ids
            ),
            recommendations[0] if recommendations else {},
        )
        tasks.append(
            {
                "id": case.get("id"),
                "task": case.get("task"),
                "query": case.get("query"),
                "status": "ready" if ready else "needs_attention",
                "expected_route_ids": expected_route_ids,
                "matched_expected_route_ids": matched_expected_route_ids,
                "route_ids": route_ids,
                "selected_route": {
                    "feature_family": selected.get("feature_family"),
                    "openwebui_model": selected.get("openwebui_model"),
                    "openwebui_route_id": selected.get("openwebui_route_id"),
                    "openwebui_route_type": selected.get("openwebui_route_type"),
                    "openwebui_action": selected.get("openwebui_action"),
                    "route_status": selected.get("route_status"),
                    "best_tps": selected.get("best_tps"),
                }
                if isinstance(selected, dict)
                else {},
                "matches": (recommendation.get("summary") or {}).get("matches", 0),
                "ready_matches": (recommendation.get("summary") or {}).get("ready_matches", 0),
            }
        )

    ready_tasks = [item for item in tasks if item.get("status") == "ready"]
    route_coverage = sorted(
        {
            route_id
            for item in tasks
            for route_id in item.get("matched_expected_route_ids", [])
            if route_id
        }
    )
    gap_report = local_parity_gap_report()
    gap_summary = gap_report.get("summary") if isinstance(gap_report.get("summary"), dict) else {}
    status = "ready" if len(ready_tasks) == len(tasks) else "needs_attention"
    return {
        "source": "chatgpt-local-popular-task-routes",
        "generated_at": now(),
        "status": status,
        "summary": {
            "popular_tasks": len(tasks),
            "ready_tasks": len(ready_tasks),
            "route_coverage": route_coverage,
            "route_coverage_count": len(route_coverage),
            "open_gaps": gap_summary.get("open_gaps", 0),
            "completion_status": LOCAL_PARITY_COMPLETION_STATUS
            if not gap_summary.get("open_gaps", 0)
            else "needs_attention",
        },
        "tasks": tasks,
        "claim_boundary": gap_report.get("claim"),
        "remaining_gap_ids": [gap.get("id") for gap in gap_report.get("gaps", []) if isinstance(gap, dict)],
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


OPTIONAL_HEAVY_EVIDENCE_CASES = [
    {
        "id": "stt-dictation-record-mode",
        "title": "Local STT, editable dictation, and Record Mode canvas",
        "feature_families": ["Voice dictation / STT", "Record mode / voice notes"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --stt-smoke --json",
        "verifiers": [
            "openwebui.local_stt_smoke",
            "openwebui.voice_dictation_draft_smoke",
            "openwebui.record_mode_canvas_smoke",
        ],
        "latest_result": {"pass": 168, "skip": 29, "fail": 0},
        "evidence": "Whisper large-v3 transcribed the local greeting fixture, saved an editable dictation draft, and stored/share-verified a local Record Mode canvas.",
    },
    {
        "id": "image-generation-editing",
        "title": "Local image generation, editing, masking, and outpainting",
        "feature_families": ["Image generation"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --image-gen-smoke --image-edit-smoke --json",
        "verifiers": [
            "openwebui.image_generation_smoke",
            "openwebui.image_edit_smoke",
            "openwebui.image_mask_edit_smoke",
            "openwebui.image_outpaint_smoke",
        ],
        "latest_result": {"pass": 170, "skip": 28, "fail": 0},
        "evidence": "OpenWebUI-to-ComfyUI generated a varied 512x512 image and verified Flux Kontext edit, masked edit, and outpaint color checks.",
    },
    {
        "id": "vision-standard",
        "title": "Standard local image understanding",
        "feature_families": ["Image understanding"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --vision-smoke --json",
        "verifiers": [
            "local_vision.direct_image_smoke",
            "local_vision.openwebui_proxy_smoke",
            "local_vision.direct_gemma_image_smoke",
            "local_vision.openwebui_gemma_proxy_smoke",
            "local_vision.direct_ocr_smoke",
            "local_vision.openwebui_ocr_smoke",
            "local_vision.direct_chart_smoke",
            "local_vision.openwebui_chart_smoke",
            "local_vision.direct_multi_image_smoke",
            "local_vision.openwebui_multi_image_smoke",
        ],
        "latest_result": {"pass": 175, "skip": 22, "fail": 0},
        "evidence": "Direct and OpenWebUI-proxied Moondream/Gemma vision recognized color, OCR text, chart, and ordered multi-image fixtures.",
    },
    {
        "id": "vision-hard",
        "title": "Dense chart, cluttered screenshot, and visual reasoning",
        "feature_families": ["Image understanding"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --vision-hard-smoke --json",
        "verifiers": [
            "local_vision.direct_dense_chart_smoke",
            "local_vision.openwebui_dense_chart_smoke",
            "local_vision.direct_cluttered_screenshot_smoke",
            "local_vision.openwebui_cluttered_screenshot_smoke",
            "local_vision.direct_visual_reasoning_smoke",
            "local_vision.openwebui_visual_reasoning_smoke",
            "local_vision.direct_gemma_visual_reasoning_smoke",
            "local_vision.openwebui_gemma_visual_reasoning_smoke",
        ],
        "latest_result": {"pass": 183, "skip": 14, "fail": 0},
        "evidence": "Hard vision fixtures verified dense chart lookup, cluttered screenshot code lookup, and structured visual reasoning through direct and OpenWebUI paths.",
    },
    {
        "id": "slopcode-generation",
        "title": "Slopcode/Qwen coding companion generation",
        "feature_families": ["Core chat and model picker", "Codex / software engineering agent"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --slopcode-smoke --json",
        "verifiers": [
            "slopcode.chat_smoke",
            "openwebui.slopcode_proxy_smoke",
            "openwebui.slopcode_profile_smoke",
        ],
        "latest_result": {"pass": 168, "skip": 29, "fail": 0},
        "evidence": "Direct Slopcode/Qwen, OpenWebUI raw model proxy, and the additive slopcode-qwen-coder-local picker preset returned the expected coding-smoke response.",
    },
    {
        "id": "glm-slow-generation",
        "title": "Direct and OpenWebUI-proxied GLM 5.2 generation",
        "feature_families": ["Core chat and model picker", "Advanced reasoning and long context"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --slow-glm --json",
        "verifiers": ["glm.slow_chat_smoke", "openwebui.glm_proxy_slow_smoke"],
        "latest_result": {"pass": 167, "skip": 32, "fail": 0},
        "evidence": "Direct llama.cpp and OpenWebUI-proxied glm52-q4-local generation both returned the expected tiny response while preserving additive model exposure.",
    },
    {
        "id": "glm-usecase-generation",
        "title": "GLM 5.2 multi-use-case prompt",
        "feature_families": ["Core chat and model picker"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --glm-usecase-smoke --json",
        "verifiers": ["openwebui.glm_usecase_smoke"],
        "latest_result": {"pass": 166, "skip": 31, "fail": 0},
        "evidence": "OpenWebUI-proxied GLM 5.2 produced expected summary, math, coding, drafting, and translation signals in one compact use-case smoke.",
    },
    {
        "id": "glm-long-context",
        "title": "Bounded GLM 5.2 long-context recall",
        "feature_families": ["Advanced reasoning and long context"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --long-context-smoke --long-context-chars 256 --json",
        "verifiers": ["glm.long_context_smoke"],
        "latest_result": {"pass": 166, "skip": 31, "fail": 0},
        "evidence": "The bounded long-context smoke recalled its sentinel while the service context verifier reported 65,536 tokens for glm52-q4-local.",
    },
    {
        "id": "glm-warm-slot",
        "title": "GLM 5.2 warm-slot prompt-cache reuse",
        "feature_families": ["Advanced reasoning and long context"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --glm-warm-smoke --json",
        "verifiers": ["glm.warm_slot_smoke"],
        "latest_result": {"pass": 166, "skip": 31, "fail": 0},
        "evidence": "Repeated and nearby tiny prompts verified cached prompt-token reuse on the active GLM endpoint.",
    },
    {
        "id": "quality-fast",
        "title": "Fast/default executable answer-quality evals",
        "feature_families": ["Core chat and model picker", "Study mode / guided learning", "Shopping research"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --quality-smoke --json",
        "verifiers": ["openwebui.quality_smoke"],
        "latest_result": {"pass": 166, "skip": 31, "fail": 0},
        "evidence": "Executable fast/default-auto quality evals covered everyday chat, study coaching, source-citation caution, shopping research, writing, memory/privacy, and local GPT sharing.",
    },
    {
        "id": "quality-slow-glm",
        "title": "Slow GLM 5.2 private-reasoning quality eval",
        "feature_families": ["Advanced reasoning and long context"],
        "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --quality-smoke --quality-slow --json",
        "verifiers": ["openwebui.quality_smoke"],
        "latest_result": {"pass": 166, "skip": 31, "fail": 0},
        "evidence": "The slow quality tier included the GLM private-reasoning eval and returned recommendation, tradeoff, risk, verification, privacy, and latency signals.",
    },
]


def local_parity_optional_heavy_evidence() -> dict:
    cases = []
    for case in OPTIONAL_HEAVY_EVIDENCE_CASES:
        result = case.get("latest_result") or {}
        status = "ready" if result.get("fail") == 0 else "needs_attention"
        cases.append(
            {
                "id": case.get("id"),
                "title": case.get("title"),
                "status": status,
                "feature_families": case.get("feature_families") or [],
                "command": case.get("command"),
                "verifiers": case.get("verifiers") or [],
                "latest_result": result,
                "evidence": case.get("evidence"),
            }
        )

    ready_cases = [case for case in cases if case.get("status") == "ready"]
    feature_families = sorted(
        {
            str(feature)
            for case in cases
            for feature in case.get("feature_families", [])
            if feature
        }
    )
    commands = [case.get("command") for case in cases if case.get("command")]
    flags = sorted(
        {
            token
            for command in commands
            for token in str(command).split()
            if token.startswith("--")
        }
    )
    return {
        "source": "chatgpt-local-optional-heavy-evidence",
        "generated_at": now(),
        "status": "ready" if len(ready_cases) == len(cases) else "needs_attention",
        "summary": {
            "optional_cases": len(cases),
            "ready_optional_cases": len(ready_cases),
            "feature_families": len(feature_families),
            "verifiers": len({verifier for case in cases for verifier in case.get("verifiers", [])}),
            "commands": len(commands),
            "failures": sum(int((case.get("latest_result") or {}).get("fail") or 0) for case in cases),
            "default_suite_skips_intentional": True,
            "glm_context_tokens": 65536,
            "slopcode_context_tokens": 65536,
        },
        "feature_families": feature_families,
        "flags": flags,
        "cases": cases,
        "docs": {
            "path": str(LOCAL_PARITY_DOCS_DIR / "chatgpt-local-parity-map.md"),
            "section": "Optional-heavy evidence",
        },
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


WORKFLOW_RECIPE_BLUEPRINTS = [
    {
        "id": "everyday-chat-workflow",
        "task_id": "everyday-chat",
        "title": "Everyday chat, drafting, summarization, and translation",
        "openwebui_entrypoint": "Model picker -> local-chatgpt-auto",
        "steps": [
            "Use local-chatgpt-auto for default low-latency local chat.",
            "Let the local auto-router choose the fast route unless the task needs coding, research, tools, or explicit GLM reasoning.",
            "Use retry/edit/branch in OpenWebUI for response iteration.",
        ],
        "expected_local_artifacts": ["saved chat when not temporary", "optional shared link", "local route event"],
        "evidence_endpoints": ["/local-parity/popular-tasks", "/local-parity/quality-scorecard"],
        "optional_case_ids": ["quality-fast"],
    },
    {
        "id": "private-long-context-workflow",
        "task_id": "private-long-context-reasoning",
        "title": "Private long-context reasoning with GLM 5.2",
        "openwebui_entrypoint": "Model picker -> glm52-q8-local on enterprise rigs, otherwise glm52-q4-local",
        "steps": [
            "Select glm52-q8-local on enterprise hardware when maximum local quality matters; otherwise select glm52-q4-local.",
            "Keep the prompt bounded when possible; use files/projects for reusable context.",
            "Use fast local routes for quick follow-ups when GLM latency is not needed.",
        ],
        "expected_local_artifacts": ["local chat", "65,536-token context window evidence", "optional benchmark record"],
        "evidence_endpoints": ["/local-parity/dashboard", "/local-parity/optional-evidence"],
        "optional_case_ids": ["glm-slow-generation", "glm-usecase-generation", "glm-long-context", "glm-warm-slot", "quality-slow-glm"],
    },
    {
        "id": "coding-help-workflow",
        "task_id": "coding-help",
        "title": "Local coding help and review",
        "openwebui_entrypoint": "Model picker -> slopcode-qwen-coder-local or local-agent-glm52",
        "steps": [
            "Use slopcode-qwen-coder-local for code synthesis and debugging.",
            "Use Local Scheduler code workspaces when you need patch, diff, check, export, or review-package artifacts.",
            "Use local-agent-glm52 only when tool, browser, or desktop actions are required.",
        ],
        "expected_local_artifacts": ["code workspace", "diff/review package", "optional local Git worktree"],
        "evidence_endpoints": ["/local-parity/runbook", "/local-parity/optional-evidence"],
        "optional_case_ids": ["slopcode-generation"],
    },
    {
        "id": "deep-research-workflow",
        "task_id": "deep-research",
        "title": "Deep research with local sources and citations",
        "openwebui_entrypoint": "Model picker -> deep-research-glm52",
        "steps": [
            "Use deep-research-glm52 for multi-source reports, source packs, and downloadable artifacts.",
            "Attach local documents or connector notes when private sources should be included.",
            "Review the plan/source policy before generating the report.",
        ],
        "expected_local_artifacts": ["research plan", "source pack", "Markdown/HTML/Word/PDF/JSON report", "portable ZIP bundle"],
        "evidence_endpoints": ["/local-parity/runbook", "/local-parity/live-status"],
        "optional_case_ids": [],
    },
    {
        "id": "file-document-qa-workflow",
        "task_id": "file-document-qa",
        "title": "File, document, and knowledge-base Q&A",
        "openwebui_entrypoint": "OpenWebUI chat -> attach files or project sources",
        "steps": [
            "Upload or reuse files from the local File Library or project sources.",
            "Use local-chatgpt-auto for fast Q&A or glm52-q4-local for private long-context reasoning.",
            "Inspect source context and saved-source reuse when the answer depends on documents.",
        ],
        "expected_local_artifacts": ["processed file", "knowledge collection", "source-context chat payload"],
        "evidence_endpoints": ["/local-parity/catalog", "/local-parity/runbook"],
        "optional_case_ids": [],
    },
    {
        "id": "data-analysis-workflow",
        "task_id": "data-analysis",
        "title": "Local data analysis and code interpreter",
        "openwebui_entrypoint": "OpenWebUI tools -> local Jupyter/code interpreter",
        "steps": [
            "Use local Jupyter-backed code execution for Python, pandas, charts, and structured data transforms.",
            "Use local sheet workbooks for spreadsheet-like create/update/explain flows.",
            "Keep generated files local and reusable through OpenWebUI file/project surfaces.",
        ],
        "expected_local_artifacts": ["Jupyter execution output", "chart/table artifact", "optional local sheet workbook"],
        "evidence_endpoints": ["/local-parity/runbook", "/local-parity/live-status"],
        "optional_case_ids": [],
    },
    {
        "id": "image-generation-workflow",
        "task_id": "image-generation",
        "title": "Local image generation and editing",
        "openwebui_entrypoint": "OpenWebUI Images -> local ComfyUI Flux workflow",
        "steps": [
            "Use the local ComfyUI image provider for text-to-image generation.",
            "Use image edit, mask edit, or outpaint flows when modifying an existing image.",
            "Release ComfyUI memory before GLM-heavy work if VRAM pressure is high.",
        ],
        "expected_local_artifacts": ["generated image file", "edited image file", "ComfyUI workflow result"],
        "evidence_endpoints": ["/local-parity/optional-evidence", "/local-parity/live-status"],
        "optional_case_ids": ["image-generation-editing"],
    },
    {
        "id": "image-understanding-workflow",
        "task_id": "image-understanding",
        "title": "Local image understanding",
        "openwebui_entrypoint": "Model picker -> local-vision-gemma4-12b or local-vision-moondream2",
        "steps": [
            "Attach an image and select a local vision model route.",
            "Use Gemma vision for stronger open-world reasoning and Moondream/RapidOCR assists for lightweight fixtures.",
            "For dense charts or cluttered screenshots, confirm results against the source image.",
        ],
        "expected_local_artifacts": ["image chat payload", "vision response", "optional OCR/chart evidence"],
        "evidence_endpoints": ["/local-parity/optional-evidence", "/local-parity/live-status"],
        "optional_case_ids": ["vision-standard", "vision-hard"],
    },
    {
        "id": "voice-dictation-workflow",
        "task_id": "voice-dictation",
        "title": "Local voice dictation and record-mode notes",
        "openwebui_entrypoint": "OpenWebUI audio input -> local Whisper STT",
        "steps": [
            "Use local Whisper STT to transcribe audio into editable text.",
            "Review/edit the transcript before sending or saving it.",
            "Use the local Record Mode canvas flow for transcript, summary, and follow-up artifacts.",
        ],
        "expected_local_artifacts": ["transcript text", "voice dictation draft", "record-mode canvas"],
        "evidence_endpoints": ["/local-parity/optional-evidence", "/local-parity/runbook"],
        "optional_case_ids": ["stt-dictation-record-mode"],
    },
    {
        "id": "memory-personalization-workflow",
        "task_id": "memory-personalization",
        "title": "Memory, personalization, and temporary/private chats",
        "openwebui_entrypoint": "OpenWebUI settings, memory, and chat controls",
        "steps": [
            "Use saved memories and custom instructions for persistent local personalization.",
            "Use temporary chats for one-off sensitive work that should not persist.",
            "Use memory-source feedback when a saved memory should or should not affect a response.",
        ],
        "expected_local_artifacts": ["memory record", "custom instruction source", "temporary-chat non-persistence evidence"],
        "evidence_endpoints": ["/local-parity/catalog", "/local-parity/continuity"],
        "optional_case_ids": [],
    },
    {
        "id": "study-learning-workflow",
        "task_id": "study-learning",
        "title": "Study mode and guided learning",
        "openwebui_entrypoint": "Model picker -> glm52-study-coach-local",
        "steps": [
            "Select glm52-study-coach-local for Socratic tutoring and stepwise scaffolding.",
            "Attach course files or images when the lesson depends on source material.",
            "Use interactive learning artifacts for variable-driven math/science explanations.",
        ],
        "expected_local_artifacts": ["study coach chat", "optional file/vision context", "interactive learning artifact"],
        "evidence_endpoints": ["/local-parity/runbook", "/local-parity/optional-evidence"],
        "optional_case_ids": ["quality-fast"],
    },
    {
        "id": "shopping-research-workflow",
        "task_id": "shopping-research",
        "title": "Shopping research and product comparison",
        "openwebui_entrypoint": "Model picker -> glm52-shopping-research-local",
        "steps": [
            "Use the shopping research preset for criteria, budget, tradeoffs, and source-backed comparison.",
            "Use local web search for product details and merchant links.",
            "Verify final price, stock, shipping, return policy, and merchant terms before purchase.",
        ],
        "expected_local_artifacts": ["buyer-guide response", "source links", "comparison criteria"],
        "evidence_endpoints": ["/local-parity/runbook", "/local-parity/source-freshness"],
        "optional_case_ids": ["quality-fast"],
    },
    {
        "id": "job-search-resume-workflow",
        "task_id": "job-search-resume",
        "title": "Job search, role-fit comparison, and resume tailoring",
        "openwebui_entrypoint": "OpenWebUI chat -> local-agent-glm52 with web search and attached resume",
        "steps": [
            "Search locally through SearXNG for current job listings and keep source URLs in the answer.",
            "Attach or reuse the local resume file so role-fit analysis is grounded in user-provided context.",
            "Draft a tailored resume or cover-letter section as a local artifact without submitting applications.",
        ],
        "expected_local_artifacts": ["search source links", "resume file context", "tailored draft artifact"],
        "evidence_endpoints": ["/local-parity/feature-map", "/local-parity/source-freshness"],
        "optional_case_ids": [],
    },
    {
        "id": "personal-finance-workflow",
        "task_id": "personal-finance-analysis",
        "title": "Personal finance analysis over local exports",
        "openwebui_entrypoint": "OpenWebUI tools -> local-agent-glm52 with local files and Jupyter",
        "steps": [
            "Upload or reuse a local spending export, budget spreadsheet, or transaction CSV.",
            "Use local Jupyter/pandas analysis to identify recurring charges, categories, trends, and budget gaps.",
            "Return financial analysis as local guidance only, without money movement or financial/legal/tax/investment advice.",
        ],
        "expected_local_artifacts": ["local spending file", "analysis table or chart", "budget summary"],
        "evidence_endpoints": ["/local-parity/feature-map", "/local-parity/quality-scorecard"],
        "optional_case_ids": [],
    },
    {
        "id": "agent-actions-workflow",
        "task_id": "agent-actions",
        "title": "Agent mode, browser/tool use, desktop actions, and calendars",
        "openwebui_entrypoint": "Model picker -> local-agent-glm52",
        "steps": [
            "Use local-agent-glm52 for browser, Playwright, desktop, calendar, and tool workflows.",
            "Keep approval mode enabled for actions that mutate local state.",
            "Use the approval dashboard to review or deny actions before execution.",
        ],
        "expected_local_artifacts": ["approval record", "tool result", "browser/desktop evidence when applicable"],
        "evidence_endpoints": ["/local-parity/runbook", "/local-parity/live-status"],
        "optional_case_ids": [],
    },
    {
        "id": "atlas-browser-chat-workflow",
        "task_id": "atlas-browser-chat",
        "title": "Atlas-style browser-native chat and approved browser actions",
        "openwebui_entrypoint": "Model picker -> local-agent-glm52 with browser approval enabled",
        "steps": [
            "Use local-agent-glm52 when a task needs rendered page context, tab-like browser work, or browser clicks.",
            "Keep browser actions limited to allowed local or user-approved hosts.",
            "Review browser approvals and screenshot evidence before trusting any action result.",
        ],
        "expected_local_artifacts": ["browser approval record", "rendered screenshot evidence", "local tool transcript"],
        "evidence_endpoints": ["/local-parity/runbook", "/local-parity/live-status", "/local-parity/source-freshness"],
        "optional_case_ids": [],
    },
    {
        "id": "developer-mode-mcp-app-workflow",
        "task_id": "developer-mode-mcp-app",
        "title": "Developer mode and custom MCP-style app setup",
        "openwebui_entrypoint": "Workspace -> Tools / OpenAPI tool server -> local-scheduler-openapi",
        "steps": [
            "Use the additive local-scheduler-openapi tool server as the local custom-app/MCP-style surface.",
            "Review discovered operations before using the app in a chat or custom assistant.",
            "Set permission mode, action controls, parameter constraints, and audit-log expectations before write-style actions.",
            "Verify app calls stay local and redacted unless an explicit external provider is configured.",
        ],
        "expected_local_artifacts": ["tool-server registration", "operation list", "permission/action-control record", "redacted app-call audit log"],
        "evidence_endpoints": ["/local-parity/runbook", "/local-parity/source-freshness", "/openapi.json"],
        "optional_case_ids": [],
    },
]


def local_parity_workflow_recipes() -> dict:
    popular_task_routes = local_parity_popular_task_routes()
    optional_evidence = local_parity_optional_heavy_evidence()
    gap_report = local_parity_gap_report()
    tasks_by_id = {
        item.get("id"): item
        for item in popular_task_routes.get("tasks", [])
        if isinstance(item, dict) and item.get("id")
    }
    optional_cases_by_id = {
        item.get("id"): item
        for item in optional_evidence.get("cases", [])
        if isinstance(item, dict) and item.get("id")
    }
    recipes = []
    for blueprint in WORKFLOW_RECIPE_BLUEPRINTS:
        task = tasks_by_id.get(blueprint.get("task_id")) or {}
        selected_route = task.get("selected_route") if isinstance(task.get("selected_route"), dict) else {}
        optional_case_ids = [case_id for case_id in blueprint.get("optional_case_ids", []) if case_id in optional_cases_by_id]
        optional_cases_ready = all(
            optional_cases_by_id.get(case_id, {}).get("status") == "ready" for case_id in optional_case_ids
        )
        ready = (
            task.get("status") == "ready"
            and selected_route.get("route_status") == "ready"
            and optional_cases_ready
        )
        recipes.append(
            {
                "id": blueprint.get("id"),
                "title": blueprint.get("title"),
                "task_id": blueprint.get("task_id"),
                "status": "ready" if ready else "needs_attention",
                "openwebui_entrypoint": blueprint.get("openwebui_entrypoint"),
                "openwebui_route_id": selected_route.get("openwebui_route_id"),
                "openwebui_model": selected_route.get("openwebui_model"),
                "openwebui_route_type": selected_route.get("openwebui_route_type"),
                "openwebui_action": selected_route.get("openwebui_action"),
                "steps": blueprint.get("steps") or [],
                "expected_local_artifacts": blueprint.get("expected_local_artifacts") or [],
                "evidence_endpoints": blueprint.get("evidence_endpoints") or [],
                "optional_case_ids": optional_case_ids,
                "optional_cases_ready": optional_cases_ready,
            }
        )

    ready_recipes = [recipe for recipe in recipes if recipe.get("status") == "ready"]
    route_ids = sorted({recipe.get("openwebui_route_id") for recipe in recipes if recipe.get("openwebui_route_id")})
    optional_case_ids = sorted({case_id for recipe in recipes for case_id in recipe.get("optional_case_ids", [])})
    gap_summary = gap_report.get("summary") if isinstance(gap_report.get("summary"), dict) else {}
    return {
        "source": "chatgpt-local-workflow-recipes",
        "generated_at": now(),
        "status": "ready" if len(ready_recipes) == len(recipes) else "needs_attention",
        "summary": {
            "workflow_recipes": len(recipes),
            "ready_workflow_recipes": len(ready_recipes),
            "route_coverage_count": len(route_ids),
            "optional_heavy_cases_linked": len(optional_case_ids),
            "open_gaps": gap_summary.get("open_gaps", 0),
            "completion_status": LOCAL_PARITY_COMPLETION_STATUS
            if not gap_summary.get("open_gaps", 0)
            else "needs_attention",
        },
        "route_coverage": route_ids,
        "optional_case_ids": optional_case_ids,
        "recipes": recipes,
        "claim_boundary": gap_report.get("claim"),
        "remaining_gap_ids": [gap.get("id") for gap in gap_report.get("gaps", []) if isinstance(gap, dict)],
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


STARTER_PROMPT_BLUEPRINTS = [
    {
        "id": "everyday-chat-starter",
        "workflow_id": "everyday-chat-workflow",
        "title": "Everyday drafting and concise answer",
        "variables": ["goal", "audience", "source_text"],
        "prompt_template": (
            "You are running locally in OpenWebUI. Help me with this everyday task.\n\n"
            "Goal: {{goal}}\n"
            "Audience: {{audience}}\n"
            "Source text or notes:\n{{source_text}}\n\n"
            "Return a concise answer first, then a short list of useful edits or follow-up questions."
        ),
        "expected_result": "clear draft, summary, translation, or answer with follow-up options",
    },
    {
        "id": "private-long-context-starter",
        "workflow_id": "private-long-context-workflow",
        "title": "Private GLM long-context analysis",
        "variables": ["decision", "context", "constraints"],
        "prompt_template": (
            "Use the local GLM 5.2 route for private long-context reasoning.\n\n"
            "Decision or question: {{decision}}\n"
            "Context:\n{{context}}\n"
            "Constraints: {{constraints}}\n\n"
            "Analyze the tradeoffs, identify risks, cite the most relevant context sections by name, "
            "and end with a recommended next step."
        ),
        "expected_result": "private reasoning summary with tradeoffs, risks, and recommendation",
    },
    {
        "id": "coding-help-starter",
        "workflow_id": "coding-help-workflow",
        "title": "Local coding help or review",
        "variables": ["repo_context", "problem", "relevant_code"],
        "prompt_template": (
            "Act as a local coding assistant. Prefer a minimal, testable change.\n\n"
            "Repository context: {{repo_context}}\n"
            "Problem: {{problem}}\n"
            "Relevant code or error output:\n{{relevant_code}}\n\n"
            "Explain the likely cause, propose the smallest fix, list tests to run, and call out any uncertainty."
        ),
        "expected_result": "diagnosis, scoped fix plan, and verification steps",
    },
    {
        "id": "deep-research-starter",
        "workflow_id": "deep-research-workflow",
        "title": "Deep research report plan",
        "variables": ["research_question", "scope", "source_preferences"],
        "prompt_template": (
            "Run this as a local deep research task.\n\n"
            "Research question: {{research_question}}\n"
            "Scope and exclusions: {{scope}}\n"
            "Preferred sources or local files: {{source_preferences}}\n\n"
            "First produce a research plan and source strategy. Then produce a cited report with findings, "
            "confidence, contradictions, and next checks."
        ),
        "expected_result": "research plan, source policy, and cited local report",
    },
    {
        "id": "file-document-qa-starter",
        "workflow_id": "file-document-qa-workflow",
        "title": "File and document Q&A",
        "variables": ["question", "attached_files", "answer_format"],
        "prompt_template": (
            "Use the attached files or project sources as the authority.\n\n"
            "Question: {{question}}\n"
            "Attached files or source names: {{attached_files}}\n"
            "Preferred answer format: {{answer_format}}\n\n"
            "Answer only from the provided sources when possible. Include source names, page or section hints, "
            "and say when the files do not contain enough evidence."
        ),
        "expected_result": "document-grounded answer with source hints and uncertainty",
    },
    {
        "id": "data-analysis-starter",
        "workflow_id": "data-analysis-workflow",
        "title": "Local data analysis",
        "variables": ["dataset_description", "analysis_goal", "output_needed"],
        "prompt_template": (
            "Use local tools for this data analysis task.\n\n"
            "Dataset: {{dataset_description}}\n"
            "Analysis goal: {{analysis_goal}}\n"
            "Needed output: {{output_needed}}\n\n"
            "Plan the analysis, write or describe the Python/pandas steps, identify data-quality issues, "
            "and summarize the result in plain language."
        ),
        "expected_result": "analysis plan, code/tool steps, and local artifact guidance",
    },
    {
        "id": "image-generation-starter",
        "workflow_id": "image-generation-workflow",
        "title": "Local Flux image generation or edit",
        "variables": ["subject", "style", "constraints"],
        "prompt_template": (
            "Prepare a local ComfyUI Flux image request.\n\n"
            "Subject: {{subject}}\n"
            "Style and mood: {{style}}\n"
            "Constraints, edits, mask, or outpaint notes: {{constraints}}\n\n"
            "Return one polished image prompt, one negative prompt if useful, and exact edit notes for OpenWebUI Images."
        ),
        "expected_result": "copy-ready image prompt and edit instructions",
    },
    {
        "id": "image-understanding-starter",
        "workflow_id": "image-understanding-workflow",
        "title": "Local image understanding",
        "variables": ["image_task", "image_context", "answer_format"],
        "prompt_template": (
            "Use the attached image and local vision route.\n\n"
            "Image task: {{image_task}}\n"
            "Known context: {{image_context}}\n"
            "Preferred answer format: {{answer_format}}\n\n"
            "Describe what is visible, answer the task, identify uncertainty, and flag any text or chart details "
            "that should be manually verified."
        ),
        "expected_result": "vision answer with visible evidence and verification notes",
    },
    {
        "id": "voice-dictation-starter",
        "workflow_id": "voice-dictation-workflow",
        "title": "Voice dictation cleanup",
        "variables": ["transcript", "desired_output", "tone"],
        "prompt_template": (
            "Clean up this locally transcribed voice note.\n\n"
            "Transcript:\n{{transcript}}\n"
            "Desired output: {{desired_output}}\n"
            "Tone: {{tone}}\n\n"
            "Preserve meaning, remove filler, structure the result, and list action items separately."
        ),
        "expected_result": "edited note, summary, and action items",
    },
    {
        "id": "memory-personalization-starter",
        "workflow_id": "memory-personalization-workflow",
        "title": "Memory and personalization check",
        "variables": ["preference_or_memory", "current_task", "privacy_level"],
        "prompt_template": (
            "Use local personalization carefully for this task.\n\n"
            "Relevant preference or memory: {{preference_or_memory}}\n"
            "Current task: {{current_task}}\n"
            "Privacy level: {{privacy_level}}\n\n"
            "State which preference matters, which should be ignored, and produce the answer without inventing "
            "personal details."
        ),
        "expected_result": "personalized answer with explicit memory boundary",
    },
    {
        "id": "study-learning-starter",
        "workflow_id": "study-learning-workflow",
        "title": "Study coach lesson",
        "variables": ["topic", "learner_level", "stuck_point"],
        "prompt_template": (
            "Act as a local study coach.\n\n"
            "Topic: {{topic}}\n"
            "Learner level: {{learner_level}}\n"
            "Where I am stuck: {{stuck_point}}\n\n"
            "Teach with questions first, then explain step by step, give one worked example, and end with a short practice check."
        ),
        "expected_result": "guided tutoring flow with practice check",
    },
    {
        "id": "shopping-research-starter",
        "workflow_id": "shopping-research-workflow",
        "title": "Shopping research comparison",
        "variables": ["product_need", "budget", "must_have_criteria"],
        "prompt_template": (
            "Use the local shopping research route for this comparison.\n\n"
            "Need: {{product_need}}\n"
            "Budget: {{budget}}\n"
            "Must-have criteria: {{must_have_criteria}}\n\n"
            "Build a comparison table, list tradeoffs, identify source checks still needed, and remind me to verify "
            "price, stock, shipping, returns, and merchant terms before purchase."
        ),
        "expected_result": "buyer guide with comparison criteria and verification checklist",
    },
    {
        "id": "job-search-resume-starter",
        "workflow_id": "job-search-resume-workflow",
        "title": "Job search and resume tailoring",
        "variables": ["target_role", "location_or_constraints", "resume_context"],
        "prompt_template": (
            "Use local search and my attached resume context for this job-search workflow.\n\n"
            "Target role: {{target_role}}\n"
            "Location, remote, salary, or other constraints: {{location_or_constraints}}\n"
            "Resume context or attached file names: {{resume_context}}\n\n"
            "Find source-backed role patterns or listings, compare my fit, identify gaps, and draft a tailored "
            "resume summary or bullet set. Do not claim an application was submitted."
        ),
        "expected_result": "source-backed role-fit summary and tailored local resume draft",
    },
    {
        "id": "personal-finance-starter",
        "workflow_id": "personal-finance-workflow",
        "title": "Personal finance local analysis",
        "variables": ["file_or_dataset", "analysis_goal", "advice_boundary"],
        "prompt_template": (
            "Use local files and local analysis tools for this personal-finance review.\n\n"
            "File or dataset: {{file_or_dataset}}\n"
            "Analysis goal: {{analysis_goal}}\n"
            "Advice boundary: {{advice_boundary}}\n\n"
            "Identify spending categories, recurring charges, notable changes, and budget opportunities. "
            "Keep account-like data local and avoid financial, legal, tax, or investment advice."
        ),
        "expected_result": "local spending analysis, recurring-charge summary, and budget-oriented next steps",
    },
    {
        "id": "agent-actions-starter",
        "workflow_id": "agent-actions-workflow",
        "title": "Local agent action plan",
        "variables": ["goal", "allowed_tools", "approval_boundary"],
        "prompt_template": (
            "Use local agent tools only within this boundary.\n\n"
            "Goal: {{goal}}\n"
            "Allowed tools or apps: {{allowed_tools}}\n"
            "Approval boundary: {{approval_boundary}}\n\n"
            "Create a step-by-step action plan, mark which steps require approval, execute only approved safe steps, "
            "and summarize local artifacts created."
        ),
        "expected_result": "approval-aware tool plan and local artifact summary",
    },
    {
        "id": "atlas-browser-chat-starter",
        "workflow_id": "atlas-browser-chat-workflow",
        "title": "Atlas-style local browser helper",
        "variables": ["page_or_url", "browser_task", "approval_boundary"],
        "prompt_template": (
            "Use the local browser-capable agent like an Atlas-style sidecar, within this boundary.\n\n"
            "Page or URL: {{page_or_url}}\n"
            "Browser task: {{browser_task}}\n"
            "Approval boundary: {{approval_boundary}}\n\n"
            "First inspect or summarize available page context. Request approval before any browser click, form fill, "
            "download, or state-changing action. Include screenshot or rendered-page evidence when a browser action runs, "
            "and clearly say what was not verified."
        ),
        "expected_result": "browser-context summary, approval-aware action plan, and rendered evidence notes",
    },
    {
        "id": "developer-mode-mcp-app-starter",
        "workflow_id": "developer-mode-mcp-app-workflow",
        "title": "Custom MCP-style app checklist",
        "variables": ["app_goal", "operations", "governance_boundary"],
        "prompt_template": (
            "Use the local custom-app/tool-server workflow for this MCP-style app check.\n\n"
            "App goal: {{app_goal}}\n"
            "Operations to expose or test: {{operations}}\n"
            "Governance boundary: {{governance_boundary}}\n\n"
            "Map the app goal to local tool-server operations, list which operations are read-only or write-like, "
            "recommend permission mode and action controls, specify parameter constraints, and describe what should appear "
            "in a redacted audit log before the app is used with real data."
        ),
        "expected_result": "custom app setup checklist with tool discovery, permissions, action controls, and audit expectations",
    },
]


def local_parity_starter_prompts() -> dict:
    workflow_recipes = local_parity_workflow_recipes()
    gap_report = local_parity_gap_report()
    recipes_by_id = {
        item.get("id"): item
        for item in workflow_recipes.get("recipes", [])
        if isinstance(item, dict) and item.get("id")
    }
    prompts = []
    for blueprint in STARTER_PROMPT_BLUEPRINTS:
        recipe = recipes_by_id.get(blueprint.get("workflow_id")) or {}
        prompt_template = blueprint.get("prompt_template") or ""
        prompt_id = blueprint.get("id")
        command = "local_chatgpt_" + re.sub(r"[^a-z0-9_]+", "_", str(prompt_id or "").lower()).strip("_")
        prompt_name = f"Local ChatGPT: {blueprint.get('title')}"
        route_family = recipe.get("openwebui_route_id")
        ready = (
            bool(recipe)
            and bool(prompt_template.strip())
            and bool(blueprint.get("variables"))
            and bool(recipe.get("openwebui_route_id"))
            and bool(command)
        )
        prompts.append(
            {
                "id": prompt_id,
                "title": blueprint.get("title"),
                "workflow_id": blueprint.get("workflow_id"),
                "task_id": recipe.get("task_id"),
                "status": "ready" if ready else "needs_attention",
                "openwebui_command": command,
                "openwebui_prompt_name": prompt_name,
                "openwebui_entrypoint": recipe.get("openwebui_entrypoint"),
                "openwebui_route_id": recipe.get("openwebui_route_id"),
                "route_family": route_family,
                "openwebui_model": recipe.get("openwebui_model"),
                "openwebui_route_type": recipe.get("openwebui_route_type"),
                "openwebui_action": recipe.get("openwebui_action"),
                "variables": blueprint.get("variables") or [],
                "prompt_template": prompt_template,
                "expected_result": blueprint.get("expected_result"),
                "copy_target": "OpenWebUI chat composer or the matching local tool route",
                "evidence_endpoints": recipe.get("evidence_endpoints") or [],
                "optional_case_ids": recipe.get("optional_case_ids") or [],
            }
        )

    ready_prompts = [prompt for prompt in prompts if prompt.get("status") == "ready"]
    route_ids = sorted({prompt.get("openwebui_route_id") for prompt in prompts if prompt.get("openwebui_route_id")})
    workflow_ids = sorted({prompt.get("workflow_id") for prompt in prompts if prompt.get("workflow_id")})
    self_contained_prompts = [
        prompt
        for prompt in prompts
        if prompt.get("openwebui_command")
        and prompt.get("openwebui_prompt_name")
        and prompt.get("route_family")
        and prompt.get("openwebui_model")
        and prompt.get("prompt_template")
    ]
    prompt_library_items = []
    for prompt in prompts:
        prompt_library_items.append(
            {
                "id": prompt.get("id"),
                "command": prompt.get("openwebui_command"),
                "name": prompt.get("openwebui_prompt_name"),
                "content": prompt.get("prompt_template"),
                "data": {
                    "source": "chatgpt-local-starter-prompts",
                    "workflow_id": prompt.get("workflow_id"),
                    "task_id": prompt.get("task_id"),
                    "openwebui_route_id": prompt.get("openwebui_route_id"),
                    "route_family": prompt.get("route_family"),
                    "openwebui_model": prompt.get("openwebui_model"),
                    "variables": prompt.get("variables") or [],
                    "expected_result": prompt.get("expected_result"),
                    "local_only": True,
                },
                "meta": {
                    "description": prompt.get("expected_result"),
                    "starter_prompt_id": prompt.get("id"),
                    "workflow_id": prompt.get("workflow_id"),
                    "openwebui_entrypoint": prompt.get("openwebui_entrypoint"),
                    "copy_target": prompt.get("copy_target"),
                    "tags": ["chatgpt-local-parity", "starter-prompt", prompt.get("openwebui_route_id")],
                },
                "tags": ["chatgpt-local-parity", "starter-prompt", str(prompt.get("openwebui_route_id") or "local")],
                "access_grants": [],
                "commit_message": "Import local ChatGPT starter prompt",
            }
        )
    openwebui_import_items = [
        {"command": item.get("command"), "name": item.get("name"), "content": item.get("content")}
        for item in prompt_library_items
    ]
    gap_summary = gap_report.get("summary") if isinstance(gap_report.get("summary"), dict) else {}
    return {
        "source": "chatgpt-local-starter-prompts",
        "generated_at": now(),
        "status": "ready" if len(ready_prompts) == len(prompts) else "needs_attention",
        "summary": {
            "starter_prompts": len(prompts),
            "ready_starter_prompts": len(ready_prompts),
            "prompt_library_items": len(prompt_library_items),
            "openwebui_import_items": len(openwebui_import_items),
            "workflow_linked_prompts": len([prompt for prompt in prompts if prompt.get("workflow_id") in recipes_by_id]),
            "ready_workflow_linked_prompts": len(
                [
                    prompt
                    for prompt in prompts
                    if recipes_by_id.get(prompt.get("workflow_id"), {}).get("status") == "ready"
                ]
            ),
            "self_contained_prompts": len(self_contained_prompts),
            "self_contained_prompt_metadata": len(self_contained_prompts) == len(prompts),
            "route_coverage_count": len(route_ids),
            "template_prompt_bodies_included": True,
            "user_prompt_bodies_excluded": True,
            "open_gaps": gap_summary.get("open_gaps", 0),
            "completion_status": LOCAL_PARITY_COMPLETION_STATUS
            if not gap_summary.get("open_gaps", 0)
            else "needs_attention",
        },
        "workflow_ids": workflow_ids,
        "route_coverage": route_ids,
        "usage_notes": [
            "Copy and paste one template into the matching OpenWebUI chat or local tool route.",
            "Replace {{variables}} with task-specific content before sending.",
            "These templates are static examples and are not copied from user chat history.",
        ],
        "prompts": prompts,
        "prompt_library_items": prompt_library_items,
        "openwebui_import_items": openwebui_import_items,
        "claim_boundary": (
            "These are static starter templates for local OpenWebUI use. They do not include user chat history, "
            "private prompt logs, or hosted ChatGPT system behavior."
        ),
        "remaining_gap_ids": [gap.get("id") for gap in gap_report.get("gaps", []) if isinstance(gap, dict)],
        "privacy": {
            "local_only": True,
            "static_templates_only": True,
            "openwebui_prompt_import_ready": len(prompt_library_items) == len(prompts),
            "template_prompt_bodies_included": True,
            "user_prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_dashboard() -> dict:
    popular_task_routes = local_parity_popular_task_routes()
    workflow_recipes = local_parity_workflow_recipes()
    starter_prompts = local_parity_starter_prompts()
    quality_scorecard = local_parity_quality_scorecard()
    route_recommendations = local_model_route_recommendations()
    capacity_plan = local_parity_capacity_plan(route_recommendations=route_recommendations)
    action_playbook = local_parity_action_playbook(route_recommendations=route_recommendations)
    live_status = local_parity_live_status()
    gap_report = local_parity_gap_report()
    source_freshness = local_parity_source_freshness()
    evidence_trace = local_parity_evidence_trace()
    optional_heavy_evidence = local_parity_optional_heavy_evidence()
    improvement_plan = local_parity_improvement_plan()
    readiness_checklist = local_parity_readiness_checklist()
    popular_summary = popular_task_routes.get("summary") or {}
    workflow_summary = workflow_recipes.get("summary") or {}
    starter_summary = starter_prompts.get("summary") or {}
    scorecard_summary = quality_scorecard.get("summary") or {}
    capacity_summary = capacity_plan.get("summary") or {}
    playbook_summary = action_playbook.get("summary") or {}
    gap_summary = gap_report.get("summary") or {}
    live_summary = live_status.get("summary") or {}
    evidence_summary = evidence_trace.get("summary") or {}
    optional_summary = optional_heavy_evidence.get("summary") or {}
    improvement_summary = improvement_plan.get("summary") or {}
    readiness_summary = readiness_checklist.get("summary") or {}
    source_summary = source_freshness.get("summary") or {}
    route_profiles = route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}
    benchmark_summary = route_recommendations.get("benchmark_summary") or {}
    route_statuses = {key: profile.get("status") for key, profile in sorted(route_profiles.items())}
    status = (
        "ready"
        if popular_task_routes.get("status") == "ready"
        and workflow_recipes.get("status") == "ready"
        and starter_prompts.get("status") == "ready"
        and action_playbook.get("status") == "ready"
        and quality_scorecard.get("local_quality_status") == "ready"
        and capacity_plan.get("status") == "ready"
        and live_status.get("live_status") == "ready"
        and evidence_trace.get("evidence_status") == "ready"
        and optional_heavy_evidence.get("status") == "ready"
        and improvement_plan.get("status") == "ready"
        and readiness_checklist.get("local_functional_status") == "ready"
        and all(status == "ready" for status in route_statuses.values())
        else "needs_attention"
    )
    return {
        "source": "chatgpt-local-parity-dashboard",
        "generated_at": now(),
        "status": status,
        "summary": {
            "local_functional_status": status,
            "completion_status": LOCAL_PARITY_COMPLETION_STATUS
            if not gap_summary.get("open_gaps", 0)
            else "needs_attention",
            "open_gaps": gap_summary.get("open_gaps", 0),
            "scope_exclusion_items": gap_summary.get("scope_exclusion_items", 0),
            "frontier_boundary_items": gap_summary.get("frontier_boundary_items", 0),
            "frontier_boundary_ready_local_mitigations": gap_summary.get(
                "frontier_boundary_ready_local_mitigations", 0
            ),
            "frontier_boundary_excluded_from_local_goal_items": gap_summary.get(
                "frontier_boundary_excluded_from_local_goal_items", 0
            ),
            "frontier_boundary_not_locally_provable_items": gap_summary.get(
                "frontier_boundary_not_locally_provable_items", 0
            ),
            "popular_tasks": popular_summary.get("popular_tasks", 0),
            "ready_popular_tasks": popular_summary.get("ready_tasks", 0),
            "workflow_recipes": workflow_summary.get("workflow_recipes", 0),
            "ready_workflow_recipes": workflow_summary.get("ready_workflow_recipes", 0),
            "starter_prompts": starter_summary.get("starter_prompts", 0),
            "ready_starter_prompts": starter_summary.get("ready_starter_prompts", 0),
            "starter_prompt_library_items": starter_summary.get("prompt_library_items", 0),
            "action_playbook_status": action_playbook.get("status"),
            "playbook_items": playbook_summary.get("playbook_items", 0),
            "ready_playbook_items": playbook_summary.get("ready_playbook_items", 0),
            "playbook_starter_commands": playbook_summary.get("starter_commands", 0),
            "playbook_hosted_boundary_items": playbook_summary.get("hosted_boundary_items", 0),
            "route_coverage_count": popular_summary.get("route_coverage_count", 0),
            "route_profiles": scorecard_summary.get("route_profiles", 0),
            "route_profiles_ready": scorecard_summary.get("route_profiles_ready") is True,
            "best_local_tps": scorecard_summary.get("best_local_tps", 0),
            "capacity_plan_status": capacity_plan.get("status"),
            "capacity_routes": capacity_summary.get("routes", 0),
            "ready_capacity_routes": capacity_summary.get("ready_routes", 0),
            "verified_context_routes": capacity_summary.get("verified_context_routes", 0),
            "max_verified_context_tokens": capacity_summary.get("max_verified_context_tokens", 0),
            "hosted_capacity_equivalent": capacity_summary.get("hosted_capacity_equivalent"),
            "benchmark_freshness_status": benchmark_summary.get("freshness_status"),
            "stale_benchmark_suites": benchmark_summary.get("stale_suites") or [],
            "benchmark_max_age_seconds": benchmark_summary.get("max_age_seconds"),
            "glm_context_tokens": 65536,
            "slopcode_context_tokens": 65536,
            "live_probes": live_summary.get("probes", 0),
            "ready_live_probes": live_summary.get("ready_probes", 0),
            "evidence_artifacts": evidence_summary.get("artifacts", 0),
            "ready_evidence_artifacts": evidence_summary.get("ready_artifacts", 0),
            "optional_heavy_evidence_status": optional_heavy_evidence.get("status"),
            "optional_heavy_cases": optional_summary.get("optional_cases", 0),
            "ready_optional_heavy_cases": optional_summary.get("ready_optional_cases", 0),
            "source_freshness_status": source_freshness.get("freshness_status"),
            "current_release_source_id": source_summary.get("current_release_source_id"),
            "current_release_coverage_ready": source_summary.get("current_release_coverage_ready") is True,
            "current_release_covered_families": source_summary.get("current_release_covered_families", 0),
            "current_release_expected_families": source_summary.get("current_release_expected_families", 0),
            "current_release_covered_evidence_terms": source_summary.get(
                "current_release_covered_evidence_terms", 0
            ),
            "current_release_expected_evidence_terms": source_summary.get(
                "current_release_expected_evidence_terms", 0
            ),
            "improvement_plan_status": improvement_plan.get("status"),
            "improvement_plan_tracks": improvement_summary.get("tracks", 0),
            "ready_improvement_plan_tracks": improvement_summary.get("ready_tracks", 0),
            "readiness_checklist_status": readiness_checklist.get("local_functional_status"),
            "objective_requirements": readiness_summary.get("requirements", 0),
            "passed_objective_requirements": readiness_summary.get("passed_requirements", 0),
            "not_locally_provable_requirements": readiness_summary.get("not_locally_provable_requirements", 0),
        },
        "urls": {
            "openwebui": "http://127.0.0.1:8080",
            "glm52_q8_openai": "http://127.0.0.1:11446/v1",
            "glm52_openai": "http://127.0.0.1:11441/v1",
            "slopcode_openai": "http://127.0.0.1:11438/v1",
            "deep_research_openai": "http://127.0.0.1:18041/v1",
            "local_scheduler": PUBLIC_BASE_URL,
            "local_agent_openai": "http://127.0.0.1:18043/v1",
            "local_vision_openai": "http://127.0.0.1:18044/v1",
            "comfyui": "http://127.0.0.1:8188",
            "searxng": "http://127.0.0.1:18080",
            "tika": "http://127.0.0.1:9998",
            "jupyter": "http://127.0.0.1:8888",
        },
        "primary_models": [
            {"id": "local-chatgpt-auto", "route": "fast_router", "best_for": "default local ChatGPT-like routing"},
            {"id": "glm52-q8-local", "route": "glm_tiny", "context_tokens": 65536, "best_for": "enterprise 8-bit private long-context reasoning"},
            {"id": "glm52-q4-local", "route": "glm_tiny", "context_tokens": 65536, "best_for": "private long-context reasoning"},
            {
                "id": "qwen3.6-35b-a3b:slopcode-cpu-64k",
                "route": "slopcode_tiny",
                "context_tokens": 65536,
                "best_for": "local coding help",
            },
            {"id": "deep-research-glm52", "route": "deep_research", "best_for": "local cited research"},
            {"id": "local-agent-glm52", "route": "local_agent", "best_for": "tool and agent workflows"},
            {"id": "local-vision-gemma4-12b", "route": "local_vision", "best_for": "image understanding"},
            {"id": "flux-2-klein-9b-fp8", "route": "comfyui_flux", "best_for": "image generation"},
            {"id": "whisper-base-bundled", "route": "local_whisper_stt", "best_for": "speech-to-text"},
        ],
        "route_profiles": {
            key: {
                "status": profile.get("status"),
                "default_model": profile.get("default_model"),
                "best_for": profile.get("best_for") or [],
                "target_tps": profile.get("target_tps"),
                "best_tps": ((profile.get("benchmark") or {}).get("best_tps") if isinstance(profile.get("benchmark"), dict) else None),
                "freshness_status": profile.get("freshness_status"),
                "latest_age_seconds": (
                    (profile.get("benchmark") or {}).get("latest_age_seconds")
                    if isinstance(profile.get("benchmark"), dict)
                    else None
                ),
                "recommendation": profile.get("recommendation"),
            }
            for key, profile in sorted(route_profiles.items())
            if isinstance(profile, dict)
        },
        "popular_tasks": [
            {
                "id": item.get("id"),
                "task": item.get("task"),
                "status": item.get("status"),
                "route": (item.get("selected_route") or {}).get("openwebui_route_id")
                if isinstance(item.get("selected_route"), dict)
                else None,
                "model": (item.get("selected_route") or {}).get("openwebui_model")
                if isinstance(item.get("selected_route"), dict)
                else None,
            }
            for item in popular_task_routes.get("tasks", [])
            if isinstance(item, dict)
        ],
        "remaining_gap": {
            "ids": [gap.get("id") for gap in gap_report.get("gaps", []) if isinstance(gap, dict)],
            "claim": gap_report.get("claim"),
            "next_actions": gap_report.get("next_actions") or [],
        },
        "verification": {
            "default_parity": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "service_status": "./scripts/status-parity.sh",
            "workflow_recipes": f"{PUBLIC_BASE_URL}/local-parity/workflows",
            "starter_prompts": f"{PUBLIC_BASE_URL}/local-parity/starter-prompts",
            "action_playbook": f"{PUBLIC_BASE_URL}/local-parity/playbook",
            "html_dashboard": f"{PUBLIC_BASE_URL}/local-parity/index.html",
            "starter_prompts_html": f"{PUBLIC_BASE_URL}/local-parity/starter-prompts.html",
            "feature_map_html": f"{PUBLIC_BASE_URL}/local-parity/feature-map.html",
            "runbook_html": f"{PUBLIC_BASE_URL}/local-parity/runbook.html",
            "route_map_html": f"{PUBLIC_BASE_URL}/local-parity/route-map.html",
            "action_playbook_html": f"{PUBLIC_BASE_URL}/local-parity/playbook.html",
            "quality_scorecard_html": f"{PUBLIC_BASE_URL}/local-parity/quality-scorecard.html",
            "capacity_plan_html": f"{PUBLIC_BASE_URL}/local-parity/capacity-plan.html",
            "optional_heavy_evidence_html": f"{PUBLIC_BASE_URL}/local-parity/optional-evidence.html",
            "live_status_html": f"{PUBLIC_BASE_URL}/local-parity/live-status.html",
            "source_freshness_html": f"{PUBLIC_BASE_URL}/local-parity/source-freshness.html",
            "continuity_html": f"{PUBLIC_BASE_URL}/local-parity/continuity.html",
            "frontier_boundary_html": f"{PUBLIC_BASE_URL}/local-parity/frontier-boundary.html",
            "gap_report_html": f"{PUBLIC_BASE_URL}/local-parity/gap-report.html",
            "improvement_plan_html": f"{PUBLIC_BASE_URL}/local-parity/improvement-plan.html",
            "readiness_checklist_html": f"{PUBLIC_BASE_URL}/local-parity/readiness-checklist.html",
            "audit_html": f"{PUBLIC_BASE_URL}/local-parity/audit.html",
            "evidence": f"{PUBLIC_BASE_URL}/local-parity/evidence",
            "live_status": f"{PUBLIC_BASE_URL}/local-parity/live-status",
            "source_freshness": f"{PUBLIC_BASE_URL}/local-parity/source-freshness",
            "continuity": f"{PUBLIC_BASE_URL}/local-parity/continuity",
            "frontier_boundary": f"{PUBLIC_BASE_URL}/local-parity/frontier-boundary",
            "capacity_plan": f"{PUBLIC_BASE_URL}/local-parity/capacity-plan",
            "optional_heavy_evidence": f"{PUBLIC_BASE_URL}/local-parity/optional-evidence",
            "gap_report": f"{PUBLIC_BASE_URL}/local-parity/gap",
            "improvement_plan": f"{PUBLIC_BASE_URL}/local-parity/improvement-plan",
            "readiness_checklist": f"{PUBLIC_BASE_URL}/local-parity/readiness-checklist",
            "audit": f"{PUBLIC_BASE_URL}/local-parity/audit",
        },
        "privacy": {
            "local_only": True,
            "loopback_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_dashboard_html() -> str:
    dashboard = local_parity_dashboard()
    summary = dashboard.get("summary") or {}
    urls = dashboard.get("urls") or {}
    routes = dashboard.get("route_profiles") or {}
    tasks = dashboard.get("popular_tasks") or []
    remaining_gap = dashboard.get("remaining_gap") or {}
    verification = dashboard.get("verification") or {}
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(dashboard.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    def endpoint_link(label: str, url: str) -> str:
        return f'<a href="{text(url)}">{text(label)}</a>'

    route_rows = []
    for route_id, route in sorted(routes.items()):
        if not isinstance(route, dict):
            continue
        route_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(route_id)}</code></td>",
                    f"<td>{text(route.get('default_model'))}</td>",
                    f'<td><span class="status status-{status_class(route.get("status"))}">{text(route.get("status"))}</span></td>',
                    f"<td>{text(route.get('best_tps'))}</td>",
                    f"<td>{text(route.get('freshness_status'))}</td>",
                    f"<td>{text(', '.join(route.get('best_for') or []))}</td>",
                    "</tr>",
                ]
            )
        )

    task_rows = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td>{text(task.get('task'))}</td>",
                    f"<td><code>{text(task.get('model'))}</code></td>",
                    f"<td><code>{text(task.get('route'))}</code></td>",
                    f'<td><span class="status status-{status_class(task.get("status"))}">{text(task.get("status"))}</span></td>',
                    "</tr>",
                ]
            )
        )

    endpoint_items = [
        ("OpenWebUI", urls.get("openwebui")),
        ("Starter Prompts HTML", verification.get("starter_prompts_html")),
        ("Feature Map HTML", verification.get("feature_map_html")),
        ("Runbook HTML", verification.get("runbook_html")),
        ("Route Map HTML", verification.get("route_map_html")),
        ("Action Playbook HTML", verification.get("action_playbook_html")),
        ("Quality Scorecard HTML", verification.get("quality_scorecard_html")),
        ("Capacity Plan HTML", verification.get("capacity_plan_html")),
        ("Optional Evidence HTML", verification.get("optional_heavy_evidence_html")),
        ("Live Status HTML", verification.get("live_status_html")),
        ("Source Freshness HTML", verification.get("source_freshness_html")),
        ("Continuity HTML", verification.get("continuity_html")),
        ("Frontier Boundary HTML", verification.get("frontier_boundary_html")),
        ("Gap Report HTML", verification.get("gap_report_html")),
        ("Improvement Plan HTML", verification.get("improvement_plan_html")),
        ("Readiness Checklist HTML", verification.get("readiness_checklist_html")),
        ("Completion Audit HTML", verification.get("audit_html")),
        ("Feature Matrix JSON", f"{PUBLIC_BASE_URL}/local-parity/feature-matrix"),
        ("Runbook JSON", f"{PUBLIC_BASE_URL}/local-parity/runbook"),
        ("Workflow Recipes JSON", verification.get("workflow_recipes")),
        ("Starter Prompts JSON", verification.get("starter_prompts")),
        ("Action Playbook JSON", verification.get("action_playbook")),
        ("Evidence Trace JSON", verification.get("evidence")),
        ("Live Status JSON", verification.get("live_status")),
        ("Source Freshness JSON", verification.get("source_freshness")),
        ("Continuity JSON", verification.get("continuity")),
        ("Frontier Boundary JSON", verification.get("frontier_boundary")),
        ("Capacity Plan JSON", verification.get("capacity_plan")),
        ("Gap Report JSON", verification.get("gap_report")),
        ("Readiness Checklist JSON", verification.get("readiness_checklist")),
        ("Audit JSON", verification.get("audit")),
        ("Service Status Command", None),
    ]
    endpoint_links = []
    for label, url in endpoint_items:
        if url:
            endpoint_links.append(f"<li>{endpoint_link(label, str(url))}</li>")
        else:
            endpoint_links.append(f"<li><code>{text(verification.get('service_status'))}</code></li>")

    next_actions = []
    for action in remaining_gap.get("next_actions") or []:
        next_actions.append(f"<li>{text(action)}</li>")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Parity Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px 20px 40px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 22px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.92em; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 18px; }}
    .metric {{ min-height: 96px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 720px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.4; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready, .status-current {{ background: #e3f4ea; color: #175734; }}
    .status-not-complete-for-full-hosted-chatgpt-parity {{ background: #fff0cc; color: #6f4b00; }}
    .status-needs_attention, .status-not_ready {{ background: #fde8e4; color: #7f231c; }}
    .gap {{ border-left: 4px solid #b7791f; }}
    .links {{ columns: 2 260px; padding-left: 18px; margin: 0; }}
    .links li {{ break-inside: avoid; margin: 0 0 8px; }}
    .actions {{ margin: 10px 0 0; padding-left: 18px; }}
    .actions li {{ margin-bottom: 7px; line-height: 1.45; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-dashboard="html" data-status="{text(dashboard.get('status'))}" data-completion-status="{text(summary.get('completion_status'))}" data-current-release-source="{text(summary.get('current_release_source_id'))}" data-current-release-families="{text(summary.get('current_release_covered_families'))}/{text(summary.get('current_release_expected_families'))}" data-current-release-terms="{text(summary.get('current_release_covered_evidence_terms'))}/{text(summary.get('current_release_expected_evidence_terms'))}" data-frontier-boundary-items="{text(summary.get('frontier_boundary_items'))}" data-frontier-boundary-ready="{text(summary.get('frontier_boundary_ready_local_mitigations'))}" data-frontier-boundary-not-provable="{text(summary.get('frontier_boundary_not_locally_provable_items'))}" data-playbook-items="{text(summary.get('playbook_items'))}" data-playbook-ready="{text(summary.get('ready_playbook_items'))}" data-capacity-routes="{text(summary.get('capacity_routes'))}" data-capacity-ready="{text(summary.get('ready_capacity_routes'))}" data-max-verified-context="{text(summary.get('max_verified_context_tokens'))}">
    <header>
      <div>
        <h1>Local ChatGPT Parity Dashboard</h1>
        <p>OpenWebUI local functional status is <span class="status status-{status_class(summary.get('local_functional_status'))}">{text(summary.get('local_functional_status'))}</span>; hosted cloud equivalence is treated as an explicit scope exclusion.</p>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Parity summary">
      {metric("Popular tasks ready", f"{summary.get('ready_popular_tasks')}/{summary.get('popular_tasks')}", "popular ChatGPT-style tasks")}
      {metric("Workflow recipes", f"{summary.get('ready_workflow_recipes')}/{summary.get('workflow_recipes')}", "OpenWebUI route recipes")}
      {metric("Starter prompts", f"{summary.get('ready_starter_prompts')}/{summary.get('starter_prompts')}", "installed prompt-library pack")}
      {metric("Action playbook", f"{summary.get('ready_playbook_items')}/{summary.get('playbook_items')}", "task-to-route rows")}
      {metric("Evidence artifacts", f"{summary.get('ready_evidence_artifacts')}/{summary.get('evidence_artifacts')}", "local proof surface")}
      {metric("Current release", f"{summary.get('current_release_covered_families')}/{summary.get('current_release_expected_families')}", "families")}
      {metric("Release evidence", f"{summary.get('current_release_covered_evidence_terms')}/{summary.get('current_release_expected_evidence_terms')}", "terms")}
      {metric("Boundary matrix", f"{summary.get('frontier_boundary_ready_local_mitigations')}/{summary.get('frontier_boundary_items')}", "local mitigations")}
      {metric("Capacity routes", f"{summary.get('ready_capacity_routes')}/{summary.get('capacity_routes')}", "route budgets")}
      {metric("Benchmark freshness", summary.get('benchmark_freshness_status'), "route baselines")}
      {metric("Best stored TPS", summary.get('best_local_tps'), "completion tokens/sec")}
      {metric("GLM context", summary.get('glm_context_tokens'), "tokens")}
      {metric("Slopcode context", summary.get('slopcode_context_tokens'), "tokens")}
      {metric("Objective checklist", f"{summary.get('passed_objective_requirements')}/{summary.get('objective_requirements')}", "local requirements passed")}
    </section>
    <section class="panel">
      <h2>Local Model Routes</h2>
      <table data-route-profiles="local-chatgpt">
        <thead><tr><th>Route</th><th>Default model</th><th>Status</th><th>Best TPS</th><th>Freshness</th><th>Best for</th></tr></thead>
        <tbody>{''.join(route_rows)}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Popular Task Coverage</h2>
      <table data-popular-tasks="local-chatgpt">
        <thead><tr><th>Task</th><th>Model</th><th>Route</th><th>Status</th></tr></thead>
        <tbody>{''.join(task_rows)}</tbody>
      </table>
    </section>
    <section class="panel gap" data-remaining-gap="{text(','.join(remaining_gap.get('ids') or []))}">
      <h2>Remaining Boundary</h2>
      <p>{text(remaining_gap.get('claim'))}</p>
      <ul class="actions">{''.join(next_actions)}</ul>
    </section>
    <section class="panel">
      <h2>Verification Links</h2>
      <ul class="links">{''.join(endpoint_links)}</ul>
    </section>
  </main>
</body>
</html>"""


def local_parity_feature_map_html() -> str:
    matrix = local_parity_feature_matrix("", 200)
    summary = matrix.get("summary") or {}
    rows = matrix.get("feature_families") or []
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(matrix.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    table_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        models = ", ".join(row.get("primary_models") or [])
        counts = (
            f"sources {len(row.get('source_ids') or [])}; "
            f"verifiers {row.get('required_verifier_count')}; "
            f"evals {row.get('quality_eval_count')}"
        )
        table_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(row.get('feature_family'))}</strong></td>",
                    f"<td>{text(row.get('sample_use_case'))}</td>",
                    f"<td>{text(row.get('local_path'))}</td>",
                    f"<td><code>{text(models)}</code></td>",
                    f"<td>{text(counts)}</td>",
                    f'<td><span class="status status-{status_class(row.get("status"))}">{text(row.get("status"))}</span></td>',
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Feature Map</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 84px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 0; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1040px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; position: sticky; top: 0; }}
    tr:last-child td {{ border-bottom: 0; }}
    td:nth-child(1) {{ width: 18%; }}
    td:nth-child(2) {{ width: 24%; }}
    td:nth-child(3) {{ width: 26%; }}
    td:nth-child(4) {{ width: 16%; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready, .status-implemented {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-feature-map="html" data-status="{text(matrix.get('matrix_status'))}" data-feature-families="{text(summary.get('feature_families'))}">
    <header>
      <div>
        <h1>Local ChatGPT Feature Map</h1>
        <p>All mapped ChatGPT feature families are shown with sample use cases, local OpenWebUI paths, models, source coverage, and verifier coverage.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/starter-prompts.html">Starter Prompts</a>
          <a href="/local-parity/runbook.html">Runbook</a>
          <a href="/local-parity/route-map.html">Route Map</a>
          <a href="/local-parity/quality-scorecard.html">Quality Scorecard</a>
          <a href="/local-parity/optional-evidence.html">Optional Evidence</a>
          <a href="/local-parity/live-status.html">Live Status</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/feature-matrix">Feature Matrix JSON</a>
          <a href="/local-parity/runbook">Runbook JSON</a>
          <a href="/local-parity/evidence">Evidence JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Feature map summary">
      <section class="metric"><span>Feature families</span><strong>{text(summary.get('feature_families'))}</strong></section>
      <section class="metric"><span>Ready families</span><strong>{text(summary.get('ready_feature_families'))}</strong></section>
      <section class="metric"><span>Source covered</span><strong>{text(summary.get('source_covered_feature_families'))}</strong></section>
      <section class="metric"><span>Verifier covered</span><strong>{text(summary.get('verifier_covered_feature_families'))}</strong></section>
      <section class="metric"><span>Quality eval covered</span><strong>{text(summary.get('quality_eval_feature_families'))}</strong></section>
      <section class="metric"><span>High-priority eval covered</span><strong>{text(summary.get('high_priority_quality_eval_feature_families'))}</strong></section>
    </section>
    <section class="panel">
      <table data-feature-map="local-chatgpt">
        <thead><tr><th>Feature family</th><th>Sample use case</th><th>Local OpenWebUI path</th><th>Primary models/tools</th><th>Coverage</th><th>Status</th></tr></thead>
        <tbody>{''.join(table_rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_runbook_html() -> str:
    runbook = local_parity_runbook("", 200)
    summary = runbook.get("summary") or {}
    entries = runbook.get("entries") or []
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(runbook.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        coverage = (
            f"sources {len(entry.get('source_ids') or [])}; "
            f"verifiers {entry.get('required_verifier_count')}; "
            f"optional {entry.get('optional_verifier_count')}; "
            f"evals {entry.get('quality_eval_count')}"
        )
        benchmark = []
        if entry.get("benchmark_suite"):
            benchmark.append(f"suite {entry.get('benchmark_suite')}")
        if entry.get("best_tps") is not None:
            benchmark.append(f"best {entry.get('best_tps')} tps")
        if entry.get("target_tps") is not None:
            benchmark.append(f"target {entry.get('target_tps')} tps")
        if entry.get("benchmark_freshness_status"):
            benchmark.append(str(entry.get("benchmark_freshness_status")))
        commands = " | ".join(entry.get("verification_commands") or [])
        route = (
            f"{entry.get('openwebui_route_id') or ''}"
            f" / {entry.get('openwebui_route_type') or ''}"
        ).strip(" /")
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(entry.get('feature_family'))}</strong><br><small>{text(entry.get('sample_use_case'))}</small></td>",
                    f"<td><code>{text(entry.get('openwebui_model'))}</code><br><small>{text(route)}</small></td>",
                    f"<td>{text(entry.get('openwebui_action'))}<br><small>{text(entry.get('local_path'))}</small></td>",
                    f"<td>{text('; '.join(benchmark) or 'local tool route')}</td>",
                    f"<td>{text(coverage)}</td>",
                    f"<td><code>{text(commands)}</code></td>",
                    f'<td><span class="status status-{status_class(entry.get("status"))}">{text(entry.get("status"))}</span></td>',
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Runbook</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1360px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small {{ color: #59655f; line-height: 1.35; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 0; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1260px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; position: sticky; top: 0; }}
    tr:last-child td {{ border-bottom: 0; }}
    td:nth-child(1) {{ width: 20%; }}
    td:nth-child(2) {{ width: 15%; }}
    td:nth-child(3) {{ width: 23%; }}
    td:nth-child(6) {{ width: 16%; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-runbook="html" data-status="{text(runbook.get('runbook_status'))}" data-feature-families="{text(summary.get('feature_families'))}" data-ready="{text(summary.get('ready_entries'))}" data-recommended-models="{text(summary.get('recommended_models'))}">
    <header>
      <div>
        <h1>Local ChatGPT Runbook</h1>
        <p>Every mapped ChatGPT feature family has a local OpenWebUI model or tool route, an action path, source and verifier coverage, and refresh commands.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/feature-map.html">Feature Map</a>
          <a href="/local-parity/route-map.html">Route Map</a>
          <a href="/local-parity/starter-prompts.html">Starter Prompts</a>
          <a href="/local-parity/quality-scorecard.html">Quality Scorecard</a>
          <a href="/local-parity/optional-evidence.html">Optional Evidence</a>
          <a href="/local-parity/live-status.html">Live Status</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/runbook">Runbook JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Runbook summary">
      {metric("Feature families", summary.get('feature_families'), "mapped rows")}
      {metric("Ready entries", f"{summary.get('ready_entries')}/{summary.get('feature_families')}", "source, route, verifier")}
      {metric("Route ready", summary.get('route_ready_entries'), "local routes")}
      {metric("Benchmarked chat routes", summary.get('benchmarked_chat_route_entries'), "route profiles")}
      {metric("Local tool routes", summary.get('local_tool_route_entries'), "tool and preset paths")}
      {metric("Recommended models", summary.get('recommended_models'), "unique local selections")}
    </section>
    <section class="panel">
      <table data-runbook="local-chatgpt">
        <thead><tr><th>Feature family</th><th>Model and route</th><th>OpenWebUI action</th><th>Benchmark</th><th>Coverage</th><th>Verify</th><th>Status</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_route_map_html() -> str:
    popular_tasks = local_parity_popular_task_routes()
    workflows = local_parity_workflow_recipes()
    starter_prompts = local_parity_starter_prompts()
    tasks = popular_tasks.get("tasks") or []
    recipes_by_task = {
        recipe.get("task_id"): recipe
        for recipe in workflows.get("recipes", [])
        if isinstance(recipe, dict) and recipe.get("task_id")
    }
    prompts_by_task = {
        prompt.get("task_id"): prompt
        for prompt in starter_prompts.get("prompts", [])
        if isinstance(prompt, dict) and prompt.get("task_id")
    }
    commands_by_prompt_id = {
        item.get("id"): item.get("command")
        for item in starter_prompts.get("prompt_library_items", [])
        if isinstance(item, dict) and item.get("id")
    }
    summary = popular_tasks.get("summary") or {}
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(popular_tasks.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    rows = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        route = task.get("selected_route") if isinstance(task.get("selected_route"), dict) else {}
        recipe = recipes_by_task.get(task_id) or {}
        prompt = prompts_by_task.get(task_id) or {}
        command = commands_by_prompt_id.get(prompt.get("id"))
        steps = recipe.get("steps") or []
        artifacts = recipe.get("expected_local_artifacts") or []
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(task.get('task'))}</strong><br><small>{text(task_id)}</small></td>",
                    f"<td><code>{text(route.get('openwebui_model') or recipe.get('openwebui_model'))}</code><br><small>{text(route.get('openwebui_route_id') or recipe.get('openwebui_route_id'))}</small></td>",
                    f"<td>{text(recipe.get('openwebui_entrypoint'))}<br><small>{text(recipe.get('openwebui_action'))}</small></td>",
                    f"<td><code>{text(command)}</code><br><small>{text(prompt.get('title'))}</small></td>",
                    f"<td>{text(' | '.join(steps[:2]))}</td>",
                    f"<td>{text(', '.join(artifacts))}</td>",
                    f'<td><span class="status status-{status_class(task.get("status"))}">{text(task.get("status"))}</span></td>',
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Route Map</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small {{ color: #59655f; line-height: 1.35; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 84px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1160px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; position: sticky; top: 0; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-route-map="html" data-status="{text(popular_tasks.get('status'))}" data-routes="{text(summary.get('route_coverage_count'))}" data-tasks="{text(summary.get('popular_tasks'))}">
    <header>
      <div>
        <h1>Local ChatGPT Route Map</h1>
        <p>Use this page to pick the local OpenWebUI model, route, workflow entrypoint, and starter command for common ChatGPT-style tasks.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/starter-prompts.html">Starter Prompts</a>
          <a href="/local-parity/runbook.html">Runbook</a>
          <a href="/local-parity/feature-map.html">Feature Map</a>
          <a href="/local-parity/quality-scorecard.html">Quality Scorecard</a>
          <a href="/local-parity/optional-evidence.html">Optional Evidence</a>
          <a href="/local-parity/live-status.html">Live Status</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/popular-tasks">Popular Tasks JSON</a>
          <a href="/local-parity/workflows">Workflows JSON</a>
          <a href="/local-parity/starter-prompts">Starter Prompts JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Route map summary">
      <section class="metric"><span>Popular tasks</span><strong>{text(summary.get('popular_tasks'))}</strong></section>
      <section class="metric"><span>Ready tasks</span><strong>{text(summary.get('ready_tasks'))}</strong></section>
      <section class="metric"><span>Route families</span><strong>{text(summary.get('route_coverage_count'))}</strong></section>
      <section class="metric"><span>Completion status</span><strong>{text(summary.get('completion_status'))}</strong></section>
    </section>
    <section class="panel">
      <table data-route-map="local-chatgpt">
        <thead><tr><th>Task</th><th>Model / route</th><th>OpenWebUI entrypoint</th><th>Starter command</th><th>First steps</th><th>Expected local artifacts</th><th>Status</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_starter_prompts_html() -> str:
    starter_prompts = local_parity_starter_prompts()
    summary = starter_prompts.get("summary") or {}
    prompts = starter_prompts.get("prompts") or []
    library_by_id = {
        item.get("id"): item
        for item in starter_prompts.get("prompt_library_items", [])
        if isinstance(item, dict) and item.get("id")
    }
    generated_at = time.strftime(
        "%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(starter_prompts.get("generated_at") or now()))
    )

    def text(value) -> str:
        if value is None:
            return ""
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    rows = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        library_item = library_by_id.get(prompt.get("id")) or {}
        variables = ", ".join(prompt.get("variables") or [])
        endpoints = ", ".join(prompt.get("evidence_endpoints") or [])
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(prompt.get('title'))}</strong><br><small><code>{text(prompt.get('id'))}</code></small></td>",
                    f"<td><code>{text(prompt.get('openwebui_command') or library_item.get('command'))}</code><br><small>{text(prompt.get('openwebui_prompt_name') or library_item.get('name'))}</small></td>",
                    f"<td><code>{text(prompt.get('openwebui_model'))}</code><br><small>{text(prompt.get('route_family') or prompt.get('openwebui_route_id'))}</small></td>",
                    f"<td>{text(prompt.get('openwebui_entrypoint'))}<br><small>{text(prompt.get('openwebui_action'))}</small><br><small>{text(prompt.get('copy_target'))}</small></td>",
                    f"<td>{text(variables)}<br><small>{text(prompt.get('expected_result'))}</small></td>",
                    f"<td><pre>{text(prompt.get('prompt_template'))}</pre><small>{text(endpoints)}</small></td>",
                    f'<td><span class="status status-{status_class(prompt.get("status"))}">{text(prompt.get("status"))}</span></td>',
                    "</tr>",
                ]
            )
        )

    usage_items = [f"<li>{text(note)}</li>" for note in starter_prompts.get("usage_notes") or []]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Starter Prompts</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    pre {{ margin: 0 0 7px; white-space: pre-wrap; overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.42; color: #17201c; }}
    small {{ color: #59655f; line-height: 1.35; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 84px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1240px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    td:nth-child(6) {{ width: 32%; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    .usage {{ margin: 8px 0 0; padding-left: 18px; }}
    .usage li {{ margin-bottom: 7px; line-height: 1.45; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-starter-prompts="html" data-status="{text(starter_prompts.get('status'))}" data-prompts="{text(summary.get('starter_prompts'))}" data-routes="{text(summary.get('route_coverage_count'))}" data-import-items="{text(summary.get('prompt_library_items'))}">
    <header>
      <div>
        <h1>Local ChatGPT Starter Prompts</h1>
        <p>Copy-ready static templates for common ChatGPT-style tasks in local OpenWebUI, mapped to the local model route that should handle each workflow.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/feature-map.html">Feature Map</a>
          <a href="/local-parity/runbook.html">Runbook</a>
          <a href="/local-parity/route-map.html">Route Map</a>
          <a href="/local-parity/quality-scorecard.html">Quality Scorecard</a>
          <a href="/local-parity/optional-evidence.html">Optional Evidence</a>
          <a href="/local-parity/live-status.html">Live Status</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/starter-prompts">Starter Prompts JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Starter prompt summary">
      <section class="metric"><span>Starter prompts</span><strong>{text(summary.get('ready_starter_prompts'))}/{text(summary.get('starter_prompts'))}</strong></section>
      <section class="metric"><span>Route families</span><strong>{text(summary.get('route_coverage_count'))}</strong></section>
      <section class="metric"><span>Prompt library items</span><strong>{text(summary.get('prompt_library_items'))}</strong><small>OpenWebUI import-ready</small></section>
      <section class="metric"><span>Workflow linked</span><strong>{text(summary.get('ready_workflow_linked_prompts'))}/{text(summary.get('workflow_linked_prompts'))}</strong></section>
      <section class="metric"><span>Template bodies</span><strong>{text(summary.get('template_prompt_bodies_included'))}</strong><small>static examples only</small></section>
      <section class="metric"><span>User prompts excluded</span><strong>{text(summary.get('user_prompt_bodies_excluded'))}</strong></section>
    </section>
    <section class="panel">
      <h2>Usage</h2>
      <ul class="usage">{''.join(usage_items)}</ul>
    </section>
    <section class="panel">
      <table data-starter-prompts="local-chatgpt">
        <thead><tr><th>Starter</th><th>Command</th><th>Model / route</th><th>OpenWebUI entrypoint</th><th>Variables / result</th><th>Template</th><th>Status</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_quality_scorecard_html() -> str:
    scorecard = local_parity_quality_scorecard()
    summary = scorecard.get("summary") or {}
    route_profiles = scorecard.get("route_profiles") or []
    quality_rows = scorecard.get("quality_by_feature_family") or []
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(scorecard.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    route_rows = []
    for route in route_profiles:
        if not isinstance(route, dict):
            continue
        route_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(route.get('id'))}</code><br><small>{text(route.get('title'))}</small></td>",
                    f"<td><code>{text(route.get('default_model'))}</code></td>",
                    f'<td><span class="status status-{status_class(route.get("status"))}">{text(route.get("status"))}</span><br><small>{text(route.get("latency_status"))}</small></td>',
                    f"<td>{text(route.get('best_tps'))}<br><small>target {text(route.get('target_tps'))}</small></td>",
                    f"<td>{text(route.get('sample_count'))}<br><small>pass rate {text(route.get('pass_rate'))}</small></td>",
                    f"<td>{text(route.get('freshness_status'))}<br><small>age {text(route.get('latest_age_seconds'))}s</small></td>",
                    "</tr>",
                ]
            )
        )

    quality_table_rows = []
    for row in quality_rows:
        if not isinstance(row, dict):
            continue
        quality_table_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(row.get('feature_family'))}</strong></td>",
                    f"<td>{text(row.get('evals'))}</td>",
                    f"<td>{text(row.get('high_priority'))}</td>",
                    f"<td>{text(row.get('smoke'))}</td>",
                    f"<td>{text(row.get('verifier'))}</td>",
                    f"<td>{text(row.get('optional_verifier'))}</td>",
                    f"<td><code>{text(', '.join(row.get('models') or []))}</code></td>",
                    f"<td><code>{text(', '.join(row.get('eval_ids') or []))}</code></td>",
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Quality Scorecard</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small {{ color: #59655f; line-height: 1.35; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 980px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready, .status-meets_target, .status-fresh {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention, .status-failing, .status-below_latency_target {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-quality-scorecard="html" data-status="{text(scorecard.get('local_quality_status'))}" data-evals="{text(summary.get('quality_evals'))}" data-feature-families="{text(summary.get('quality_eval_feature_families'))}" data-routes="{text(summary.get('route_profiles'))}">
    <header>
      <div>
        <h1>Local ChatGPT Quality Scorecard</h1>
        <p>{text(scorecard.get('claim_boundary'))}</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/feature-map.html">Feature Map</a>
          <a href="/local-parity/runbook.html">Runbook</a>
          <a href="/local-parity/route-map.html">Route Map</a>
          <a href="/local-parity/starter-prompts.html">Starter Prompts</a>
          <a href="/local-parity/optional-evidence.html">Optional Evidence</a>
          <a href="/local-parity/live-status.html">Live Status</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/quality-scorecard">Quality JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Quality scorecard summary">
      <section class="metric"><span>Local quality status</span><strong>{text(scorecard.get('local_quality_status'))}</strong></section>
      <section class="metric"><span>Quality evals</span><strong>{text(summary.get('quality_evals'))}</strong><small>{text(summary.get('executable_quality_evals'))} executable</small></section>
      <section class="metric"><span>Feature families covered</span><strong>{text(summary.get('quality_eval_feature_families'))}</strong><small>{text(summary.get('high_priority_quality_eval_feature_families'))} high priority</small></section>
      <section class="metric"><span>Rubric-only evals</span><strong>{text(summary.get('rubric_quality_evals'))}</strong></section>
      <section class="metric"><span>Route profiles ready</span><strong>{text(summary.get('route_profiles_ready'))}</strong><small>{text(summary.get('route_profiles'))} profiles</small></section>
      <section class="metric"><span>Benchmark freshness</span><strong>{text(summary.get('benchmark_freshness_status'))}</strong><small>stale {text(len(summary.get('stale_benchmark_suites') or []))}</small></section>
      <section class="metric"><span>Best stored TPS</span><strong>{text(summary.get('best_local_tps'))}</strong><small>completion tokens/sec</small></section>
      <section class="metric"><span>Verifier evals</span><strong>{text(summary.get('verifier_quality_evals'))}</strong><small>{text(summary.get('smoke_quality_evals'))} smoke</small></section>
    </section>
    <section class="panel">
      <h2>Route Benchmark Profiles</h2>
      <table data-quality-route-profiles="local-chatgpt">
        <thead><tr><th>Route</th><th>Default model</th><th>Status</th><th>Best TPS</th><th>Samples</th><th>Freshness</th></tr></thead>
        <tbody>{''.join(route_rows)}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Feature Family Eval Coverage</h2>
      <table data-quality-feature-families="local-chatgpt">
        <thead><tr><th>Feature family</th><th>Evals</th><th>High priority</th><th>Smoke</th><th>Verifier</th><th>Optional</th><th>Models</th><th>Eval ids</th></tr></thead>
        <tbody>{''.join(quality_table_rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_optional_evidence_html() -> str:
    optional_evidence = local_parity_optional_heavy_evidence()
    summary = optional_evidence.get("summary") or {}
    cases = optional_evidence.get("cases") or []
    generated_at = time.strftime(
        "%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(optional_evidence.get("generated_at") or now()))
    )

    def text(value) -> str:
        if value is None:
            return ""
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    rows = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        latest = case.get("latest_result") if isinstance(case.get("latest_result"), dict) else {}
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(case.get('title'))}</strong><br><small><code>{text(case.get('id'))}</code></small></td>",
                    f"<td>{text(', '.join(case.get('feature_families') or []))}</td>",
                    f"<td><code>{text(case.get('command'))}</code></td>",
                    f"<td><code>{text(', '.join(case.get('verifiers') or []))}</code></td>",
                    f"<td>pass {text(latest.get('pass'))}<br><small>skip {text(latest.get('skip'))}; fail {text(latest.get('fail'))}</small></td>",
                    f"<td>{text(case.get('evidence'))}</td>",
                    f'<td><span class="status status-{status_class(case.get("status"))}">{text(case.get("status"))}</span></td>',
                    "</tr>",
                ]
            )
        )

    flags = [f"<code>{text(flag)}</code>" for flag in optional_evidence.get("flags") or []]
    glm_context_text = f"{int(summary.get('glm_context_tokens') or 0):,}"
    slopcode_context_text = f"{int(summary.get('slopcode_context_tokens') or 0):,}"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Optional Evidence</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small {{ color: #59655f; line-height: 1.35; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1220px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    .flags {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
    .flags code {{ display: inline-flex; align-items: center; min-height: 28px; border: 1px solid #d7ddd8; border-radius: 8px; padding: 4px 8px; background: #f7f8f6; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-optional-evidence="html" data-status="{text(optional_evidence.get('status'))}" data-cases="{text(summary.get('optional_cases'))}" data-ready="{text(summary.get('ready_optional_cases'))}" data-features="{text(summary.get('feature_families'))}" data-verifiers="{text(summary.get('verifiers'))}">
    <header>
      <div>
        <h1>Local ChatGPT Optional Evidence</h1>
        <p>Heavy local parity checks are kept out of the default fast suite, but remain mapped here with current evidence and runnable refresh commands.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/feature-map.html">Feature Map</a>
          <a href="/local-parity/runbook.html">Runbook</a>
          <a href="/local-parity/route-map.html">Route Map</a>
          <a href="/local-parity/starter-prompts.html">Starter Prompts</a>
          <a href="/local-parity/quality-scorecard.html">Quality Scorecard</a>
          <a href="/local-parity/live-status.html">Live Status</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/optional-evidence">Optional Evidence JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Optional evidence summary">
      <section class="metric"><span>Optional cases ready</span><strong>{text(summary.get('ready_optional_cases'))}/{text(summary.get('optional_cases'))}</strong></section>
      <section class="metric"><span>Feature families</span><strong>{text(summary.get('feature_families'))}</strong></section>
      <section class="metric"><span>Verifier checks</span><strong>{text(summary.get('verifiers'))}</strong></section>
      <section class="metric"><span>Commands</span><strong>{text(summary.get('commands'))}</strong></section>
      <section class="metric"><span>Failures</span><strong>{text(summary.get('failures'))}</strong></section>
      <section class="metric"><span>Default skips intentional</span><strong>{text(summary.get('default_suite_skips_intentional'))}</strong></section>
      <section class="metric"><span>GLM context</span><strong>{text(glm_context_text)}</strong><small>tokens</small></section>
      <section class="metric"><span>Slopcode context</span><strong>{text(slopcode_context_text)}</strong><small>tokens</small></section>
    </section>
    <section class="panel">
      <h2>Refresh Flags</h2>
      <p class="flags">{' '.join(flags)}</p>
    </section>
    <section class="panel">
      <table data-optional-evidence="local-chatgpt">
        <thead><tr><th>Case</th><th>Feature families</th><th>Command</th><th>Verifiers</th><th>Latest result</th><th>Evidence</th><th>Status</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_audit_html() -> str:
    audit = local_parity_completion_audit()
    summary = audit.get("summary") or {}
    requirements = audit.get("requirements") or []
    gaps = audit.get("remaining_gaps") or []
    next_actions = audit.get("next_actions") or []
    evidence_summary = ((audit.get("evidence_trace") or {}).get("summary") or {})
    scorecard_summary = ((audit.get("quality_scorecard") or {}).get("summary") or {})
    popular_summary = ((audit.get("popular_task_routes") or {}).get("summary") or {})
    workflow_summary = ((audit.get("workflow_recipes") or {}).get("summary") or {})
    starter_summary = ((audit.get("starter_prompts") or {}).get("summary") or {})
    source_freshness_summary = ((audit.get("source_freshness") or {}).get("summary") or {})
    frontier_summary = ((audit.get("frontier_boundary") or {}).get("summary") or {})
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(audit.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def compact_evidence(value) -> str:
        if isinstance(value, dict):
            candidate = value.get("summary") if isinstance(value.get("summary"), dict) else value
            parts = []
            for key in sorted(candidate.keys()):
                val = candidate.get(key)
                if val is None:
                    continue
                if isinstance(val, dict):
                    val = f"{len(val)} fields"
                elif isinstance(val, list):
                    val = f"{len(val)} items"
                elif isinstance(val, bool):
                    val = str(val).lower()
                parts.append(f"{key}={val}")
                if len(parts) >= 6:
                    break
            return "; ".join(parts)
        if isinstance(value, list):
            return f"{len(value)} items"
        return str(value or "")

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    requirement_rows = []
    for item in requirements:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        requirement_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(item.get('id'))}</code></td>",
                    f'<td><span class="status status-{status_class(status)}">{text(status)}</span></td>',
                    f"<td>{text(compact_evidence(item.get('evidence')))}</td>",
                    "</tr>",
                ]
            )
        )

    gap_rows = []
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        gap_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(gap.get('id'))}</code></td>",
                    f'<td><span class="status status-{status_class(gap.get("status"))}">{text(gap.get("status"))}</span></td>',
                    f"<td>{text(gap.get('summary'))}</td>",
                    f"<td>{text(compact_evidence(gap.get('evidence')))}</td>",
                    f"<td>{text(gap.get('next_action'))}</td>",
                    "</tr>",
                ]
            )
        )

    action_items = [f"<li>{text(action)}</li>" for action in next_actions]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Completion Audit</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 860px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready, .status-passed, .status-current {{ background: #e3f4ea; color: #175734; }}
    .status-not-complete-for-full-hosted-chatgpt-parity, .status-not-proven, .status-not_locally_provable, .status-excluded_from_local_goal, .status-inherent_local_limit {{ background: #fff0cc; color: #6f4b00; }}
    .status-failed, .status-not_ready, .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    .actions {{ margin: 8px 0 0; padding-left: 18px; }}
    .actions li {{ margin-bottom: 7px; line-height: 1.45; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-completion-audit="html" data-status="{text(audit.get('local_functional_status'))}" data-completion-status="{text(audit.get('completion_status'))}" data-requirements="{text(len(requirements))}" data-blocking="{text(len(audit.get('blocking_requirements') or []))}" data-open-gaps="{text(summary.get('open_gaps'))}" data-current-release-source="{text(source_freshness_summary.get('current_release_source_id'))}" data-current-release-families="{text(source_freshness_summary.get('current_release_covered_families'))}/{text(source_freshness_summary.get('current_release_expected_families'))}" data-current-release-terms="{text(source_freshness_summary.get('current_release_covered_evidence_terms'))}/{text(source_freshness_summary.get('current_release_expected_evidence_terms'))}" data-frontier-boundary-items="{text(frontier_summary.get('boundary_items'))}" data-frontier-boundary-ready="{text(frontier_summary.get('ready_local_mitigations'))}" data-frontier-boundary-excluded="{text(frontier_summary.get('excluded_from_local_goal_items'))}" data-frontier-boundary-not-provable="{text(frontier_summary.get('not_locally_provable_items'))}">
    <header>
      <div>
        <h1>Local ChatGPT Completion Audit</h1>
        <p>{text(audit.get('objective'))}</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/starter-prompts.html">Starter Prompts</a>
          <a href="/local-parity/feature-map.html">Feature Map</a>
          <a href="/local-parity/runbook.html">Runbook</a>
          <a href="/local-parity/route-map.html">Route Map</a>
          <a href="/local-parity/quality-scorecard.html">Quality Scorecard</a>
          <a href="/local-parity/optional-evidence.html">Optional Evidence</a>
          <a href="/local-parity/live-status.html">Live Status</a>
          <a href="/local-parity/audit">Audit JSON</a>
          <a href="/local-parity/evidence">Evidence JSON</a>
          <a href="/local-parity/gap">Gap JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Completion audit summary">
      {metric("Local functional status", audit.get('local_functional_status'), "OpenWebUI local workflows")}
      {metric("Hosted scope status", audit.get('full_hosted_chatgpt_parity_status'), "excluded cloud items")}
      {metric("Completion status", audit.get('completion_status'), "local goal")}
      {metric("Blocking requirements", len(audit.get('blocking_requirements') or []), "failed local requirements")}
      {metric("Open local gaps", summary.get('open_gaps'), f"non-inherent {summary.get('non_inherent_open_gaps')}")}
      {metric("Popular tasks", f"{popular_summary.get('ready_tasks')}/{popular_summary.get('popular_tasks')}", "ready local routes")}
      {metric("Workflow recipes", f"{workflow_summary.get('ready_workflow_recipes')}/{workflow_summary.get('workflow_recipes')}", "OpenWebUI steps")}
      {metric("Starter prompts", f"{starter_summary.get('ready_starter_prompts')}/{starter_summary.get('starter_prompts')}", "prompt-library items")}
      {metric("Current release", f"{source_freshness_summary.get('current_release_covered_families')}/{source_freshness_summary.get('current_release_expected_families')}", "families")}
      {metric("Release evidence", f"{source_freshness_summary.get('current_release_covered_evidence_terms')}/{source_freshness_summary.get('current_release_expected_evidence_terms')}", "terms")}
      {metric("Primary GLM route", "glm52-q8-local / glm52-q4-local", "local long-context model")}
      {metric("Scope exclusions", f"{frontier_summary.get('excluded_from_local_goal_items')}/{frontier_summary.get('boundary_items')}", "hosted capabilities")}
      {metric("Evidence artifacts", f"{evidence_summary.get('ready_artifacts')}/{evidence_summary.get('artifacts')}", "privacy-safe proof")}
      {metric("Quality evals", scorecard_summary.get('quality_evals'), "executable")}
      {metric("Best stored TPS", scorecard_summary.get('best_local_tps'), "completion tokens/sec")}
      {metric("Context window", "65,536", "GLM 5.2 and Slopcode/Qwen")}
    </section>
    <section class="panel">
      <h2>Requirement Audit</h2>
      <table data-audit-requirements="local-chatgpt">
        <thead><tr><th>Requirement</th><th>Status</th><th>Evidence summary</th></tr></thead>
        <tbody>{''.join(requirement_rows)}</tbody>
      </table>
    </section>
    <section class="panel" data-audit-gaps="local-chatgpt">
      <h2>Local Gaps</h2>
      <table>
        <thead><tr><th>Gap</th><th>Status</th><th>Summary</th><th>Evidence</th><th>Next action</th></tr></thead>
        <tbody>{''.join(gap_rows)}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Next Actions</h2>
      <ul class="actions">{''.join(action_items)}</ul>
    </section>
  </main>
</body>
</html>"""


def local_http_probe(
    probe_id: str,
    title: str,
    url: str,
    expected_text: str | None = None,
    *,
    timeout_seconds: int | None = None,
    attempts: int = 1,
) -> dict:
    started = time.time()
    result = {
        "id": probe_id,
        "title": title,
        "kind": "http",
        "url": url,
        "expected_text": expected_text,
    }
    timeout = timeout_seconds or LOCAL_PARITY_LIVE_STATUS_TIMEOUT_SECONDS
    last_error: Exception | None = None
    attempts = max(1, attempts)
    for attempt in range(1, attempts + 1):
        try:
            req = request.Request(url, headers={"User-Agent": "openwebui-local-scheduler/0.1"})
            with request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(4096)
                text = body.decode("utf-8", "replace")
                status_code = int(getattr(resp, "status", 0) or 0)
            expected_ok = expected_text in text if expected_text else True
            ok = 200 <= status_code < 300 and expected_ok
            result.update(
                {
                    "status": "ready" if ok else "not_ready",
                    "http_status": status_code,
                    "expected_text_present": expected_ok,
                    "elapsed_ms": int((time.time() - started) * 1000),
                    "attempts": attempt,
                }
            )
            if ok:
                return result
        except Exception as exc:
            last_error = exc
            result.update(
                {
                    "status": "not_ready",
                    "error": type(exc).__name__,
                    "elapsed_ms": int((time.time() - started) * 1000),
                    "attempts": attempt,
                }
            )
        if attempt < attempts:
            time.sleep(0.25)
    if last_error:
        result["error"] = type(last_error).__name__
    return result


def local_tcp_probe(probe_id: str, title: str, host: str, port: int) -> dict:
    started = time.time()
    result = {
        "id": probe_id,
        "title": title,
        "kind": "tcp",
        "host": host,
        "port": port,
        "url": f"tcp://{host}:{port}",
    }
    try:
        with socket.create_connection((host, port), timeout=LOCAL_PARITY_LIVE_STATUS_TIMEOUT_SECONDS):
            pass
        result.update({"status": "ready", "elapsed_ms": int((time.time() - started) * 1000)})
    except Exception as exc:
        result.update(
            {
                "status": "not_ready",
                "error": type(exc).__name__,
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        )
    return result


def local_parity_live_status() -> dict:
    probes = [
        local_http_probe("openwebui", "OpenWebUI health", "http://127.0.0.1:8080/health"),
        local_http_probe("glm52", "GLM 5.2 model endpoint", "http://127.0.0.1:11441/v1/models", "glm52-q4-local"),
        local_http_probe("deep_research", "Deep research model endpoint", "http://127.0.0.1:18041/v1/models", "deep-research-glm52"),
        local_http_probe("local_agent", "Local agent model endpoint", "http://127.0.0.1:18043/v1/models", "local-agent-glm52"),
        local_http_probe("local_auto_router", "Local auto-router model endpoint", "http://127.0.0.1:18043/v1/models", "local-auto-router"),
        local_tcp_probe("playwright_agent", "Playwright browser agent", "127.0.0.1", 18045),
        local_http_probe("local_vision_moondream", "Local vision Moondream endpoint", "http://127.0.0.1:18044/v1/models", "local-vision-moondream2"),
        local_http_probe("local_vision_gemma", "Local vision Gemma endpoint", "http://127.0.0.1:18044/v1/models", "local-vision-gemma4-12b"),
        local_http_probe(
            "searxng",
            "SearXNG search",
            "http://127.0.0.1:18080/search?q=test&format=json",
            timeout_seconds=max(8, LOCAL_PARITY_LIVE_STATUS_TIMEOUT_SECONDS),
            attempts=2,
        ),
        local_http_probe("tika", "Tika content extraction", "http://127.0.0.1:9998/tika"),
        local_http_probe("jupyter", "Jupyter code execution", "http://127.0.0.1:8888/api"),
        local_http_probe("comfyui", "ComfyUI image workflow", "http://127.0.0.1:8188/object_info", "KSampler"),
    ]
    ready = [item for item in probes if item.get("status") == "ready"]
    required_ids = {
        "openwebui",
        "glm52",
        "deep_research",
        "local_agent",
        "local_auto_router",
        "playwright_agent",
        "local_vision_moondream",
        "local_vision_gemma",
        "searxng",
        "tika",
        "jupyter",
        "comfyui",
    }
    ready_ids = {item.get("id") for item in ready}
    live_status = "ready" if required_ids.issubset(ready_ids) else "needs_attention"
    return {
        "source": "chatgpt-local-live-status",
        "generated_at": now(),
        "live_status": live_status,
        "summary": {
            "probes": len(probes),
            "ready_probes": len(ready),
            "required_probes": len(required_ids),
            "missing_required_probe_ids": sorted(required_ids - ready_ids),
        },
        "probes": probes,
        "privacy": {
            "local_only": True,
            "loopback_only": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_live_status_html() -> str:
    live_status = local_parity_live_status()
    route_recommendations = local_model_route_recommendations()
    summary = live_status.get("summary") or {}
    probes = live_status.get("probes") or []
    profiles = (
        route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}
    )
    benchmark_summary = route_recommendations.get("benchmark_summary") or {}
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(live_status.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    probe_rows = []
    for probe in probes:
        if not isinstance(probe, dict):
            continue
        details = []
        if probe.get("http_status") is not None:
            details.append(f"HTTP {probe.get('http_status')}")
        if probe.get("expected_text"):
            details.append(f"expects {probe.get('expected_text')}")
        if probe.get("expected_text_present") is not None:
            details.append(f"text={str(probe.get('expected_text_present')).lower()}")
        if probe.get("attempts") is not None:
            details.append(f"attempts={probe.get('attempts')}")
        if probe.get("error"):
            details.append(f"error={probe.get('error')}")
        probe_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(probe.get('title'))}</strong><br><small><code>{text(probe.get('id'))}</code></small></td>",
                    f"<td><code>{text(probe.get('url'))}</code></td>",
                    f"<td>{text(probe.get('kind'))}</td>",
                    f"<td>{text(probe.get('elapsed_ms'))}</td>",
                    f"<td>{text('; '.join(details))}</td>",
                    f'<td><span class="status status-{status_class(probe.get("status"))}">{text(probe.get("status"))}</span></td>',
                    "</tr>",
                ]
            )
        )

    route_rows = []
    for route_id, profile in sorted(profiles.items()):
        if not isinstance(profile, dict):
            continue
        benchmark = profile.get("benchmark") if isinstance(profile.get("benchmark"), dict) else {}
        route_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(route_id)}</code></td>",
                    f"<td>{text(profile.get('default_model'))}</td>",
                    f'<td><span class="status status-{status_class(profile.get("status"))}">{text(profile.get("status"))}</span></td>',
                    f"<td>{text(benchmark.get('best_tps'))}</td>",
                    f"<td>{text(benchmark.get('latest_tps'))}</td>",
                    f"<td>{text(benchmark.get('samples'))}</td>",
                    f"<td>{text(profile.get('freshness_status'))}</td>",
                    "</tr>",
                ]
            )
        )

    missing_ids = summary.get("missing_required_probe_ids") or []
    missing_detail = ", ".join(str(item) for item in missing_ids) if missing_ids else "none"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Live Status</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1260px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small {{ color: #59655f; line-height: 1.35; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 860px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready, .status-current, .status-available {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention, .status-not_ready {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-live-status="html" data-status="{text(live_status.get('live_status'))}" data-probes="{text(summary.get('probes'))}" data-ready="{text(summary.get('ready_probes'))}" data-required="{text(summary.get('required_probes'))}">
    <header>
      <div>
        <h1>Local ChatGPT Live Status</h1>
        <p>Loopback-only runtime probes for OpenWebUI, GLM 5.2, local sidecars, browser tooling, document extraction, code execution, search, and ComfyUI.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/feature-map.html">Feature Map</a>
          <a href="/local-parity/runbook.html">Runbook</a>
          <a href="/local-parity/route-map.html">Route Map</a>
          <a href="/local-parity/starter-prompts.html">Starter Prompts</a>
          <a href="/local-parity/quality-scorecard.html">Quality Scorecard</a>
          <a href="/local-parity/optional-evidence.html">Optional Evidence</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/live-status">Live Status JSON</a>
          <a href="/local-parity/evidence">Evidence JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Live status summary">
      {metric("Live status", live_status.get('live_status'), "required runtime probes")}
      {metric("Ready probes", f"{summary.get('ready_probes')}/{summary.get('probes')}", "HTTP and TCP")}
      {metric("Required probes", summary.get('required_probes'), f"missing {missing_detail}")}
      {metric("Benchmark freshness", benchmark_summary.get('freshness_status'), "stored route samples")}
      {metric("Benchmark records", benchmark_summary.get('count'), "local route samples")}
      {metric("Stale suites", len(benchmark_summary.get('stale_suites') or []), "freshness gate")}
    </section>
    <section class="panel">
      <h2>Runtime Probes</h2>
      <table data-live-probes="local-chatgpt">
        <thead><tr><th>Probe</th><th>Endpoint</th><th>Kind</th><th>Elapsed ms</th><th>Details</th><th>Status</th></tr></thead>
        <tbody>{''.join(probe_rows)}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Route Profiles</h2>
      <table data-live-route-profiles="local-chatgpt">
        <thead><tr><th>Route</th><th>Default model</th><th>Status</th><th>Best TPS</th><th>Latest TPS</th><th>Samples</th><th>Freshness</th></tr></thead>
        <tbody>{''.join(route_rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_quality_scorecard() -> dict:
    catalog = local_parity_catalog()
    route_recommendations = local_model_route_recommendations()
    quality_evals = load_local_parity_doc("chatgpt-local-quality-evals.json")
    counts = catalog.get("counts") or {}
    profiles = route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}

    route_profiles = []
    for profile_id, profile in sorted(profiles.items()):
        benchmark = profile.get("benchmark") if isinstance(profile.get("benchmark"), dict) else {}
        target_tps = benchmark_float(profile.get("target_tps"))
        best_tps = benchmark_float(benchmark.get("best_tps"))
        route_profiles.append(
            {
                "id": profile_id,
                "title": profile.get("title"),
                "default_model": profile.get("default_model"),
                "benchmark_suite": profile.get("benchmark_suite"),
                "status": profile.get("status"),
                "target_tps": target_tps,
                "best_tps": best_tps,
                "pass_rate": benchmark_float(benchmark.get("pass_rate")),
                "sample_count": int(benchmark.get("count") or 0),
                "freshness_status": profile.get("freshness_status") or benchmark.get("freshness_status") or "unmeasured",
                "latest_age_seconds": benchmark.get("latest_age_seconds"),
                "max_age_seconds": benchmark.get("max_age_seconds"),
                "latency_status": "meets_target" if target_tps > 0 and best_tps >= target_tps else "below_target",
                "latest_benchmark_id": (benchmark.get("latest") or {}).get("id") if isinstance(benchmark.get("latest"), dict) else None,
            }
        )

    feature_families = sorted({str(item.get("feature_family")) for item in quality_evals if item.get("feature_family")})
    high_priority_feature_families = sorted(
        {str(item.get("feature_family")) for item in quality_evals if item.get("feature_family") and item.get("priority") == "high"}
    )
    quality_by_feature = []
    for family in feature_families:
        family_evals = [item for item in quality_evals if item.get("feature_family") == family]
        quality_by_feature.append(
            {
                "feature_family": family,
                "evals": len(family_evals),
                "smoke": len([item for item in family_evals if item.get("evaluation_mode") == "smoke"]),
                "verifier": len([item for item in family_evals if item.get("evaluation_mode") == "verifier"]),
                "optional_verifier": len(
                    [
                        item
                        for item in family_evals
                        if item.get("evaluation_mode") == "verifier" and item.get("verifier_tier", "default") == "optional"
                    ]
                ),
                "high_priority": len([item for item in family_evals if item.get("priority") == "high"]),
                "models": sorted({str(item.get("model")) for item in family_evals if item.get("model")}),
                "eval_ids": [item.get("id") for item in family_evals if item.get("id")],
            }
        )

    all_route_profiles_ready = bool(route_profiles) and all(item.get("status") == "ready" for item in route_profiles)
    all_route_profiles_meet_targets = bool(route_profiles) and all(
        item.get("latency_status") == "meets_target" for item in route_profiles
    )
    all_route_profiles_fresh = bool(route_profiles) and all(
        item.get("freshness_status") == "fresh" for item in route_profiles
    )
    all_evals_executable = (
        counts.get("quality_evals") == counts.get("executable_quality_evals")
        and counts.get("quality_evals", 0) > 0
        and counts.get("rubric_quality_evals") == 0
    )
    high_priority_covered = (
        counts.get("high_priority_quality_evals", 0)
        >= counts.get("feature_families", LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES)
        == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
    )
    feature_family_quality_covered = (
        len(feature_families) == counts.get("feature_families") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
    )
    high_priority_feature_family_coverage = (
        len(high_priority_feature_families) == counts.get("feature_families") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
    )
    local_quality_status = (
        "ready"
        if all_evals_executable
        and high_priority_covered
        and feature_family_quality_covered
        and high_priority_feature_family_coverage
        and all_route_profiles_ready
        and all_route_profiles_meet_targets
        and all_route_profiles_fresh
        else "needs_attention"
    )

    return {
        "source": "chatgpt-local-quality-scorecard",
        "generated_at": now(),
        "local_quality_status": local_quality_status,
        "claim_boundary": "This scorecard measures local eval coverage and local route benchmark readiness; it does not prove hosted ChatGPT frontier-model equivalence.",
        "summary": {
            "quality_evals": counts.get("quality_evals", 0),
            "executable_quality_evals": counts.get("executable_quality_evals", 0),
            "rubric_quality_evals": counts.get("rubric_quality_evals", 0),
            "high_priority_quality_evals": counts.get("high_priority_quality_evals", 0),
            "smoke_quality_evals": counts.get("smoke_quality_evals", 0),
            "verifier_quality_evals": counts.get("verifier_quality_evals", 0),
            "default_verifier_quality_evals": counts.get("default_verifier_quality_evals", 0),
            "optional_verifier_quality_evals": counts.get("optional_verifier_quality_evals", 0),
            "all_evals_executable": all_evals_executable,
            "high_priority_covered": high_priority_covered,
            "quality_eval_feature_families": len(feature_families),
            "feature_family_quality_covered": feature_family_quality_covered,
            "high_priority_quality_eval_feature_families": len(high_priority_feature_families),
            "high_priority_feature_family_coverage": high_priority_feature_family_coverage,
            "route_profiles": len(route_profiles),
            "route_profiles_ready": all_route_profiles_ready,
            "route_profiles_meet_targets": all_route_profiles_meet_targets,
            "route_profiles_fresh": all_route_profiles_fresh,
            "benchmark_freshness_status": (route_recommendations.get("benchmark_summary") or {}).get("freshness_status"),
            "stale_benchmark_suites": (route_recommendations.get("benchmark_summary") or {}).get("stale_suites") or [],
            "best_local_tps": (route_recommendations.get("benchmark_summary") or {}).get("best_tps", 0),
        },
        "quality_by_mode": local_parity_status_counts(quality_evals, "evaluation_mode"),
        "quality_by_tier": local_parity_status_counts(quality_evals, "quality_tier"),
        "quality_by_priority": local_parity_status_counts(quality_evals, "priority"),
        "quality_by_feature_family": quality_by_feature,
        "route_profiles": route_profiles,
        "recommended_routes": {
            profile_id: {
                "default_model": profile.get("default_model"),
                "status": profile.get("status"),
                "recommendation": profile.get("recommendation"),
                "best_for": profile.get("best_for") or [],
                "tradeoffs": profile.get("tradeoffs") or [],
            }
            for profile_id, profile in sorted(profiles.items())
        },
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_continuity_report() -> dict:
    catalog = local_parity_catalog()
    known_verifiers = {
        verifier
        for item in catalog.get("use_cases", [])
        for verifier in (item.get("required_verifiers") or []) + (item.get("optional_verifiers") or [])
        if isinstance(verifier, str) and verifier.strip()
    }
    for item in catalog.get("quality_evals", []):
        known_verifiers.update(
            verifier
            for verifier in item.get("required_verifiers", [])
            if isinstance(verifier, str) and verifier.strip()
        )

    capabilities = [
        {
            "id": "chat-history-export-import",
            "title": "Chat history export/import",
            "local_path": "OpenWebUI chat search, tag/archive, account JSON export, stats export, and chat import/restore.",
            "required_verifiers": [
                "openwebui.chat_history_management_smoke",
                "openwebui.account_chat_export_smoke",
            ],
        },
        {
            "id": "shareable-local-snapshots",
            "title": "Shareable local conversation and artifact snapshots",
            "local_path": "OpenWebUI shared chat links plus local artifact share-link preservation.",
            "required_verifiers": [
                "openwebui.shared_chat_link_lifecycle_smoke",
                "openwebui.canvas_artifact_share_e2e_smoke",
                "openwebui.interactive_chart_artifact_smoke",
            ],
        },
        {
            "id": "local-gpt-package-portability",
            "title": "Local GPT-style assistant package export/import",
            "local_path": "OpenWebUI local GPT catalog/storefront metadata, read-only sharing, package export/import, and imported package execution.",
            "required_verifiers": [
                "openwebui.local_gpt_catalog_discovery_smoke",
                "openwebui.local_gpt_storefront_smoke",
                "openwebui.gpt_package_export_import_smoke",
            ],
        },
        {
            "id": "code-workspace-package-portability",
            "title": "Local code workspace package and patch portability",
            "local_path": "Local Scheduler code workspace package export/import, Git patch bundle export, and isolated local Git worktree evidence.",
            "required_verifiers": [
                "local_scheduler.local_code_workspace_smoke",
            ],
        },
        {
            "id": "project-and-file-context-reuse",
            "title": "Project, file, and knowledge context reuse",
            "local_path": "OpenWebUI File Library reuse, saved project response sources, shared project source context, and knowledge chat context.",
            "required_verifiers": [
                "openwebui.file_library_chat_reuse_smoke",
                "openwebui.project_response_source_smoke",
                "openwebui.project_sharing_roles_smoke",
                "openwebui.knowledge_chat_context_smoke",
            ],
        },
        {
            "id": "research-report-library-portability",
            "title": "Deep research report library and downloadable artifacts",
            "local_path": "Deep Research stores local source packs, report library entries, reviewed revisions, downloadable Markdown/HTML/Word/PDF/JSON artifacts, and a portable ZIP bundle.",
            "required_verifiers": [
                "deep_research.plan_artifacts_smoke",
                "deep_research.report_library_smoke",
                "deep_research.report_review_smoke",
            ],
        },
        {
            "id": "local-app-connector-artifact-portability",
            "title": "Local app connector artifact persistence",
            "local_path": "Local Scheduler stores notes, sites, sheets, code workspaces, benchmark records, and connector-searchable artifacts under local storage.",
            "required_verifiers": [
                "local_scheduler.local_app_connector_smoke",
                "local_scheduler.local_sites_smoke",
                "local_scheduler.local_sheets_smoke",
                "local_scheduler.local_model_benchmark_smoke",
            ],
        },
    ]

    ready_capabilities = []
    for capability in capabilities:
        missing = [
            verifier
            for verifier in capability.get("required_verifiers", [])
            if verifier not in known_verifiers
        ]
        capability["status"] = "ready" if not missing else "needs_attention"
        capability["missing_verifiers"] = missing
        capability["verifier_count"] = len(capability.get("required_verifiers") or [])
        ready_capabilities.append(capability) if not missing else None

    continuity_status = "ready" if len(ready_capabilities) == len(capabilities) else "needs_attention"
    return {
        "source": "chatgpt-local-continuity-fallback",
        "generated_at": now(),
        "continuity_status": continuity_status,
        "claim_boundary": (
            "This proves local export/import, share-link, and reusable-artifact fallback coverage. "
            "It does not prove hosted ChatGPT cross-device sync, mobile app continuity, or cloud account recovery."
        ),
        "summary": {
            "capabilities": len(capabilities),
            "ready_capabilities": len(ready_capabilities),
            "local_export_import_fallback": continuity_status == "ready",
            "hosted_sync_equivalence": False,
            "required_verifiers": sum(item.get("verifier_count", 0) for item in capabilities),
        },
        "capabilities": capabilities,
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_source_freshness_html() -> str:
    freshness = local_parity_source_freshness()
    summary = freshness.get("summary") or {}
    source_statuses = freshness.get("source_statuses") or []
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(freshness.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    def source_link(source: dict) -> str:
        url = str(source.get("url") or "")
        if url.startswith(("http://", "https://")):
            return f'<a href="{text(url)}" rel="noreferrer">{text(url)}</a>'
        return f"<code>{text(url)}</code>" if url else ""

    rows = []
    for source in source_statuses:
        if not isinstance(source, dict):
            continue
        families = ", ".join(str(family) for family in (source.get("feature_families") or []) if family)
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(source.get('title'))}</strong><br><small><code>{text(source.get('id'))}</code></small></td>",
                    f"<td>{source_link(source)}</td>",
                    f"<td>{text(source.get('source_kind'))}</td>",
                    f"<td>{text(source.get('retrieved'))}</td>",
                    f"<td>{text(source.get('age_days'))}</td>",
                    f"<td>{text(source.get('feature_family_count'))}</td>",
                    f"<td>{text(families)}</td>",
                    f"<td>{text(source.get('evidence_summary'))}</td>",
                    f'<td><span class="status status-{status_class(source.get("status"))}">{text(source.get("status"))}</span></td>',
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Source Freshness</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1260px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small {{ color: #59655f; line-height: 1.35; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1480px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-current {{ background: #e3f4ea; color: #175734; }}
    .status-stale, .status-missing_retrieved, .status-invalid_retrieved, .status-needs_refresh {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-source-freshness="html" data-status="{text(freshness.get('freshness_status'))}" data-sources="{text(summary.get('source_entries'))}" data-feature-families="{text(summary.get('feature_families'))}" data-official="{text(summary.get('official_sources'))}" data-current-release-families="{text(summary.get('current_release_covered_families'))}/{text(summary.get('current_release_expected_families'))}" data-current-release-terms="{text(summary.get('current_release_covered_evidence_terms'))}/{text(summary.get('current_release_expected_evidence_terms'))}">
    <header>
      <div>
        <h1>Local ChatGPT Source Freshness</h1>
        <p>Current source coverage for the local ChatGPT feature map, including official source count, retrieval dates, age, and feature-family coverage.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/feature-map.html">Feature Map</a>
          <a href="/local-parity/runbook.html">Runbook</a>
          <a href="/local-parity/continuity.html">Continuity</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/source-freshness">Source Freshness JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Source freshness summary">
      {metric("Freshness status", freshness.get('freshness_status'), f"max age {freshness.get('max_age_days_allowed')} days")}
      {metric("Source entries", summary.get('source_entries'), "snapshot records")}
      {metric("Official sources", summary.get('official_sources'), "OpenAI sources")}
      {metric("Local-only sources", summary.get('local_only_sources'), "runtime source")}
      {metric("Feature coverage", f"{summary.get('covered_feature_families')}/{summary.get('feature_families')}", "families")}
      {metric("Source URLs", f"{summary.get('sources_with_urls')}/{summary.get('source_entries')}", "linkable records")}
      {metric("Evidence summaries", f"{summary.get('sources_with_evidence_summaries')}/{summary.get('source_entries')}", "review notes")}
      {metric("Stale sources", summary.get('stale_sources'), "needs refresh")}
      {metric("Max source age", summary.get('max_source_age_days'), "days")}
      {metric("Release notes current", summary.get('release_notes_source_current'), "ChatGPT release notes")}
      {metric("Current release families", f"{summary.get('current_release_covered_families')}/{summary.get('current_release_expected_families')}", "release-note families")}
      {metric("Current release terms", f"{summary.get('current_release_covered_evidence_terms')}/{summary.get('current_release_expected_evidence_terms')}", "evidence signals")}
    </section>
    <section class="panel">
      <h2>Current Release Coverage</h2>
      <table data-current-release-coverage="local-chatgpt">
        <thead><tr><th>Source</th><th>Status</th><th>Families</th><th>Evidence terms</th><th>Missing families</th><th>Missing evidence terms</th></tr></thead>
        <tbody>
          <tr>
            <td><code>{text((freshness.get('current_release') or {}).get('source_id'))}</code></td>
            <td>{text((freshness.get('current_release') or {}).get('status'))}</td>
            <td>{text(summary.get('current_release_covered_families'))}/{text(summary.get('current_release_expected_families'))}</td>
            <td>{text(summary.get('current_release_covered_evidence_terms'))}/{text(summary.get('current_release_expected_evidence_terms'))}</td>
            <td>{text(', '.join((freshness.get('current_release') or {}).get('missing_families') or []) or 'none')}</td>
            <td>{text(', '.join((freshness.get('current_release') or {}).get('missing_evidence_terms') or []) or 'none')}</td>
          </tr>
        </tbody>
      </table>
    </section>
    <section class="panel">
      <table data-source-freshness="local-chatgpt">
        <thead><tr><th>Source</th><th>URL</th><th>Kind</th><th>Retrieved</th><th>Age days</th><th>Family count</th><th>Feature families</th><th>Evidence summary</th><th>Status</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_continuity_html() -> str:
    continuity = local_parity_continuity_report()
    summary = continuity.get("summary") or {}
    capabilities = continuity.get("capabilities") or []
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(continuity.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    rows = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        verifiers = ", ".join(capability.get("required_verifiers") or [])
        missing = ", ".join(capability.get("missing_verifiers") or []) or "none"
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(capability.get('title'))}</strong><br><small><code>{text(capability.get('id'))}</code></small></td>",
                    f"<td>{text(capability.get('local_path'))}</td>",
                    f"<td><code>{text(verifiers)}</code></td>",
                    f"<td>{text(missing)}</td>",
                    f'<td><span class="status status-{status_class(capability.get("status"))}">{text(capability.get("status"))}</span></td>',
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Continuity Fallback</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17201c;
      background: #f7f8f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1260px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small {{ color: #59655f; line-height: 1.35; }}
    .generated {{ color: #59655f; font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 980px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .boundary {{ border-left: 4px solid #b7791f; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{
      main {{ padding: 20px 12px 32px; }}
      header {{ display: block; }}
      .generated {{ white-space: normal; margin-top: 8px; }}
      h1 {{ font-size: 23px; }}
      .metric strong {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <main data-local-parity-continuity="html" data-status="{text(continuity.get('continuity_status'))}" data-capabilities="{text(summary.get('capabilities'))}" data-ready="{text(summary.get('ready_capabilities'))}" data-hosted-sync-equivalence="{text(summary.get('hosted_sync_equivalence'))}">
    <header>
      <div>
        <h1>Local ChatGPT Continuity Fallback</h1>
        <p>Local export, import, share-link, package, report, and artifact fallback coverage for workflows that hosted ChatGPT normally syncs across devices.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/runbook.html">Runbook</a>
          <a href="/local-parity/source-freshness.html">Source Freshness</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/continuity">Continuity JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Continuity summary">
      {metric("Continuity status", continuity.get('continuity_status'), "local fallback")}
      {metric("Capabilities ready", f"{summary.get('ready_capabilities')}/{summary.get('capabilities')}", "fallback areas")}
      {metric("Required verifiers", summary.get('required_verifiers'), "coverage checks")}
      {metric("Local fallback", summary.get('local_export_import_fallback'), "export/import")}
      {metric("Hosted sync equivalent", summary.get('hosted_sync_equivalence'), "explicit boundary")}
    </section>
    <section class="panel boundary">
      <h2>Claim Boundary</h2>
      <p>{text(continuity.get('claim_boundary'))}</p>
    </section>
    <section class="panel">
      <table data-continuity="local-chatgpt">
        <thead><tr><th>Capability</th><th>Local path</th><th>Required verifiers</th><th>Missing</th><th>Status</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_capacity_plan(*, route_recommendations: dict | None = None) -> dict:
    route_recommendations = route_recommendations or local_model_route_recommendations()
    profiles = (
        route_recommendations.get("profiles")
        if isinstance(route_recommendations.get("profiles"), dict)
        else {}
    )
    benchmark_summary = route_recommendations.get("benchmark_summary") or {}

    def route_item(
        *,
        route_id: str,
        openwebui_model: str,
        profile_key: str,
        latency_class: str,
        planning_context_tokens: int | None,
        verified_context_tokens: bool,
        recommended_input_tokens: int,
        reserve_output_tokens: int,
        selection_rule: str,
    ) -> dict:
        profile = profiles.get(profile_key) if isinstance(profiles.get(profile_key), dict) else {}
        benchmark = profile.get("benchmark") if isinstance(profile.get("benchmark"), dict) else {}
        latest = benchmark.get("latest") if isinstance(benchmark.get("latest"), dict) else {}
        best = benchmark.get("best") if isinstance(benchmark.get("best"), dict) else {}
        return {
            "id": route_id,
            "profile": profile_key,
            "status": profile.get("status") or "unmeasured",
            "openwebui_model": openwebui_model,
            "runtime_model": profile.get("default_model"),
            "latency_class": latency_class,
            "planning_context_tokens": planning_context_tokens,
            "verified_context_tokens": verified_context_tokens,
            "recommended_input_tokens": recommended_input_tokens,
            "reserve_output_tokens": reserve_output_tokens,
            "target_tps": profile.get("target_tps"),
            "best_tps": benchmark.get("best_tps", 0.0),
            "latest_tps": latest.get("approx_completion_tps"),
            "latest_elapsed_seconds": latest.get("elapsed_seconds"),
            "latest_completion_tokens": latest.get("completion_tokens"),
            "best_elapsed_seconds": best.get("elapsed_seconds"),
            "best_completion_tokens": best.get("completion_tokens"),
            "benchmark_freshness_status": profile.get("freshness_status") or "unmeasured",
            "latest_age_seconds": profile.get("latest_age_seconds"),
            "selection_rule": selection_rule,
            "best_for": profile.get("best_for") or [],
            "tradeoffs": profile.get("tradeoffs") or [],
        }

    routes = [
        route_item(
            route_id="fast_router",
            openwebui_model="local-chatgpt-auto",
            profile_key="fast_router",
            latency_class="interactive",
            planning_context_tokens=None,
            verified_context_tokens=False,
            recommended_input_tokens=6000,
            reserve_output_tokens=1000,
            selection_rule=(
                "Use as the default ChatGPT-like OpenWebUI route for everyday prompts, short summaries, drafts, "
                "and latency-sensitive work."
            ),
        ),
        route_item(
            route_id="slopcode_tiny",
            openwebui_model="slopcode-qwen-coder-local",
            profile_key="slopcode_tiny",
            latency_class="slow_coding",
            planning_context_tokens=65536,
            verified_context_tokens=True,
            recommended_input_tokens=61440,
            reserve_output_tokens=4096,
            selection_rule=(
                "Use for local coding help when code quality matters more than interactive speed; keep output reserve "
                "for patches, explanations, and tests."
            ),
        ),
        route_item(
            route_id="glm_tiny",
            openwebui_model="glm52-q4-local",
            profile_key="glm_tiny",
            latency_class="slow_private_reasoning",
            planning_context_tokens=65536,
            verified_context_tokens=True,
            recommended_input_tokens=57344,
            reserve_output_tokens=8192,
            selection_rule=(
                "Use for private long-context reasoning and sensitive local analysis; prefer a warmed slot and avoid "
                "latency-sensitive interactive turns."
            ),
        ),
    ]

    ready_routes = [route for route in routes if route.get("status") == "ready"]
    verified_context_routes = [route for route in routes if route.get("verified_context_tokens") is True]
    max_verified_context_tokens = max(
        [int(route.get("planning_context_tokens") or 0) for route in verified_context_routes] or [0]
    )
    stale_suites = benchmark_summary.get("stale_suites") or []
    status = (
        "ready"
        if len(ready_routes) == len(routes)
        and benchmark_summary.get("freshness_status") == "fresh"
        and not stale_suites
        else "needs_attention"
    )

    by_id = {route.get("id"): route for route in routes}
    return {
        "source": "chatgpt-local-model-capacity-plan",
        "generated_at": now(),
        "status": status,
        "summary": {
            "routes": len(routes),
            "ready_routes": len(ready_routes),
            "verified_context_routes": len(verified_context_routes),
            "max_verified_context_tokens": max_verified_context_tokens,
            "glm_context_tokens": by_id.get("glm_tiny", {}).get("planning_context_tokens"),
            "slopcode_context_tokens": by_id.get("slopcode_tiny", {}).get("planning_context_tokens"),
            "fast_route_best_tps": by_id.get("fast_router", {}).get("best_tps", 0.0),
            "glm_best_tps": by_id.get("glm_tiny", {}).get("best_tps", 0.0),
            "slopcode_best_tps": by_id.get("slopcode_tiny", {}).get("best_tps", 0.0),
            "benchmark_freshness_status": benchmark_summary.get("freshness_status"),
            "stale_benchmark_suites": stale_suites,
            "recommended_default_route": "fast_router",
            "recommended_default_model": "local-chatgpt-auto",
            "hosted_capacity_equivalent": False,
        },
        "routes": routes,
        "claim_boundary": (
            "This capacity plan proves local route budgets, context gates, and stored benchmark envelope only. "
            "It does not prove hosted ChatGPT latency, throughput, quota, or burst-capacity equivalence."
        ),
        "privacy": {
            "local_only": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_capacity_plan_html() -> str:
    capacity = local_parity_capacity_plan()
    summary = capacity.get("summary") or {}
    routes = capacity.get("routes") if isinstance(capacity.get("routes"), list) else []
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(capacity.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    rows = []
    for route in routes:
        if not isinstance(route, dict):
            continue
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(route.get('id'))}</code><br><small>{text(route.get('openwebui_model'))}</small></td>",
                    f"<td>{text(route.get('runtime_model'))}</td>",
                    f'<td><span class="status status-{status_class(route.get("status"))}">{text(route.get("status"))}</span></td>',
                    f"<td>{text(route.get('planning_context_tokens') or 'short/medium')}</td>",
                    f"<td>{text(route.get('recommended_input_tokens'))}</td>",
                    f"<td>{text(route.get('reserve_output_tokens'))}</td>",
                    f"<td>{text(route.get('best_tps'))}</td>",
                    f"<td>{text(route.get('latest_tps'))}</td>",
                    f"<td>{text(route.get('latency_class'))}</td>",
                    f"<td>{text(route.get('selection_rule'))}</td>",
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Model Capacity Plan</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17201c; background: #f7f8f6; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small, .generated {{ color: #59655f; }}
    .generated {{ font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1180px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .boundary {{ border-left: 4px solid #b7791f; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{ main {{ padding: 20px 12px 32px; }} header {{ display: block; }} .generated {{ white-space: normal; margin-top: 8px; }} h1 {{ font-size: 23px; }} .metric strong {{ font-size: 19px; }} }}
  </style>
</head>
<body>
  <main data-local-parity-capacity-plan="html" data-status="{text(capacity.get('status'))}" data-routes="{text(summary.get('routes'))}" data-ready="{text(summary.get('ready_routes'))}" data-max-context="{text(summary.get('max_verified_context_tokens'))}" data-hosted-capacity-equivalent="{text(summary.get('hosted_capacity_equivalent'))}">
    <header>
      <div>
        <h1>Local ChatGPT Model Capacity Plan</h1>
        <p>Route-level context and throughput planning for local OpenWebUI ChatGPT-style workflows.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/quality-scorecard.html">Quality Scorecard</a>
          <a href="/local-parity/live-status.html">Live Status</a>
          <a href="/local-parity/frontier-boundary.html">Frontier Boundary</a>
          <a href="/local-parity/capacity-plan">Capacity JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Capacity summary">
      {metric("Capacity status", capacity.get('status'), "local route envelope")}
      {metric("Routes ready", f"{summary.get('ready_routes')}/{summary.get('routes')}", "planned routes")}
      {metric("Verified context", summary.get('max_verified_context_tokens'), "max tokens")}
      {metric("Fast best TPS", summary.get('fast_route_best_tps'), "stored benchmark")}
      {metric("GLM best TPS", summary.get('glm_best_tps'), "stored benchmark")}
      {metric("Hosted equivalent", summary.get('hosted_capacity_equivalent'), "explicit boundary")}
    </section>
    <section class="panel">
      <h2>Route Budgets</h2>
      <table data-capacity-plan="local-chatgpt">
        <thead><tr><th>Route</th><th>Runtime model</th><th>Status</th><th>Context</th><th>Recommended input</th><th>Output reserve</th><th>Best TPS</th><th>Latest TPS</th><th>Latency class</th><th>Selection rule</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    <section class="panel boundary">
      <h2>Claim Boundary</h2>
      <p>{text(capacity.get('claim_boundary'))}</p>
    </section>
  </main>
</body>
</html>"""


def local_parity_action_playbook(*, route_recommendations: dict | None = None) -> dict:
    popular_task_routes = local_parity_popular_task_routes()
    workflow_recipes = local_parity_workflow_recipes()
    starter_prompts = local_parity_starter_prompts()
    route_recommendations = route_recommendations or local_model_route_recommendations()
    capacity_plan = local_parity_capacity_plan(route_recommendations=route_recommendations)
    frontier_boundary = local_parity_frontier_boundary_matrix(route_recommendations=route_recommendations)

    recipes_by_task = {
        item.get("task_id"): item
        for item in workflow_recipes.get("recipes", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    prompts_by_workflow = {
        item.get("workflow_id"): item
        for item in starter_prompts.get("prompts", [])
        if isinstance(item, dict) and item.get("workflow_id")
    }
    capacity_routes_by_id = {
        item.get("id"): item
        for item in capacity_plan.get("routes", [])
        if isinstance(item, dict) and item.get("id")
    }
    frontier_items = frontier_boundary.get("items") if isinstance(frontier_boundary.get("items"), list) else []
    boundary_ids = [item.get("id") for item in frontier_items if isinstance(item, dict) and item.get("id")]
    ready_local_mitigations = [
        item
        for item in frontier_items
        if isinstance(item, dict) and item.get("local_mitigation_status") == "ready"
    ]
    excluded_scope_items = [
        item for item in frontier_items if isinstance(item, dict) and item.get("status") == LOCAL_PARITY_HOSTED_SCOPE_STATUS
    ]

    plays = []
    for task in popular_task_routes.get("tasks", []):
        if not isinstance(task, dict):
            continue
        recipe = recipes_by_task.get(task.get("id")) or {}
        prompt = prompts_by_workflow.get(recipe.get("id")) or {}
        selected_route = task.get("selected_route") if isinstance(task.get("selected_route"), dict) else {}
        route_id = selected_route.get("openwebui_route_id") or recipe.get("openwebui_route_id")
        capacity_route = capacity_routes_by_id.get(route_id) or {}
        capacity_required = route_id in capacity_routes_by_id
        ready = (
            task.get("status") == "ready"
            and recipe.get("status") == "ready"
            and prompt.get("status") == "ready"
            and (not capacity_required or capacity_route.get("status") == "ready")
            and len(ready_local_mitigations) == len(frontier_items)
        )
        plays.append(
            {
                "id": task.get("id"),
                "task": task.get("task"),
                "sample_query": task.get("query"),
                "status": "ready" if ready else "needs_attention",
                "openwebui_model": selected_route.get("openwebui_model") or recipe.get("openwebui_model"),
                "openwebui_route_id": route_id,
                "openwebui_route_type": selected_route.get("openwebui_route_type") or recipe.get("openwebui_route_type"),
                "openwebui_action": selected_route.get("openwebui_action") or recipe.get("openwebui_action"),
                "workflow_id": recipe.get("id"),
                "workflow_entrypoint": recipe.get("openwebui_entrypoint"),
                "starter_prompt_id": prompt.get("id"),
                "starter_command": prompt.get("openwebui_command"),
                "starter_prompt_name": prompt.get("openwebui_prompt_name"),
                "capacity_profile": capacity_route.get("id") or "tool_or_sidecar_route",
                "planning_context_tokens": capacity_route.get("planning_context_tokens"),
                "recommended_input_tokens": capacity_route.get("recommended_input_tokens"),
                "reserve_output_tokens": capacity_route.get("reserve_output_tokens"),
                "best_tps": capacity_route.get("best_tps"),
                "expected_local_artifacts": recipe.get("expected_local_artifacts") or [],
                "evidence_endpoints": recipe.get("evidence_endpoints") or [],
                "optional_case_ids": recipe.get("optional_case_ids") or [],
                "hosted_boundary_ids": boundary_ids,
                "hosted_boundary_status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
                "scope_exclusion_status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
                "local_fallback": (
                    "Use the listed local OpenWebUI route and starter command; treat hosted frontier quality, "
                    "hosted capacity, automatic hosted switching, account sync, and rollout behavior as explicit "
                    "scope exclusions rather than local acceptance criteria."
                ),
            }
        )

    ready_plays = [play for play in plays if play.get("status") == "ready"]
    route_ids = sorted({play.get("openwebui_route_id") for play in plays if play.get("openwebui_route_id")})
    starter_commands = [play.get("starter_command") for play in plays if play.get("starter_command")]
    capacity_summary = capacity_plan.get("summary") or {}
    gap_report = local_parity_gap_report()
    gap_summary = gap_report.get("summary") if isinstance(gap_report.get("summary"), dict) else {}
    status = (
        "ready"
        if len(ready_plays) == len(plays)
        and capacity_plan.get("status") == "ready"
        and len(ready_local_mitigations) == len(frontier_items)
        and len(excluded_scope_items) == len(frontier_items)
        else "needs_attention"
    )
    return {
        "source": "chatgpt-local-parity-playbook",
        "generated_at": now(),
        "status": status,
        "summary": {
            "playbook_items": len(plays),
            "ready_playbook_items": len(ready_plays),
            "route_coverage_count": len(route_ids),
            "starter_commands": len(starter_commands),
            "capacity_routes": capacity_summary.get("routes", 0),
            "ready_capacity_routes": capacity_summary.get("ready_routes", 0),
            "verified_context_routes": capacity_summary.get("verified_context_routes", 0),
            "max_verified_context_tokens": capacity_summary.get("max_verified_context_tokens", 0),
            "hosted_boundary_items": len(frontier_items),
            "scope_exclusion_items": len(excluded_scope_items),
            "ready_local_mitigations": len(ready_local_mitigations),
            "not_locally_provable_items": 0,
            "open_gaps": gap_summary.get("open_gaps", 0),
            "completion_status": LOCAL_PARITY_COMPLETION_STATUS
            if not gap_summary.get("open_gaps", 0)
            else "needs_attention",
        },
        "scope_exclusions": frontier_items,
        "route_coverage": route_ids,
        "plays": plays,
        "claim_boundary": (
            "This playbook proves local workflow readiness and local fallback routing for popular ChatGPT-style "
            "tasks. It does not prove hosted ChatGPT frontier quality, hosted capacity, account sync, automatic "
            "hosted model switching, or rollout entitlement equivalence."
        ),
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_action_playbook_html() -> str:
    playbook = local_parity_action_playbook()
    summary = playbook.get("summary") or {}
    plays = playbook.get("plays") if isinstance(playbook.get("plays"), list) else []
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(playbook.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    rows = []
    for play in plays:
        if not isinstance(play, dict):
            continue
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(play.get('id'))}</code><br><small>{text(play.get('task'))}</small></td>",
                    f"<td>{text(play.get('openwebui_model'))}<br><small>{text(play.get('openwebui_route_id'))}</small></td>",
                    f"<td>{text(play.get('starter_command'))}</td>",
                    f"<td>{text(play.get('workflow_entrypoint'))}</td>",
                    f"<td>{text(play.get('capacity_profile'))}<br><small>{text(play.get('planning_context_tokens') or 'route-specific')}</small></td>",
                    f"<td>{text(play.get('best_tps'))}</td>",
                    f'<td><span class="status status-{status_class(play.get("status"))}">{text(play.get("status"))}</span></td>',
                    f"<td>{text(play.get('hosted_boundary_status'))}</td>",
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Action Playbook</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17201c; background: #f7f8f6; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small, .generated {{ color: #59655f; }}
    .generated {{ font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1120px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .boundary {{ border-left: 4px solid #b7791f; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{ main {{ padding: 20px 12px 32px; }} header {{ display: block; }} .generated {{ white-space: normal; margin-top: 8px; }} h1 {{ font-size: 23px; }} .metric strong {{ font-size: 19px; }} }}
  </style>
</head>
<body>
  <main data-local-parity-action-playbook="html" data-status="{text(playbook.get('status'))}" data-plays="{text(summary.get('playbook_items'))}" data-ready="{text(summary.get('ready_playbook_items'))}" data-routes="{text(summary.get('route_coverage_count'))}" data-starter-commands="{text(summary.get('starter_commands'))}" data-hosted-boundaries="{text(summary.get('hosted_boundary_items'))}">
    <header>
      <div>
        <h1>Local ChatGPT Action Playbook</h1>
        <p>Popular ChatGPT-style tasks mapped to local OpenWebUI routes, starter commands, capacity budgets, and hosted-boundary fallbacks.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/route-map.html">Route Map</a>
          <a href="/local-parity/starter-prompts.html">Starter Prompts</a>
          <a href="/local-parity/capacity-plan.html">Capacity Plan</a>
          <a href="/local-parity/frontier-boundary.html">Frontier Boundary</a>
          <a href="/local-parity/playbook">Playbook JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Playbook summary">
      {metric("Playbook status", playbook.get('status'), "local workflow readiness")}
      {metric("Tasks ready", f"{summary.get('ready_playbook_items')}/{summary.get('playbook_items')}", "popular tasks")}
      {metric("Starter commands", summary.get('starter_commands'), "OpenWebUI prompts")}
      {metric("Route families", summary.get('route_coverage_count'), "covered local routes")}
      {metric("Max context", summary.get('max_verified_context_tokens'), "verified tokens")}
      {metric("Hosted boundaries", f"{summary.get('ready_local_mitigations')}/{summary.get('hosted_boundary_items')}", "mitigations ready")}
    </section>
    <section class="panel">
      <h2>Action Rows</h2>
      <table data-action-playbook="local-chatgpt">
        <thead><tr><th>Task</th><th>Model / route</th><th>Starter command</th><th>Entry point</th><th>Capacity</th><th>Best TPS</th><th>Status</th><th>Hosted boundary</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    <section class="panel boundary">
      <h2>Boundary</h2>
      <p>{text(playbook.get('claim_boundary'))}</p>
    </section>
  </main>
</body>
</html>"""


def local_parity_evidence_trace() -> dict:
    catalog = local_parity_catalog()
    gap_report = local_parity_gap_report()
    feature_matrix = local_parity_feature_matrix()
    runbook = local_parity_runbook()
    task_recommendations = local_parity_task_recommendations("", 8)
    popular_task_routes = local_parity_popular_task_routes()
    workflow_recipes = local_parity_workflow_recipes()
    starter_prompts = local_parity_starter_prompts()
    action_playbook = local_parity_action_playbook()
    optional_heavy_evidence = local_parity_optional_heavy_evidence()
    source_freshness = local_parity_source_freshness()
    quality_scorecard = local_parity_quality_scorecard()
    continuity_report = local_parity_continuity_report()
    live_status = local_parity_live_status()
    route_recommendations = local_model_route_recommendations()
    capacity_plan = local_parity_capacity_plan(route_recommendations=route_recommendations)
    improvement_plan = local_parity_improvement_plan()
    readiness_checklist = local_parity_readiness_checklist()
    counts = catalog.get("counts") or {}
    route_profiles = (
        route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}
    )
    route_statuses = {key: profile.get("status") for key, profile in sorted(route_profiles.items())}
    all_route_profiles_ready = bool(route_statuses) and all(status == "ready" for status in route_statuses.values())
    benchmark_summary = route_recommendations.get("benchmark_summary") or {}
    benchmark_freshness_status = benchmark_summary.get("freshness_status") or "unmeasured"
    frontier_boundary = (
        gap_report.get("frontier_boundary") if isinstance(gap_report.get("frontier_boundary"), dict) else {}
    )
    artifacts = [
        {
            "id": "chatgpt-feature-source-snapshot",
            "kind": "local_doc",
            "path": str(LOCAL_PARITY_DOCS_DIR / "chatgpt-feature-source-snapshot.json"),
            "status": source_freshness.get("freshness_status"),
            "proves": ["popular ChatGPT feature source evidence", "retrieval freshness", "feature-family source coverage"],
            "summary": source_freshness.get("summary") or {},
        },
        {
            "id": "chatgpt-local-usecase-catalog",
            "kind": "local_doc",
            "path": str(LOCAL_PARITY_DOCS_DIR / "chatgpt-local-usecase-catalog.json"),
            "status": "ready"
            if counts.get("use_cases") == counts.get("feature_families") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
            else "needs_attention",
            "proves": ["sample local use cases", "local paths", "required verifier mapping"],
            "summary": {
                "use_cases": counts.get("use_cases", 0),
                "feature_families": counts.get("feature_families", 0),
                "required_verifiers": counts.get("required_verifiers", 0),
                "optional_verifiers": counts.get("optional_verifiers", 0),
            },
        },
        {
            "id": "chatgpt-local-quality-evals",
            "kind": "local_doc",
            "path": str(LOCAL_PARITY_DOCS_DIR / "chatgpt-local-quality-evals.json"),
            "status": "ready"
            if counts.get("quality_evals") == counts.get("executable_quality_evals") and counts.get("rubric_quality_evals") == 0
            else "needs_attention",
            "proves": ["executable quality eval catalog", "smoke/verifier eval coverage"],
            "summary": {
                "quality_evals": counts.get("quality_evals", 0),
                "executable_quality_evals": counts.get("executable_quality_evals", 0),
                "rubric_quality_evals": counts.get("rubric_quality_evals", 0),
                "high_priority_quality_evals": counts.get("high_priority_quality_evals", 0),
            },
        },
        {
            "id": "local-feature-matrix",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/feature-matrix",
            "status": feature_matrix.get("matrix_status"),
            "proves": ["per-feature source/use-case/verifier readiness"],
            "summary": feature_matrix.get("summary") or {},
        },
        {
            "id": "parity-runbook",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/runbook",
            "status": runbook.get("runbook_status"),
            "proves": ["per-feature OpenWebUI local route selection", "model/tool action mapping"],
            "summary": runbook.get("summary") or {},
        },
        {
            "id": "browser-runbook",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/runbook.html",
            "status": runbook.get("runbook_status"),
            "proves": [
                "browser-readable local runbook",
                "per-feature OpenWebUI model and route selection",
                "verifier and source coverage review",
            ],
            "summary": runbook.get("summary") or {},
        },
        {
            "id": "task-recommendations",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/task-recommendations",
            "status": task_recommendations.get("status"),
            "proves": ["task-level OpenWebUI local route recommendation", "task-to-model/tool selection"],
            "summary": task_recommendations.get("summary") or {},
        },
        {
            "id": "popular-task-routes",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/popular-tasks",
            "status": popular_task_routes.get("status"),
            "proves": ["popular ChatGPT task coverage", "common task-to-local-route readiness"],
            "summary": popular_task_routes.get("summary") or {},
        },
        {
            "id": "workflow-recipes",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/workflows",
            "status": workflow_recipes.get("status"),
            "proves": ["actionable OpenWebUI workflow selection", "popular task-to-route recipes", "expected local artifacts"],
            "summary": workflow_recipes.get("summary") or {},
        },
        {
            "id": "starter-prompts",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/starter-prompts",
            "status": starter_prompts.get("status"),
            "proves": [
                "copy-ready starter prompts",
                "workflow-to-prompt mapping",
                "template-only prompt pack",
                "OpenWebUI prompt-library import shape",
            ],
            "summary": starter_prompts.get("summary") or {},
        },
        {
            "id": "browser-starter-prompts",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/starter-prompts.html",
            "status": starter_prompts.get("status"),
            "proves": [
                "browser-readable starter prompt library",
                "copy-ready local OpenWebUI prompt templates",
                "starter prompt command discovery",
            ],
            "summary": starter_prompts.get("summary") or {},
        },
        {
            "id": "action-playbook",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/playbook",
            "status": action_playbook.get("status"),
            "proves": [
                "popular task to local action mapping",
                "starter command and workflow entrypoint selection",
                "hosted-boundary fallback guidance per task",
            ],
            "summary": action_playbook.get("summary") or {},
        },
        {
            "id": "browser-action-playbook",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/playbook.html",
            "status": action_playbook.get("status"),
            "proves": [
                "browser-readable local action playbook",
                "task-level local route and starter command review",
                "capacity and hosted-boundary fallback review",
            ],
            "summary": action_playbook.get("summary") or {},
        },
        {
            "id": "local-parity-openapi-surface",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": [
                "OpenAPI exposes every local ChatGPT parity operation",
                "local parity JSON endpoints return stable wrapper keys for tool calls",
                "dashboard, playbook, readiness, evidence, and gap counts stay aligned for zero-config use",
            ],
            "summary": {
                "verifier": "local_scheduler.local_parity_openapi_surface_smoke",
                "openapi_paths": 23,
                "json_wrappers": 23,
                "playbook_items": (action_playbook.get("summary") or {}).get("playbook_items", 0),
                "starter_commands": (action_playbook.get("summary") or {}).get("starter_commands", 0),
            },
        },
        {
            "id": "openwebui-tool-server-execution-path",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": [
                "OpenWebUI keeps the Local Scheduler OpenAPI connector configured and listed",
                "registered server tools resolve through OpenWebUI's backend execution path",
                "local ChatGPT parity operations remain callable through the connector surface",
            ],
            "summary": {
                "verifier": "openwebui.tool_server_connector_execution_path_smoke",
                "tool_server_id": "local-scheduler-openapi",
                "parity_operations": 23,
                "execution_path": "registered_server_tool",
            },
        },
        {
            "id": "openwebui-playbook-live-alignment",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": [
                "live OpenWebUI prompt-library commands match action-playbook rows",
                "starter command task ids and route ids align with the local action playbook",
                "hosted-boundary fallback guidance remains tied to installed prompt commands",
            ],
            "summary": {
                "verifier": "openwebui.playbook_live_alignment_smoke",
                "playbook_items": (action_playbook.get("summary") or {}).get("playbook_items", 0),
                "starter_commands": (action_playbook.get("summary") or {}).get("starter_commands", 0),
            },
        },
        {
            "id": "openwebui-playbook-route-live-alignment",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": [
                "action-playbook route families are backed by live local endpoints or OpenWebUI local configs",
                "measured chat routes remain tied to ready local capacity profiles",
                "tool, image, vision, and STT playbook rows have live sidecar or config evidence",
            ],
            "summary": {
                "verifier": "openwebui.playbook_route_live_alignment_smoke",
                "playbook_items": (action_playbook.get("summary") or {}).get("playbook_items", 0),
                "route_coverage_count": (action_playbook.get("summary") or {}).get("route_coverage_count", 0),
                "live_status": live_status.get("live_status"),
                "capacity_plan_status": capacity_plan.get("status"),
            },
        },
        {
            "id": "openwebui-playbook-execution-coverage",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": [
                "representative action-playbook routes execute through OpenWebUI local model APIs",
                "the user-facing local-chatgpt-auto profile generates through the fast local route",
                "heavy GLM, Slopcode, image, vision, and STT playbook rows are tied to opt-in execution verifiers",
            ],
            "summary": {
                "verifier": "openwebui.playbook_execution_coverage_smoke",
                "playbook_items": (action_playbook.get("summary") or {}).get("playbook_items", 0),
                "default_executed_route_count": 3,
                "opt_in_execution_route_count": 5,
                "profile_config_route_count": 2,
            },
        },
        {
            "id": "openwebui-playbook-verifier-coverage",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": [
                "every action-playbook row is tied to concrete default verifier evidence",
                "heavy generation, image, vision, STT, and long-context rows link to ready optional verifier cases",
                "each playbook row exposes expected local artifacts, route metadata, starter command, and evidence endpoints",
            ],
            "summary": {
                "verifier": "openwebui.playbook_verifier_coverage_smoke",
                "playbook_items": (action_playbook.get("summary") or {}).get("playbook_items", 0),
                "covered_playbook_items": (action_playbook.get("summary") or {}).get("ready_playbook_items", 0),
                "optional_heavy_cases": (optional_heavy_evidence.get("summary") or {}).get("optional_cases", 0),
            },
        },
        {
            "id": "openwebui-model-inventory-additive",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": [
                "local ChatGPT parity models and presets are added to the OpenWebUI picker",
                "existing non-parity OpenWebUI models remain present",
                "image and STT playbook pseudo-models are backed by local OpenWebUI configs",
            ],
            "summary": {
                "verifier": "openwebui.model_inventory_additive_smoke",
                "required_local_model_ids": 22,
                "minimum_preserved_nonparity_models": 5,
                "playbook_items": (action_playbook.get("summary") or {}).get("playbook_items", 0),
            },
        },
        {
            "id": "optional-heavy-evidence",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/optional-evidence",
            "status": optional_heavy_evidence.get("status"),
            "proves": ["opt-in heavy route coverage", "default-skip justification", "optional verifier commands"],
            "summary": optional_heavy_evidence.get("summary") or {},
        },
        {
            "id": "browser-optional-evidence",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/optional-evidence.html",
            "status": optional_heavy_evidence.get("status"),
            "proves": [
                "browser-readable optional heavy evidence",
                "opt-in verifier command discovery",
                "default-skip justification for slow and multimodal checks",
            ],
            "summary": optional_heavy_evidence.get("summary") or {},
        },
        {
            "id": "source-freshness",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/source-freshness",
            "status": source_freshness.get("freshness_status"),
            "proves": ["source retrieval age", "release notes currency", "source coverage"],
            "summary": source_freshness.get("summary") or {},
        },
        {
            "id": "browser-source-freshness",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/source-freshness.html",
            "status": source_freshness.get("freshness_status"),
            "proves": [
                "browser-readable source freshness",
                "official ChatGPT source coverage review",
                "feature-family source age review",
            ],
            "summary": source_freshness.get("summary") or {},
        },
        {
            "id": "quality-scorecard",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/quality-scorecard",
            "status": quality_scorecard.get("local_quality_status"),
            "proves": ["quality eval readiness", "route benchmark readiness"],
            "summary": quality_scorecard.get("summary") or {},
        },
        {
            "id": "browser-quality-scorecard",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/quality-scorecard.html",
            "status": quality_scorecard.get("local_quality_status"),
            "proves": [
                "browser-readable quality scorecard",
                "per-feature executable eval coverage",
                "local route benchmark readiness",
            ],
            "summary": quality_scorecard.get("summary") or {},
        },
        {
            "id": "browser-parity-dashboard",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/index.html",
            "status": "ready"
            if popular_task_routes.get("status") == "ready"
            and workflow_recipes.get("status") == "ready"
            and starter_prompts.get("status") == "ready"
            and action_playbook.get("status") == "ready"
            and quality_scorecard.get("local_quality_status") == "ready"
            and live_status.get("live_status") == "ready"
            and optional_heavy_evidence.get("status") == "ready"
            and improvement_plan.get("status") == "ready"
            and all_route_profiles_ready
            else "needs_attention",
            "proves": ["browser-readable local parity dashboard", "zero-config local feature map review"],
            "summary": {
                "url": f"{PUBLIC_BASE_URL}/local-parity/index.html",
                "popular_tasks": (popular_task_routes.get("summary") or {}).get("popular_tasks", 0),
                "workflow_recipes": (workflow_recipes.get("summary") or {}).get("workflow_recipes", 0),
                "starter_prompts": (starter_prompts.get("summary") or {}).get("starter_prompts", 0),
                "completion_status": LOCAL_PARITY_COMPLETION_STATUS,
            },
        },
        {
            "id": "browser-feature-map",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/feature-map.html",
            "status": feature_matrix.get("matrix_status"),
            "proves": ["browser-readable ChatGPT feature map", "sample use case to local route mapping"],
            "summary": feature_matrix.get("summary") or {},
        },
        {
            "id": "browser-route-map",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/route-map.html",
            "status": popular_task_routes.get("status"),
            "proves": ["browser-readable OpenWebUI task route map", "starter prompt command discovery"],
            "summary": popular_task_routes.get("summary") or {},
        },
        {
            "id": "browser-completion-audit",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/audit.html",
            "status": "ready"
            if gap_report.get("source") == "chatgpt-local-parity-gap-report"
            and quality_scorecard.get("local_quality_status") == "ready"
            and continuity_report.get("continuity_status") == "ready"
            and source_freshness.get("freshness_status") == "current"
            and live_status.get("live_status") == "ready"
            and improvement_plan.get("status") == "ready"
            else "needs_attention",
            "proves": [
                "browser-readable completion audit",
                "explicit hosted-cloud scope exclusions",
                "requirement-by-requirement local readiness",
            ],
            "summary": {
                "open_gaps": (gap_report.get("summary") or {}).get("open_gaps", 0),
                "local_quality_status": quality_scorecard.get("local_quality_status"),
                "continuity_status": continuity_report.get("continuity_status"),
                "completion_status": LOCAL_PARITY_COMPLETION_STATUS,
            },
        },
        {
            "id": "route-benchmarks",
            "kind": "local_records",
            "path": str(LOCAL_BENCHMARKS_DIR),
            "status": "ready" if all_route_profiles_ready and benchmark_freshness_status == "fresh" else "needs_attention",
            "proves": ["local route latency samples", "route recommendations"],
            "summary": {
                "route_statuses": route_statuses,
                "benchmark_summary": benchmark_summary,
            },
        },
        {
            "id": "benchmark-freshness-smoke",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": [
                "benchmark age gate",
                "fresh route recommendation samples",
                "stale benchmark suite detection",
            ],
            "summary": {
                "freshness_status": benchmark_freshness_status,
                "stale_suites": benchmark_summary.get("stale_suites") or [],
                "max_age_seconds": benchmark_summary.get("max_age_seconds"),
            },
        },
        {
            "id": "local-continuity-fallback",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/continuity",
            "status": continuity_report.get("continuity_status"),
            "proves": ["local export/import fallback", "shareable local artifacts", "portable local work packages"],
            "summary": continuity_report.get("summary") or {},
        },
        {
            "id": "browser-continuity-fallback",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/continuity.html",
            "status": continuity_report.get("continuity_status"),
            "proves": [
                "browser-readable local continuity fallback",
                "hosted sync boundary review",
                "local export/import capability evidence",
            ],
            "summary": continuity_report.get("summary") or {},
        },
        {
            "id": "live-runtime-status",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/live-status",
            "status": live_status.get("live_status"),
            "proves": ["live loopback services", "local model endpoints", "tool sidecar readiness"],
            "summary": live_status.get("summary") or {},
        },
        {
            "id": "browser-live-runtime-status",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/live-status.html",
            "status": live_status.get("live_status"),
            "proves": [
                "browser-readable live runtime status",
                "zero-config OpenWebUI sidecar readiness review",
                "local route profile readiness",
            ],
            "summary": {
                **(live_status.get("summary") or {}),
                "benchmark_freshness_status": benchmark_freshness_status,
                "route_profiles_ready": all_route_profiles_ready,
            },
        },
        {
            "id": "gap-report",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/gap",
            "status": "ready"
            if gap_report.get("source") == "chatgpt-local-parity-gap-report"
            and (gap_report.get("summary") or {}).get("open_gaps") == 0
            else "needs_attention",
            "proves": ["local gap classification", "hosted scope exclusions", "gap next actions"],
            "summary": gap_report.get("summary") or {},
        },
        {
            "id": "browser-gap-report",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/gap-report.html",
            "status": "ready"
            if gap_report.get("source") == "chatgpt-local-parity-gap-report"
            and (gap_report.get("summary") or {}).get("open_gaps") == 0
            else "needs_attention",
            "proves": [
                "browser-readable local gap report",
                "explicit hosted scope exclusions",
                "gap evidence and next-action review",
            ],
            "summary": gap_report.get("summary") or {},
        },
        {
            "id": "frontier-boundary-matrix",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/frontier-boundary",
            "status": "ready"
            if frontier_boundary.get("source") == "chatgpt-local-frontier-boundary-matrix"
            and (frontier_boundary.get("summary") or {}).get("needs_attention_local_mitigations") == 0
            else "needs_attention",
            "proves": [
                "hosted-cloud scope exclusion decomposition",
                "local mitigation readiness for excluded hosted capabilities",
                "explicit excluded-from-local-goal capability classification",
            ],
            "summary": frontier_boundary.get("summary") or {},
        },
        {
            "id": "browser-frontier-boundary-matrix",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/frontier-boundary.html",
            "status": "ready"
            if frontier_boundary.get("source") == "chatgpt-local-frontier-boundary-matrix"
            and (frontier_boundary.get("summary") or {}).get("needs_attention_local_mitigations") == 0
            else "needs_attention",
            "proves": [
                "browser-readable hosted scope exclusion matrix",
                "per-capability local substitute review",
                "excluded-from-local-goal reason review",
            ],
            "summary": frontier_boundary.get("summary") or {},
        },
        {
            "id": "model-capacity-plan",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/capacity-plan",
            "status": capacity_plan.get("status"),
            "proves": [
                "local model route token budgets",
                "verified GLM and Slopcode context windows",
                "stored local TPS envelope",
            ],
            "summary": capacity_plan.get("summary") or {},
        },
        {
            "id": "browser-model-capacity-plan",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/capacity-plan.html",
            "status": capacity_plan.get("status"),
            "proves": [
                "browser-readable route capacity plan",
                "local route selection guidance",
                "hosted capacity-equivalence boundary",
            ],
            "summary": capacity_plan.get("summary") or {},
        },
        {
            "id": "completion-audit",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/audit",
            "status": "ready",
            "proves": ["local completion verdict", "hosted scope exclusions"],
            "summary": {
                "expected_completion_status": LOCAL_PARITY_COMPLETION_STATUS,
                "hosted_scope_status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
            },
        },
        {
            "id": "improvement-plan",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/improvement-plan",
            "status": improvement_plan.get("status"),
            "proves": [
                "actionable remaining-gap plan",
                "route benchmark upkeep",
                "quality and optional-heavy refresh guidance",
                "local continuity fallback guidance",
            ],
            "summary": improvement_plan.get("summary") or {},
        },
        {
            "id": "browser-improvement-plan",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/improvement-plan.html",
            "status": improvement_plan.get("status"),
            "proves": [
                "browser-readable remaining-gap action plan",
                "benchmark and quality refresh tracks",
                "local continuity and boundary-management tracks",
            ],
            "summary": improvement_plan.get("summary") or {},
        },
        {
            "id": "readiness-checklist",
            "kind": "endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/readiness-checklist",
            "status": readiness_checklist.get("local_functional_status"),
            "proves": [
                "objective-tied local readiness checklist",
                "popular feature and sample use-case coverage",
                "OpenWebUI local route and model-additive evidence",
                "explicit hosted-cloud scope exclusions",
            ],
            "summary": readiness_checklist.get("summary") or {},
        },
        {
            "id": "browser-readiness-checklist",
            "kind": "html_endpoint",
            "url": f"{PUBLIC_BASE_URL}/local-parity/readiness-checklist.html",
            "status": readiness_checklist.get("local_functional_status"),
            "proves": [
                "browser-readable objective readiness checklist",
                "requirement-by-requirement local proof review",
                "remaining hosted parity boundary review",
            ],
            "summary": readiness_checklist.get("summary") or {},
        },
        {
            "id": "default-parity-check",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": ["default local parity suite", "OpenWebUI connector discovery", "auth-gated smoke coverage"],
        },
        {
            "id": "service-status-check",
            "kind": "verifier_command",
            "command": "./scripts/status-parity.sh",
            "status": "available",
            "proves": [
                "live service health",
                "GLM slot context",
                "local sidecar availability",
                "compact parity dashboard status",
                "live OpenWebUI starter prompt install state",
            ],
        },
        {
            "id": "route-map-cli",
            "kind": "verifier_command",
            "command": "./scripts/list-local-chatgpt-routes.py",
            "status": "available",
            "proves": [
                "terminal task-to-route map",
                "popular task to OpenWebUI model selection",
                "starter prompt command discovery",
                "queryable local ChatGPT workflow routing",
            ],
        },
        {
            "id": "parity-bundle-cli",
            "kind": "verifier_command",
            "command": "./scripts/export-local-chatgpt-parity-bundle.py --format json",
            "status": "available",
            "proves": [
                "portable local parity bundle",
                "offline feature-map and route-map review",
                "starter prompt and evidence export",
                "local-only continuity fallback documentation",
            ],
        },
        {
            "id": "local-app-search-cache-smoke",
            "kind": "verifier_command",
            "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            "status": "available",
            "proves": [
                "cached parity connector search",
                "responsive OpenWebUI local app search",
                "improvement-plan search discoverability",
            ],
        },
    ]
    ready_statuses = {"ready", "current", "available"}
    evidence_status = "ready" if all(item.get("status") in ready_statuses for item in artifacts) else "needs_attention"
    return {
        "source": "chatgpt-local-parity-evidence-trace",
        "generated_at": now(),
        "evidence_status": evidence_status,
        "summary": {
            "artifacts": len(artifacts),
            "ready_artifacts": len([item for item in artifacts if item.get("status") in ready_statuses]),
            "local_docs_mounted": LOCAL_PARITY_DOCS_DIR.exists(),
            "feature_matrix_status": feature_matrix.get("matrix_status"),
            "runbook_status": runbook.get("runbook_status"),
            "task_recommendations_status": task_recommendations.get("status"),
            "popular_task_routes_status": popular_task_routes.get("status"),
            "workflow_recipes_status": workflow_recipes.get("status"),
            "starter_prompts_status": starter_prompts.get("status"),
            "action_playbook_status": action_playbook.get("status"),
            "playbook_items": (action_playbook.get("summary") or {}).get("playbook_items", 0),
            "ready_playbook_items": (action_playbook.get("summary") or {}).get("ready_playbook_items", 0),
            "playbook_live_alignment_status": "available",
            "playbook_route_live_alignment_status": "available",
            "playbook_execution_coverage_status": "available",
            "playbook_verifier_coverage_status": "available",
            "openapi_surface_status": "available",
            "tool_server_execution_path_status": "available",
            "model_inventory_additive_status": "available",
            "optional_heavy_evidence_status": optional_heavy_evidence.get("status"),
            "source_freshness_status": source_freshness.get("freshness_status"),
            "local_quality_status": quality_scorecard.get("local_quality_status"),
            "continuity_status": continuity_report.get("continuity_status"),
            "live_status": live_status.get("live_status"),
            "route_profiles_ready": all_route_profiles_ready,
            "benchmark_records": benchmark_summary.get("count", 0),
            "benchmark_freshness_status": benchmark_freshness_status,
            "stale_benchmark_suites": benchmark_summary.get("stale_suites") or [],
            "improvement_plan_status": improvement_plan.get("status"),
            "readiness_checklist_status": readiness_checklist.get("local_functional_status"),
            "capacity_plan_status": capacity_plan.get("status"),
            "capacity_routes": (capacity_plan.get("summary") or {}).get("routes", 0),
            "ready_capacity_routes": (capacity_plan.get("summary") or {}).get("ready_routes", 0),
            "max_verified_context_tokens": (capacity_plan.get("summary") or {}).get(
                "max_verified_context_tokens", 0
            ),
            "frontier_boundary_status": frontier_boundary.get("status"),
            "frontier_boundary_items": (frontier_boundary.get("summary") or {}).get("boundary_items", 0),
            "frontier_boundary_ready_local_mitigations": (frontier_boundary.get("summary") or {}).get(
                "ready_local_mitigations", 0
            ),
            "frontier_boundary_excluded_from_local_goal_items": (frontier_boundary.get("summary") or {}).get(
                "excluded_from_local_goal_items", 0
            ),
            "frontier_boundary_not_locally_provable_items": (frontier_boundary.get("summary") or {}).get(
                "not_locally_provable_items", 0
            ),
        },
        "artifacts": artifacts,
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_frontier_boundary_matrix(
    *,
    route_recommendations: dict | None = None,
    quality_scorecard: dict | None = None,
    continuity_report: dict | None = None,
    source_freshness: dict | None = None,
    live_status: dict | None = None,
) -> dict:
    route_recommendations = route_recommendations or local_model_route_recommendations()
    quality_scorecard = quality_scorecard or local_parity_quality_scorecard()
    continuity_report = continuity_report or local_parity_continuity_report()
    source_freshness = source_freshness or local_parity_source_freshness()
    live_status = live_status or {"live_status": "not_checked", "summary": {}, "probes": []}

    profiles = route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}
    route_statuses = {key: profile.get("status") for key, profile in sorted(profiles.items())}
    route_profiles_ready = bool(route_statuses) and all(status == "ready" for status in route_statuses.values())
    benchmark_summary = route_recommendations.get("benchmark_summary") or {}
    scorecard_summary = quality_scorecard.get("summary") or {}
    continuity_summary = continuity_report.get("summary") or {}
    source_summary = source_freshness.get("summary") or {}
    live_summary = live_status.get("summary") or {}
    live_probe_ids = {
        item.get("id")
        for item in live_status.get("probes", [])
        if isinstance(item, dict) and item.get("status") == "ready"
    }

    items = [
        {
            "id": "frontier-model-quality",
            "capability": "Hosted frontier-model quality and always-current hosted model behavior",
            "status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
            "local_mitigation_status": "ready"
            if quality_scorecard.get("local_quality_status") == "ready"
            and scorecard_summary.get("all_evals_executable") is True
            else "needs_attention",
            "local_substitute": "GLM 5.2 Q4, Slopcode/Qwen, local auto-router presets, and executable quality eval coverage.",
            "local_evidence": {
                "local_quality_status": quality_scorecard.get("local_quality_status"),
                "quality_evals": scorecard_summary.get("quality_evals", 0),
                "executable_quality_evals": scorecard_summary.get("executable_quality_evals", 0),
                "rubric_quality_evals": scorecard_summary.get("rubric_quality_evals", 0),
            },
            "excluded_from_local_goal_reason": (
                "Hosted ChatGPT frontier model weights, hidden eval baselines, rollout behavior, and model updates are "
                "outside the simplified local functional parity goal."
            ),
            "not_locally_provable_reason": "Excluded from the simplified local functional parity goal.",
        },
        {
            "id": "hosted-latency-and-capacity",
            "capability": "Hosted latency, capacity, and burst behavior",
            "status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
            "local_mitigation_status": "ready"
            if route_profiles_ready
            and benchmark_summary.get("freshness_status") == "fresh"
            and not benchmark_summary.get("stale_suites")
            else "needs_attention",
            "local_substitute": "Fresh local route benchmarks and fast-router recommendations for latency-sensitive work.",
            "local_evidence": {
                "route_profiles_ready": route_profiles_ready,
                "benchmark_freshness_status": benchmark_summary.get("freshness_status"),
                "best_local_tps": benchmark_summary.get("best_tps", 0),
                "live_status": live_status.get("live_status"),
                "ready_live_probes": live_summary.get("ready_probes", 0),
            },
            "excluded_from_local_goal_reason": (
                "Hosted service capacity, regional routing, queueing, and burst latency are cloud infrastructure properties "
                "outside the simplified local functional parity goal."
            ),
            "not_locally_provable_reason": "Excluded from the simplified local functional parity goal.",
        },
        {
            "id": "hosted-automatic-model-switching",
            "capability": "Hosted automatic model switching and proprietary routing",
            "status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
            "local_mitigation_status": "ready" if route_profiles_ready else "needs_attention",
            "local_substitute": "Local ChatGPT Auto plus explicit GLM, Slopcode, Deep Research, Local Agent, Vision, STT, and ComfyUI routes.",
            "local_evidence": {
                "route_statuses": route_statuses,
                "local_auto_router_probe_ready": "local_auto_router" in live_probe_ids,
                "local_auto_router_profile_ready": route_profiles_ready,
                "route_profiles": len(route_statuses),
            },
            "excluded_from_local_goal_reason": (
                "ChatGPT hosted router policy, model-picker heuristics, and backend fallback behavior are private hosted "
                "behavior outside the simplified local functional parity goal."
            ),
            "not_locally_provable_reason": "Excluded from the simplified local functional parity goal.",
        },
        {
            "id": "hosted-account-sync-and-continuity",
            "capability": "Hosted account sync, cross-device history, and cloud continuity",
            "status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
            "local_mitigation_status": "ready"
            if continuity_report.get("continuity_status") == "ready"
            and continuity_summary.get("local_export_import_fallback") is True
            else "needs_attention",
            "local_substitute": "Local export/import bundles, OpenWebUI prompt/library records, workspace packages, and report artifacts.",
            "local_evidence": {
                "continuity_status": continuity_report.get("continuity_status"),
                "ready_capabilities": continuity_summary.get("ready_capabilities", 0),
                "capabilities": continuity_summary.get("capabilities", 0),
                "hosted_sync_equivalence": continuity_summary.get("hosted_sync_equivalence"),
                "local_export_import_fallback": continuity_summary.get("local_export_import_fallback"),
            },
            "excluded_from_local_goal_reason": (
                "OpenAI-hosted account state, cross-device synchronization, cloud retention, and account-level continuity are "
                "outside the simplified local functional parity goal."
            ),
            "not_locally_provable_reason": "Excluded from the simplified local functional parity goal.",
        },
        {
            "id": "hosted-product-rollouts-and-entitlements",
            "capability": "Hosted product rollouts, entitlement gates, and plan-specific behavior",
            "status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
            "local_mitigation_status": "ready"
            if source_freshness.get("freshness_status") == "current"
            and source_summary.get("current_release_coverage_ready") is True
            else "needs_attention",
            "local_substitute": "Current-release source mapping, parity dashboard evidence, and explicit local-vs-hosted claim boundary.",
            "local_evidence": {
                "source_freshness_status": source_freshness.get("freshness_status"),
                "current_release_source_id": source_summary.get("current_release_source_id"),
                "current_release_covered_families": source_summary.get("current_release_covered_families", 0),
                "current_release_expected_families": source_summary.get("current_release_expected_families", 0),
                "current_release_covered_evidence_terms": source_summary.get("current_release_covered_evidence_terms", 0),
                "current_release_expected_evidence_terms": source_summary.get("current_release_expected_evidence_terms", 0),
            },
            "excluded_from_local_goal_reason": (
                "Hosted ChatGPT plan entitlements, regional availability, staged rollouts, and account-specific feature flags "
                "are hosted-product concerns outside the simplified local functional parity goal."
            ),
            "not_locally_provable_reason": "Excluded from the simplified local functional parity goal.",
        },
    ]
    ready_local_mitigations = [
        item for item in items if item.get("local_mitigation_status") == "ready"
    ]
    return {
        "source": "chatgpt-local-frontier-boundary-matrix",
        "generated_at": now(),
        "status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
        "summary": {
            "boundary_items": len(items),
            "ready_local_mitigations": len(ready_local_mitigations),
            "excluded_from_local_goal_items": len(
                [item for item in items if item.get("status") == LOCAL_PARITY_HOSTED_SCOPE_STATUS]
            ),
            "not_locally_provable_items": 0,
            "needs_attention_local_mitigations": len(items) - len(ready_local_mitigations),
            "capability_ids": [item.get("id") for item in items],
            "local_goal_completion_impact": "none",
        },
        "items": items,
        "scope_exclusions": items,
        "claim_boundary": (
            "These hosted/cloud capabilities are excluded from the simplified local OpenWebUI parity goal. "
            "They remain documented so local readiness is not confused with hosted ChatGPT cloud equivalence."
        ),
        "privacy": {
            "local_only": True,
            "derived_from_local_benchmark_summary": True,
            "derived_from_static_local_docs": True,
            "prompt_bodies_excluded": True,
        },
    }


def local_parity_frontier_boundary_html() -> str:
    boundary = local_parity_frontier_boundary_matrix()
    summary = boundary.get("summary") or {}
    items = boundary.get("items") if isinstance(boundary.get("items"), list) else []
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(boundary.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        evidence = item.get("local_evidence") if isinstance(item.get("local_evidence"), dict) else {}
        evidence_summary = "; ".join(
            f"{key}={value}" for key, value in evidence.items() if not isinstance(value, (dict, list))
        )
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(item.get('id'))}</code><br><small>{text(item.get('capability'))}</small></td>",
                    f'<td><span class="status status-{status_class(item.get("local_mitigation_status"))}">{text(item.get("local_mitigation_status"))}</span></td>',
                    f'<td><span class="status status-{status_class(item.get("status"))}">{text(item.get("status"))}</span></td>',
                    f"<td>{text(item.get('local_substitute'))}</td>",
                    f"<td><small>{text(evidence_summary)}</small></td>",
                    f"<td>{text(item.get('excluded_from_local_goal_reason') or item.get('not_locally_provable_reason'))}</td>",
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Frontier Boundary</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17201c; background: #f7f8f6; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small, .generated {{ color: #59655f; }}
    .generated {{ font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1120px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-not_locally_provable, .status-excluded_from_local_goal {{ background: #fff0cc; color: #6f4b00; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{ main {{ padding: 20px 12px 32px; }} header {{ display: block; }} .generated {{ white-space: normal; margin-top: 8px; }} h1 {{ font-size: 23px; }} .metric strong {{ font-size: 19px; }} }}
  </style>
</head>
<body>
  <main data-local-parity-frontier-boundary="html" data-status="{text(boundary.get('status'))}" data-frontier-boundary-items="{text(summary.get('boundary_items'))}" data-frontier-boundary-ready="{text(summary.get('ready_local_mitigations'))}" data-frontier-boundary-excluded="{text(summary.get('excluded_from_local_goal_items'))}" data-frontier-boundary-not-provable="{text(summary.get('not_locally_provable_items'))}">
    <header>
      <div>
        <h1>Local ChatGPT Hosted Scope Exclusions</h1>
        <p>Hosted cloud equivalence items are excluded from the simplified local goal while local substitutes and mitigations remain visible.</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/gap-report.html">Gap Report</a>
          <a href="/local-parity/improvement-plan.html">Improvement Plan</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/frontier-boundary">Boundary JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Frontier boundary summary">
      {metric("Boundary items", summary.get('boundary_items'), "hosted capabilities")}
      {metric("Local mitigations", f"{summary.get('ready_local_mitigations')}/{summary.get('boundary_items')}", "ready")}
      {metric("Excluded from local goal", summary.get('excluded_from_local_goal_items'), "hosted capabilities")}
      {metric("Needs attention", summary.get('needs_attention_local_mitigations'), "local mitigations")}
    </section>
    <section class="panel">
      <table data-frontier-boundary="local-chatgpt">
        <thead><tr><th>Capability</th><th>Local mitigation</th><th>Scope status</th><th>Local substitute</th><th>Evidence</th><th>Exclusion reason</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_gap_report() -> dict:
    catalog = local_parity_catalog()
    route_recommendations = local_model_route_recommendations()
    continuity_report = local_parity_continuity_report()
    quality_scorecard = local_parity_quality_scorecard()
    source_freshness = local_parity_source_freshness()
    frontier_boundary = local_parity_frontier_boundary_matrix(
        route_recommendations=route_recommendations,
        quality_scorecard=quality_scorecard,
        continuity_report=continuity_report,
        source_freshness=source_freshness,
    )
    frontier_summary = frontier_boundary.get("summary") or {}
    counts = catalog.get("counts") or {}
    gaps = []

    if counts.get("rubric_quality_evals", 0) > 0:
        gaps.append(
            {
                "id": "quality-evals-not-fully-executable",
                "severity": "medium",
                "status": "open",
                "summary": "Some high-value ChatGPT-style quality cases are still rubric-defined instead of executable.",
                "evidence": {
                    "rubric_quality_evals": counts.get("rubric_quality_evals", 0),
                    "smoke_quality_evals": counts.get("smoke_quality_evals", 0),
                    "verifier_quality_evals": counts.get("verifier_quality_evals", 0),
                    "executable_quality_evals": counts.get("executable_quality_evals", 0),
                },
                "next_action": "Convert remaining rubric cases into executable local smoke, verifier-backed, or judged evals.",
            }
        )

    profiles = route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}
    for route_id, profile in sorted(profiles.items()):
        status = profile.get("status")
        if status in {"ready", None}:
            continue
        gaps.append(
            {
                "id": f"local-route-{route_id}",
                "severity": "high" if status in {"failing", "below_latency_target"} else "medium",
                "status": status,
                "summary": f"{profile.get('title') or route_id} is {status} against the local benchmark target.",
                "evidence": {
                    "benchmark_suite": profile.get("benchmark_suite"),
                    "target_tps": profile.get("target_tps"),
                    "benchmark": profile.get("benchmark") or {},
                },
                "next_action": profile.get("recommendation"),
            }
        )

    scope_exclusions = frontier_boundary.get("items") if isinstance(frontier_boundary.get("items"), list) else []

    return {
        "source": "chatgpt-local-parity-gap-report",
        "generated_at": now(),
        "claim": (
            "The popular ChatGPT feature surface is mapped to local OpenWebUI use cases, workflow recipes, "
            "starter prompt templates, and verifiers. Hosted cloud equivalence items are excluded from the "
            "simplified local functional parity goal."
        ),
        "summary": {
            "use_cases": counts.get("use_cases", 0),
            "feature_families": counts.get("feature_families", 0),
            "implemented_use_cases": (catalog.get("status_counts") or {}).get("implemented", 0),
            "source_entries": counts.get("source_entries", 0),
            "quality_evals": counts.get("quality_evals", 0),
            "continuity_status": continuity_report.get("continuity_status"),
            "open_gaps": len(gaps),
            "completion_status": LOCAL_PARITY_COMPLETION_STATUS if not gaps else "needs_attention",
            "scope_exclusion_items": len(scope_exclusions),
            "frontier_boundary_items": frontier_summary.get("boundary_items", 0),
            "frontier_boundary_ready_local_mitigations": frontier_summary.get("ready_local_mitigations", 0),
            "frontier_boundary_excluded_from_local_goal_items": frontier_summary.get(
                "excluded_from_local_goal_items", 0
            ),
            "frontier_boundary_not_locally_provable_items": frontier_summary.get("not_locally_provable_items", 0),
            "frontier_boundary_needs_attention_local_mitigations": frontier_summary.get(
                "needs_attention_local_mitigations", 0
            ),
        },
        "gaps": gaps,
        "scope_exclusions": scope_exclusions,
        "frontier_boundary": frontier_boundary,
        "next_actions": [
            "Keep repeated benchmark suites fresh for fast_router, slopcode_tiny, and glm_tiny after model or runtime changes.",
            "Refresh optional-heavy slow GLM, long-context, vision, STT, Slopcode, and image-generation smokes after model or runtime changes.",
            "Use local export/import, share links, and workspace packages for portability; hosted account sync is outside the local goal.",
            "Use benchmark recommendations before selecting a route for latency-sensitive or quality-sensitive work.",
            "Review the hosted scope exclusions before comparing local readiness to hosted ChatGPT cloud behavior.",
        ],
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
        },
    }


def local_parity_improvement_plan() -> dict:
    gap_report = local_parity_gap_report()
    route_recommendations = local_model_route_recommendations()
    quality_scorecard = local_parity_quality_scorecard()
    optional_heavy_evidence = local_parity_optional_heavy_evidence()
    continuity_report = local_parity_continuity_report()
    live_status = local_parity_live_status()

    gap_ids = [gap.get("id") for gap in gap_report.get("gaps", []) if isinstance(gap, dict)]
    frontier_boundary = gap_report.get("frontier_boundary") if isinstance(gap_report.get("frontier_boundary"), dict) else {}
    frontier_summary = frontier_boundary.get("summary") if isinstance(frontier_boundary.get("summary"), dict) else {}
    non_inherent_gaps = [
        gap
        for gap in gap_report.get("gaps", [])
        if isinstance(gap, dict) and gap.get("status") != "inherent_local_limit"
    ]
    route_profiles = (
        route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}
    )
    route_statuses = {key: profile.get("status") for key, profile in sorted(route_profiles.items())}
    route_profiles_ready = bool(route_statuses) and all(status == "ready" for status in route_statuses.values())
    benchmark_summary = route_recommendations.get("benchmark_summary") or {}
    scorecard_summary = quality_scorecard.get("summary") or {}
    optional_summary = optional_heavy_evidence.get("summary") or {}
    continuity_summary = continuity_report.get("summary") or {}
    live_summary = live_status.get("summary") or {}
    benchmark_freshness_status = benchmark_summary.get("freshness_status") or "unmeasured"
    benchmark_fresh = benchmark_freshness_status == "fresh" and not benchmark_summary.get("stale_suites")

    tracks = [
        {
            "id": "benchmark-freshness",
            "title": "Keep local model route benchmarks fresh",
            "priority": "high",
            "status": "ready"
            if route_profiles_ready and benchmark_summary.get("count", 0) >= 3 and benchmark_fresh
            else "needs_attention",
            "gap_addressed": ["local-functional-parity-maintenance"],
            "local_action": (
                "Refresh kept baseline samples after any model, quantization, runtime, or hardware change; route latency-sensitive "
                "work to `local-chatgpt-auto`, coding to Slopcode/Qwen, and private long-context work to GLM 5.2."
            ),
            "commands": [
                "curl -fsS http://127.0.0.1:18042/local-benchmarks/recommendations | jq '.profiles'",
                "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --json",
            ],
            "acceptance_checks": [
                "local_scheduler.local_model_benchmark_baseline_smoke",
                "service.local_model_benchmark_freshness_smoke",
                "openwebui.local_model_performance_envelope",
                "local_scheduler.local_parity_catalog_smoke",
            ],
            "current_evidence": {
                "route_statuses": route_statuses,
                "benchmark_records": benchmark_summary.get("count", 0),
                "benchmark_freshness_status": benchmark_freshness_status,
                "stale_benchmark_suites": benchmark_summary.get("stale_suites") or [],
                "max_age_seconds": benchmark_summary.get("max_age_seconds"),
                "best_local_tps": benchmark_summary.get("best_tps", 0),
            },
        },
        {
            "id": "quality-eval-refresh",
            "title": "Keep executable quality coverage complete",
            "priority": "high",
            "status": "ready"
            if quality_scorecard.get("local_quality_status") == "ready"
            and scorecard_summary.get("all_evals_executable") is True
            else "needs_attention",
            "gap_addressed": ["local-functional-parity-maintenance"],
            "local_action": (
                "Keep all high-priority ChatGPT-style quality cases executable so route regressions are caught before promoting "
                "new local models or presets."
            ),
            "commands": [
                "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --quality-smoke --json",
                "curl -fsS http://127.0.0.1:18042/local-parity/quality-scorecard | jq '.scorecard.summary'",
            ],
            "acceptance_checks": [
                "openwebui.quality_smoke",
                "local_scheduler.local_parity_catalog_smoke",
            ],
            "current_evidence": {
                "quality_evals": scorecard_summary.get("quality_evals", 0),
                "executable_quality_evals": scorecard_summary.get("executable_quality_evals", 0),
                "rubric_quality_evals": scorecard_summary.get("rubric_quality_evals", 0),
            },
        },
        {
            "id": "optional-heavy-refresh",
            "title": "Refresh heavy multimodal and slow-route evidence",
            "priority": "medium",
            "status": "ready" if optional_heavy_evidence.get("status") == "ready" else "needs_attention",
            "gap_addressed": ["local-functional-parity-maintenance"],
            "local_action": (
                "Re-run heavy evidence after changes to GLM, Slopcode, vision, STT, ComfyUI, or long-context settings; keep these "
                "out of the fast default suite but linked from the parity map."
            ),
            "commands": [
                "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --vision-smoke --stt-smoke --image-gen-smoke --json",
                "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --slow-glm --long-context-smoke --slopcode-smoke --json",
            ],
            "acceptance_checks": [
                "openwebui.local_stt_smoke",
                "openwebui.image_generation_smoke",
                "openwebui.local_vision_smoke",
                "openwebui.glm_proxy_slow_smoke",
                "openwebui.slopcode_profile_smoke",
            ],
            "current_evidence": {
                "optional_cases": optional_summary.get("optional_cases", 0),
                "ready_optional_cases": optional_summary.get("ready_optional_cases", 0),
                "flags": optional_heavy_evidence.get("flags") or [],
            },
        },
        {
            "id": "continuity-fallback",
            "title": "Use local portability instead of hosted sync",
            "priority": "medium",
            "status": "ready"
            if continuity_report.get("continuity_status") == "ready"
            and continuity_summary.get("local_export_import_fallback") is True
            else "needs_attention",
            "gap_addressed": ["local-functional-parity-maintenance"],
            "local_action": (
                "Use exported parity bundles, local workspace packages, shared local artifacts, and OpenWebUI prompt/library records "
                "as the local replacement for hosted cross-device continuity."
            ),
            "commands": [
                "./scripts/export-local-chatgpt-parity-bundle.py --format markdown --output /tmp/local-chatgpt-parity-bundle.md",
                "curl -fsS http://127.0.0.1:18042/local-parity/continuity | jq '.continuity.summary'",
            ],
            "acceptance_checks": [
                "service.local_chatgpt_parity_bundle_cli_smoke",
                "local_scheduler.local_parity_catalog_smoke",
                "local_scheduler.local_code_workspace_smoke",
            ],
            "current_evidence": {
                "continuity_status": continuity_report.get("continuity_status"),
                "ready_capabilities": continuity_summary.get("ready_capabilities", 0),
                "hosted_sync_equivalence": continuity_summary.get("hosted_sync_equivalence"),
            },
        },
        {
            "id": "boundary-management",
            "title": "Keep hosted-cloud exclusions explicit",
            "priority": "high",
            "status": "ready"
            if not non_inherent_gaps
            and frontier_summary.get("excluded_from_local_goal_items") == frontier_summary.get("boundary_items")
            else "needs_attention",
            "gap_addressed": ["hosted-scope-exclusions"],
            "local_action": (
                "Keep local functional parity and hosted ChatGPT cloud equivalence separate: local OpenWebUI routes are "
                "the acceptance target, while hosted frontier quality, capacity, routing, sync, and rollout behavior are "
                "explicit scope exclusions."
            ),
            "commands": [
                "curl -fsS http://127.0.0.1:18042/local-parity/audit | jq '.audit.completion_status'",
                "curl -fsS http://127.0.0.1:18042/local-parity/gaps | jq '.gap_report.summary'",
                "curl -fsS http://127.0.0.1:18042/local-parity/gap | jq '.gap_report.scope_exclusions[].id'",
            ],
            "acceptance_checks": [
                "local_scheduler.local_parity_catalog_smoke",
                "service.local_scheduler_openapi",
            ],
            "current_evidence": {
                "remaining_gap_ids": gap_ids,
                "non_inherent_open_gaps": len(non_inherent_gaps),
                "frontier_boundary_items": frontier_summary.get("boundary_items", 0),
                "frontier_boundary_ready_local_mitigations": frontier_summary.get("ready_local_mitigations", 0),
                "frontier_boundary_excluded_from_local_goal_items": frontier_summary.get(
                    "excluded_from_local_goal_items", 0
                ),
                "frontier_boundary_not_locally_provable_items": frontier_summary.get("not_locally_provable_items", 0),
                "live_status": live_status.get("live_status"),
            },
        },
    ]
    ready_tracks = [track for track in tracks if track.get("status") == "ready"]
    return {
        "source": "chatgpt-local-parity-improvement-plan",
        "generated_at": now(),
        "status": "ready" if len(ready_tracks) == len(tracks) else "needs_attention",
        "summary": {
            "tracks": len(tracks),
            "ready_tracks": len(ready_tracks),
            "remaining_gap_id": None,
            "remaining_gap_present": False,
            "non_inherent_open_gaps": len(non_inherent_gaps),
            "completion_status": LOCAL_PARITY_COMPLETION_STATUS if not non_inherent_gaps else "needs_attention",
            "route_profiles_ready": route_profiles_ready,
            "benchmark_records": benchmark_summary.get("count", 0),
            "benchmark_freshness_status": benchmark_freshness_status,
            "stale_benchmark_suites": benchmark_summary.get("stale_suites") or [],
            "benchmark_max_age_seconds": benchmark_summary.get("max_age_seconds"),
            "best_local_tps": benchmark_summary.get("best_tps", 0),
            "quality_evals": scorecard_summary.get("quality_evals", 0),
            "optional_cases": optional_summary.get("optional_cases", 0),
            "ready_optional_cases": optional_summary.get("ready_optional_cases", 0),
            "continuity_status": continuity_report.get("continuity_status"),
            "live_status": live_status.get("live_status"),
            "ready_live_probes": live_summary.get("ready_probes", 0),
            "frontier_boundary_items": frontier_summary.get("boundary_items", 0),
            "frontier_boundary_ready_local_mitigations": frontier_summary.get("ready_local_mitigations", 0),
            "frontier_boundary_excluded_from_local_goal_items": frontier_summary.get(
                "excluded_from_local_goal_items", 0
            ),
            "frontier_boundary_not_locally_provable_items": frontier_summary.get("not_locally_provable_items", 0),
            "frontier_boundary_needs_attention_local_mitigations": frontier_summary.get(
                "needs_attention_local_mitigations", 0
            ),
        },
        "tracks": tracks,
        "frontier_boundary": frontier_boundary,
        "scope_exclusions": gap_report.get("scope_exclusions") or [],
        "claim_boundary": (
            "This plan improves local functional parity and verification depth. Hosted ChatGPT frontier-model quality, "
            "hosted account sync, product latency/capacity, private routing, and cloud continuity are excluded from "
            "the simplified local goal."
        ),
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_gap_report_html() -> str:
    gap_report = local_parity_gap_report()
    summary = gap_report.get("summary") or {}
    gaps = gap_report.get("gaps") or []
    frontier_boundary = gap_report.get("frontier_boundary") if isinstance(gap_report.get("frontier_boundary"), dict) else {}
    frontier_summary = frontier_boundary.get("summary") if isinstance(frontier_boundary.get("summary"), dict) else {}
    frontier_items = frontier_boundary.get("items") if isinstance(frontier_boundary.get("items"), list) else []
    next_actions = gap_report.get("next_actions") or []
    primary_context_tokens = None
    for gap in gaps:
        evidence = gap.get("evidence") if isinstance(gap, dict) else {}
        if isinstance(evidence, dict) and isinstance(evidence.get("context_tokens"), int):
            primary_context_tokens = evidence.get("context_tokens")
            break
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(gap_report.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    def compact_evidence(value) -> str:
        if not isinstance(value, dict):
            return str(value or "")
        parts = []
        for key, val in value.items():
            if isinstance(val, dict):
                if key == "benchmark_summary":
                    parts.append(f"{key}: best_tps={val.get('best_tps')}; records={val.get('count')}; freshness={val.get('freshness_status')}")
                elif key == "continuity_fallback":
                    parts.append(f"{key}: ready={val.get('ready_capabilities')}/{val.get('capabilities')}; hosted_sync={val.get('hosted_sync_equivalence')}")
                elif key == "frontier_boundary":
                    parts.append(
                        f"{key}: items={val.get('boundary_items')}; ready_mitigations={val.get('ready_local_mitigations')}; excluded={val.get('excluded_from_local_goal_items')}"
                    )
                else:
                    parts.append(f"{key}: {len(val)} fields")
            else:
                parts.append(f"{key}: {val}")
        return "; ".join(parts)

    gap_rows = []
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        gap_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(gap.get('id'))}</code></td>",
                    f"<td>{text(gap.get('severity'))}</td>",
                    f'<td><span class="status status-{status_class(gap.get("status"))}">{text(gap.get("status"))}</span></td>',
                    f"<td>{text(gap.get('summary'))}</td>",
                    f"<td>{text(compact_evidence(gap.get('evidence')))}</td>",
                    f"<td>{text(gap.get('next_action'))}</td>",
                    "</tr>",
                ]
            )
        )
    frontier_rows = []
    for item in frontier_items:
        if not isinstance(item, dict):
            continue
        evidence = item.get("local_evidence") if isinstance(item.get("local_evidence"), dict) else {}
        evidence_summary = "; ".join(
            f"{key}={value}" for key, value in evidence.items() if not isinstance(value, (dict, list))
        )
        frontier_rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><code>{text(item.get('id'))}</code><br><small>{text(item.get('capability'))}</small></td>",
                    f'<td><span class="status status-{status_class(item.get("local_mitigation_status"))}">{text(item.get("local_mitigation_status"))}</span></td>',
                    f'<td><span class="status status-{status_class(item.get("status"))}">{text(item.get("status"))}</span></td>',
                    f"<td>{text(item.get('local_substitute'))}</td>",
                    f"<td><small>{text(evidence_summary)}</small></td>",
                    f"<td>{text(item.get('excluded_from_local_goal_reason') or item.get('not_locally_provable_reason'))}</td>",
                    "</tr>",
                ]
            )
        )
    action_items = [f"<li>{text(action)}</li>" for action in next_actions]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Gap Report</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17201c; background: #f7f8f6; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1260px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; line-height: 1.25; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small, .generated {{ color: #59655f; }}
    .generated {{ font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1120px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-inherent_local_limit, .status-not_complete_for_full_hosted_chatgpt_parity, .status-not_locally_provable, .status-excluded_from_local_goal {{ background: #fff0cc; color: #6f4b00; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-open, .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    .actions {{ margin: 8px 0 0; padding-left: 18px; }}
    .actions li {{ margin-bottom: 7px; line-height: 1.45; }}
    @media (max-width: 680px) {{ main {{ padding: 20px 12px 32px; }} header {{ display: block; }} .generated {{ white-space: normal; margin-top: 8px; }} h1 {{ font-size: 23px; }} .metric strong {{ font-size: 19px; }} }}
  </style>
</head>
<body>
  <main data-local-parity-gap-report="html" data-open-gaps="{text(summary.get('open_gaps'))}" data-continuity-status="{text(summary.get('continuity_status'))}" data-use-cases="{text(summary.get('use_cases'))}" data-frontier-boundary-items="{text(frontier_summary.get('boundary_items'))}" data-frontier-boundary-ready="{text(frontier_summary.get('ready_local_mitigations'))}" data-frontier-boundary-excluded="{text(frontier_summary.get('excluded_from_local_goal_items'))}" data-frontier-boundary-not-provable="{text(frontier_summary.get('not_locally_provable_items'))}">
    <header>
      <div>
        <h1>Local ChatGPT Gap Report</h1>
        <p>{text(gap_report.get('claim'))}</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/improvement-plan.html">Improvement Plan</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/gap">Gap JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Gap report summary">
      {metric("Open local gaps", summary.get('open_gaps'), "remaining blockers")}
      {metric("Use cases", summary.get('use_cases'), "mapped")}
      {metric("Feature families", summary.get('feature_families'), "mapped")}
      {metric("Quality evals", summary.get('quality_evals'), "executable catalog")}
      {metric("Continuity", summary.get('continuity_status'), "fallback status")}
      {metric("Sources", summary.get('source_entries'), "source snapshot")}
      {metric("Primary GLM route", "glm52-q8-local / glm52-q4-local", "local long-context model")}
      {metric("GLM context", "65,536", "tokens")}
      {metric("Scope exclusions", f"{frontier_summary.get('excluded_from_local_goal_items')}/{frontier_summary.get('boundary_items')}", "hosted capabilities")}
    </section>
    <section class="panel">
      <table data-gap-report="local-chatgpt">
        <thead><tr><th>Gap</th><th>Severity</th><th>Status</th><th>Summary</th><th>Evidence</th><th>Next action</th></tr></thead>
        <tbody>{''.join(gap_rows)}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Hosted Scope Exclusions</h2>
      <table data-frontier-boundary="local-chatgpt">
        <thead><tr><th>Capability</th><th>Local mitigation</th><th>Scope status</th><th>Local substitute</th><th>Evidence</th><th>Exclusion reason</th></tr></thead>
        <tbody>{''.join(frontier_rows)}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Next Actions</h2>
      <ul class="actions">{''.join(action_items)}</ul>
    </section>
  </main>
</body>
</html>"""


def local_parity_improvement_plan_html() -> str:
    improvement_plan = local_parity_improvement_plan()
    summary = improvement_plan.get("summary") or {}
    tracks = improvement_plan.get("tracks") or []
    generated_at = time.strftime(
        "%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(improvement_plan.get("generated_at") or now()))
    )

    def text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    rows = []
    for track in tracks:
        if not isinstance(track, dict):
            continue
        commands = " | ".join(track.get("commands") or [])
        checks = ", ".join(track.get("acceptance_checks") or [])
        evidence = track.get("current_evidence") if isinstance(track.get("current_evidence"), dict) else {}
        evidence_summary = "; ".join(f"{key}={value}" for key, value in evidence.items() if not isinstance(value, (dict, list)))
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(track.get('title'))}</strong><br><small><code>{text(track.get('id'))}</code></small></td>",
                    f"<td>{text(track.get('priority'))}</td>",
                    f'<td><span class="status status-{status_class(track.get("status"))}">{text(track.get("status"))}</span></td>',
                    f"<td>{text(track.get('local_action'))}</td>",
                    f"<td><code>{text(commands)}</code></td>",
                    f"<td><code>{text(checks)}</code><br><small>{text(evidence_summary)}</small></td>",
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Improvement Plan</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17201c; background: #f7f8f6; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small, .generated {{ color: #59655f; }}
    .generated {{ font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1180px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-ready {{ background: #e3f4ea; color: #175734; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{ main {{ padding: 20px 12px 32px; }} header {{ display: block; }} .generated {{ white-space: normal; margin-top: 8px; }} h1 {{ font-size: 23px; }} .metric strong {{ font-size: 19px; }} }}
  </style>
</head>
<body>
  <main data-local-parity-improvement-plan="html" data-status="{text(improvement_plan.get('status'))}" data-tracks="{text(summary.get('tracks'))}" data-ready="{text(summary.get('ready_tracks'))}" data-completion-status="{text(summary.get('completion_status'))}" data-frontier-boundary-items="{text(summary.get('frontier_boundary_items'))}" data-frontier-boundary-ready="{text(summary.get('frontier_boundary_ready_local_mitigations'))}" data-frontier-boundary-excluded="{text(summary.get('frontier_boundary_excluded_from_local_goal_items'))}" data-frontier-boundary-not-provable="{text(summary.get('frontier_boundary_not_locally_provable_items'))}">
    <header>
      <div>
        <h1>Local ChatGPT Improvement Plan</h1>
        <p>{text(improvement_plan.get('claim_boundary'))}</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/gap-report.html">Gap Report</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/improvement-plan">Improvement Plan JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Improvement plan summary">
      {metric("Tracks ready", f"{summary.get('ready_tracks')}/{summary.get('tracks')}", "action tracks")}
      {metric("Completion", summary.get('completion_status'), "local goal")}
      {metric("Non-inherent gaps", summary.get('non_inherent_open_gaps'), "local blockers")}
      {metric("Boundary matrix", f"{summary.get('frontier_boundary_ready_local_mitigations')}/{summary.get('frontier_boundary_items')}", "local mitigations")}
      {metric("Scope exclusions", summary.get('frontier_boundary_excluded_from_local_goal_items'), "hosted capabilities")}
      {metric("Benchmark freshness", summary.get('benchmark_freshness_status'), "route baselines")}
      {metric("Best local TPS", summary.get('best_local_tps'), "completion tokens/sec")}
      {metric("Quality evals", summary.get('quality_evals'), "executable")}
      {metric("Optional cases", f"{summary.get('ready_optional_cases')}/{summary.get('optional_cases')}", "heavy evidence")}
      {metric("Live probes", summary.get('ready_live_probes'), "ready")}
    </section>
    <section class="panel">
      <table data-improvement-plan="local-chatgpt">
        <thead><tr><th>Track</th><th>Priority</th><th>Status</th><th>Local action</th><th>Commands</th><th>Acceptance checks</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_readiness_checklist() -> dict:
    catalog = local_parity_catalog()
    feature_matrix = local_parity_feature_matrix()
    runbook = local_parity_runbook()
    popular_task_routes = local_parity_popular_task_routes()
    workflow_recipes = local_parity_workflow_recipes()
    starter_prompts = local_parity_starter_prompts()
    quality_scorecard = local_parity_quality_scorecard()
    source_freshness = local_parity_source_freshness()
    optional_heavy_evidence = local_parity_optional_heavy_evidence()
    live_status = local_parity_live_status()
    route_recommendations = local_model_route_recommendations()
    gap_report = local_parity_gap_report()
    improvement_plan = local_parity_improvement_plan()

    counts = catalog.get("counts") or {}
    matrix_summary = feature_matrix.get("summary") or {}
    runbook_summary = runbook.get("summary") or {}
    popular_summary = popular_task_routes.get("summary") or {}
    workflow_summary = workflow_recipes.get("summary") or {}
    starter_summary = starter_prompts.get("summary") or {}
    scorecard_summary = quality_scorecard.get("summary") or {}
    freshness_summary = source_freshness.get("summary") or {}
    optional_summary = optional_heavy_evidence.get("summary") or {}
    live_summary = live_status.get("summary") or {}
    benchmark_summary = route_recommendations.get("benchmark_summary") or {}
    improvement_summary = improvement_plan.get("summary") or {}
    current_release_expected_families = len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_FAMILIES)
    current_release_expected_evidence_terms = len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_EVIDENCE_TERMS)
    current_release_coverage_ready = (
        freshness_summary.get("current_release_source_id") == LOCAL_PARITY_CURRENT_RELEASE_SOURCE_ID
        and freshness_summary.get("current_release_coverage_ready") is True
        and freshness_summary.get("current_release_expected_families") == current_release_expected_families
        and freshness_summary.get("current_release_covered_families") == current_release_expected_families
        and freshness_summary.get("current_release_missing_families") == 0
        and freshness_summary.get("current_release_expected_evidence_terms")
        == current_release_expected_evidence_terms
        and freshness_summary.get("current_release_covered_evidence_terms")
        == current_release_expected_evidence_terms
        and freshness_summary.get("current_release_missing_evidence_terms") == 0
    )

    route_profiles = (
        route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}
    )
    route_profiles_ready = bool(route_profiles) and all(
        isinstance(profile, dict) and profile.get("status") == "ready" for profile in route_profiles.values()
    )
    gap_ids = [gap.get("id") for gap in gap_report.get("gaps", []) if isinstance(gap, dict)]
    non_inherent_open_gaps = int(improvement_summary.get("non_inherent_open_gaps") or 0)

    def requirement(
        requirement_id: str,
        title: str,
        objective_fragment: str,
        status: str,
        evidence: list[dict],
        metrics: dict | None = None,
        remaining_work: list[str] | None = None,
        proof_scope: str = "local_functional",
    ) -> dict:
        return {
            "id": requirement_id,
            "title": title,
            "objective_fragment": objective_fragment,
            "status": status,
            "proof_scope": proof_scope,
            "metrics": metrics or {},
            "evidence": evidence,
            "remaining_work": remaining_work or [],
        }

    requirements = [
        requirement(
            "popular-feature-map-current",
            "Popular ChatGPT feature map is current",
            "map the most popular ChatGPT features",
            "passed"
            if feature_matrix.get("matrix_status") == "ready"
            and source_freshness.get("freshness_status") == "current"
            and current_release_coverage_ready
            and matrix_summary.get("feature_families") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
            and freshness_summary.get("covered_feature_families") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
            else "needs_attention",
            [
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/feature-matrix"},
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/source-freshness"},
                {"kind": "html_endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/source-freshness.html"},
                {"kind": "local_doc", "path": str(LOCAL_PARITY_DOCS_DIR / "chatgpt-feature-source-snapshot.json")},
            ],
            {
                "feature_families": matrix_summary.get("feature_families", 0),
                "source_entries": freshness_summary.get("source_entries", 0),
                "official_sources": freshness_summary.get("official_sources", 0),
                "max_source_age_days": freshness_summary.get("max_source_age_days"),
                "current_release_source_id": freshness_summary.get("current_release_source_id"),
                "current_release_coverage_ready": current_release_coverage_ready,
                "current_release_covered_families": freshness_summary.get("current_release_covered_families", 0),
                "current_release_expected_families": current_release_expected_families,
                "current_release_covered_evidence_terms": freshness_summary.get(
                    "current_release_covered_evidence_terms", 0
                ),
                "current_release_expected_evidence_terms": current_release_expected_evidence_terms,
            },
        ),
        requirement(
            "sample-use-cases-mapped",
            "Sample use cases are mapped for every feature family",
            "and sample use cases",
            "passed"
            if counts.get("use_cases") == counts.get("feature_families") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
            and (catalog.get("status_counts") or {}).get("implemented") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
            else "needs_attention",
            [
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/catalog"},
                {"kind": "local_doc", "path": str(LOCAL_PARITY_DOCS_DIR / "chatgpt-local-usecase-catalog.json")},
            ],
            {
                "use_cases": counts.get("use_cases", 0),
                "implemented_use_cases": (catalog.get("status_counts") or {}).get("implemented", 0),
                "required_verifiers": counts.get("required_verifiers", 0),
            },
        ),
        requirement(
            "openwebui-routes-ready",
            "OpenWebUI routes cover popular tasks",
            "test and iterate on OpenWebUI",
            "passed"
            if runbook.get("runbook_status") == "ready"
            and popular_task_routes.get("status") == "ready"
            and popular_summary.get("ready_tasks") == popular_summary.get("popular_tasks")
            and popular_summary.get("route_coverage_count", 0) >= 10
            else "needs_attention",
            [
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/runbook"},
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/popular-tasks"},
                {"kind": "html_endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/route-map.html"},
            ],
            {
                "runbook_entries": runbook_summary.get("entries", runbook_summary.get("feature_families", 0)),
                "popular_tasks": popular_summary.get("popular_tasks", 0),
                "ready_popular_tasks": popular_summary.get("ready_tasks", 0),
                "route_coverage_count": popular_summary.get("route_coverage_count", 0),
            },
        ),
        requirement(
            "workflow-and-starter-pack-ready",
            "Workflow recipes and starter prompts are import-ready",
            "sample use cases and OpenWebUI parity workflows",
            "passed"
            if workflow_recipes.get("status") == "ready"
            and starter_prompts.get("status") == "ready"
            and workflow_summary.get("ready_workflow_recipes") == workflow_summary.get("workflow_recipes")
            and starter_summary.get("ready_starter_prompts") == starter_summary.get("starter_prompts")
            and starter_summary.get("openwebui_import_items") == starter_summary.get("starter_prompts")
            else "needs_attention",
            [
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/workflows"},
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/starter-prompts"},
                {"kind": "html_endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/starter-prompts.html"},
            ],
            {
                "workflow_recipes": workflow_summary.get("workflow_recipes", 0),
                "starter_prompts": starter_summary.get("starter_prompts", 0),
                "openwebui_import_items": starter_summary.get("openwebui_import_items", 0),
            },
        ),
        requirement(
            "glm52-local-primary-ready",
            "GLM 5.2 local primary lane is available",
            "using GLM 5.2 and local models",
            "passed"
            if live_status.get("live_status") == "ready"
            and scorecard_summary.get("route_profiles_ready") is True
            and scorecard_summary.get("route_profiles_fresh") is True
            and route_profiles_ready
            else "needs_attention",
            [
                {"kind": "endpoint", "url": "http://127.0.0.1:11441/v1/models"},
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/live-status"},
                {"kind": "verifier", "name": "service.glm_context_window"},
                {"kind": "verifier", "name": "openwebui.local_model_performance_envelope"},
            ],
            {
                "primary_model": "glm52-q4-local",
                "glm_context_tokens": 65536,
                "glm_context_display": "65,536",
                "slopcode_context_tokens": 65536,
                "route_profiles": scorecard_summary.get("route_profiles", 0),
                "best_local_tps": scorecard_summary.get("best_local_tps", 0),
                "benchmark_records": benchmark_summary.get("count", 0),
            },
        ),
        requirement(
            "local-models-additive",
            "Local model additions are additive",
            "makensure the models are adding, not replacing the models available",
            "passed"
            if runbook.get("runbook_status") == "ready"
            and starter_prompts.get("status") == "ready"
            and "glm52-q4-local" in json.dumps(runbook.get("entries") or [])
            and "local-chatgpt-auto" in json.dumps(starter_prompts.get("prompts") or [])
            else "needs_attention",
            [
                {"kind": "verifier", "name": "openwebui.models.additive"},
                {"kind": "verifier", "name": "openwebui.model_inventory_additive_smoke"},
                {"kind": "verifier", "name": "openwebui.glm_reasoning_profiles"},
                {"kind": "verifier", "name": "openwebui.local_auto_router_profile"},
                {"kind": "verifier", "name": "openwebui.starter_prompt_live_pack_smoke"},
            ],
            {
                "primary_local_models": 8,
                "starter_prompts": starter_summary.get("starter_prompts", 0),
                "route_coverage_count": starter_summary.get("route_coverage_count", 0),
            },
        ),
        requirement(
            "quality-evidence-ready",
            "Executable local quality coverage is ready",
            "test and iterate until parity evidence is explicit",
            "passed"
            if quality_scorecard.get("local_quality_status") == "ready"
            and scorecard_summary.get("all_evals_executable") is True
            and scorecard_summary.get("rubric_quality_evals") == 0
            else "needs_attention",
            [
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/quality-scorecard"},
                {"kind": "local_doc", "path": str(LOCAL_PARITY_DOCS_DIR / "chatgpt-local-quality-evals.json")},
                {"kind": "command", "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --quality-smoke --json"},
            ],
            {
                "quality_evals": scorecard_summary.get("quality_evals", 0),
                "executable_quality_evals": scorecard_summary.get("executable_quality_evals", 0),
                "quality_eval_feature_families": scorecard_summary.get("quality_eval_feature_families", 0),
            },
        ),
        requirement(
            "multimodal-and-tools-evidence-ready",
            "Local multimodal and tool routes have linked evidence",
            "local models plus local tools for ChatGPT-style features",
            "passed"
            if optional_heavy_evidence.get("status") == "ready"
            and optional_summary.get("ready_optional_cases") == optional_summary.get("optional_cases")
            and optional_summary.get("optional_cases", 0) >= 10
            else "needs_attention",
            [
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/optional-evidence"},
                {"kind": "html_endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/optional-evidence.html"},
                {"kind": "command", "command": "OPENWEBUI_EMAIL='admin@local.test' OPENWEBUI_PASSWORD='openwebui-local-admin' ./scripts/parity-check.py --vision-smoke --stt-smoke --image-gen-smoke --json"},
            ],
            {
                "optional_cases": optional_summary.get("optional_cases", 0),
                "ready_optional_cases": optional_summary.get("ready_optional_cases", 0),
                "default_suite_skips_intentional": optional_summary.get("default_suite_skips_intentional"),
            },
        ),
        requirement(
            "zero-config-runtime-ready",
            "Local zero-config runtime services are live",
            "test it all works e2e with zero config",
            "passed"
            if live_status.get("live_status") == "ready"
            and live_summary.get("ready_probes") == live_summary.get("required_probes") == 12
            else "needs_attention",
            [
                {"kind": "endpoint", "url": f"{PUBLIC_BASE_URL}/local-parity/live-status"},
                {"kind": "command", "command": "./scripts/status-parity.sh"},
            ],
            {
                "live_probes": live_summary.get("probes", 0),
                "ready_live_probes": live_summary.get("ready_probes", 0),
                "required_live_probes": live_summary.get("required_probes", 0),
            },
        ),
    ]

    passed = len([item for item in requirements if item.get("status") == "passed"])
    needs_attention = len([item for item in requirements if item.get("status") == "needs_attention"])
    not_locally_provable = len([item for item in requirements if item.get("status") == "not_locally_provable"])
    local_functional_status = "ready" if needs_attention == 0 and passed == len(requirements) else "needs_attention"
    scope_exclusions = (gap_report.get("scope_exclusions") or []) if isinstance(gap_report, dict) else []

    return {
        "source": "chatgpt-local-readiness-checklist",
        "generated_at": now(),
        "objective": (
            "Map popular ChatGPT features and sample use cases, test and iterate OpenWebUI, and use GLM 5.2 plus "
            "local models without replacing existing model availability."
        ),
        "local_functional_status": local_functional_status,
        "full_hosted_chatgpt_parity_status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
        "completion_status": LOCAL_PARITY_COMPLETION_STATUS
        if local_functional_status == "ready" and non_inherent_open_gaps == 0
        else "needs_attention",
        "claim_boundary": (
            "This checklist proves local functional readiness against the mapped objective. Hosted frontier quality, hosted "
            "capacity, private hosted routing, and hosted account/cloud continuity are excluded from this local goal."
        ),
        "summary": {
            "requirements": len(requirements),
            "passed_requirements": passed,
            "needs_attention_requirements": needs_attention,
            "not_locally_provable_requirements": not_locally_provable,
            "scope_exclusion_items": len(scope_exclusions),
            "scope_exclusion_ids": [item.get("id") for item in scope_exclusions if isinstance(item, dict)],
            "feature_families": counts.get("feature_families", 0),
            "use_cases": counts.get("use_cases", 0),
            "popular_tasks": popular_summary.get("popular_tasks", 0),
            "workflow_recipes": workflow_summary.get("workflow_recipes", 0),
            "starter_prompts": starter_summary.get("starter_prompts", 0),
            "route_coverage_count": popular_summary.get("route_coverage_count", 0),
            "quality_evals": scorecard_summary.get("quality_evals", 0),
            "optional_cases": optional_summary.get("optional_cases", 0),
            "source_entries": freshness_summary.get("source_entries", 0),
            "official_sources": freshness_summary.get("official_sources", 0),
            "current_release_source_id": freshness_summary.get("current_release_source_id"),
            "current_release_coverage_ready": current_release_coverage_ready,
            "current_release_covered_families": freshness_summary.get("current_release_covered_families", 0),
            "current_release_expected_families": current_release_expected_families,
            "current_release_covered_evidence_terms": freshness_summary.get(
                "current_release_covered_evidence_terms", 0
            ),
            "current_release_expected_evidence_terms": current_release_expected_evidence_terms,
            "glm_context_tokens": 65536,
            "slopcode_context_tokens": 65536,
            "route_profiles": scorecard_summary.get("route_profiles", 0),
            "best_local_tps": scorecard_summary.get("best_local_tps", 0),
            "live_status": live_status.get("live_status"),
            "remaining_gap_ids": gap_ids,
            "non_inherent_open_gaps": non_inherent_open_gaps,
        },
        "requirements": requirements,
        "scope_exclusions": scope_exclusions,
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def local_parity_readiness_checklist_html() -> str:
    checklist = local_parity_readiness_checklist()
    summary = checklist.get("summary") or {}
    requirements = checklist.get("requirements") or []
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(checklist.get("generated_at") or now())))

    def text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value).lower()
        return html_escape(str(value))

    def status_class(status: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", str(status or "unknown").lower()).strip("-")
        return normalized or "unknown"

    def metric(label: str, value, detail: str = "") -> str:
        return "\n".join(
            [
                '<section class="metric">',
                f"<span>{text(label)}</span>",
                f"<strong>{text(value)}</strong>",
                f"<small>{text(detail)}</small>" if detail else "",
                "</section>",
            ]
        )

    def evidence_label(item: dict) -> str:
        if item.get("url"):
            return str(item.get("url"))
        if item.get("path"):
            return str(item.get("path"))
        if item.get("name"):
            return str(item.get("name"))
        if item.get("command"):
            return str(item.get("command"))
        return str(item.get("kind") or "")

    rows = []
    for item in requirements:
        if not isinstance(item, dict):
            continue
        evidence = "; ".join(evidence_label(entry) for entry in item.get("evidence") or [] if isinstance(entry, dict))
        metrics = "; ".join(
            f"{key}={value}" for key, value in (item.get("metrics") or {}).items() if not isinstance(value, (dict, list))
        )
        remaining = " ".join(item.get("remaining_work") or [])
        rows.append(
            "\n".join(
                [
                    "<tr>",
                    f"<td><strong>{text(item.get('title'))}</strong><br><small><code>{text(item.get('id'))}</code></small></td>",
                    f"<td>{text(item.get('objective_fragment'))}</td>",
                    f'<td><span class="status status-{status_class(item.get("status"))}">{text(item.get("status"))}</span></td>',
                    f"<td><code>{text(evidence)}</code><br><small>{text(metrics)}</small></td>",
                    f"<td>{text(remaining)}</td>",
                    "</tr>",
                ]
            )
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local ChatGPT Readiness Checklist</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17201c; background: #f7f8f6; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8f6; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 28px 20px 42px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; font-weight: 700; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    a {{ color: #0f5d66; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; white-space: normal; overflow-wrap: anywhere; }}
    small, .generated {{ color: #59655f; }}
    .generated {{ font-size: 13px; white-space: nowrap; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric {{ min-height: 86px; border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 12px; }}
    .metric span {{ display: block; color: #59655f; font-size: 12px; line-height: 1.3; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric small {{ display: block; margin-top: 6px; color: #59655f; line-height: 1.35; }}
    .panel {{ border: 1px solid #d7ddd8; border-radius: 8px; background: #ffffff; padding: 16px; margin-top: 14px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 1120px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e9e6; text-align: left; vertical-align: top; line-height: 1.42; }}
    th {{ color: #3d4943; font-size: 12px; font-weight: 700; text-transform: uppercase; background: #f2f5f2; }}
    tr:last-child td {{ border-bottom: 0; }}
    .status {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 700; background: #eef1ef; color: #344039; white-space: nowrap; }}
    .status-passed {{ background: #e3f4ea; color: #175734; }}
    .status-not-locally-provable, .status-excluded-from-local-goal {{ background: #fff0cc; color: #6f4b00; }}
    .status-needs_attention {{ background: #fde8e4; color: #7f231c; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .links a {{ display: inline-flex; align-items: center; min-height: 34px; border: 1px solid #c8d2cc; border-radius: 8px; padding: 6px 10px; background: #ffffff; }}
    @media (max-width: 680px) {{ main {{ padding: 20px 12px 32px; }} header {{ display: block; }} .generated {{ white-space: normal; margin-top: 8px; }} h1 {{ font-size: 23px; }} .metric strong {{ font-size: 19px; }} }}
  </style>
</head>
<body>
  <main data-local-parity-readiness-checklist="html" data-status="{text(checklist.get('local_functional_status'))}" data-requirements="{text(summary.get('requirements'))}" data-passed="{text(summary.get('passed_requirements'))}" data-not-locally-provable="{text(summary.get('not_locally_provable_requirements'))}" data-completion-status="{text(checklist.get('completion_status'))}" data-current-release-source="{text(summary.get('current_release_source_id'))}" data-current-release-families="{text(summary.get('current_release_covered_families'))}/{text(summary.get('current_release_expected_families'))}" data-current-release-terms="{text(summary.get('current_release_covered_evidence_terms'))}/{text(summary.get('current_release_expected_evidence_terms'))}">
    <header>
      <div>
        <h1>Local ChatGPT Readiness Checklist</h1>
        <p>{text(checklist.get('claim_boundary'))}</p>
        <nav class="links" aria-label="Related local parity views">
          <a href="/local-parity/index.html">Dashboard</a>
          <a href="/local-parity/gap-report.html">Gap Report</a>
          <a href="/local-parity/improvement-plan.html">Improvement Plan</a>
          <a href="/local-parity/audit.html">Completion Audit</a>
          <a href="/local-parity/readiness-checklist">Checklist JSON</a>
        </nav>
      </div>
      <p class="generated">Generated {text(generated_at)}</p>
    </header>
    <section class="summary" aria-label="Readiness summary">
      {metric("Local status", checklist.get('local_functional_status'), "functional")}
      {metric("Requirements passed", f"{summary.get('passed_requirements')}/{summary.get('requirements')}", "objective checklist")}
      {metric("Scope exclusions", summary.get('scope_exclusion_items'), "hosted capabilities")}
      {metric("Feature families", summary.get('feature_families'), "mapped")}
      {metric("Popular tasks", summary.get('popular_tasks'), "routed")}
      {metric("Starter prompts", summary.get('starter_prompts'), "OpenWebUI")}
      {metric("Current release", f"{summary.get('current_release_covered_families')}/{summary.get('current_release_expected_families')}", "families")}
      {metric("Release evidence", f"{summary.get('current_release_covered_evidence_terms')}/{summary.get('current_release_expected_evidence_terms')}", "terms")}
      {metric("GLM context", f"{int(summary.get('glm_context_tokens') or 0):,}", "tokens")}
      {metric("Best local TPS", summary.get('best_local_tps'), "completion tokens/sec")}
    </section>
    <section class="panel">
      <table data-readiness-checklist="local-chatgpt">
        <thead><tr><th>Requirement</th><th>Objective fragment</th><th>Status</th><th>Evidence and metrics</th><th>Remaining work</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def local_parity_completion_audit() -> dict:
    catalog = local_parity_catalog()
    gap_report = local_parity_gap_report()
    route_recommendations = local_model_route_recommendations()
    quality_scorecard = local_parity_quality_scorecard()
    continuity_report = local_parity_continuity_report()
    source_freshness = local_parity_source_freshness()
    feature_matrix = local_parity_feature_matrix()
    runbook = local_parity_runbook()
    task_recommendations = local_parity_task_recommendations("code", 12)
    research_task_recommendations = local_parity_task_recommendations("research", 8)
    popular_task_routes = local_parity_popular_task_routes()
    workflow_recipes = local_parity_workflow_recipes()
    starter_prompts = local_parity_starter_prompts()
    evidence_trace = local_parity_evidence_trace()
    live_status = local_parity_live_status()
    improvement_plan = local_parity_improvement_plan()
    counts = catalog.get("counts") or {}
    status_counts = catalog.get("status_counts") or {}
    profiles = route_recommendations.get("profiles") if isinstance(route_recommendations.get("profiles"), dict) else {}
    route_statuses = {key: profile.get("status") for key, profile in sorted(profiles.items())}
    open_gap_ids = [gap.get("id") for gap in gap_report.get("gaps", []) if isinstance(gap, dict)]
    frontier_boundary = gap_report.get("frontier_boundary") if isinstance(gap_report.get("frontier_boundary"), dict) else {}
    frontier_summary = frontier_boundary.get("summary") if isinstance(frontier_boundary.get("summary"), dict) else {}
    task_recommendation_entries = (
        task_recommendations.get("recommendations") if isinstance(task_recommendations.get("recommendations"), list) else []
    )
    research_task_entries = (
        research_task_recommendations.get("recommendations")
        if isinstance(research_task_recommendations.get("recommendations"), list)
        else []
    )
    popular_tasks = popular_task_routes.get("tasks") if isinstance(popular_task_routes.get("tasks"), list) else []
    popular_task_ids = [item.get("id") for item in popular_tasks if isinstance(item, dict)]
    popular_route_coverage = (popular_task_routes.get("summary") or {}).get("route_coverage") or []
    workflow_entries = workflow_recipes.get("recipes") if isinstance(workflow_recipes.get("recipes"), list) else []
    workflow_ids = [item.get("id") for item in workflow_entries if isinstance(item, dict)]
    workflow_route_coverage = workflow_recipes.get("route_coverage") if isinstance(workflow_recipes.get("route_coverage"), list) else []
    starter_entries = starter_prompts.get("prompts") if isinstance(starter_prompts.get("prompts"), list) else []
    starter_ids = [item.get("id") for item in starter_entries if isinstance(item, dict)]
    starter_route_coverage = starter_prompts.get("route_coverage") if isinstance(starter_prompts.get("route_coverage"), list) else []
    non_inherent_gaps = [
        gap
        for gap in gap_report.get("gaps", [])
        if isinstance(gap, dict) and gap.get("status") != "inherent_local_limit"
    ]
    source_freshness_summary = source_freshness.get("summary") or {}
    current_release_expected_families = len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_FAMILIES)
    current_release_expected_evidence_terms = len(LOCAL_PARITY_EXPECTED_CURRENT_RELEASE_EVIDENCE_TERMS)
    current_release_coverage_ready = (
        source_freshness_summary.get("current_release_source_id") == LOCAL_PARITY_CURRENT_RELEASE_SOURCE_ID
        and source_freshness_summary.get("current_release_coverage_ready") is True
        and source_freshness_summary.get("current_release_expected_families") == current_release_expected_families
        and source_freshness_summary.get("current_release_covered_families") == current_release_expected_families
        and source_freshness_summary.get("current_release_missing_families") == 0
        and source_freshness_summary.get("current_release_expected_evidence_terms")
        == current_release_expected_evidence_terms
        and source_freshness_summary.get("current_release_covered_evidence_terms")
        == current_release_expected_evidence_terms
        and source_freshness_summary.get("current_release_missing_evidence_terms") == 0
    )

    requirements = [
        {
            "id": "feature-map-current",
            "status": "passed"
            if counts.get("feature_families") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
            and counts.get("source_entries") == LOCAL_PARITY_EXPECTED_SOURCE_ENTRIES
            and counts.get("official_sources") == LOCAL_PARITY_EXPECTED_OFFICIAL_SOURCES
            and source_freshness.get("freshness_status") == "current"
            and current_release_coverage_ready
            else "failed",
            "evidence": {
                "feature_families": counts.get("feature_families", 0),
                "source_entries": counts.get("source_entries", 0),
                "official_sources": counts.get("official_sources", 0),
                "source_freshness": source_freshness_summary,
                "current_release": source_freshness.get("current_release") or {},
            },
        },
        {
            "id": "feature-source-freshness-current",
            "status": "passed"
            if source_freshness.get("freshness_status") == "current"
            and current_release_coverage_ready
            else "failed",
            "evidence": {
                "freshness_status": source_freshness.get("freshness_status"),
                "max_age_days_allowed": source_freshness.get("max_age_days_allowed"),
                "summary": source_freshness_summary,
                "current_release": source_freshness.get("current_release") or {},
            },
        },
        {
            "id": "feature-family-matrix-ready",
            "status": "passed" if feature_matrix.get("matrix_status") == "ready" else "failed",
            "evidence": {
                "matrix_status": feature_matrix.get("matrix_status"),
                "summary": feature_matrix.get("summary") or {},
            },
        },
        {
            "id": "runbook-ready",
            "status": "passed" if runbook.get("runbook_status") == "ready" else "failed",
            "evidence": {
                "runbook_status": runbook.get("runbook_status"),
                "summary": runbook.get("summary") or {},
            },
        },
        {
            "id": "task-route-recommendations-ready",
            "status": "passed"
            if task_recommendations.get("status") == "ready"
            and research_task_recommendations.get("status") == "ready"
            and any(item.get("openwebui_route_id") == "slopcode_tiny" for item in task_recommendation_entries if isinstance(item, dict))
            and any(item.get("openwebui_route_id") == "deep_research" for item in research_task_entries if isinstance(item, dict))
            else "failed",
            "evidence": {
                "code_task_summary": task_recommendations.get("summary") or {},
                "research_task_summary": research_task_recommendations.get("summary") or {},
                "code_route_ids": [
                    item.get("openwebui_route_id") for item in task_recommendation_entries if isinstance(item, dict)
                ],
                "research_route_ids": [
                    item.get("openwebui_route_id") for item in research_task_entries if isinstance(item, dict)
                ],
            },
        },
        {
            "id": "popular-task-routes-ready",
            "status": "passed"
            if popular_task_routes.get("status") == "ready"
            and len(popular_tasks) == LOCAL_PARITY_EXPECTED_POPULAR_TASKS
            and len([item for item in popular_tasks if isinstance(item, dict) and item.get("status") == "ready"]) == len(popular_tasks)
            and {
                "everyday-chat",
                "coding-help",
                "deep-research",
                "file-document-qa",
                "data-analysis",
                "image-generation",
                "image-understanding",
                "voice-dictation",
                "memory-personalization",
                "study-learning",
                "shopping-research",
                "job-search-resume",
                "personal-finance-analysis",
                "agent-actions",
                "atlas-browser-chat",
                "developer-mode-mcp-app",
                "private-long-context-reasoning",
            }.issubset(set(popular_task_ids))
            and {
                "fast_router",
                "glm_tiny",
                "slopcode_tiny",
                "deep_research",
                "local_agent",
                "comfyui_flux",
                "local_vision",
                "local_whisper_stt",
                "glm52_study_coach_preset",
                "glm52_shopping_research_preset",
            }.issubset(set(popular_route_coverage))
            else "failed",
            "evidence": {
                "summary": popular_task_routes.get("summary") or {},
                "task_ids": popular_task_ids,
                "route_coverage": popular_route_coverage,
            },
        },
        {
            "id": "workflow-recipes-ready",
            "status": "passed"
            if workflow_recipes.get("status") == "ready"
            and len(workflow_entries) == LOCAL_PARITY_EXPECTED_POPULAR_TASKS
            and len([item for item in workflow_entries if isinstance(item, dict) and item.get("status") == "ready"]) == len(workflow_entries)
            and {
                "everyday-chat-workflow",
                "private-long-context-workflow",
                "coding-help-workflow",
                "deep-research-workflow",
                "file-document-qa-workflow",
                "data-analysis-workflow",
                "image-generation-workflow",
                "image-understanding-workflow",
                "voice-dictation-workflow",
                "memory-personalization-workflow",
                "study-learning-workflow",
                "shopping-research-workflow",
                "job-search-resume-workflow",
                "personal-finance-workflow",
                "agent-actions-workflow",
                "atlas-browser-chat-workflow",
                "developer-mode-mcp-app-workflow",
            }.issubset(set(workflow_ids))
            and {
                "fast_router",
                "glm_tiny",
                "slopcode_tiny",
                "deep_research",
                "local_agent",
                "comfyui_flux",
                "local_vision",
                "local_whisper_stt",
                "glm52_study_coach_preset",
                "glm52_shopping_research_preset",
            }.issubset(set(workflow_route_coverage))
            else "failed",
            "evidence": {
                "summary": workflow_recipes.get("summary") or {},
                "workflow_ids": workflow_ids,
                "route_coverage": workflow_route_coverage,
            },
        },
        {
            "id": "starter-prompts-ready",
            "status": "passed"
            if starter_prompts.get("status") == "ready"
            and len(starter_entries) == LOCAL_PARITY_EXPECTED_POPULAR_TASKS
            and len([item for item in starter_entries if isinstance(item, dict) and item.get("status") == "ready"]) == len(starter_entries)
            and {
                "everyday-chat-starter",
                "private-long-context-starter",
                "coding-help-starter",
                "deep-research-starter",
                "file-document-qa-starter",
                "data-analysis-starter",
                "image-generation-starter",
                "image-understanding-starter",
                "voice-dictation-starter",
                "memory-personalization-starter",
                "study-learning-starter",
                "shopping-research-starter",
                "job-search-resume-starter",
                "personal-finance-starter",
                "agent-actions-starter",
                "atlas-browser-chat-starter",
                "developer-mode-mcp-app-starter",
            }.issubset(set(starter_ids))
            and {
                "fast_router",
                "glm_tiny",
                "slopcode_tiny",
                "deep_research",
                "local_agent",
                "comfyui_flux",
                "local_vision",
                "local_whisper_stt",
                "glm52_study_coach_preset",
                "glm52_shopping_research_preset",
            }.issubset(set(starter_route_coverage))
            and all(item.get("prompt_template") for item in starter_entries if isinstance(item, dict))
            and all(item.get("variables") for item in starter_entries if isinstance(item, dict))
            and (starter_prompts.get("summary") or {}).get("prompt_library_items") == len(starter_entries)
            and (starter_prompts.get("summary") or {}).get("openwebui_import_items") == len(starter_entries)
            and len(starter_prompts.get("prompt_library_items") or []) == len(starter_entries)
            and len(starter_prompts.get("openwebui_import_items") or []) == len(starter_entries)
            and starter_prompts.get("privacy", {}).get("static_templates_only") is True
            and starter_prompts.get("privacy", {}).get("openwebui_prompt_import_ready") is True
            and starter_prompts.get("privacy", {}).get("user_prompt_bodies_excluded") is True
            else "failed",
            "evidence": {
                "summary": starter_prompts.get("summary") or {},
                "starter_ids": starter_ids,
                "route_coverage": starter_route_coverage,
                "privacy": starter_prompts.get("privacy") or {},
            },
        },
        {
            "id": "sample-use-cases-covered",
            "status": "passed"
            if counts.get("use_cases") == counts.get("feature_families") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
            and status_counts.get("implemented") == LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
            else "failed",
            "evidence": {
                "use_cases": counts.get("use_cases", 0),
                "feature_families": counts.get("feature_families", 0),
                "implemented_use_cases": status_counts.get("implemented", 0),
            },
        },
        {
            "id": "quality-evals-executable",
            "status": "passed"
            if counts.get("quality_evals") == counts.get("executable_quality_evals")
            and counts.get("quality_evals", 0) >= LOCAL_PARITY_EXPECTED_FEATURE_FAMILIES
            and counts.get("rubric_quality_evals") == 0
            else "failed",
            "evidence": {
                "quality_evals": counts.get("quality_evals", 0),
                "executable_quality_evals": counts.get("executable_quality_evals", 0),
                "rubric_quality_evals": counts.get("rubric_quality_evals", 0),
                "smoke_quality_evals": counts.get("smoke_quality_evals", 0),
                "verifier_quality_evals": counts.get("verifier_quality_evals", 0),
            },
        },
        {
            "id": "local-route-benchmarks-ready",
            "status": "passed" if profiles and all(status == "ready" for status in route_statuses.values()) else "failed",
            "evidence": {
                "route_statuses": route_statuses,
                "benchmark_summary": route_recommendations.get("benchmark_summary") or {},
            },
        },
        {
            "id": "quality-scorecard-ready",
            "status": "passed" if quality_scorecard.get("local_quality_status") == "ready" else "failed",
            "evidence": {
                "local_quality_status": quality_scorecard.get("local_quality_status"),
                "summary": quality_scorecard.get("summary") or {},
            },
        },
        {
            "id": "local-continuity-fallback-ready",
            "status": "passed" if continuity_report.get("continuity_status") == "ready" else "failed",
            "evidence": {
                "continuity_status": continuity_report.get("continuity_status"),
                "summary": continuity_report.get("summary") or {},
            },
        },
        {
            "id": "evidence-trace-ready",
            "status": "passed" if evidence_trace.get("evidence_status") == "ready" else "failed",
            "evidence": {
                "evidence_status": evidence_trace.get("evidence_status"),
                "summary": evidence_trace.get("summary") or {},
            },
        },
        {
            "id": "live-runtime-ready",
            "status": "passed" if live_status.get("live_status") == "ready" else "failed",
            "evidence": {
                "live_status": live_status.get("live_status"),
                "summary": live_status.get("summary") or {},
            },
        },
        {
            "id": "local-privacy-posture",
            "status": "passed"
            if catalog.get("privacy", {}).get("local_only") is True
            and gap_report.get("privacy", {}).get("local_only") is True
            and quality_scorecard.get("privacy", {}).get("local_only") is True
            and continuity_report.get("privacy", {}).get("local_only") is True
            and source_freshness.get("privacy", {}).get("local_only") is True
            and feature_matrix.get("privacy", {}).get("local_only") is True
            and runbook.get("privacy", {}).get("local_only") is True
            and task_recommendations.get("privacy", {}).get("local_only") is True
            and popular_task_routes.get("privacy", {}).get("local_only") is True
            and workflow_recipes.get("privacy", {}).get("local_only") is True
            and starter_prompts.get("privacy", {}).get("local_only") is True
            and starter_prompts.get("privacy", {}).get("static_templates_only") is True
            and starter_prompts.get("privacy", {}).get("openwebui_prompt_import_ready") is True
            and starter_prompts.get("privacy", {}).get("user_prompt_bodies_excluded") is True
            and evidence_trace.get("privacy", {}).get("local_only") is True
            and live_status.get("privacy", {}).get("local_only") is True
            and improvement_plan.get("privacy", {}).get("local_only") is True
            and catalog.get("privacy", {}).get("prompt_bodies_excluded") is True
            and gap_report.get("privacy", {}).get("prompt_bodies_excluded") is True
            and quality_scorecard.get("privacy", {}).get("prompt_bodies_excluded") is True
            and continuity_report.get("privacy", {}).get("prompt_bodies_excluded") is True
            and source_freshness.get("privacy", {}).get("prompt_bodies_excluded") is True
            and feature_matrix.get("privacy", {}).get("prompt_bodies_excluded") is True
            and runbook.get("privacy", {}).get("prompt_bodies_excluded") is True
            and task_recommendations.get("privacy", {}).get("prompt_bodies_excluded") is True
            and popular_task_routes.get("privacy", {}).get("prompt_bodies_excluded") is True
            and workflow_recipes.get("privacy", {}).get("prompt_bodies_excluded") is True
            and evidence_trace.get("privacy", {}).get("prompt_bodies_excluded") is True
            and live_status.get("privacy", {}).get("prompt_bodies_excluded") is True
            and improvement_plan.get("privacy", {}).get("prompt_bodies_excluded") is True
            else "failed",
            "evidence": {
                "catalog_privacy": catalog.get("privacy") or {},
                "gap_privacy": gap_report.get("privacy") or {},
                "quality_scorecard_privacy": quality_scorecard.get("privacy") or {},
                "continuity_report_privacy": continuity_report.get("privacy") or {},
                "source_freshness_privacy": source_freshness.get("privacy") or {},
                "feature_matrix_privacy": feature_matrix.get("privacy") or {},
                "runbook_privacy": runbook.get("privacy") or {},
                "task_recommendations_privacy": task_recommendations.get("privacy") or {},
                "popular_task_routes_privacy": popular_task_routes.get("privacy") or {},
                "workflow_recipes_privacy": workflow_recipes.get("privacy") or {},
                "starter_prompts_privacy": starter_prompts.get("privacy") or {},
                "evidence_trace_privacy": evidence_trace.get("privacy") or {},
                "live_status_privacy": live_status.get("privacy") or {},
                "improvement_plan_privacy": improvement_plan.get("privacy") or {},
            },
        },
        {
            "id": "improvement-plan-ready",
            "status": "passed"
            if improvement_plan.get("status") == "ready"
            and (improvement_plan.get("summary") or {}).get("tracks")
            == (improvement_plan.get("summary") or {}).get("ready_tracks")
            and (improvement_plan.get("summary") or {}).get("completion_status")
            == LOCAL_PARITY_COMPLETION_STATUS
            else "failed",
            "evidence": improvement_plan.get("summary") or {},
        },
    ]
    blocking_requirements = [item for item in requirements if item.get("status") == "failed"]
    local_ready = not blocking_requirements and not non_inherent_gaps
    full_hosted_equivalent = False
    scope_exclusions = gap_report.get("scope_exclusions") or []
    return {
        "source": "chatgpt-local-parity-completion-audit",
        "generated_at": now(),
        "objective": "Map popular ChatGPT features and sample use cases, then test and iterate OpenWebUI toward parity using GLM 5.2 and local models.",
        "local_functional_status": "ready" if local_ready else "not_ready",
        "full_hosted_chatgpt_parity_status": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
        "completion_status": LOCAL_PARITY_COMPLETION_STATUS if local_ready else "needs_attention",
        "requirements": requirements,
        "blocking_requirements": blocking_requirements,
        "remaining_gaps": gap_report.get("gaps") or [],
        "scope_exclusions": scope_exclusions,
        "frontier_boundary": frontier_boundary,
        "summary": {
            "local_functional_requirements_passed": local_ready,
            "full_hosted_equivalent": full_hosted_equivalent,
            "hosted_cloud_equivalence_scope": LOCAL_PARITY_HOSTED_SCOPE_STATUS,
            "open_gaps": (gap_report.get("summary") or {}).get("open_gaps", 0),
            "non_inherent_open_gaps": len(non_inherent_gaps),
            "inherent_open_gaps": len(gap_report.get("gaps") or []) - len(non_inherent_gaps),
            "scope_exclusion_items": len(scope_exclusions),
            "frontier_boundary_items": frontier_summary.get("boundary_items", 0),
            "frontier_boundary_ready_local_mitigations": frontier_summary.get("ready_local_mitigations", 0),
            "frontier_boundary_excluded_from_local_goal_items": frontier_summary.get(
                "excluded_from_local_goal_items", 0
            ),
            "frontier_boundary_not_locally_provable_items": frontier_summary.get("not_locally_provable_items", 0),
            "frontier_boundary_needs_attention_local_mitigations": frontier_summary.get(
                "needs_attention_local_mitigations", 0
            ),
            "local_quality_status": quality_scorecard.get("local_quality_status"),
            "continuity_status": continuity_report.get("continuity_status"),
            "source_freshness_status": source_freshness.get("freshness_status"),
            "current_release_source_id": source_freshness_summary.get("current_release_source_id"),
            "current_release_coverage_ready": current_release_coverage_ready,
            "current_release_covered_families": source_freshness_summary.get("current_release_covered_families", 0),
            "current_release_expected_families": current_release_expected_families,
            "current_release_covered_evidence_terms": source_freshness_summary.get(
                "current_release_covered_evidence_terms", 0
            ),
            "current_release_expected_evidence_terms": current_release_expected_evidence_terms,
            "feature_matrix_status": feature_matrix.get("matrix_status"),
            "runbook_status": runbook.get("runbook_status"),
            "task_recommendations_status": task_recommendations.get("status"),
            "popular_task_routes_status": popular_task_routes.get("status"),
            "workflow_recipes_status": workflow_recipes.get("status"),
            "starter_prompts_status": starter_prompts.get("status"),
            "evidence_trace_status": evidence_trace.get("evidence_status"),
            "live_status": live_status.get("live_status"),
            "improvement_plan_status": improvement_plan.get("status"),
        },
        "feature_matrix": feature_matrix,
        "runbook": runbook,
        "task_recommendations": task_recommendations,
        "research_task_recommendations": research_task_recommendations,
        "popular_task_routes": popular_task_routes,
        "workflow_recipes": workflow_recipes,
        "starter_prompts": starter_prompts,
        "quality_scorecard": quality_scorecard,
        "continuity_report": continuity_report,
        "source_freshness": source_freshness,
        "current_release": source_freshness.get("current_release") or {},
        "evidence_trace": evidence_trace,
        "live_status": live_status,
        "improvement_plan": improvement_plan,
        "next_actions": gap_report.get("next_actions") or [],
        "privacy": {
            "local_only": True,
            "derived_from_static_local_docs": True,
            "derived_from_local_benchmark_summary": True,
            "prompt_bodies_excluded": True,
        },
    }


def local_parity_search_candidates() -> list[dict]:
    current = time.monotonic()
    with LOCAL_APP_PARITY_SEARCH_CACHE_LOCK:
        cached = LOCAL_APP_PARITY_SEARCH_CACHE.get("candidates") or []
        if cached and current < float(LOCAL_APP_PARITY_SEARCH_CACHE.get("expires_at") or 0.0):
            return deepcopy(cached)

    candidates: list[dict] = []

    def add_candidate(source: str, item_id: str, title: str, text_parts: list, url: str, updated_at: int | None = None):
        candidates.append(
            {
                "source": source,
                "id": item_id,
                "title": title,
                "text": searchable_text(text_parts),
                "url": url,
                "updated_at": updated_at or now(),
            }
        )

    parity_catalog = local_parity_catalog()
    for use_case in parity_catalog.get("use_cases", []):
        add_candidate(
            "chatgpt-local-usecase",
            use_case.get("id"),
            use_case.get("feature_family") or use_case.get("id") or "ChatGPT local use case",
            [
                use_case.get("sample_use_case"),
                use_case.get("local_path"),
                use_case.get("primary_models"),
                use_case.get("required_verifiers"),
                use_case.get("optional_verifiers"),
                use_case.get("status"),
            ],
            f"{PUBLIC_BASE_URL}/local-parity/catalog",
            parity_catalog.get("generated_at") or 0,
        )

    gap_report = local_parity_gap_report()
    add_candidate(
        "chatgpt-local-parity-gap-report",
        "chatgpt-local-parity-gap-report",
        "ChatGPT local parity gap report",
        [
            gap_report.get("claim"),
            gap_report.get("summary"),
            gap_report.get("gaps"),
            gap_report.get("scope_exclusions"),
            gap_report.get("frontier_boundary"),
        ],
        f"{PUBLIC_BASE_URL}/local-parity/gap-report",
        gap_report.get("generated_at") or 0,
    )

    improvement_plan = local_parity_improvement_plan()
    add_candidate(
        "chatgpt-local-parity-improvement-plan",
        "chatgpt-local-parity-improvement-plan",
        "ChatGPT local parity improvement plan",
        [
            improvement_plan.get("status"),
            improvement_plan.get("summary"),
            improvement_plan.get("tracks"),
            improvement_plan.get("claim_boundary"),
        ],
        f"{PUBLIC_BASE_URL}/local-parity/improvement-plan",
        improvement_plan.get("generated_at") or 0,
    )

    audit = local_parity_completion_audit()
    add_candidate(
        "chatgpt-local-parity-completion-audit",
        "chatgpt-local-parity-completion-audit",
        "ChatGPT local parity completion audit",
        [
            audit.get("objective"),
            audit.get("local_functional_status"),
            audit.get("full_hosted_chatgpt_parity_status"),
            audit.get("requirements"),
            audit.get("remaining_gaps"),
        ],
        f"{PUBLIC_BASE_URL}/local-parity/audit",
        audit.get("generated_at") or 0,
    )

    report_specs = [
        (
            local_parity_feature_matrix(),
            "chatgpt-local-feature-matrix",
            "chatgpt-local-feature-matrix",
            "ChatGPT local feature matrix",
            ["matrix_status", "summary", "feature_families"],
            "/local-parity/feature-matrix",
        ),
        (
            local_parity_runbook(),
            "chatgpt-local-parity-runbook",
            "chatgpt-local-parity-runbook",
            "ChatGPT local OpenWebUI runbook",
            ["runbook_status", "summary", "entries"],
            "/local-parity/runbook",
        ),
        (
            local_parity_task_recommendations("", 8),
            "chatgpt-local-task-recommendations",
            "chatgpt-local-task-recommendations",
            "ChatGPT local task recommendations",
            ["query", "status", "summary", "recommendations", "remaining_gap_ids"],
            "/local-parity/task-recommendations",
        ),
        (
            local_parity_popular_task_routes(),
            "chatgpt-local-popular-task-routes",
            "chatgpt-local-popular-task-routes",
            "ChatGPT local popular task routes",
            ["status", "summary", "tasks", "remaining_gap_ids"],
            "/local-parity/popular-tasks",
        ),
        (
            local_parity_workflow_recipes(),
            "chatgpt-local-workflow-recipes",
            "chatgpt-local-workflow-recipes",
            "ChatGPT local workflow recipes",
            ["status", "summary", "route_coverage", "optional_case_ids", "recipes", "remaining_gap_ids"],
            "/local-parity/workflows",
        ),
        (
            local_parity_starter_prompts(),
            "chatgpt-local-starter-prompts",
            "chatgpt-local-starter-prompts",
            "ChatGPT local starter prompts",
            [
                "status",
                "summary",
                "route_coverage",
                "workflow_ids",
                "usage_notes",
                "prompts",
                "prompt_library_items",
                "openwebui_import_items",
                "remaining_gap_ids",
            ],
            "/local-parity/starter-prompts",
        ),
        (
            local_parity_action_playbook(),
            "chatgpt-local-parity-playbook",
            "chatgpt-local-parity-playbook",
            "ChatGPT local action playbook",
            ["status", "summary", "route_coverage", "plays", "claim_boundary"],
            "/local-parity/playbook",
        ),
        (
            local_parity_dashboard(),
            "chatgpt-local-parity-dashboard",
            "chatgpt-local-parity-dashboard",
            "ChatGPT local parity dashboard",
            ["status", "summary", "primary_models", "popular_tasks", "remaining_gap"],
            "/local-parity/dashboard",
        ),
        (
            local_parity_readiness_checklist(),
            "chatgpt-local-readiness-checklist",
            "chatgpt-local-readiness-checklist",
            "ChatGPT local objective readiness checklist",
            [
                "objective",
                "local_functional_status",
                "completion_status",
                "summary",
                "requirements",
                "claim_boundary",
            ],
            "/local-parity/readiness-checklist",
        ),
        (
            local_parity_optional_heavy_evidence(),
            "chatgpt-local-optional-heavy-evidence",
            "chatgpt-local-optional-heavy-evidence",
            "ChatGPT local optional-heavy evidence",
            ["status", "summary", "feature_families", "flags", "cases"],
            "/local-parity/optional-evidence",
        ),
        (
            local_parity_quality_scorecard(),
            "chatgpt-local-quality-scorecard",
            "chatgpt-local-quality-scorecard",
            "ChatGPT local quality scorecard",
            ["local_quality_status", "claim_boundary", "summary", "quality_by_feature_family", "route_profiles"],
            "/local-parity/quality-scorecard",
        ),
        (
            local_parity_capacity_plan(),
            "chatgpt-local-model-capacity-plan",
            "chatgpt-local-model-capacity-plan",
            "ChatGPT local model capacity plan",
            ["status", "summary", "routes", "claim_boundary"],
            "/local-parity/capacity-plan",
        ),
        (
            local_parity_continuity_report(),
            "chatgpt-local-continuity-fallback",
            "chatgpt-local-continuity-fallback",
            "ChatGPT local continuity fallback",
            ["continuity_status", "claim_boundary", "summary", "capabilities"],
            "/local-parity/continuity",
        ),
        (
            local_parity_frontier_boundary_matrix(),
            "chatgpt-local-frontier-boundary-matrix",
            "chatgpt-local-frontier-boundary-matrix",
            "ChatGPT local hosted-frontier boundary matrix",
            ["status", "summary", "items", "privacy"],
            "/local-parity/frontier-boundary",
        ),
        (
            local_parity_source_freshness(),
            "chatgpt-feature-source-freshness",
            "chatgpt-feature-source-freshness",
            "ChatGPT feature source freshness",
            ["freshness_status", "summary", "missing_feature_families", "stale_source_ids", "source_statuses"],
            "/local-parity/source-freshness",
        ),
        (
            local_parity_evidence_trace(),
            "chatgpt-local-parity-evidence-trace",
            "chatgpt-local-parity-evidence-trace",
            "ChatGPT local parity evidence trace",
            ["evidence_status", "summary", "artifacts"],
            "/local-parity/evidence",
        ),
        (
            local_parity_live_status(),
            "chatgpt-local-live-status",
            "chatgpt-local-live-status",
            "ChatGPT local live status",
            ["live_status", "summary", "probes"],
            "/local-parity/live-status",
        ),
    ]
    for report, source, item_id, title, keys, path in report_specs:
        add_candidate(
            source,
            item_id,
            title,
            [report.get(key) for key in keys],
            f"{PUBLIC_BASE_URL}{path}",
            report.get("generated_at") or 0,
        )

    with LOCAL_APP_PARITY_SEARCH_CACHE_LOCK:
        LOCAL_APP_PARITY_SEARCH_CACHE["expires_at"] = time.monotonic() + max(1, LOCAL_APP_PARITY_SEARCH_CACHE_SECONDS)
        LOCAL_APP_PARITY_SEARCH_CACHE["candidates"] = deepcopy(candidates)
    return candidates


def local_app_search_uncached(query: str, limit: int = 8) -> list[dict]:
    query = (query or "").strip().lower()
    terms = [term for term in re.split(r"\s+", query) if term]
    limit = max(1, min(25, int(limit or 8)))
    candidates = []

    parity_catalog = local_parity_catalog()
    for use_case in parity_catalog.get("use_cases", []):
        candidates.append(
            {
                "source": "chatgpt-local-usecase",
                "id": use_case.get("id"),
                "title": use_case.get("feature_family") or use_case.get("id") or "ChatGPT local use case",
                "text": searchable_text(
                    [
                        use_case.get("sample_use_case"),
                        use_case.get("local_path"),
                        use_case.get("primary_models"),
                        use_case.get("required_verifiers"),
                        use_case.get("optional_verifiers"),
                        use_case.get("status"),
                    ]
                ),
                "url": f"{PUBLIC_BASE_URL}/local-parity/catalog",
                "updated_at": parity_catalog.get("generated_at") or 0,
            }
        )
    parity_gap_report = local_parity_gap_report()
    candidates.append(
        {
            "source": "chatgpt-local-parity-gap-report",
            "id": "chatgpt-local-parity-gap-report",
            "title": "ChatGPT local parity gap report",
            "text": searchable_text([parity_gap_report.get("claim"), parity_gap_report.get("summary"), parity_gap_report.get("gaps")]),
            "url": f"{PUBLIC_BASE_URL}/local-parity/gap-report",
            "updated_at": parity_gap_report.get("generated_at") or 0,
        }
    )
    parity_improvement_plan = local_parity_improvement_plan()
    candidates.append(
        {
            "source": "chatgpt-local-parity-improvement-plan",
            "id": "chatgpt-local-parity-improvement-plan",
            "title": "ChatGPT local parity improvement plan",
            "text": searchable_text(
                [
                    parity_improvement_plan.get("status"),
                    parity_improvement_plan.get("summary"),
                    parity_improvement_plan.get("tracks"),
                    parity_improvement_plan.get("claim_boundary"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/improvement-plan",
            "updated_at": parity_improvement_plan.get("generated_at") or 0,
        }
    )
    parity_audit = local_parity_completion_audit()
    candidates.append(
        {
            "source": "chatgpt-local-parity-completion-audit",
            "id": "chatgpt-local-parity-completion-audit",
            "title": "ChatGPT local parity completion audit",
            "text": searchable_text(
                [
                    parity_audit.get("objective"),
                    parity_audit.get("local_functional_status"),
                    parity_audit.get("full_hosted_chatgpt_parity_status"),
                    parity_audit.get("requirements"),
                    parity_audit.get("remaining_gaps"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/audit",
            "updated_at": parity_audit.get("generated_at") or 0,
        }
    )
    feature_matrix = local_parity_feature_matrix()
    candidates.append(
        {
            "source": "chatgpt-local-feature-matrix",
            "id": "chatgpt-local-feature-matrix",
            "title": "ChatGPT local feature matrix",
            "text": searchable_text(
                [
                    feature_matrix.get("matrix_status"),
                    feature_matrix.get("summary"),
                    feature_matrix.get("feature_families"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/feature-matrix",
            "updated_at": feature_matrix.get("generated_at") or 0,
        }
    )
    runbook = local_parity_runbook()
    candidates.append(
        {
            "source": "chatgpt-local-parity-runbook",
            "id": "chatgpt-local-parity-runbook",
            "title": "ChatGPT local OpenWebUI runbook",
            "text": searchable_text(
                [
                    runbook.get("runbook_status"),
                    runbook.get("summary"),
                    runbook.get("entries"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/runbook",
            "updated_at": runbook.get("generated_at") or 0,
        }
    )
    task_recommendations = local_parity_task_recommendations("", min(limit, 8))
    candidates.append(
        {
            "source": "chatgpt-local-task-recommendations",
            "id": "chatgpt-local-task-recommendations",
            "title": "ChatGPT local task recommendations",
            "text": searchable_text(
                [
                    task_recommendations.get("query"),
                    task_recommendations.get("status"),
                    task_recommendations.get("summary"),
                    task_recommendations.get("recommendations"),
                    task_recommendations.get("remaining_gap_ids"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/task-recommendations",
            "updated_at": task_recommendations.get("generated_at") or 0,
        }
    )
    popular_task_routes = local_parity_popular_task_routes()
    candidates.append(
        {
            "source": "chatgpt-local-popular-task-routes",
            "id": "chatgpt-local-popular-task-routes",
            "title": "ChatGPT local popular task routes",
            "text": searchable_text(
                [
                    popular_task_routes.get("status"),
                    popular_task_routes.get("summary"),
                    popular_task_routes.get("tasks"),
                    popular_task_routes.get("remaining_gap_ids"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/popular-tasks",
            "updated_at": popular_task_routes.get("generated_at") or 0,
        }
    )
    workflow_recipes = local_parity_workflow_recipes()
    candidates.append(
        {
            "source": "chatgpt-local-workflow-recipes",
            "id": "chatgpt-local-workflow-recipes",
            "title": "ChatGPT local workflow recipes",
            "text": searchable_text(
                [
                    workflow_recipes.get("status"),
                    workflow_recipes.get("summary"),
                    workflow_recipes.get("route_coverage"),
                    workflow_recipes.get("optional_case_ids"),
                    workflow_recipes.get("recipes"),
                    workflow_recipes.get("remaining_gap_ids"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/workflows",
            "updated_at": workflow_recipes.get("generated_at") or 0,
        }
    )
    starter_prompts = local_parity_starter_prompts()
    candidates.append(
        {
            "source": "chatgpt-local-starter-prompts",
            "id": "chatgpt-local-starter-prompts",
            "title": "ChatGPT local starter prompts",
            "text": searchable_text(
                [
                    starter_prompts.get("status"),
                    starter_prompts.get("summary"),
                    starter_prompts.get("route_coverage"),
                    starter_prompts.get("workflow_ids"),
                    starter_prompts.get("usage_notes"),
                    starter_prompts.get("prompts"),
                    starter_prompts.get("prompt_library_items"),
                    starter_prompts.get("openwebui_import_items"),
                    starter_prompts.get("remaining_gap_ids"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/starter-prompts",
            "updated_at": starter_prompts.get("generated_at") or 0,
        }
    )
    parity_dashboard = local_parity_dashboard()
    candidates.append(
        {
            "source": "chatgpt-local-parity-dashboard",
            "id": "chatgpt-local-parity-dashboard",
            "title": "ChatGPT local parity dashboard",
            "text": searchable_text(
                [
                    parity_dashboard.get("status"),
                    parity_dashboard.get("summary"),
                    parity_dashboard.get("primary_models"),
                    parity_dashboard.get("popular_tasks"),
                    parity_dashboard.get("remaining_gap"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/dashboard",
            "updated_at": parity_dashboard.get("generated_at") or 0,
        }
    )
    readiness_checklist = local_parity_readiness_checklist()
    candidates.append(
        {
            "source": "chatgpt-local-readiness-checklist",
            "id": "chatgpt-local-readiness-checklist",
            "title": "ChatGPT local objective readiness checklist",
            "text": searchable_text(
                [
                    readiness_checklist.get("objective"),
                    readiness_checklist.get("local_functional_status"),
                    readiness_checklist.get("completion_status"),
                    readiness_checklist.get("summary"),
                    readiness_checklist.get("requirements"),
                    readiness_checklist.get("claim_boundary"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/readiness-checklist",
            "updated_at": readiness_checklist.get("generated_at") or 0,
        }
    )
    optional_heavy_evidence = local_parity_optional_heavy_evidence()
    candidates.append(
        {
            "source": "chatgpt-local-optional-heavy-evidence",
            "id": "chatgpt-local-optional-heavy-evidence",
            "title": "ChatGPT local optional-heavy evidence",
            "text": searchable_text(
                [
                    optional_heavy_evidence.get("status"),
                    optional_heavy_evidence.get("summary"),
                    optional_heavy_evidence.get("feature_families"),
                    optional_heavy_evidence.get("flags"),
                    optional_heavy_evidence.get("cases"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/optional-evidence",
            "updated_at": optional_heavy_evidence.get("generated_at") or 0,
        }
    )
    quality_scorecard = local_parity_quality_scorecard()
    candidates.append(
        {
            "source": "chatgpt-local-quality-scorecard",
            "id": "chatgpt-local-quality-scorecard",
            "title": "ChatGPT local quality scorecard",
            "text": searchable_text(
                [
                    quality_scorecard.get("local_quality_status"),
                    quality_scorecard.get("claim_boundary"),
                    quality_scorecard.get("summary"),
                    quality_scorecard.get("quality_by_feature_family"),
                    quality_scorecard.get("route_profiles"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/quality-scorecard",
            "updated_at": quality_scorecard.get("generated_at") or 0,
        }
    )
    continuity_report = local_parity_continuity_report()
    candidates.append(
        {
            "source": "chatgpt-local-continuity-fallback",
            "id": "chatgpt-local-continuity-fallback",
            "title": "ChatGPT local continuity fallback",
            "text": searchable_text(
                [
                    continuity_report.get("continuity_status"),
                    continuity_report.get("claim_boundary"),
                    continuity_report.get("summary"),
                    continuity_report.get("capabilities"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/continuity",
            "updated_at": continuity_report.get("generated_at") or 0,
        }
    )
    source_freshness = local_parity_source_freshness()
    candidates.append(
        {
            "source": "chatgpt-feature-source-freshness",
            "id": "chatgpt-feature-source-freshness",
            "title": "ChatGPT feature source freshness",
            "text": searchable_text(
                [
                    source_freshness.get("freshness_status"),
                    source_freshness.get("summary"),
                    source_freshness.get("missing_feature_families"),
                    source_freshness.get("stale_source_ids"),
                    source_freshness.get("source_statuses"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/source-freshness",
            "updated_at": source_freshness.get("generated_at") or 0,
        }
    )
    evidence_trace = local_parity_evidence_trace()
    candidates.append(
        {
            "source": "chatgpt-local-parity-evidence-trace",
            "id": "chatgpt-local-parity-evidence-trace",
            "title": "ChatGPT local parity evidence trace",
            "text": searchable_text(
                [
                    evidence_trace.get("evidence_status"),
                    evidence_trace.get("summary"),
                    evidence_trace.get("artifacts"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/evidence",
            "updated_at": evidence_trace.get("generated_at") or 0,
        }
    )
    live_status = local_parity_live_status()
    candidates.append(
        {
            "source": "chatgpt-local-live-status",
            "id": "chatgpt-local-live-status",
            "title": "ChatGPT local live status",
            "text": searchable_text(
                [
                    live_status.get("live_status"),
                    live_status.get("summary"),
                    live_status.get("probes"),
                ]
            ),
            "url": f"{PUBLIC_BASE_URL}/local-parity/live-status",
            "updated_at": live_status.get("generated_at") or 0,
        }
    )

    for note in list_local_app_notes():
        candidates.append(
            {
                "source": "local-app-note",
                "id": note.get("id"),
                "title": note.get("title") or "Local app note",
                "text": searchable_text([note.get("content"), note.get("tags")]),
                "url": note.get("url"),
                "updated_at": note.get("updated_at") or note.get("created_at") or 0,
            }
        )

    for connection in list_local_app_connections():
        candidates.append(
            {
                "source": "local-app-connection",
                "id": connection.get("id"),
                "title": connection.get("title") or connection.get("app_name") or "Local app connection",
                "text": searchable_text(
                    [
                        connection.get("app_name"),
                        connection.get("provider"),
                        connection.get("account"),
                        connection.get("workspace"),
                        connection.get("status"),
                        connection.get("permission_mode"),
                        connection.get("capabilities"),
                        connection.get("permission_receipt"),
                        connection.get("disconnect_receipt"),
                    ]
                ),
                "url": connection.get("url"),
                "updated_at": connection.get("updated_at") or connection.get("connected_at") or connection.get("created_at") or 0,
            }
        )

    for control in list_local_app_action_controls():
        candidates.append(
            {
                "source": "local-app-action-control",
                "id": control.get("id"),
                "title": control.get("title") or control.get("app_name") or "Local app action control",
                "text": searchable_text(
                    [
                        control.get("app_name"),
                        control.get("provider"),
                        control.get("mode"),
                        control.get("allowed_actions"),
                        control.get("blocked_actions"),
                        control.get("new_actions_policy"),
                        control.get("parameter_constraints"),
                    ]
                ),
                "url": control.get("url"),
                "updated_at": control.get("updated_at") or control.get("created_at") or 0,
            }
        )

    for call_log in list_local_app_call_logs():
        candidates.append(
            {
                "source": "local-app-call-log",
                "id": call_log.get("id"),
                "title": call_log.get("title") or call_log.get("action_name") or "Local app call log",
                "text": searchable_text(
                    [
                        call_log.get("app_name"),
                        call_log.get("provider"),
                        call_log.get("action_name"),
                        call_log.get("action_type"),
                        call_log.get("status"),
                        call_log.get("approval_id"),
                        call_log.get("control_id"),
                        call_log.get("parameter_keys"),
                        call_log.get("prompt_summary"),
                        call_log.get("result_summary"),
                    ]
                ),
                "url": call_log.get("url"),
                "updated_at": call_log.get("updated_at") or call_log.get("created_at") or 0,
            }
        )

    for draft in list_local_email_drafts():
        candidates.append(
            {
                "source": "local-email-draft",
                "id": draft.get("id"),
                "title": draft.get("title") or draft.get("subject") or "Local email draft",
                "text": searchable_text(
                    [
                        draft.get("provider"),
                        draft.get("from"),
                        draft.get("to"),
                        draft.get("cc"),
                        draft.get("subject"),
                        draft.get("body"),
                        draft.get("status"),
                        draft.get("tags"),
                        draft.get("send_receipt"),
                    ]
                ),
                "url": draft.get("url"),
                "updated_at": draft.get("updated_at") or draft.get("created_at") or 0,
            }
        )

    for session in list_local_security_sessions():
        candidates.append(
            {
                "source": "local-security-session",
                "id": session.get("id"),
                "title": session.get("title") or session.get("device") or "Local security session",
                "text": searchable_text(
                    [
                        session.get("app"),
                        session.get("device"),
                        session.get("browser"),
                        session.get("location"),
                        session.get("status"),
                        session.get("trusted_device"),
                        session.get("current_session"),
                        session.get("logout_receipt"),
                    ]
                ),
                "url": session.get("url"),
                "updated_at": session.get("updated_at") or session.get("sign_in_at") or session.get("created_at") or 0,
            }
        )

    for guide in list_local_pronunciations():
        candidates.append(
            {
                "source": "local-pronunciation-guide",
                "id": guide.get("id"),
                "title": guide.get("title") or "Local pronunciation guide",
                "text": searchable_text(
                    [
                        guide.get("word"),
                        guide.get("language"),
                        guide.get("respelling"),
                        guide.get("syllables"),
                        guide.get("stress"),
                        guide.get("tips"),
                        guide.get("audio"),
                    ]
                ),
                "url": guide.get("url"),
                "updated_at": guide.get("updated_at") or guide.get("created_at") or 0,
            }
        )

    for briefing in list_local_sports_briefings():
        candidates.append(
            {
                "source": "local-sports-briefing",
                "id": briefing.get("id"),
                "title": briefing.get("title") or "Local sports briefing",
                "text": searchable_text(
                    [
                        briefing.get("topic"),
                        briefing.get("sport"),
                        briefing.get("competition"),
                        briefing.get("query"),
                        briefing.get("summary"),
                        briefing.get("source_highlights"),
                        briefing.get("sources"),
                        briefing.get("conversation_starters"),
                        briefing.get("citation_block"),
                    ]
                ),
                "url": briefing.get("url"),
                "updated_at": briefing.get("updated_at") or briefing.get("created_at") or 0,
            }
        )

    for site in list_local_sites():
        candidates.append(
            {
                "source": "local-site",
                "id": site.get("id"),
                "title": site.get("title") or "Local site",
                "text": searchable_text([site.get("description"), site.get("tags"), site.get("url")]),
                "url": site.get("url"),
                "updated_at": site.get("updated_at") or site.get("created_at") or 0,
            }
        )

    for workbook in list_local_sheets():
        candidates.append(
            {
                "source": "local-sheet",
                "id": workbook.get("id"),
                "title": workbook.get("title") or "Local spreadsheet",
                "text": searchable_text(
                    [
                        workbook.get("description"),
                        workbook.get("tags"),
                        workbook.get("sheets"),
                        workbook.get("url"),
                    ]
                ),
                "url": workbook.get("url"),
                "updated_at": workbook.get("updated_at") or workbook.get("created_at") or 0,
            }
        )

    for workspace in list_local_code_workspaces():
        candidates.append(
            {
                "source": "local-code-workspace",
                "id": workspace.get("id"),
                "title": workspace.get("title") or "Local code workspace",
                "text": searchable_text(
                    [
                        workspace.get("description"),
                        workspace.get("tags"),
                        workspace.get("files"),
                        workspace.get("last_diff"),
                        workspace.get("url"),
                    ]
                ),
                "url": workspace.get("url"),
                "updated_at": workspace.get("updated_at") or workspace.get("created_at") or 0,
            }
        )

    for worktree in list_local_code_git_worktrees():
        candidates.append(
            {
                "source": "local-code-git-worktree",
                "id": worktree.get("id"),
                "title": f"Git worktree {worktree.get('branch') or worktree.get('id')}",
                "text": searchable_text(
                    [
                        worktree.get("workspace_id"),
                        worktree.get("branch"),
                        worktree.get("status_short"),
                        worktree.get("diff_stat"),
                        worktree.get("path"),
                    ]
                ),
                "url": worktree.get("path"),
                "updated_at": worktree.get("updated_at") or worktree.get("created_at") or 0,
            }
        )
        github_pr = worktree.get("last_github_pr") if isinstance(worktree.get("last_github_pr"), dict) else {}
        if github_pr:
            candidates.append(
                {
                    "source": "local-code-github-pr-draft",
                    "id": github_pr.get("id"),
                    "title": github_pr.get("title") or "Local GitHub PR draft",
                    "text": searchable_text(
                        [
                            github_pr.get("id"),
                            github_pr.get("worktree_id"),
                            github_pr.get("workspace_id"),
                            github_pr.get("base"),
                            github_pr.get("head"),
                            github_pr.get("body"),
                            github_pr.get("diff_stat"),
                            github_pr.get("publish_status"),
                        ]
                    ),
                    "url": github_pr.get("url"),
                    "updated_at": github_pr.get("created_at") or worktree.get("updated_at") or worktree.get("created_at") or 0,
                }
            )

    for goal in list_local_goals():
        candidates.append(
            {
                "source": "local-goal",
                "id": goal.get("id"),
                "title": goal.get("title") or "Local goal",
                "text": searchable_text(
                    [
                        goal.get("objective"),
                        goal.get("success_criteria"),
                        goal.get("status"),
                        goal.get("tags"),
                        goal.get("evidence"),
                        goal.get("evaluation"),
                    ]
                ),
                "url": goal.get("url"),
                "updated_at": goal.get("updated_at") or goal.get("created_at") or 0,
            }
        )

    for benchmark in list_local_model_benchmarks():
        candidates.append(
            {
                "source": "local-model-benchmark",
                "id": benchmark.get("id"),
                "title": benchmark.get("title") or "Local model benchmark",
                "text": searchable_text(
                    [
                        benchmark.get("id"),
                        benchmark.get("suite"),
                        benchmark.get("status"),
                        benchmark.get("model"),
                        benchmark.get("base_url"),
                        benchmark.get("elapsed_seconds"),
                        benchmark.get("approx_completion_tps"),
                        benchmark.get("url"),
                    ]
                ),
                "url": benchmark.get("url"),
                "updated_at": benchmark.get("finished_at") or benchmark.get("created_at") or 0,
            }
        )

    for task in load_tasks().values():
        candidates.append(
            {
                "source": "scheduled-task",
                "id": task.id,
                "title": task.title,
                "text": searchable_text([task.prompt, task.last_status, task.model]),
                "url": f"{PUBLIC_BASE_URL}/tasks/{task.id}",
                "updated_at": task.updated_at,
            }
        )

    for run in list_runs():
        candidates.append(
            {
                "source": "task-run",
                "id": run.get("id"),
                "title": run.get("title") or "Task run",
                "text": searchable_text([run.get("prompt"), run.get("answer"), run.get("status")]),
                "url": run.get("url"),
                "updated_at": run.get("finished_at") or run.get("started_at") or 0,
            }
        )

    for digest in list_pulse_digests():
        candidates.append(
            {
                "source": "pulse-digest",
                "id": digest.get("id"),
                "title": digest.get("title") or "Pulse digest",
                "text": searchable_text([digest.get("answer"), digest.get("cards")]),
                "url": digest.get("url"),
                "updated_at": digest.get("finished_at") or digest.get("created_at") or 0,
            }
        )

    results = []
    for item in candidates:
        haystack = f"{item.get('title', '')}\n{item.get('text', '')}".lower()
        if terms and not all(term in haystack for term in terms):
            continue
        cleaned = re.sub(r"\s+", " ", item.get("text") or "").strip()
        source = item.get("source")
        source_priority = 10 if source == "chatgpt-local-usecase" else 0
        if source == "chatgpt-local-parity-gap-report" and any(
            term in {"frontier", "gap", "gaps", "quality", "hosted", "continuity"} for term in terms
        ):
            source_priority = max(source_priority, 9)
        if source == "chatgpt-local-parity-improvement-plan" and any(
            term in {"improvement", "plan", "latency", "benchmark", "frontier", "quality", "continuity"} for term in terms
        ):
            source_priority = max(source_priority, 9)
        results.append(
            {
                "source": source,
                "id": item.get("id"),
                "title": item.get("title"),
                "snippet": cleaned[:320],
                "url": item.get("url"),
                "updated_at": item.get("updated_at"),
                "_rank": source_priority,
            }
        )

    results.sort(key=lambda item: (item.get("_rank") or 0, item.get("updated_at") or 0), reverse=True)
    return [{key: value for key, value in item.items() if key != "_rank"} for item in results[:limit]]


def local_app_search(query: str, limit: int = 8) -> list[dict]:
    query = (query or "").strip().lower()
    terms = [term for term in re.split(r"\s+", query) if term]
    limit = max(1, min(25, int(limit or 8)))
    fast_results = []
    for draft in list_local_email_drafts():
        text = searchable_text(
            [
                draft.get("provider"),
                draft.get("from"),
                draft.get("to"),
                draft.get("cc"),
                draft.get("subject"),
                draft.get("body"),
                draft.get("status"),
                draft.get("tags"),
                draft.get("send_receipt"),
            ]
        )
        haystack = f"{draft.get('title') or draft.get('subject') or ''}\n{text}".lower()
        if terms and not all(term in haystack for term in terms):
            continue
        fast_results.append(
            {
                "source": "local-email-draft",
                "id": draft.get("id"),
                "title": draft.get("title") or draft.get("subject") or "Local email draft",
                "snippet": re.sub(r"\s+", " ", text or "").strip()[:320],
                "url": draft.get("url"),
                "updated_at": draft.get("updated_at") or draft.get("created_at") or 0,
            }
        )
    if fast_results:
        fast_results.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
        return fast_results[:limit]
    for connection in list_local_app_connections():
        text = searchable_text(
            [
                connection.get("app_name"),
                connection.get("provider"),
                connection.get("account"),
                connection.get("workspace"),
                connection.get("status"),
                connection.get("permission_mode"),
                connection.get("capabilities"),
                connection.get("permission_receipt"),
                connection.get("disconnect_receipt"),
            ]
        )
        haystack = f"{connection.get('title') or connection.get('app_name') or ''}\n{text}".lower()
        if terms and not all(term in haystack for term in terms):
            continue
        fast_results.append(
            {
                "source": "local-app-connection",
                "id": connection.get("id"),
                "title": connection.get("title") or connection.get("app_name") or "Local app connection",
                "snippet": re.sub(r"\s+", " ", text or "").strip()[:320],
                "url": connection.get("url"),
                "updated_at": connection.get("updated_at") or connection.get("connected_at") or connection.get("created_at") or 0,
            }
        )
    if fast_results:
        fast_results.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
        return fast_results[:limit]
    for control in list_local_app_action_controls():
        text = searchable_text(
            [
                control.get("app_name"),
                control.get("provider"),
                control.get("mode"),
                control.get("allowed_actions"),
                control.get("blocked_actions"),
                control.get("new_actions_policy"),
                control.get("parameter_constraints"),
            ]
        )
        haystack = f"{control.get('title') or control.get('app_name') or ''}\n{text}".lower()
        if terms and not all(term in haystack for term in terms):
            continue
        fast_results.append(
            {
                "source": "local-app-action-control",
                "id": control.get("id"),
                "title": control.get("title") or control.get("app_name") or "Local app action control",
                "snippet": re.sub(r"\s+", " ", text or "").strip()[:320],
                "url": control.get("url"),
                "updated_at": control.get("updated_at") or control.get("created_at") or 0,
            }
        )
    if fast_results:
        fast_results.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
        return fast_results[:limit]
    for call_log in list_local_app_call_logs():
        text = searchable_text(
            [
                call_log.get("app_name"),
                call_log.get("provider"),
                call_log.get("action_name"),
                call_log.get("action_type"),
                call_log.get("status"),
                call_log.get("approval_id"),
                call_log.get("control_id"),
                call_log.get("parameter_keys"),
                call_log.get("prompt_summary"),
                call_log.get("result_summary"),
            ]
        )
        haystack = f"{call_log.get('title') or call_log.get('action_name') or ''}\n{text}".lower()
        if terms and not all(term in haystack for term in terms):
            continue
        fast_results.append(
            {
                "source": "local-app-call-log",
                "id": call_log.get("id"),
                "title": call_log.get("title") or call_log.get("action_name") or "Local app call log",
                "snippet": re.sub(r"\s+", " ", text or "").strip()[:320],
                "url": call_log.get("url"),
                "updated_at": call_log.get("updated_at") or call_log.get("created_at") or 0,
            }
        )
    if fast_results:
        fast_results.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
        return fast_results[:limit]
    for session in list_local_security_sessions():
        text = searchable_text(
            [
                session.get("app"),
                session.get("device"),
                session.get("browser"),
                session.get("location"),
                session.get("status"),
                session.get("trusted_device"),
                session.get("current_session"),
                session.get("logout_receipt"),
            ]
        )
        haystack = f"{session.get('title') or session.get('device') or ''}\n{text}".lower()
        if terms and not all(term in haystack for term in terms):
            continue
        fast_results.append(
            {
                "source": "local-security-session",
                "id": session.get("id"),
                "title": session.get("title") or session.get("device") or "Local security session",
                "snippet": re.sub(r"\s+", " ", text or "").strip()[:320],
                "url": session.get("url"),
                "updated_at": session.get("updated_at") or session.get("sign_in_at") or session.get("created_at") or 0,
            }
        )
    if fast_results:
        fast_results.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
        return fast_results[:limit]
    candidates = local_parity_search_candidates()

    def add_candidate(source: str, item_id: str | None, title: str, text_parts: list, url: str | None, updated_at: int | None):
        candidates.append(
            {
                "source": source,
                "id": item_id,
                "title": title,
                "text": searchable_text(text_parts),
                "url": url,
                "updated_at": updated_at or 0,
            }
        )

    for note in list_local_app_notes():
        add_candidate(
            "local-app-note",
            note.get("id"),
            note.get("title") or "Local app note",
            [note.get("content"), note.get("tags")],
            note.get("url"),
            note.get("updated_at") or note.get("created_at") or 0,
        )

    for connection in list_local_app_connections():
        add_candidate(
            "local-app-connection",
            connection.get("id"),
            connection.get("title") or connection.get("app_name") or "Local app connection",
            [
                connection.get("app_name"),
                connection.get("provider"),
                connection.get("account"),
                connection.get("workspace"),
                connection.get("status"),
                connection.get("permission_mode"),
                connection.get("capabilities"),
                connection.get("permission_receipt"),
                connection.get("disconnect_receipt"),
            ],
            connection.get("url"),
            connection.get("updated_at") or connection.get("connected_at") or connection.get("created_at") or 0,
        )

    for control in list_local_app_action_controls():
        add_candidate(
            "local-app-action-control",
            control.get("id"),
            control.get("title") or control.get("app_name") or "Local app action control",
            [
                control.get("app_name"),
                control.get("provider"),
                control.get("mode"),
                control.get("allowed_actions"),
                control.get("blocked_actions"),
                control.get("new_actions_policy"),
                control.get("parameter_constraints"),
            ],
            control.get("url"),
            control.get("updated_at") or control.get("created_at") or 0,
        )

    for call_log in list_local_app_call_logs():
        add_candidate(
            "local-app-call-log",
            call_log.get("id"),
            call_log.get("title") or call_log.get("action_name") or "Local app call log",
            [
                call_log.get("app_name"),
                call_log.get("provider"),
                call_log.get("action_name"),
                call_log.get("action_type"),
                call_log.get("status"),
                call_log.get("approval_id"),
                call_log.get("control_id"),
                call_log.get("parameter_keys"),
                call_log.get("prompt_summary"),
                call_log.get("result_summary"),
            ],
            call_log.get("url"),
            call_log.get("updated_at") or call_log.get("created_at") or 0,
        )

    for draft in list_local_email_drafts():
        add_candidate(
            "local-email-draft",
            draft.get("id"),
            draft.get("title") or draft.get("subject") or "Local email draft",
            [
                draft.get("provider"),
                draft.get("from"),
                draft.get("to"),
                draft.get("cc"),
                draft.get("subject"),
                draft.get("body"),
                draft.get("status"),
                draft.get("tags"),
                draft.get("send_receipt"),
            ],
            draft.get("url"),
            draft.get("updated_at") or draft.get("created_at") or 0,
        )

    for session in list_local_security_sessions():
        add_candidate(
            "local-security-session",
            session.get("id"),
            session.get("title") or session.get("device") or "Local security session",
            [
                session.get("app"),
                session.get("device"),
                session.get("browser"),
                session.get("location"),
                session.get("status"),
                session.get("trusted_device"),
                session.get("current_session"),
                session.get("logout_receipt"),
            ],
            session.get("url"),
            session.get("updated_at") or session.get("sign_in_at") or session.get("created_at") or 0,
        )

    for guide in list_local_pronunciations():
        add_candidate(
            "local-pronunciation-guide",
            guide.get("id"),
            guide.get("title") or "Local pronunciation guide",
            [
                guide.get("word"),
                guide.get("language"),
                guide.get("respelling"),
                guide.get("syllables"),
                guide.get("stress"),
                guide.get("tips"),
                guide.get("audio"),
            ],
            guide.get("url"),
            guide.get("updated_at") or guide.get("created_at") or 0,
        )

    for briefing in list_local_sports_briefings():
        add_candidate(
            "local-sports-briefing",
            briefing.get("id"),
            briefing.get("title") or "Local sports briefing",
            [
                briefing.get("topic"),
                briefing.get("sport"),
                briefing.get("competition"),
                briefing.get("query"),
                briefing.get("summary"),
                briefing.get("source_highlights"),
                briefing.get("sources"),
                briefing.get("conversation_starters"),
                briefing.get("citation_block"),
            ],
            briefing.get("url"),
            briefing.get("updated_at") or briefing.get("created_at") or 0,
        )

    for site in list_local_sites():
        add_candidate(
            "local-site",
            site.get("id"),
            site.get("title") or "Local site",
            [site.get("description"), site.get("tags"), site.get("url")],
            site.get("url"),
            site.get("updated_at") or site.get("created_at") or 0,
        )

    for workbook in list_local_sheets():
        add_candidate(
            "local-sheet",
            workbook.get("id"),
            workbook.get("title") or "Local spreadsheet",
            [workbook.get("description"), workbook.get("tags"), workbook.get("sheets"), workbook.get("url")],
            workbook.get("url"),
            workbook.get("updated_at") or workbook.get("created_at") or 0,
        )

    for workspace in list_local_code_workspaces():
        add_candidate(
            "local-code-workspace",
            workspace.get("id"),
            workspace.get("title") or "Local code workspace",
            [
                workspace.get("description"),
                workspace.get("tags"),
                workspace.get("files"),
                workspace.get("last_diff"),
                workspace.get("url"),
            ],
            workspace.get("url"),
            workspace.get("updated_at") or workspace.get("created_at") or 0,
        )

    for worktree in list_local_code_git_worktrees():
        add_candidate(
            "local-code-git-worktree",
            worktree.get("id"),
            f"Git worktree {worktree.get('branch') or worktree.get('id')}",
            [
                worktree.get("workspace_id"),
                worktree.get("branch"),
                worktree.get("status_short"),
                worktree.get("diff_stat"),
                worktree.get("path"),
            ],
            worktree.get("path"),
            worktree.get("updated_at") or worktree.get("created_at") or 0,
        )
        github_pr = worktree.get("last_github_pr") if isinstance(worktree.get("last_github_pr"), dict) else {}
        if github_pr:
            add_candidate(
                "local-code-github-pr-draft",
                github_pr.get("id"),
                github_pr.get("title") or "Local GitHub PR draft",
                [
                    github_pr.get("id"),
                    github_pr.get("worktree_id"),
                    github_pr.get("workspace_id"),
                    github_pr.get("base"),
                    github_pr.get("head"),
                    github_pr.get("body"),
                    github_pr.get("diff_stat"),
                    github_pr.get("publish_status"),
                ],
                github_pr.get("url"),
                github_pr.get("created_at") or worktree.get("updated_at") or worktree.get("created_at") or 0,
            )

    for goal in list_local_goals():
        add_candidate(
            "local-goal",
            goal.get("id"),
            goal.get("title") or "Local goal",
            [
                goal.get("objective"),
                goal.get("success_criteria"),
                goal.get("status"),
                goal.get("tags"),
                goal.get("evidence"),
                goal.get("evaluation"),
            ],
            goal.get("url"),
            goal.get("updated_at") or goal.get("created_at") or 0,
        )

    for benchmark in list_local_model_benchmarks():
        add_candidate(
            "local-model-benchmark",
            benchmark.get("id"),
            benchmark.get("title") or "Local model benchmark",
            [
                benchmark.get("id"),
                benchmark.get("suite"),
                benchmark.get("status"),
                benchmark.get("model"),
                benchmark.get("base_url"),
                benchmark.get("elapsed_seconds"),
                benchmark.get("approx_completion_tps"),
                benchmark.get("url"),
            ],
            benchmark.get("url"),
            benchmark.get("finished_at") or benchmark.get("created_at") or 0,
        )

    for task in load_tasks().values():
        add_candidate(
            "scheduled-task",
            task.id,
            task.title,
            [task.prompt, task.last_status, task.model],
            f"{PUBLIC_BASE_URL}/tasks/{task.id}",
            task.updated_at,
        )

    for run in list_runs():
        add_candidate(
            "task-run",
            run.get("id"),
            run.get("title") or "Task run",
            [run.get("prompt"), run.get("answer"), run.get("status")],
            run.get("url"),
            run.get("finished_at") or run.get("started_at") or 0,
        )

    for digest in list_pulse_digests():
        add_candidate(
            "pulse-digest",
            digest.get("id"),
            digest.get("title") or "Pulse digest",
            [digest.get("answer"), digest.get("cards")],
            digest.get("url"),
            digest.get("finished_at") or digest.get("created_at") or 0,
        )

    results = []
    for item in candidates:
        haystack = f"{item.get('title', '')}\n{item.get('text', '')}".lower()
        if terms and not all(term in haystack for term in terms):
            continue
        source = item.get("source")
        source_priority = 10 if source == "chatgpt-local-usecase" else 0
        if source == "chatgpt-local-parity-gap-report" and any(
            term in {"frontier", "gap", "gaps", "quality", "hosted", "continuity"} for term in terms
        ):
            source_priority = max(source_priority, 9)
        if source == "chatgpt-local-parity-improvement-plan" and any(
            term in {"improvement", "plan", "latency", "benchmark", "frontier", "quality", "continuity"} for term in terms
        ):
            source_priority = max(source_priority, 9)
        cleaned = re.sub(r"\s+", " ", item.get("text") or "").strip()
        results.append(
            {
                "source": source,
                "id": item.get("id"),
                "title": item.get("title"),
                "snippet": cleaned[:320],
                "url": item.get("url"),
                "updated_at": item.get("updated_at"),
                "_rank": source_priority,
            }
        )

    results.sort(key=lambda item: (item.get("_rank") or 0, item.get("updated_at") or 0), reverse=True)
    return [{key: value for key, value in item.items() if key != "_rank"} for item in results[:limit]]


def approval_mode(payload: dict | None = None, query: dict | None = None) -> str:
    payload = payload or {}
    query = query or {}
    value = (
        payload.get("approval_mode")
        or payload.get("permission_mode")
        or payload.get("app_permission_mode")
        or (query.get("approval_mode") or [""])[0]
        or (query.get("permission_mode") or [""])[0]
        or os.environ.get("LOCAL_SCHEDULER_APP_PERMISSION_MODE", "never_ask")
    )
    value = str(value).strip().lower().replace("-", "_")
    aliases = {
        "never": "never_ask",
        "none": "never_ask",
        "off": "never_ask",
        "always": "always_ask",
        "changes": "any_changes",
        "important": "important_actions",
    }
    value = aliases.get(value, value)
    if value not in {"never_ask", "always_ask", "any_changes", "important_actions"}:
        return "never_ask"
    return value


def requires_approval(mode: str, *, mutation: bool, important: bool) -> bool:
    if mode == "never_ask":
        return False
    if mode == "always_ask":
        return True
    if mode == "any_changes":
        return mutation
    if mode == "important_actions":
        return important
    return False


def create_approval(action: str, summary: str, mode: str, *, payload: dict | None, path: str, method: str, important: bool) -> dict:
    approval_id = str(uuid.uuid4())
    created = now()
    approval = {
        "id": approval_id,
        "status": "pending",
        "action": action,
        "summary": summary,
        "permission_mode": mode,
        "important": important,
        "method": method,
        "path": path,
        "payload": payload or {},
        "created_at": created,
        "updated_at": created,
        "url": f"{PUBLIC_BASE_URL}/approvals/{approval_id}",
    }
    write_approval(approval)
    return approval


def approve_or_require(
    handler: BaseHTTPRequestHandler,
    *,
    action: str,
    summary: str,
    payload: dict | None = None,
    query: dict | None = None,
    mutation: bool = True,
    important: bool = True,
) -> bool:
    mode = approval_mode(payload, query)
    if not requires_approval(mode, mutation=mutation, important=important):
        return True

    approval_id = (payload or {}).get("approval_id") or ((query or {}).get("approval_id") or [""])[0]
    if approval_id:
        approval = read_approval(str(approval_id))
        if approval and approval.get("status") == "approved" and approval.get("action") == action:
            approval["status"] = "used"
            approval["used_at"] = now()
            approval["updated_at"] = now()
            write_approval(approval)
            return True

    approval = create_approval(
        action,
        summary,
        mode,
        payload=payload,
        path=parse.urlparse(handler.path).path,
        method=handler.command,
        important=important,
    )
    send_json(handler, 202, {"approval_required": True, "approval": approval})
    return False


def prompt_text(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def build_pulse_prompt(payload: dict) -> str:
    topics = prompt_text(payload.get("topics") or ["next useful local AI follow-up"])
    context = prompt_text(payload.get("context") or "")
    feedback = prompt_text(payload.get("feedback") or "")
    return "\n".join(
        [
            "Create a concise proactive Pulse digest for the user.",
            "Use the supplied memory, recent context, and feedback to identify what would help next.",
            "Return short, scan-friendly card text with concrete next actions.",
            "",
            "Topics:",
            topics,
            "",
            "Context:",
            context or "(none supplied)",
            "",
            "Feedback:",
            feedback or "(none supplied)",
        ]
    )


def text_snippets(text: str, limit: int) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    snippets = []
    for part in parts:
        part = part.strip()
        if len(part) < 12:
            continue
        snippets.append(part[:260])
        if len(snippets) >= limit:
            break
    return snippets


def build_pulse_cards(payload: dict, answer: str) -> list[dict]:
    max_cards = max(1, min(8, int(payload.get("max_cards") or 3)))
    topics = payload.get("topics")
    if not isinstance(topics, list) or not topics:
        topics = ["Today", "Research", "Next step"]
    snippets = text_snippets(answer, max_cards)
    cards = []
    accents = ["teal", "blue", "violet", "amber", "rose", "slate", "green", "cyan"]
    icons = ["spark", "search", "calendar", "note", "check", "link", "idea", "flag"]
    for idx in range(max_cards):
        topic = str(topics[idx % len(topics)]).strip() or f"Pulse item {idx + 1}"
        summary = snippets[idx] if idx < len(snippets) else f"Review {topic} and decide the next local follow-up."
        detail = answer[:1200] if idx == 0 and answer else summary
        cards.append(
            {
                "id": f"card-{idx + 1}",
                "title": topic[:80],
                "summary": summary,
                "detail": detail,
                "accent": accents[idx % len(accents)],
                "icon": icons[idx % len(icons)],
                "actions": ["open sources", "save for later", "ask follow-up"],
            }
        )
    return cards


def create_pulse_digest(payload: dict) -> dict:
    created = now()
    pulse_id = payload.get("id") or str(uuid.uuid4())
    title = str(payload.get("title") or "Local Pulse digest").strip()[:200]
    task = Task(
        id=f"pulse-{pulse_id}",
        title=title,
        prompt=build_pulse_prompt(payload),
        enabled=False,
        base_url=normalize_base_url(payload.get("base_url") or DEFAULT_BASE_URL),
        model=str(payload.get("model") or DEFAULT_MODEL),
        api_key=str(payload.get("api_key") or ""),
        interval_seconds=None,
        run_at=None,
        next_run_at=None,
        options=payload.get("options") if isinstance(payload.get("options"), dict) else {},
        created_at=created,
        updated_at=created,
    )

    digest = {
        "id": pulse_id,
        "title": title,
        "created_at": created,
        "status": "running",
        "model": task.model,
        "base_url": task.base_url,
        "prompt": task.prompt,
        "answer": "",
        "error": "",
        "cards": [],
        "saved": False,
        "url": f"{PUBLIC_BASE_URL}/pulse/cards/{pulse_id}",
    }
    write_pulse_digest(digest)

    try:
        answer = chat_completions(task)
        digest["answer"] = answer
        digest["cards"] = build_pulse_cards(payload, answer)
        digest["status"] = "completed"
    except Exception as exc:
        digest["status"] = "failed"
        digest["error"] = str(exc)[:2000]
        digest["cards"] = build_pulse_cards(payload, "")
    digest["finished_at"] = now()
    write_pulse_digest(digest)
    return digest


def run_task(task_id: str) -> dict:
    with LOCK:
        if task_id in RUNNING:
            raise RuntimeError("task is already running")
        tasks = load_tasks()
        task = tasks.get(task_id)
        if not task:
            raise KeyError("task not found")
        RUNNING.add(task_id)

    run_id = str(uuid.uuid4())
    started = now()
    run = {
        "id": run_id,
        "task_id": task_id,
        "title": task.title,
        "prompt": task.prompt,
        "model": task.model,
        "base_url": normalize_base_url(task.base_url),
        "started_at": started,
        "finished_at": None,
        "status": "running",
        "answer": "",
        "error": "",
        "url": f"{PUBLIC_BASE_URL}/runs/{run_id}",
    }
    write_run(run)

    try:
        run["answer"] = chat_completions(task)
        run["status"] = "completed"
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = str(exc)[:2000]
    finally:
        finished = now()
        run["finished_at"] = finished
        write_run(run)
        with LOCK:
            tasks = load_tasks()
            latest = tasks.get(task_id)
            if latest:
                latest.last_run_at = finished
                latest.last_status = run["status"]
                latest.last_run_id = run_id
                if latest.interval_seconds:
                    latest.next_run_at = finished + latest.interval_seconds
                else:
                    latest.next_run_at = None
                    latest.enabled = False
                latest.updated_at = finished
                tasks[task_id] = latest
                save_tasks(tasks)
            RUNNING.discard(task_id)
    return run


def create_task(payload: dict) -> Task:
    created = now()
    task_id = payload.get("id") or str(uuid.uuid4())
    title = str(payload.get("title") or "Scheduled task").strip()[:200]
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    interval = payload.get("interval_seconds")
    interval_seconds = None
    if interval not in (None, ""):
        interval_seconds = max(1, int(interval))
    run_at = parse_time(payload.get("run_at"))
    enabled = bool(payload.get("enabled", True))
    next_run_at = parse_time(payload.get("next_run_at"))
    if enabled and next_run_at is None:
        if run_at is not None:
            next_run_at = run_at
        elif interval_seconds:
            next_run_at = created + interval_seconds

    return Task(
        id=task_id,
        title=title,
        prompt=prompt,
        enabled=enabled,
        base_url=normalize_base_url(payload.get("base_url") or DEFAULT_BASE_URL),
        model=str(payload.get("model") or DEFAULT_MODEL),
        api_key=str(payload.get("api_key") or ""),
        interval_seconds=interval_seconds,
        run_at=run_at,
        next_run_at=next_run_at,
        options=payload.get("options") if isinstance(payload.get("options"), dict) else {},
        created_at=created,
        updated_at=created,
    )


def local_benchmark_id(value: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", value or "").strip("-")
    return safe_id[:120] or str(uuid.uuid4())


def local_benchmark_path(benchmark_id: str) -> Path:
    return LOCAL_BENCHMARKS_DIR / f"{local_benchmark_id(benchmark_id)}.json"


def read_local_model_benchmark(benchmark_id: str) -> dict | None:
    path = local_benchmark_path(benchmark_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_local_model_benchmark(benchmark: dict):
    local_benchmark_path(benchmark["id"]).write_text(json.dumps(benchmark, indent=2, ensure_ascii=False), encoding="utf-8")


def list_local_model_benchmarks() -> list[dict]:
    benchmarks = []
    for path in LOCAL_BENCHMARKS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        benchmarks.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "source": "local-model-benchmark",
                "suite": item.get("suite"),
                "status": item.get("status"),
                "model": item.get("model"),
                "base_url": item.get("base_url"),
                "elapsed_seconds": item.get("elapsed_seconds"),
                "completion_tokens": item.get("completion_tokens"),
                "approx_completion_tps": item.get("approx_completion_tps"),
                "created_at": item.get("created_at"),
                "finished_at": item.get("finished_at"),
                "url": item.get("url"),
            }
        )
    benchmarks.sort(key=lambda item: item.get("finished_at") or item.get("created_at") or 0, reverse=True)
    return benchmarks


def benchmark_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def benchmark_timestamp(item: dict | None) -> int | None:
    if not item:
        return None
    value = benchmark_float(item.get("finished_at") or item.get("created_at"))
    return int(value) if value > 0 else None


def benchmark_age_seconds(item: dict | None, reference_time: int | None = None) -> int | None:
    timestamp = benchmark_timestamp(item)
    if timestamp is None:
        return None
    current = int(reference_time if reference_time is not None else now())
    return max(0, current - timestamp)


def benchmark_freshness_status(
    item: dict | None,
    reference_time: int | None = None,
    max_age_seconds: int = LOCAL_BENCHMARK_FRESH_MAX_AGE_SECONDS,
) -> str:
    age_seconds = benchmark_age_seconds(item, reference_time)
    if age_seconds is None:
        return "unmeasured"
    return "fresh" if age_seconds <= max_age_seconds else "stale"


def benchmark_summary_item(item: dict | None) -> dict | None:
    if not item:
        return None
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "source": "local-model-benchmark",
        "suite": item.get("suite"),
        "status": item.get("status"),
        "model": item.get("model"),
        "response_model": item.get("response_model"),
        "base_url": item.get("base_url"),
        "elapsed_seconds": item.get("elapsed_seconds"),
        "completion_tokens": item.get("completion_tokens"),
        "approx_completion_tps": item.get("approx_completion_tps"),
        "created_at": item.get("created_at"),
        "finished_at": item.get("finished_at"),
        "url": item.get("url"),
    }


def summarize_benchmark_group(items: list[dict], reference_time: int | None = None) -> dict:
    count = len(items)
    passed = sum(1 for item in items if item.get("status") == "passed")
    failed = sum(1 for item in items if item.get("status") == "failed")
    running = sum(1 for item in items if item.get("status") == "running")
    tps_values = [benchmark_float(item.get("approx_completion_tps")) for item in items]
    tps_values = [value for value in tps_values if value > 0]
    elapsed_values = [benchmark_float(item.get("elapsed_seconds")) for item in items]
    elapsed_values = [value for value in elapsed_values if value > 0]
    latest = max(items, key=lambda item: benchmark_float(item.get("finished_at") or item.get("created_at"))) if items else None
    best = max(items, key=lambda item: benchmark_float(item.get("approx_completion_tps"))) if items else None
    latest_age_seconds = benchmark_age_seconds(latest, reference_time)
    freshness_status = benchmark_freshness_status(latest, reference_time)
    return {
        "count": count,
        "passed": passed,
        "failed": failed,
        "running": running,
        "pass_rate": round(passed / count, 3) if count else 0.0,
        "latest": benchmark_summary_item(latest),
        "best": benchmark_summary_item(best),
        "freshness_status": freshness_status,
        "max_age_seconds": LOCAL_BENCHMARK_FRESH_MAX_AGE_SECONDS,
        "latest_age_seconds": latest_age_seconds,
        "latest_age_hours": round(latest_age_seconds / 3600, 3) if latest_age_seconds is not None else None,
        "best_tps": round(max(tps_values), 3) if tps_values else 0.0,
        "avg_tps": round(sum(tps_values) / len(tps_values), 3) if tps_values else 0.0,
        "avg_elapsed_seconds": round(sum(elapsed_values) / len(elapsed_values), 3) if elapsed_values else 0.0,
    }


def summarize_local_model_benchmarks() -> dict:
    generated_at = now()
    records = []
    for path in LOCAL_BENCHMARKS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        records.append(item)
    records.sort(key=lambda item: benchmark_float(item.get("finished_at") or item.get("created_at")), reverse=True)

    by_suite: dict[str, list[dict]] = {}
    by_model: dict[str, list[dict]] = {}
    by_suite_model: dict[str, dict[str, list[dict]]] = {}
    for item in records:
        suite = str(item.get("suite") or "unknown")
        model = str(item.get("response_model") or item.get("model") or "unknown")
        by_suite.setdefault(suite, []).append(item)
        by_model.setdefault(model, []).append(item)
        by_suite_model.setdefault(suite, {}).setdefault(model, []).append(item)

    group_summary = summarize_benchmark_group(records, generated_at)
    suite_summaries = {suite: summarize_benchmark_group(items, generated_at) for suite, items in sorted(by_suite.items())}
    model_summaries = {model: summarize_benchmark_group(items, generated_at) for model, items in sorted(by_model.items())}
    matrix_summaries = {
        suite: {model: summarize_benchmark_group(items, generated_at) for model, items in sorted(models.items())}
        for suite, models in sorted(by_suite_model.items())
    }
    stale_suites = sorted(
        suite for suite, group in suite_summaries.items() if group.get("freshness_status") not in {"fresh", "unmeasured"}
    )
    measured_suites = [group for group in suite_summaries.values() if group.get("count", 0) > 0]
    freshness_status = (
        "unmeasured"
        if not records
        else "stale"
        if stale_suites
        else "fresh"
        if measured_suites
        else "unmeasured"
    )

    return {
        "source": "local-model-benchmark-summary",
        "count": len(records),
        **group_summary,
        "freshness_status": freshness_status,
        "stale_suites": stale_suites,
        "max_age_seconds": LOCAL_BENCHMARK_FRESH_MAX_AGE_SECONDS,
        "generated_at": generated_at,
        "latest": benchmark_summary_item(records[0]) if records else None,
        "by_suite": suite_summaries,
        "by_model": model_summaries,
        "matrix": matrix_summaries,
        "privacy": {
            "local_only": True,
            "stored_under": str(LOCAL_BENCHMARKS_DIR),
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
        },
    }


def benchmark_recommendation_status(group: dict, target_tps: float = 0.0) -> str:
    count = int(group.get("count") or 0)
    passed = int(group.get("passed") or 0)
    pass_rate = benchmark_float(group.get("pass_rate"))
    best_tps = benchmark_float(group.get("best_tps"))
    freshness_status = str(group.get("freshness_status") or "unmeasured")
    if count <= 0:
        return "unmeasured"
    if freshness_status == "stale":
        return "stale_benchmark"
    if passed <= 0 or pass_rate <= 0:
        return "failing"
    if target_tps > 0 and best_tps < target_tps:
        return "below_latency_target"
    return "ready"


def local_model_route_recommendations() -> dict:
    summary = summarize_local_model_benchmarks()
    by_suite = summary.get("by_suite") if isinstance(summary.get("by_suite"), dict) else {}

    profiles = {
        "fast_router": {
            "title": "Default local ChatGPT-like route",
            "benchmark_suite": "fast_router",
            "default_model": "local-auto-router",
            "target_tps": 20.0,
            "best_for": [
                "everyday questions",
                "short summaries",
                "drafting",
                "simple tutoring",
                "automatic local route selection",
            ],
            "tradeoffs": [
                "heuristic routing instead of frontier model auto-switching",
                "quality depends on selected local lane",
            ],
        },
        "slopcode_tiny": {
            "title": "Local coding route",
            "benchmark_suite": "slopcode_tiny",
            "default_model": "qwen3.6-35b-a3b:slopcode-cpu-64k",
            "target_tps": 1.0,
            "best_for": [
                "code explanation",
                "small fixes",
                "SQL and Python snippets",
                "local software-engineering workflows",
            ],
            "tradeoffs": [
                "CPU-heavy route can be slow",
                "not equivalent to hosted Codex frontier quality",
            ],
        },
        "glm_tiny": {
            "title": "Private GLM 5.2 reasoning route",
            "benchmark_suite": "glm_tiny",
            "default_model": "glm52-q8-local or glm52-q4-local",
            "target_tps": 0.1,
            "best_for": [
                "private long-context reasoning",
                "architecture review",
                "sensitive local analysis",
                "65k-token context tasks",
            ],
            "tradeoffs": [
                "very large Q4 model with slow CPU-first generation",
                "keep warmed when latency matters",
            ],
        },
    }

    recommendations = {}
    for key, profile in profiles.items():
        suite = profile["benchmark_suite"]
        group = by_suite.get(suite) or {}
        status = benchmark_recommendation_status(group, benchmark_float(profile.get("target_tps")))
        recommendations[key] = {
            **profile,
            "status": status,
            "freshness_status": group.get("freshness_status") or "unmeasured",
            "latest_age_seconds": group.get("latest_age_seconds"),
            "benchmark": group,
            "recommendation": (
                "Use now for its target use cases"
                if status == "ready"
                else "Usable but below the local latency target; collect more samples and prefer warmed routes"
                if status == "below_latency_target"
                else "Benchmark data is stale; refresh this suite before relying on it for route selection"
                if status == "stale_benchmark"
                else "Run this benchmark suite before relying on it for route selection"
                if status == "unmeasured"
                else "Do not rely on this route until benchmark failures are fixed"
            ),
        }

    ranked_benchmark_suites = []
    for suite, group in by_suite.items():
        score = (
            benchmark_float(group.get("pass_rate")) * 1000
            + min(benchmark_float(group.get("best_tps")), 250.0)
            - min(benchmark_float(group.get("avg_elapsed_seconds")), 1000.0) / 100
        )
        ranked_benchmark_suites.append(
            {
                "suite": suite,
                "score": round(score, 3),
                "status": benchmark_recommendation_status(group),
                "count": group.get("count", 0),
                "pass_rate": group.get("pass_rate", 0.0),
                "freshness_status": group.get("freshness_status") or "unmeasured",
                "latest_age_seconds": group.get("latest_age_seconds"),
                "max_age_seconds": group.get("max_age_seconds"),
                "best_tps": group.get("best_tps", 0.0),
                "avg_elapsed_seconds": group.get("avg_elapsed_seconds", 0.0),
                "latest": group.get("latest"),
                "best": group.get("best"),
            }
        )
    ranked_benchmark_suites.sort(key=lambda item: item["score"], reverse=True)

    return {
        "source": "local-model-route-recommendations",
        "generated_at": now(),
        "profiles": recommendations,
        "ranked_benchmark_suites": ranked_benchmark_suites,
        "unbenchmarked_live_routes": [
            {
                "route": "deep-research-glm52",
                "best_for": ["multi-source cited reports", "private connector-backed research"],
                "verification": "deep_research.* parity smokes",
            },
            {
                "route": "local-agent-glm52",
                "best_for": ["browser actions", "tool use", "desktop/system tasks with approvals"],
                "verification": "local_agent.* and OpenWebUI tool connector smokes",
            },
            {
                "route": "local-instant-gemma4-12b",
                "best_for": ["fast direct everyday replies"],
                "verification": "openwebui.fast_local_instant_smoke and performance envelope",
            },
        ],
        "benchmark_summary": {
            "count": summary.get("count", 0),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "pass_rate": summary.get("pass_rate", 0.0),
            "freshness_status": summary.get("freshness_status") or "unmeasured",
            "stale_suites": summary.get("stale_suites") or [],
            "max_age_seconds": summary.get("max_age_seconds"),
            "latest_age_seconds": summary.get("latest_age_seconds"),
            "best_tps": summary.get("best_tps", 0.0),
            "latest": summary.get("latest"),
        },
        "privacy": {
            "local_only": True,
            "prompt_bodies_excluded": True,
            "content_bodies_excluded": True,
            "derived_from": "local-model-benchmark-summary",
        },
    }


def delete_local_model_benchmark(benchmark_id: str) -> bool:
    path = local_benchmark_path(benchmark_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def local_only_base_url(base_url: str) -> bool:
    parsed = parse.urlparse(base_url or "")
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def benchmark_suite_defaults(suite: str) -> dict:
    suite = (suite or "fast_router").strip().lower().replace("-", "_")
    if suite == "glm_tiny":
        return {
            "suite": "glm_tiny",
            "title": "GLM 5.2 tiny local benchmark",
            "base_url": "http://127.0.0.1:11441/v1",
            "model": "glm52-q4-local",
            "prompt": "Reply with exactly: ok",
            "expected_contains": ["ok"],
            "max_tokens": 4,
            "timeout_seconds": 900,
        }
    if suite == "slopcode_tiny":
        return {
            "suite": "slopcode_tiny",
            "title": "Slopcode/Qwen tiny local benchmark",
            "base_url": "http://127.0.0.1:11438/v1",
            "model": "qwen3.6-35b-a3b:slopcode-cpu-64k",
            "prompt": "Reply with exactly: ok",
            "expected_contains": ["ok"],
            "max_tokens": 4,
            "timeout_seconds": 240,
        }
    return {
        "suite": "fast_router",
        "title": "Fast local auto-router benchmark",
        "base_url": "http://127.0.0.1:18043/v1",
        "model": "local-auto-router",
        "prompt": "Reply exactly: OK",
        "expected_contains": ["OK"],
        "max_tokens": 64,
        "timeout_seconds": 180,
    }


def expected_signals(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:20]
    return [str(value).strip()]


def run_local_model_benchmark(payload: dict) -> dict:
    payload = payload or {}
    suite_defaults = benchmark_suite_defaults(str(payload.get("suite") or "fast_router"))
    suite = str(payload.get("suite") or suite_defaults["suite"]).strip().lower().replace("-", "_")[:80]
    benchmark_id = local_benchmark_id(str(payload.get("id") or f"benchmark-{suite}-{uuid.uuid4().hex[:8]}"))
    if read_local_model_benchmark(benchmark_id):
        raise ValueError("benchmark id already exists")
    title = str(payload.get("title") or suite_defaults["title"]).strip()[:200]
    base_url = normalize_base_url(str(payload.get("base_url") or suite_defaults["base_url"]))
    if not local_only_base_url(base_url):
        raise ValueError("benchmark base_url must be a local loopback HTTP endpoint")
    model = str(payload.get("model") or suite_defaults["model"]).strip()[:200]
    prompt = str(payload.get("prompt") or suite_defaults["prompt"])
    if not prompt.strip():
        raise ValueError("benchmark prompt is required")
    if len(prompt.encode("utf-8")) > 200_000:
        raise ValueError("benchmark prompt exceeds 200 KiB")
    max_tokens = min(max(int(payload.get("max_tokens") or suite_defaults["max_tokens"]), 1), 512)
    timeout_seconds = min(max(int(payload.get("timeout_seconds") or suite_defaults["timeout_seconds"]), 1), REQUEST_TIMEOUT_SECONDS)
    expected = expected_signals(payload.get("expected_contains") or suite_defaults.get("expected_contains"))
    created = now()
    benchmark = {
        "id": benchmark_id,
        "title": title,
        "source": "local-model-benchmark",
        "suite": suite,
        "status": "running",
        "base_url": base_url,
        "model": model,
        "max_tokens": max_tokens,
        "timeout_seconds": timeout_seconds,
        "expected_contains": expected,
        "prompt_chars": len(prompt),
        "prompt_preview": prompt[:400],
        "content_preview": "",
        "created_at": created,
        "started_at": created,
        "finished_at": None,
        "url": f"{PUBLIC_BASE_URL}/local-benchmarks/{benchmark_id}",
        "privacy": {
            "local_only": True,
            "loopback_base_url": True,
            "prompt_preview_only": True,
            "api_key_from_request_body": False,
        },
    }
    write_local_model_benchmark(benchmark)

    request_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": payload.get("temperature", 0),
    }
    started_monotonic = time.monotonic()
    try:
        req = request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "openwebui-local-benchmark/0.1"},
            method="POST",
        )
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
        elapsed = time.monotonic() - started_monotonic
        content = chat_content_from_response(data)
        completion_tokens = completion_tokens_from_response(data, content)
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        missing = [signal for signal in expected if signal.lower() not in content.lower()]
        request_ok = not missing and bool(content.strip())
        benchmark.update(
            {
                "status": "passed" if request_ok else "failed",
                "finished_at": now(),
                "elapsed_seconds": round(elapsed, 3),
                "response_model": data.get("model"),
                "content_preview": re.sub(r"\s+", " ", content).strip()[:500],
                "completion_tokens": completion_tokens,
                "prompt_tokens": usage.get("prompt_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "usage": usage,
                "approx_completion_tps": round(completion_tokens / max(elapsed, 0.001), 3),
                "response_token_per_second": usage.get("response_token/s"),
                "missing_expected": missing,
                "local_auto_router": data.get("local_auto_router") if isinstance(data.get("local_auto_router"), dict) else None,
            }
        )
    except Exception as exc:
        elapsed = time.monotonic() - started_monotonic
        benchmark.update(
            {
                "status": "failed",
                "finished_at": now(),
                "elapsed_seconds": round(elapsed, 3),
                "error": safe_text(exc)[:2000],
                "completion_tokens": 0,
                "approx_completion_tps": 0.0,
            }
        )
    write_local_model_benchmark(benchmark)
    return benchmark


def benchmark_baseline_suites(payload: dict) -> list[str]:
    requested = payload.get("suites") if isinstance(payload.get("suites"), list) else None
    if not requested:
        requested = ["fast_router"]
        if bool(payload.get("include_code")):
            requested.append("slopcode_tiny")
        if bool(payload.get("include_glm")):
            requested.append("glm_tiny")
        if bool(payload.get("include_all")):
            requested = ["fast_router", "slopcode_tiny", "glm_tiny"]

    suites = []
    for value in requested:
        suite = str(value or "").strip().lower().replace("-", "_")
        if suite in {"fast_router", "slopcode_tiny", "glm_tiny"} and suite not in suites:
            suites.append(suite)
    if not suites:
        raise ValueError("at least one supported benchmark suite is required")
    return suites[:6]


def run_local_model_benchmark_baseline(payload: dict) -> dict:
    payload = payload or {}
    suites = benchmark_baseline_suites(payload)
    keep_records = bool(payload.get("keep_records", True))
    baseline_id = local_benchmark_id(str(payload.get("id") or f"baseline-{uuid.uuid4().hex[:8]}"))
    created = now()
    benchmarks = []
    for suite in suites:
        defaults = benchmark_suite_defaults(suite)
        benchmark_payload = {
            "id": f"{baseline_id}-{suite}-{uuid.uuid4().hex[:6]}",
            "title": f"Local route baseline: {defaults['title']}",
            "suite": suite,
            "base_url": defaults["base_url"],
            "model": defaults["model"],
            "prompt": defaults["prompt"],
            "expected_contains": defaults["expected_contains"],
            "max_tokens": defaults["max_tokens"],
            "timeout_seconds": defaults["timeout_seconds"],
            "temperature": payload.get("temperature", 0),
        }
        if isinstance(payload.get("overrides"), dict) and isinstance(payload["overrides"].get(suite), dict):
            benchmark_payload.update(payload["overrides"][suite])
            benchmark_payload["suite"] = suite
        benchmark = run_local_model_benchmark(benchmark_payload)
        benchmark["baseline_id"] = baseline_id
        benchmark["baseline_keep_records"] = keep_records
        benchmark["baseline_created_at"] = created
        write_local_model_benchmark(benchmark)
        benchmarks.append(benchmark)

    deleted_ids = []
    if not keep_records:
        for benchmark in benchmarks:
            if delete_local_model_benchmark(str(benchmark.get("id") or "")):
                deleted_ids.append(benchmark.get("id"))

    return {
        "id": baseline_id,
        "source": "local-model-benchmark-baseline",
        "created_at": created,
        "finished_at": now(),
        "suites": suites,
        "keep_records": keep_records,
        "benchmarks": [benchmark_summary_item(benchmark) for benchmark in benchmarks],
        "deleted_ids": deleted_ids,
        "summary": summarize_local_model_benchmarks(),
        "recommendations": local_model_route_recommendations(),
        "privacy": {
            "local_only": True,
            "loopback_base_urls_only": True,
            "prompt_bodies_excluded_from_response": True,
            "content_bodies_excluded_from_response": True,
        },
    }


def due_loop():
    while True:
        try:
            due = []
            with LOCK:
                tasks = load_tasks()
                current = now()
                for task in tasks.values():
                    if task.enabled and task.next_run_at and task.next_run_at <= current and task.id not in RUNNING:
                        due.append(task.id)
            for task_id in due:
                Thread(target=run_task, args=(task_id,), daemon=True).start()
        except Exception as exc:
            print(f"scheduler loop error: {exc}", flush=True)
        time.sleep(max(1, POLL_SECONDS))


def openapi_schema() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "OpenWebUI Local Scheduled Tasks", "version": "0.1.0"},
        "paths": {
            "/approvals": {
                "get": {
                    "operationId": "list_app_action_approvals",
                    "summary": "List pending or historical app action approvals",
                    "parameters": [{"name": "status", "in": "query", "required": False, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/approvals/{approval_id}": {
                "get": {
                    "operationId": "get_app_action_approval",
                    "summary": "Get one app action approval",
                    "parameters": [{"name": "approval_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/approvals/{approval_id}/approve": {
                "post": {
                    "operationId": "approve_app_action",
                    "summary": "Approve a pending app action",
                    "parameters": [{"name": "approval_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/approvals/{approval_id}/deny": {
                "post": {
                    "operationId": "deny_app_action",
                    "summary": "Deny a pending app action",
                    "parameters": [{"name": "approval_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/tasks": {
                "get": {"operationId": "list_tasks", "summary": "List scheduled tasks", "responses": {"200": {"description": "OK"}}},
                "post": {"operationId": "create_task", "summary": "Create a scheduled task", "responses": {"200": {"description": "OK"}}},
            },
            "/tasks/{task_id}/run": {
                "post": {"operationId": "run_task_now", "summary": "Run a task immediately", "responses": {"200": {"description": "OK"}}}
            },
            "/tasks/{task_id}/runs": {
                "get": {"operationId": "list_task_runs", "summary": "List runs for a task", "responses": {"200": {"description": "OK"}}}
            },
            "/tasks/{task_id}": {
                "delete": {"operationId": "delete_task", "summary": "Delete a task", "responses": {"200": {"description": "OK"}}}
            },
            "/runs/{run_id}": {
                "delete": {"operationId": "delete_run", "summary": "Delete a stored task run", "responses": {"200": {"description": "OK"}}}
            },
            "/pulse/run": {
                "post": {
                    "operationId": "run_pulse_digest",
                    "summary": "Run a proactive Pulse-style digest immediately",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "topics": {"type": "array", "items": {"type": "string"}},
                                        "context": {},
                                        "feedback": {},
                                        "max_cards": {"type": "integer"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/pulse/cards": {
                "get": {"operationId": "list_pulse_digests", "summary": "List Pulse-style digests", "responses": {"200": {"description": "OK"}}}
            },
            "/pulse/cards/{pulse_id}": {
                "get": {
                    "operationId": "get_pulse_digest",
                    "summary": "Get one Pulse-style digest",
                    "parameters": [{"name": "pulse_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "save_pulse_digest",
                    "summary": "Save or unsave one Pulse-style digest",
                    "parameters": [{"name": "pulse_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_pulse_digest",
                    "summary": "Delete one Pulse-style digest",
                    "parameters": [{"name": "pulse_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/local-app/search": {
                "get": {
                    "operationId": "search_local_app_items",
                    "summary": "Search local connector notes, parity catalog items, scheduled tasks, runs, and Pulse digests",
                    "parameters": [
                        {"name": "q", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/catalog": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_catalog",
                    "summary": "Get the local ChatGPT feature and use-case parity catalog",
                    "parameters": [
                        {"name": "q", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/feature-matrix": {
                "get": {
                    "operationId": "get_local_chatgpt_feature_matrix",
                    "summary": "Get local ChatGPT feature-family readiness matrix",
                    "parameters": [
                        {"name": "q", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/runbook": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_runbook",
                    "summary": "Get per-feature OpenWebUI local model and tool runbook",
                    "parameters": [
                        {"name": "q", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/task-recommendations": {
                "get": {
                    "operationId": "recommend_local_chatgpt_task_routes",
                    "summary": "Recommend local OpenWebUI model and tool routes for a ChatGPT-style task",
                    "parameters": [
                        {"name": "q", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/popular-tasks": {
                "get": {
                    "operationId": "get_local_chatgpt_popular_task_routes",
                    "summary": "Get curated popular ChatGPT task coverage mapped to local OpenWebUI routes",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/workflows": {
                "get": {
                    "operationId": "get_local_chatgpt_workflow_recipes",
                    "summary": "Get actionable OpenWebUI workflow recipes for popular ChatGPT-style tasks",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/starter-prompts": {
                "get": {
                    "operationId": "get_local_chatgpt_starter_prompts",
                    "summary": "Get copy-ready starter prompt templates for local OpenWebUI ChatGPT-style workflows",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/playbook": {
                "get": {
                    "operationId": "get_local_chatgpt_action_playbook",
                    "summary": "Get local ChatGPT action playbook with routes, starter commands, capacity, and hosted-boundary fallbacks",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/dashboard": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_dashboard",
                    "summary": "Get compact local ChatGPT parity status, model routes, context, TPS, and remaining gap",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/optional-evidence": {
                "get": {
                    "operationId": "get_local_chatgpt_optional_heavy_evidence",
                    "summary": "Get optional-heavy local parity evidence and opt-in verifier commands",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/gaps": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_gap_report",
                    "summary": "Get current local ChatGPT parity gaps and next actions",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/gap-report": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_gap_report_alias",
                    "summary": "Get current local ChatGPT parity gap report by readable alias",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/gap": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_gap_report_short_alias",
                    "summary": "Get current local ChatGPT parity gap report by short alias",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/improvement-plan": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_improvement_plan",
                    "summary": "Get actionable local ChatGPT parity improvement plan for the remaining gap",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/readiness-checklist": {
                "get": {
                    "operationId": "get_local_chatgpt_readiness_checklist",
                    "summary": "Get objective-tied local ChatGPT readiness checklist",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/audit": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_completion_audit",
                    "summary": "Get local ChatGPT parity completion audit",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/quality-scorecard": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_quality_scorecard",
                    "summary": "Get local ChatGPT quality and route scorecard",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/capacity-plan": {
                "get": {
                    "operationId": "get_local_chatgpt_model_capacity_plan",
                    "summary": "Get local ChatGPT model capacity, context, and TPS plan",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/continuity": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_continuity_report",
                    "summary": "Get local ChatGPT export/import and portability fallback report",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/frontier-boundary": {
                "get": {
                    "operationId": "get_local_chatgpt_frontier_boundary_matrix",
                    "summary": "Get local ChatGPT hosted-frontier boundary matrix",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/source-freshness": {
                "get": {
                    "operationId": "get_local_chatgpt_feature_source_freshness",
                    "summary": "Get local ChatGPT feature source freshness",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/evidence": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_evidence_trace",
                    "summary": "Get local ChatGPT parity evidence trace",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-parity/live-status": {
                "get": {
                    "operationId": "get_local_chatgpt_parity_live_status",
                    "summary": "Get local ChatGPT parity live runtime status",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-app/notes": {
                "get": {
                    "operationId": "list_local_app_notes",
                    "summary": "List notes saved through the local app connector",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "save_local_app_note",
                    "summary": "Create or update a local app connector note",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "content": {"type": "string"},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                    "required": ["content"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-app/notes/{note_id}": {
                "get": {
                    "operationId": "get_local_app_note",
                    "summary": "Get one local app connector note",
                    "parameters": [
                        {"name": "note_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_app_note",
                    "summary": "Delete a local app connector note",
                    "parameters": [
                        {"name": "note_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                }
            },
            "/local-app/connections": {
                "get": {
                    "operationId": "list_local_app_connections",
                    "summary": "List local app connection ledger entries",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_app_connection",
                    "summary": "Create or update a local app connection ledger entry",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "app_name": {"type": "string"},
                                        "provider": {"type": "string"},
                                        "account": {"type": "string"},
                                        "workspace": {"type": "string"},
                                        "permission_mode": {"type": "string"},
                                        "capabilities": {"type": "object"},
                                        "sync_enabled": {"type": "boolean"},
                                        "workspace_enabled": {"type": "boolean"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                    "required": ["app_name"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-app/connections/{connection_id}": {
                "get": {
                    "operationId": "get_local_app_connection",
                    "summary": "Get one local app connection ledger entry",
                    "parameters": [
                        {"name": "connection_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_app_connection",
                    "summary": "Delete one local app connection ledger entry",
                    "parameters": [
                        {"name": "connection_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-app/connections/{connection_id}/permission": {
                "post": {
                    "operationId": "update_local_app_connection_permission",
                    "summary": "Record an approved local app-specific permission preference",
                    "parameters": [
                        {"name": "connection_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "permission_mode": {"type": "string"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                    "required": ["permission_mode"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-app/connections/{connection_id}/disconnect": {
                "post": {
                    "operationId": "disconnect_local_app_connection",
                    "summary": "Record a local-only approved app disconnect without external OAuth revocation",
                    "parameters": [
                        {"name": "connection_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-app/action-controls": {
                "get": {
                    "operationId": "list_local_app_action_controls",
                    "summary": "List local app action-control policies",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_app_action_control",
                    "summary": "Create or update a local app action-control policy with parameter constraints",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "app_name": {"type": "string"},
                                        "provider": {"type": "string"},
                                        "mode": {"type": "string"},
                                        "allowed_actions": {"type": "array", "items": {"type": "string"}},
                                        "blocked_actions": {"type": "array", "items": {"type": "string"}},
                                        "new_actions_policy": {"type": "string"},
                                        "parameter_constraints": {"type": "object"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                    "required": ["app_name"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-app/action-controls/{control_id}": {
                "get": {
                    "operationId": "get_local_app_action_control",
                    "summary": "Get one local app action-control policy",
                    "parameters": [
                        {"name": "control_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_app_action_control",
                    "summary": "Delete one local app action-control policy",
                    "parameters": [
                        {"name": "control_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-app/action-controls/{control_id}/evaluate": {
                "post": {
                    "operationId": "evaluate_local_app_action_control",
                    "summary": "Evaluate a proposed local app action against local action controls without executing it",
                    "parameters": [
                        {"name": "control_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "action_name": {"type": "string"},
                                        "action_type": {"type": "string"},
                                        "parameters": {"type": "object"},
                                    },
                                    "required": ["action_name"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/local-app/call-logs": {
                "get": {
                    "operationId": "list_local_app_call_logs",
                    "summary": "List local app-call audit records",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_app_call_log",
                    "summary": "Create or update a redacted local app-call audit record",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "app_name": {"type": "string"},
                                        "provider": {"type": "string"},
                                        "action_name": {"type": "string"},
                                        "action_type": {"type": "string"},
                                        "status": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                        "control_id": {"type": "string"},
                                        "evaluation": {"type": "object"},
                                        "parameters": {"type": "object"},
                                        "prompt_summary": {"type": "string"},
                                        "result_summary": {"type": "string"},
                                        "approval_mode": {"type": "string"},
                                    },
                                    "required": ["app_name", "action_name"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-app/call-logs/{log_id}": {
                "get": {
                    "operationId": "get_local_app_call_log",
                    "summary": "Get one local app-call audit record",
                    "parameters": [
                        {"name": "log_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_app_call_log",
                    "summary": "Delete one local app-call audit record",
                    "parameters": [
                        {"name": "log_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-email/drafts": {
                "get": {
                    "operationId": "list_local_email_drafts",
                    "summary": "List local approval-gated email drafts",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_email_draft",
                    "summary": "Create or update a local email draft without external delivery",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "provider": {"type": "string"},
                                        "from": {"type": "string"},
                                        "to": {"type": "array", "items": {"type": "string"}},
                                        "cc": {"type": "array", "items": {"type": "string"}},
                                        "bcc": {"type": "array", "items": {"type": "string"}},
                                        "subject": {"type": "string"},
                                        "body": {"type": "string"},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                    "required": ["to", "subject", "body"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-email/drafts/{draft_id}": {
                "get": {
                    "operationId": "get_local_email_draft",
                    "summary": "Get one local email draft",
                    "parameters": [
                        {"name": "draft_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_email_draft",
                    "summary": "Delete one local email draft",
                    "parameters": [
                        {"name": "draft_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-email/drafts/{draft_id}/send": {
                "post": {
                    "operationId": "send_local_email_draft",
                    "summary": "Record a local-only approved send for an email draft without external delivery",
                    "parameters": [
                        {"name": "draft_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-security/sessions": {
                "get": {
                    "operationId": "list_local_security_sessions",
                    "summary": "List local active-session ledger entries",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_security_session",
                    "summary": "Create or update a local security-session ledger entry",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "app": {"type": "string"},
                                        "device": {"type": "string"},
                                        "browser": {"type": "string"},
                                        "location": {"type": "string"},
                                        "trusted_device": {"type": "boolean"},
                                        "current_session": {"type": "boolean"},
                                        "sign_in_at": {"type": "string"},
                                        "status": {"type": "string"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-security/sessions/logout-all": {
                "post": {
                    "operationId": "logout_all_local_security_sessions",
                    "summary": "Record a local-only approved logout-all action for local session ledger entries",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-security/sessions/{session_id}": {
                "get": {
                    "operationId": "get_local_security_session",
                    "summary": "Get one local active-session ledger entry",
                    "parameters": [
                        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_security_session",
                    "summary": "Delete one local active-session ledger entry",
                    "parameters": [
                        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-security/sessions/{session_id}/logout": {
                "post": {
                    "operationId": "logout_local_security_session",
                    "summary": "Record a local-only approved logout action for one local session ledger entry",
                    "parameters": [
                        {"name": "session_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-pronunciation/guides": {
                "get": {
                    "operationId": "list_local_pronunciation_guides",
                    "summary": "List local pronunciation guides with text guidance and WAV fallback audio",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_pronunciation_guide",
                    "summary": "Create local pronunciation text guidance and a local WAV audio fallback",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "word": {"type": "string"},
                                        "text": {"type": "string"},
                                        "language": {"type": "string"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                    "required": ["word"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-pronunciation/guides/{guide_id}": {
                "get": {
                    "operationId": "get_local_pronunciation_guide",
                    "summary": "Get one local pronunciation guide",
                    "parameters": [
                        {"name": "guide_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_pronunciation_guide",
                    "summary": "Delete one local pronunciation guide and generated WAV audio",
                    "parameters": [
                        {"name": "guide_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-pronunciation/audio/{guide_id}.wav": {
                "get": {
                    "operationId": "get_local_pronunciation_audio",
                    "summary": "Download local WAV pronunciation fallback audio",
                    "parameters": [
                        {"name": "guide_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "WAV audio"}},
                }
            },
            "/local-sports/briefings": {
                "get": {
                    "operationId": "list_local_sports_briefings",
                    "summary": "List local sports and current-event source briefings",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_sports_briefing",
                    "summary": "Create a local sports/current-events briefing from local SearXNG sources",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "topic": {"type": "string"},
                                        "query": {"type": "string"},
                                        "sport": {"type": "string"},
                                        "competition": {"type": "string"},
                                        "max_sources": {"type": "integer"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                    "required": ["topic"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-sports/briefings/{briefing_id}": {
                "get": {
                    "operationId": "get_local_sports_briefing",
                    "summary": "Get one local sports/current-events briefing",
                    "parameters": [
                        {"name": "briefing_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_sports_briefing",
                    "summary": "Delete one local sports/current-events briefing",
                    "parameters": [
                        {"name": "briefing_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-sites": {
                "get": {
                    "operationId": "list_local_sites",
                    "summary": "List locally published sites",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "publish_local_site",
                    "summary": "Publish or update a local static HTML site",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "slug": {"type": "string"},
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                        "html": {"type": "string"},
                                        "content": {"type": "string"},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-sites/{site_id}": {
                "get": {
                    "operationId": "get_local_site",
                    "summary": "Get one locally published site metadata record",
                    "parameters": [
                        {"name": "site_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_site",
                    "summary": "Delete a locally published site",
                    "parameters": [
                        {"name": "site_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-sheets": {
                "get": {
                    "operationId": "list_local_sheets",
                    "summary": "List locally stored spreadsheet workbooks",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_sheet_workbook",
                    "summary": "Create or replace a local spreadsheet workbook",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                        "rows": {"type": "array", "items": {"type": "array", "items": {}}},
                                        "sheet_name": {"type": "string"},
                                        "sheets": {},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-sheets/{workbook_id}": {
                "get": {
                    "operationId": "get_local_sheet_workbook",
                    "summary": "Get a local spreadsheet workbook with rows",
                    "parameters": [
                        {"name": "workbook_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_sheet_workbook",
                    "summary": "Delete a local spreadsheet workbook",
                    "parameters": [
                        {"name": "workbook_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-sheets/{workbook_id}/explain": {
                "post": {
                    "operationId": "explain_local_sheet_workbook",
                    "summary": "Explain a local spreadsheet workbook and summarize matching rows",
                    "parameters": [
                        {"name": "workbook_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"question": {"type": "string"}},
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-sheets/{workbook_id}/cells": {
                "post": {
                    "operationId": "update_local_sheet_cells",
                    "summary": "Update cells in a local spreadsheet workbook",
                    "parameters": [
                        {"name": "workbook_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "sheet": {"type": "string"},
                                        "updates": {"type": "array", "items": {"type": "object"}},
                                        "cell": {"type": "string"},
                                        "row": {"type": "integer"},
                                        "column": {},
                                        "value": {},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                }
            },
            "/local-goals": {
                "get": {
                    "operationId": "list_local_goals",
                    "summary": "List local Codex-style goals with objective, success criteria, and evidence",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_goal",
                    "summary": "Create or update a local goal with success criteria",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "objective": {"type": "string"},
                                        "success_criteria": {"type": "array", "items": {"type": "string"}},
                                        "status": {"type": "string"},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                    "required": ["objective", "success_criteria"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-goals/{goal_id}": {
                "get": {
                    "operationId": "get_local_goal",
                    "summary": "Get one local goal record",
                    "parameters": [
                        {"name": "goal_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_goal",
                    "summary": "Delete a local goal record",
                    "parameters": [
                        {"name": "goal_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-goals/{goal_id}/progress": {
                "post": {
                    "operationId": "update_local_goal_progress",
                    "summary": "Add local evidence against a goal's success criteria",
                    "parameters": [
                        {"name": "goal_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "evidence": {"type": "array", "items": {"type": "object"}},
                                        "status": {"type": "string"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                }
            },
            "/local-goals/{goal_id}/evaluate": {
                "get": {
                    "operationId": "evaluate_local_goal",
                    "summary": "Evaluate whether local goal success criteria have evidence",
                    "parameters": [
                        {"name": "goal_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-benchmarks": {
                "get": {
                    "operationId": "list_local_model_benchmarks",
                    "summary": "List local model benchmark runs",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "run_local_model_benchmark",
                    "summary": "Run a bounded local-only OpenAI-compatible model benchmark and store the result",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "suite": {"type": "string"},
                                        "base_url": {"type": "string"},
                                        "model": {"type": "string"},
                                        "prompt": {"type": "string"},
                                        "expected_contains": {},
                                        "max_tokens": {"type": "integer"},
                                        "timeout_seconds": {"type": "integer"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-benchmarks/summary": {
                "get": {
                    "operationId": "summarize_local_model_benchmarks",
                    "summary": "Summarize stored local model benchmark runs by suite and model",
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/local-benchmarks/baseline": {
                "post": {
                    "operationId": "run_local_model_benchmark_baseline",
                    "summary": "Run a local route benchmark baseline across one or more supported local model suites",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "suites": {"type": "array", "items": {"type": "string"}},
                                        "include_code": {"type": "boolean"},
                                        "include_glm": {"type": "boolean"},
                                        "include_all": {"type": "boolean"},
                                        "keep_records": {"type": "boolean"},
                                        "overrides": {},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-benchmarks/recommendations": {
                "get": {
                    "operationId": "recommend_local_model_routes",
                    "summary": "Recommend local model routes from stored benchmark summaries",
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/local-benchmarks/{benchmark_id}": {
                "get": {
                    "operationId": "get_local_model_benchmark",
                    "summary": "Get one local model benchmark run",
                    "parameters": [
                        {"name": "benchmark_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_model_benchmark",
                    "summary": "Delete one local model benchmark run",
                    "parameters": [
                        {"name": "benchmark_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-code/workspaces": {
                "get": {
                    "operationId": "list_local_code_workspaces",
                    "summary": "List local Codex-style code workspaces",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "create_local_code_workspace",
                    "summary": "Create or replace a local code workspace",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                        "files": {},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-code/workspaces/import": {
                "post": {
                    "operationId": "import_local_code_workspace_package",
                    "summary": "Import a local code workspace JSON package as a new additive workspace",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "package": {"type": "object"},
                                        "id": {"type": "string"},
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                }
            },
            "/local-code/workspaces/{workspace_id}": {
                "get": {
                    "operationId": "get_local_code_workspace",
                    "summary": "Get a local code workspace with files",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_code_workspace",
                    "summary": "Delete a local code workspace",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-code/workspaces/{workspace_id}/export": {
                "post": {
                    "operationId": "export_local_code_workspace_package",
                    "summary": "Export a local code workspace JSON package with a Git patch bundle",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "include_history": {"type": "boolean"},
                                        "include_command_output": {"type": "boolean"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-code/git-worktrees": {
                "get": {
                    "operationId": "list_local_code_git_worktrees",
                    "summary": "List isolated local Git worktrees created from code workspaces",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-code/git-worktrees/{worktree_id}": {
                "get": {
                    "operationId": "get_local_code_git_worktree",
                    "summary": "Get isolated local Git worktree metadata",
                    "parameters": [
                        {"name": "worktree_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "delete": {
                    "operationId": "delete_local_code_git_worktree",
                    "summary": "Delete an isolated local Git worktree",
                    "parameters": [
                        {"name": "worktree_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "approval_mode", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "approval_id", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                },
            },
            "/local-code/git-worktrees/{worktree_id}/github-pr": {
                "post": {
                    "operationId": "prepare_local_code_github_pr",
                    "summary": "Prepare a GitHub pull request payload from a local Git worktree, with approval-gated publish when configured",
                    "parameters": [
                        {"name": "worktree_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "body": {"type": "string"},
                                        "base": {"type": "string"},
                                        "head": {"type": "string"},
                                        "repository": {"type": "string"},
                                        "draft": {"type": "boolean"},
                                        "publish": {"type": "boolean"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                }
            },
            "/local-code/workspaces/{workspace_id}/git-worktree": {
                "post": {
                    "operationId": "create_local_code_git_worktree",
                    "summary": "Create an isolated local Git worktree from a code workspace and its current patch",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "branch": {"type": "string"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                }
            },
            "/local-code/workspaces/{workspace_id}/analyze": {
                "post": {
                    "operationId": "analyze_local_code_workspace",
                    "summary": "Analyze files, symbols, TODOs, and local-only privacy posture for a code workspace",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-code/workspaces/{workspace_id}/checks": {
                "post": {
                    "operationId": "run_local_code_workspace_checks",
                    "summary": "Run local static checks over a code workspace without executing arbitrary project code",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-code/workspaces/{workspace_id}/command": {
                "post": {
                    "operationId": "run_local_code_workspace_command",
                    "summary": "Run an explicitly approved no-shell command inside a temporary local code workspace copy",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "command": {"type": "array", "items": {"type": "string"}},
                                        "timeout_seconds": {"type": "integer"},
                                        "keep_run_dir": {"type": "boolean"},
                                        "approval_id": {"type": "string"},
                                    },
                                    "required": ["command"],
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                }
            },
            "/local-code/workspaces/{workspace_id}/review": {
                "post": {
                    "operationId": "prepare_local_code_workspace_review",
                    "summary": "Prepare a local PR-style review package with diff, changed files, and verification notes",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "base_branch": {"type": "string"},
                                        "target_branch": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/local-code/workspaces/{workspace_id}/patch": {
                "post": {
                    "operationId": "apply_local_code_workspace_patch",
                    "summary": "Apply a reviewable local code patch and return clean diffs",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "summary": {"type": "string"},
                                        "patches": {"type": "array", "items": {"type": "object"}},
                                        "path": {"type": "string"},
                                        "find": {"type": "string"},
                                        "replace": {"type": "string"},
                                        "replace_all": {"type": "boolean"},
                                        "approval_mode": {"type": "string"},
                                        "approval_id": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}, "202": {"description": "Approval required"}},
                }
            },
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "openwebui-local-scheduler/0.1"

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), fmt % args), flush=True)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = parse.urlparse(self.path)
        path = parsed.path
        query = parse.parse_qs(parsed.query)
        if path == "/health":
            with LOCK:
                tasks = load_tasks()
            return send_json(
                self,
                200,
                {
                    "status": "ok",
                    "tasks": len(tasks),
                    "pulse_digests": len(list_pulse_digests()),
                    "approvals": len(list_approvals()),
                    "local_app_notes": len(list_local_app_notes()),
                    "local_app_connections": len(list_local_app_connections()),
                    "local_app_action_controls": len(list_local_app_action_controls()),
                    "local_app_call_logs": len(list_local_app_call_logs()),
                    "local_email_drafts": len(list_local_email_drafts()),
                    "local_security_sessions": len(list_local_security_sessions()),
                    "local_pronunciation_guides": len(list_local_pronunciations()),
                    "local_sports_briefings": len(list_local_sports_briefings()),
                    "local_sites": len(list_local_sites()),
                    "local_sheets": len(list_local_sheets()),
                    "local_code_workspaces": len(list_local_code_workspaces()),
                    "local_code_git_worktrees": len(list_local_code_git_worktrees()),
                    "local_model_benchmarks": len(list_local_model_benchmarks()),
                    "local_goals": len(list_local_goals()),
                    "running": len(RUNNING),
                },
            )
        if path == "/openapi.json":
            return send_json(self, 200, openapi_schema())
        if path == "/approvals":
            status_filter = (query.get("status") or [""])[0] or None
            return send_json(self, 200, {"data": list_approvals(status_filter)})
        match = re.match(r"^/approvals/([^/]+)$", path)
        if match:
            approval = read_approval(match.group(1))
            if not approval:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"approval": approval})
        if path == "/tasks":
            with LOCK:
                tasks = [asdict(task) for task in load_tasks().values()]
            tasks.sort(key=lambda item: item.get("created_at", 0), reverse=True)
            return send_json(self, 200, {"data": tasks})
        if path == "/runs":
            return send_json(self, 200, {"data": list_runs()})
        if path == "/pulse/cards":
            return send_json(self, 200, {"data": list_pulse_digests()})
        if path == "/local-app/search":
            search_query = (query.get("q") or [""])[0]
            limit = int((query.get("limit") or ["8"])[0] or "8")
            return send_json(self, 200, {"data": local_app_search(search_query, limit)})
        if path == "/local-parity/catalog":
            search_query = (query.get("q") or [""])[0]
            limit = int((query.get("limit") or ["100"])[0] or "100")
            return send_json(self, 200, {"catalog": local_parity_catalog(search_query, limit)})
        if path == "/local-parity/feature-matrix":
            search_query = (query.get("q") or [""])[0]
            limit = int((query.get("limit") or ["100"])[0] or "100")
            return send_json(self, 200, {"matrix": local_parity_feature_matrix(search_query, limit)})
        if path == "/local-parity/runbook":
            search_query = (query.get("q") or [""])[0]
            limit = int((query.get("limit") or ["100"])[0] or "100")
            return send_json(self, 200, {"runbook": local_parity_runbook(search_query, limit)})
        if path == "/local-parity/task-recommendations":
            search_query = (query.get("q") or [""])[0]
            limit = int((query.get("limit") or ["8"])[0] or "8")
            return send_json(self, 200, {"recommendations": local_parity_task_recommendations(search_query, limit)})
        if path == "/local-parity/popular-tasks":
            return send_json(self, 200, {"popular_tasks": local_parity_popular_task_routes()})
        if path == "/local-parity/workflows":
            return send_json(self, 200, {"workflows": local_parity_workflow_recipes()})
        if path == "/local-parity/starter-prompts":
            return send_json(self, 200, {"starter_prompts": local_parity_starter_prompts()})
        if path == "/local-parity/playbook":
            return send_json(self, 200, {"playbook": local_parity_action_playbook()})
        if path == "/local-parity/dashboard":
            return send_json(self, 200, {"dashboard": local_parity_dashboard()})
        if path in {"/local-parity", "/local-parity/", "/local-parity/index.html"}:
            return send_html(self, 200, local_parity_dashboard_html())
        if path == "/local-parity/starter-prompts.html":
            return send_html(self, 200, local_parity_starter_prompts_html())
        if path == "/local-parity/feature-map.html":
            return send_html(self, 200, local_parity_feature_map_html())
        if path == "/local-parity/runbook.html":
            return send_html(self, 200, local_parity_runbook_html())
        if path == "/local-parity/route-map.html":
            return send_html(self, 200, local_parity_route_map_html())
        if path == "/local-parity/playbook.html":
            return send_html(self, 200, local_parity_action_playbook_html())
        if path == "/local-parity/audit.html":
            return send_html(self, 200, local_parity_audit_html())
        if path == "/local-parity/optional-evidence.html":
            return send_html(self, 200, local_parity_optional_evidence_html())
        if path == "/local-parity/optional-evidence":
            return send_json(self, 200, {"optional_evidence": local_parity_optional_heavy_evidence()})
        if path == "/local-parity/gap-report.html":
            return send_html(self, 200, local_parity_gap_report_html())
        if path in {"/local-parity/gaps", "/local-parity/gap-report", "/local-parity/gap"}:
            return send_json(self, 200, {"gap_report": local_parity_gap_report()})
        if path == "/local-parity/improvement-plan.html":
            return send_html(self, 200, local_parity_improvement_plan_html())
        if path == "/local-parity/improvement-plan":
            return send_json(self, 200, {"improvement_plan": local_parity_improvement_plan()})
        if path == "/local-parity/readiness-checklist.html":
            return send_html(self, 200, local_parity_readiness_checklist_html())
        if path == "/local-parity/readiness-checklist":
            return send_json(self, 200, {"readiness": local_parity_readiness_checklist()})
        if path == "/local-parity/audit":
            return send_json(self, 200, {"audit": local_parity_completion_audit()})
        if path == "/local-parity/quality-scorecard":
            return send_json(self, 200, {"scorecard": local_parity_quality_scorecard()})
        if path == "/local-parity/quality-scorecard.html":
            return send_html(self, 200, local_parity_quality_scorecard_html())
        if path == "/local-parity/capacity-plan.html":
            return send_html(self, 200, local_parity_capacity_plan_html())
        if path == "/local-parity/capacity-plan":
            return send_json(self, 200, {"capacity_plan": local_parity_capacity_plan()})
        if path == "/local-parity/continuity.html":
            return send_html(self, 200, local_parity_continuity_html())
        if path == "/local-parity/continuity":
            return send_json(self, 200, {"continuity": local_parity_continuity_report()})
        if path == "/local-parity/frontier-boundary.html":
            return send_html(self, 200, local_parity_frontier_boundary_html())
        if path == "/local-parity/frontier-boundary":
            return send_json(self, 200, {"frontier_boundary": local_parity_frontier_boundary_matrix()})
        if path == "/local-parity/source-freshness.html":
            return send_html(self, 200, local_parity_source_freshness_html())
        if path == "/local-parity/source-freshness":
            return send_json(self, 200, {"freshness": local_parity_source_freshness()})
        if path == "/local-parity/evidence":
            return send_json(self, 200, {"evidence": local_parity_evidence_trace()})
        if path == "/local-parity/live-status.html":
            return send_html(self, 200, local_parity_live_status_html())
        if path == "/local-parity/live-status":
            return send_json(self, 200, {"live_status": local_parity_live_status()})
        if path == "/local-app/notes":
            return send_json(self, 200, {"data": list_local_app_notes()})
        match = re.match(r"^/local-app/notes/([^/]+)$", path)
        if match:
            note = read_local_app_note(match.group(1))
            if not note:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"note": note})
        if path == "/local-app/connections":
            return send_json(self, 200, {"data": list_local_app_connections()})
        match = re.match(r"^/local-app/connections/([^/]+)$", path)
        if match:
            connection = read_local_app_connection(match.group(1))
            if not connection:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"connection": connection})
        if path == "/local-app/action-controls":
            return send_json(self, 200, {"data": list_local_app_action_controls()})
        match = re.match(r"^/local-app/action-controls/([^/]+)$", path)
        if match:
            control = read_local_app_action_control(match.group(1))
            if not control:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"control": control})
        if path == "/local-app/call-logs":
            return send_json(self, 200, {"data": list_local_app_call_logs()})
        match = re.match(r"^/local-app/call-logs/([^/]+)$", path)
        if match:
            call_log = read_local_app_call_log(match.group(1))
            if not call_log:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"call_log": call_log})
        if path == "/local-email/drafts":
            return send_json(self, 200, {"data": list_local_email_drafts()})
        match = re.match(r"^/local-email/drafts/([^/]+)$", path)
        if match:
            draft = read_local_email_draft(match.group(1))
            if not draft:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"draft": draft})
        if path == "/local-security/sessions":
            return send_json(self, 200, {"data": list_local_security_sessions()})
        match = re.match(r"^/local-security/sessions/([^/]+)$", path)
        if match:
            session = read_local_security_session(match.group(1))
            if not session:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"session": session})
        if path == "/local-pronunciation/guides":
            return send_json(self, 200, {"data": list_local_pronunciations()})
        match = re.match(r"^/local-pronunciation/guides/([^/]+)$", path)
        if match:
            guide = read_local_pronunciation(match.group(1))
            if not guide:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"guide": guide})
        match = re.match(r"^/local-pronunciation/audio/([^/]+)\.wav$", path)
        if match:
            audio_path = local_pronunciation_audio_path(match.group(1))
            if not audio_path.exists():
                return send_json(self, 404, {"error": "not found"})
            return send_bytes(self, 200, audio_path.read_bytes(), "audio/wav")
        if path == "/local-sports/briefings":
            return send_json(self, 200, {"data": list_local_sports_briefings()})
        match = re.match(r"^/local-sports/briefings/([^/]+)$", path)
        if match:
            briefing = read_local_sports_briefing(match.group(1))
            if not briefing:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"briefing": briefing})
        if path == "/local-sites":
            return send_json(self, 200, {"data": list_local_sites()})
        match = re.match(r"^/local-sites/([^/]+)/index\.html$", path)
        if match:
            index_path = local_site_index_path(match.group(1))
            if not index_path.exists():
                return send_json(self, 404, {"error": "not found"})
            return send_html(self, 200, index_path.read_text(encoding="utf-8"))
        match = re.match(r"^/local-sites/([^/]+)$", path)
        if match:
            site = read_local_site(match.group(1))
            if not site:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"site": site})
        if path == "/local-sheets":
            return send_json(self, 200, {"data": list_local_sheets()})
        match = re.match(r"^/local-sheets/([^/]+)$", path)
        if match:
            workbook = read_local_sheet(match.group(1))
            if not workbook:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"workbook": workbook})
        if path == "/local-code/workspaces":
            return send_json(self, 200, {"data": list_local_code_workspaces()})
        if path == "/local-code/git-worktrees":
            return send_json(self, 200, {"data": list_local_code_git_worktrees()})
        match = re.match(r"^/local-code/git-worktrees/([^/]+)$", path)
        if match:
            worktree = read_local_code_git_worktree(match.group(1))
            if not worktree:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"git_worktree": worktree})
        if path == "/local-goals":
            return send_json(self, 200, {"data": list_local_goals()})
        match = re.match(r"^/local-goals/([^/]+)/evaluate$", path)
        if match:
            goal = read_local_goal(match.group(1))
            if not goal:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"evaluation": local_goal_evaluation(goal)})
        match = re.match(r"^/local-goals/([^/]+)$", path)
        if match:
            goal = read_local_goal(match.group(1))
            if not goal:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"goal": goal})
        if path == "/local-benchmarks":
            return send_json(self, 200, {"data": list_local_model_benchmarks()})
        if path == "/local-benchmarks/summary":
            return send_json(self, 200, {"summary": summarize_local_model_benchmarks()})
        if path == "/local-benchmarks/recommendations":
            return send_json(self, 200, {"recommendations": local_model_route_recommendations()})
        match = re.match(r"^/local-benchmarks/([^/]+)$", path)
        if match:
            benchmark = read_local_model_benchmark(match.group(1))
            if not benchmark:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"benchmark": benchmark})
        match = re.match(r"^/local-code/workspaces/([^/]+)$", path)
        if match:
            workspace = read_local_code_workspace(match.group(1))
            if not workspace:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"workspace": workspace})
        match = re.match(r"^/pulse/cards/([^/]+)$", path)
        if match:
            file_path = PULSE_DIR / f"{match.group(1)}.json"
            if not file_path.exists():
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, json.loads(file_path.read_text(encoding="utf-8")))
        match = re.match(r"^/tasks/([^/]+)/runs$", path)
        if match:
            return send_json(self, 200, {"data": list_runs(match.group(1))})
        match = re.match(r"^/runs/([^/]+)$", path)
        if match:
            file_path = RUNS_DIR / f"{match.group(1)}.json"
            if not file_path.exists():
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, json.loads(file_path.read_text(encoding="utf-8")))
        return send_json(self, 404, {"error": "not found"})

    def do_POST(self):
        path = parse.urlparse(self.path).path
        try:
            match = re.match(r"^/approvals/([^/]+)/(approve|deny)$", path)
            if match:
                approval_id, decision = match.groups()
                approval = read_approval(approval_id)
                if not approval:
                    return send_json(self, 404, {"error": "not found"})
                if approval.get("status") != "pending":
                    return send_json(self, 400, {"error": f"approval is {approval.get('status')}"})
                approval["status"] = "approved" if decision == "approve" else "denied"
                approval["approved_at" if decision == "approve" else "denied_at"] = now()
                approval["updated_at"] = now()
                write_approval(approval)
                return send_json(self, 200, {"approval": approval})

            if path == "/pulse/run":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="run_pulse_digest",
                    summary=str(payload.get("title") or "Run Pulse-style digest"),
                    payload=payload,
                    important=True,
                ):
                    return
                digest = create_pulse_digest(payload)
                return send_json(self, 200, {"pulse": digest})

            match = re.match(r"^/pulse/cards/([^/]+)$", path)
            if match:
                pulse_id = match.group(1)
                file_path = PULSE_DIR / f"{pulse_id}.json"
                if not file_path.exists():
                    return send_json(self, 404, {"error": "not found"})
                digest = json.loads(file_path.read_text(encoding="utf-8"))
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="save_pulse_digest",
                    summary=f"Save Pulse-style digest {pulse_id}",
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                digest["saved"] = bool(payload.get("saved", True))
                digest["updated_at"] = now()
                write_pulse_digest(digest)
                return send_json(self, 200, {"pulse": digest})

            if path == "/tasks":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_task",
                    summary=str(payload.get("title") or "Create scheduled task"),
                    payload=payload,
                    important=True,
                ):
                    return
                task = create_task(payload)
                with LOCK:
                    tasks = load_tasks()
                    tasks[task.id] = task
                    save_tasks(tasks)
                return send_json(self, 200, {"task": asdict(task)})

            if path == "/local-app/notes":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="save_local_app_note",
                    summary=str(payload.get("title") or "Save local app connector note"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                note = create_or_update_local_app_note(payload)
                return send_json(self, 200, {"note": note})

            if path == "/local-app/connections":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_app_connection",
                    summary=str(payload.get("app_name") or payload.get("name") or "Create local app connection"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                connection = create_or_update_local_app_connection(payload)
                return send_json(self, 200, {"connection": connection})

            match = re.match(r"^/local-app/connections/([^/]+)/permission$", path)
            if match:
                connection_id = match.group(1)
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="update_local_app_connection_permission",
                    summary=f"Update local app connection permission {connection_id}",
                    payload=payload,
                    mutation=True,
                    important=True,
                ):
                    return
                try:
                    connection = update_local_app_connection_permission(connection_id, payload)
                except FileNotFoundError:
                    return send_json(self, 404, {"error": "not found"})
                return send_json(self, 200, {"connection": connection})

            match = re.match(r"^/local-app/connections/([^/]+)/disconnect$", path)
            if match:
                connection_id = match.group(1)
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="disconnect_local_app_connection",
                    summary=f"Disconnect local app connection {connection_id}",
                    payload=payload,
                    mutation=True,
                    important=True,
                ):
                    return
                try:
                    connection = disconnect_local_app_connection(connection_id, payload)
                except FileNotFoundError:
                    return send_json(self, 404, {"error": "not found"})
                return send_json(self, 200, {"connection": connection})

            if path == "/local-app/action-controls":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_app_action_control",
                    summary=str(payload.get("title") or payload.get("app_name") or "Create local app action control"),
                    payload=payload,
                    mutation=True,
                    important=True,
                ):
                    return
                control = create_or_update_local_app_action_control(payload)
                return send_json(self, 200, {"control": control})

            match = re.match(r"^/local-app/action-controls/([^/]+)/evaluate$", path)
            if match:
                control_id = match.group(1)
                payload = read_json(self)
                try:
                    evaluation = evaluate_local_app_action_control(control_id, payload)
                except FileNotFoundError:
                    return send_json(self, 404, {"error": "not found"})
                return send_json(self, 200, {"evaluation": evaluation})

            if path == "/local-app/call-logs":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_app_call_log",
                    summary=str(payload.get("title") or payload.get("action_name") or "Create local app call log"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                call_log = create_or_update_local_app_call_log(payload)
                return send_json(self, 200, {"call_log": call_log})

            if path == "/local-email/drafts":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_email_draft",
                    summary=str(payload.get("subject") or payload.get("title") or "Create local email draft"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                draft = create_or_update_local_email_draft(payload)
                return send_json(self, 200, {"draft": draft})

            match = re.match(r"^/local-email/drafts/([^/]+)/send$", path)
            if match:
                draft_id = match.group(1)
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="send_local_email_draft",
                    summary=f"Send local email draft {draft_id}",
                    payload=payload,
                    mutation=True,
                    important=True,
                ):
                    return
                try:
                    draft = send_local_email_draft(draft_id, payload)
                except FileNotFoundError:
                    return send_json(self, 404, {"error": "not found"})
                return send_json(self, 200, {"draft": draft})

            if path == "/local-security/sessions":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_security_session",
                    summary=str(payload.get("title") or payload.get("device") or "Create local security session"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                session = create_or_update_local_security_session(payload)
                return send_json(self, 200, {"session": session})

            if path == "/local-security/sessions/logout-all":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="logout_all_local_security_sessions",
                    summary="Log out all local security-session ledger entries",
                    payload=payload,
                    mutation=True,
                    important=True,
                ):
                    return
                result = logout_all_local_security_sessions(payload)
                return send_json(self, 200, {"logout": result})

            match = re.match(r"^/local-security/sessions/([^/]+)/logout$", path)
            if match:
                session_id = match.group(1)
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="logout_local_security_session",
                    summary=f"Log out local security session {session_id}",
                    payload=payload,
                    mutation=True,
                    important=True,
                ):
                    return
                try:
                    session = logout_local_security_session(session_id, payload)
                except FileNotFoundError:
                    return send_json(self, 404, {"error": "not found"})
                return send_json(self, 200, {"session": session})

            if path == "/local-pronunciation/guides":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_pronunciation_guide",
                    summary=str(payload.get("title") or payload.get("word") or "Create local pronunciation guide"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                guide = create_local_pronunciation(payload)
                return send_json(self, 200, {"guide": guide})

            if path == "/local-sports/briefings":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_sports_briefing",
                    summary=str(payload.get("title") or payload.get("topic") or "Create local sports briefing"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                briefing = create_local_sports_briefing(payload)
                return send_json(self, 200, {"briefing": briefing})

            if path == "/local-sites":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="publish_local_site",
                    summary=str(payload.get("title") or "Publish local site"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                site = create_or_update_local_site(payload)
                return send_json(self, 200, {"site": site})

            if path == "/local-sheets":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_sheet_workbook",
                    summary=str(payload.get("title") or "Create local spreadsheet workbook"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                workbook = create_or_update_local_sheet(payload)
                return send_json(self, 200, {"workbook": workbook})

            if path == "/local-goals":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_goal",
                    summary=str(payload.get("title") or "Create local goal"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                return send_json(self, 200, {"goal": create_or_update_local_goal(payload)})

            match = re.match(r"^/local-goals/([^/]+)/progress$", path)
            if match:
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="update_local_goal_progress",
                    summary=f"Update local goal progress {match.group(1)}",
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                return send_json(self, 200, {"goal": update_local_goal_progress(match.group(1), payload)})

            if path == "/local-benchmarks":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="run_local_model_benchmark",
                    summary=str(payload.get("title") or "Run local model benchmark"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                return send_json(self, 200, {"benchmark": run_local_model_benchmark(payload)})

            if path == "/local-benchmarks/baseline":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="run_local_model_benchmark_baseline",
                    summary="Run local model benchmark baseline",
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                return send_json(self, 200, {"baseline": run_local_model_benchmark_baseline(payload)})

            if path == "/local-code/workspaces":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_code_workspace",
                    summary=str(payload.get("title") or "Create local code workspace"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                workspace = create_or_update_local_code_workspace(payload)
                return send_json(self, 200, {"workspace": workspace})

            if path == "/local-code/workspaces/import":
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="import_local_code_workspace_package",
                    summary=str(payload.get("title") or "Import local code workspace package"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                workspace = import_local_code_workspace_package(payload)
                return send_json(self, 200, {"workspace": workspace})

            match = re.match(r"^/local-code/workspaces/([^/]+)/export$", path)
            if match:
                payload = read_json(self)
                return send_json(self, 200, {"export": export_local_code_workspace_package(match.group(1), payload)})

            match = re.match(r"^/local-code/workspaces/([^/]+)/git-worktree$", path)
            if match:
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="create_local_code_git_worktree",
                    summary=f"Create isolated Git worktree for local code workspace {match.group(1)}",
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                return send_json(self, 200, {"git_worktree": create_local_code_git_worktree(match.group(1), payload)})

            match = re.match(r"^/local-code/git-worktrees/([^/]+)/github-pr$", path)
            if match:
                payload = read_json(self)
                safe_payload, _ = sanitize_github_pr_payload(payload)
                if truthy(safe_payload.get("publish")):
                    approval_payload = {**safe_payload, "approval_mode": "always_ask"}
                    if not approve_or_require(
                        self,
                        action="prepare_local_code_github_pr",
                        summary=f"Publish GitHub PR for local Git worktree {match.group(1)}",
                        payload=approval_payload,
                        mutation=True,
                        important=True,
                    ):
                        return
                return send_json(self, 200, {"github_pr": prepare_local_code_github_pr(match.group(1), payload)})

            match = re.match(r"^/local-code/workspaces/([^/]+)/analyze$", path)
            if match:
                payload = read_json(self)
                workspace = read_local_code_workspace(match.group(1))
                if not workspace:
                    return send_json(self, 404, {"error": "not found"})
                return send_json(self, 200, {"analysis": local_code_analysis(workspace)})

            match = re.match(r"^/local-code/workspaces/([^/]+)/checks$", path)
            if match:
                payload = read_json(self)
                return send_json(self, 200, {"check": run_local_code_checks(match.group(1))})

            match = re.match(r"^/local-code/workspaces/([^/]+)/command$", path)
            if match:
                payload = read_json(self)
                approval_payload = {**payload, "approval_mode": "always_ask"}
                if not approve_or_require(
                    self,
                    action="run_local_code_workspace_command",
                    summary=f"Run local code command in workspace {match.group(1)}",
                    payload=approval_payload,
                    mutation=True,
                    important=True,
                ):
                    return
                return send_json(self, 200, {"command": run_local_code_command(match.group(1), payload)})

            match = re.match(r"^/local-code/workspaces/([^/]+)/review$", path)
            if match:
                payload = read_json(self)
                return send_json(self, 200, {"review": prepare_local_code_review_package(match.group(1), payload)})

            match = re.match(r"^/local-code/workspaces/([^/]+)/patch$", path)
            if match:
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="apply_local_code_workspace_patch",
                    summary=str(payload.get("summary") or f"Apply patch in local code workspace {match.group(1)}"),
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                return send_json(self, 200, apply_local_code_patch(match.group(1), payload))

            match = re.match(r"^/local-sheets/([^/]+)/explain$", path)
            if match:
                payload = read_json(self)
                workbook = read_local_sheet(match.group(1))
                if not workbook:
                    return send_json(self, 404, {"error": "not found"})
                return send_json(
                    self,
                    200,
                    {"explanation": local_sheet_explanation(workbook, str(payload.get("question") or ""))},
                )

            match = re.match(r"^/local-sheets/([^/]+)/cells$", path)
            if match:
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="update_local_sheet_cells",
                    summary=f"Update cells in local spreadsheet {match.group(1)}",
                    payload=payload,
                    mutation=True,
                    important=False,
                ):
                    return
                return send_json(self, 200, update_local_sheet_cells(match.group(1), payload))

            match = re.match(r"^/tasks/([^/]+)/run$", path)
            if match:
                payload = read_json(self)
                if not approve_or_require(
                    self,
                    action="run_task_now",
                    summary=f"Run scheduled task {match.group(1)}",
                    payload=payload,
                    important=True,
                ):
                    return
                run = run_task(match.group(1))
                return send_json(self, 200, {"run": run})
        except KeyError as exc:
            return send_json(self, 404, {"error": str(exc)})
        except Exception as exc:
            return send_json(self, 400, {"error": str(exc)})
        return send_json(self, 404, {"error": "not found"})

    def do_DELETE(self):
        parsed = parse.urlparse(self.path)
        path = parsed.path
        query = parse.parse_qs(parsed.query)
        match = re.match(r"^/pulse/cards/([^/]+)$", path)
        if match:
            if not approve_or_require(
                self,
                action="delete_pulse_digest",
                summary=f"Delete Pulse-style digest {match.group(1)}",
                query=query,
                important=True,
            ):
                return
            file_path = PULSE_DIR / f"{match.group(1)}.json"
            if not file_path.exists():
                return send_json(self, 404, {"error": "not found"})
            file_path.unlink()
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/runs/([^/]+)$", path)
        if match:
            if not approve_or_require(
                self,
                action="delete_run",
                summary=f"Delete stored task run {match.group(1)}",
                query=query,
                important=True,
            ):
                return
            file_path = RUNS_DIR / f"{match.group(1)}.json"
            if not file_path.exists():
                return send_json(self, 404, {"error": "not found"})
            file_path.unlink()
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-app/notes/([^/]+)$", path)
        if match:
            note_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_app_note",
                summary=f"Delete local app connector note {note_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_app_note(note_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-app/connections/([^/]+)$", path)
        if match:
            connection_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_app_connection",
                summary=f"Delete local app connection {connection_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_app_connection(connection_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-app/action-controls/([^/]+)$", path)
        if match:
            control_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_app_action_control",
                summary=f"Delete local app action control {control_id}",
                query=query,
                mutation=True,
                important=True,
            ):
                return
            if not delete_local_app_action_control(control_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-app/call-logs/([^/]+)$", path)
        if match:
            log_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_app_call_log",
                summary=f"Delete local app call log {log_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_app_call_log(log_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-email/drafts/([^/]+)$", path)
        if match:
            draft_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_email_draft",
                summary=f"Delete local email draft {draft_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_email_draft(draft_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-security/sessions/([^/]+)$", path)
        if match:
            session_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_security_session",
                summary=f"Delete local security session {session_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_security_session(session_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-pronunciation/guides/([^/]+)$", path)
        if match:
            guide_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_pronunciation_guide",
                summary=f"Delete local pronunciation guide {guide_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_pronunciation(guide_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-sports/briefings/([^/]+)$", path)
        if match:
            briefing_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_sports_briefing",
                summary=f"Delete local sports briefing {briefing_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_sports_briefing(briefing_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-sites/([^/]+)$", path)
        if match:
            site_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_site",
                summary=f"Delete local site {site_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_site(site_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-sheets/([^/]+)$", path)
        if match:
            workbook_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_sheet_workbook",
                summary=f"Delete local spreadsheet workbook {workbook_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_sheet(workbook_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-benchmarks/([^/]+)$", path)
        if match:
            benchmark_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_model_benchmark",
                summary=f"Delete local model benchmark {benchmark_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_model_benchmark(benchmark_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-code/workspaces/([^/]+)$", path)
        if match:
            workspace_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_code_workspace",
                summary=f"Delete local code workspace {workspace_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_code_workspace(workspace_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-code/git-worktrees/([^/]+)$", path)
        if match:
            worktree_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_code_git_worktree",
                summary=f"Delete isolated local Git worktree {worktree_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_code_git_worktree(worktree_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/local-goals/([^/]+)$", path)
        if match:
            goal_id = match.group(1)
            if not approve_or_require(
                self,
                action="delete_local_goal",
                summary=f"Delete local goal {goal_id}",
                query=query,
                mutation=True,
                important=False,
            ):
                return
            if not delete_local_goal(goal_id):
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"status": True})

        match = re.match(r"^/tasks/([^/]+)$", path)
        if not match:
            return send_json(self, 404, {"error": "not found"})
        task_id = match.group(1)
        if not approve_or_require(
            self,
            action="delete_task",
            summary=f"Delete scheduled task {task_id}",
            query=query,
            important=True,
        ):
            return
        with LOCK:
            tasks = load_tasks()
            if task_id not in tasks:
                return send_json(self, 404, {"error": "not found"})
            del tasks[task_id]
            save_tasks(tasks)
        return send_json(self, 200, {"status": True})


def warm_local_parity_search_cache():
    try:
        count = len(local_parity_search_candidates())
        print(f"local parity search cache warmed with {count} candidates", flush=True)
    except Exception as exc:
        print(f"local parity search cache warm failed: {type(exc).__name__}: {exc}", flush=True)


def main():
    Thread(target=due_loop, daemon=True).start()
    Thread(target=warm_local_parity_search_cache, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"local scheduler listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
