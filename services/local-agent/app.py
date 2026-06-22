#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from html import escape
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib import parse, request


MODEL_ID = os.environ.get("LOCAL_AGENT_MODEL_ID", "local-agent-glm52")
GLM_MODEL = os.environ.get("LOCAL_AGENT_GLM_MODEL", "glm52-q4-local")
GLM_BASE_URL = os.environ.get("LOCAL_AGENT_GLM_BASE_URL", "http://127.0.0.1:11441/v1")
AUTO_ROUTER_MODEL_ID = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_MODEL_ID", "local-auto-router")
AUTO_ROUTER_FAST_MODEL = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_FAST_MODEL", "gemma4:12b-256k-gpu")
AUTO_ROUTER_FAST_BASE_URL = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_FAST_BASE_URL", "http://127.0.0.1:11434/v1")
AUTO_ROUTER_CODE_MODEL = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_CODE_MODEL", "qwen3.6-35b-a3b:slopcode-cpu-64k")
AUTO_ROUTER_CODE_BASE_URL = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_CODE_BASE_URL", "http://127.0.0.1:11438/v1")
AUTO_ROUTER_RESEARCH_MODEL = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_RESEARCH_MODEL", "deep-research-glm52")
AUTO_ROUTER_RESEARCH_BASE_URL = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_RESEARCH_BASE_URL", "http://127.0.0.1:18041/v1")
AUTO_ROUTER_AGENT_MODEL = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_AGENT_MODEL", MODEL_ID)
AUTO_ROUTER_AGENT_BASE_URL = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_AGENT_BASE_URL", "http://127.0.0.1:18043/v1")
SEARXNG_URL = os.environ.get("LOCAL_AGENT_SEARXNG_URL", "http://127.0.0.1:18080/search")
TIKA_URL = os.environ.get("LOCAL_AGENT_TIKA_URL", "http://127.0.0.1:9998/tika")
SCHEDULER_URL = os.environ.get("LOCAL_AGENT_SCHEDULER_URL", "http://127.0.0.1:18042")
PUBLIC_BASE_URL = os.environ.get("LOCAL_AGENT_PUBLIC_BASE_URL", "http://127.0.0.1:18043")
PLAYWRIGHT_WS_URL = os.environ.get("LOCAL_AGENT_PLAYWRIGHT_WS_URL", "ws://127.0.0.1:18045")
HOST = os.environ.get("LOCAL_AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("LOCAL_AGENT_PORT", "18043"))
STORAGE = Path(os.environ.get("LOCAL_AGENT_STORAGE", "/data"))
GLM_TIMEOUT = int(os.environ.get("LOCAL_AGENT_GLM_TIMEOUT_SECONDS", "21600"))
AUTO_ROUTER_FAST_TIMEOUT = int(os.environ.get("LOCAL_AGENT_AUTO_ROUTER_FAST_TIMEOUT_SECONDS", "180"))
AUTO_ROUTER_CODE_TIMEOUT = int(os.environ.get("LOCAL_AGENT_AUTO_ROUTER_CODE_TIMEOUT_SECONDS", "240"))
AUTO_ROUTER_RESEARCH_TIMEOUT = int(os.environ.get("LOCAL_AGENT_AUTO_ROUTER_RESEARCH_TIMEOUT_SECONDS", "300"))
AUTO_ROUTER_AGENT_TIMEOUT = int(os.environ.get("LOCAL_AGENT_AUTO_ROUTER_AGENT_TIMEOUT_SECONDS", "120"))
AUTO_ROUTER_GLM_COLD_FALLBACK = os.environ.get("LOCAL_AGENT_AUTO_ROUTER_GLM_COLD_FALLBACK", "1").lower() not in {
    "0",
    "false",
    "no",
}
AUTO_ROUTER_GLM_WARM_MIN_DECODED = int(os.environ.get("LOCAL_AGENT_AUTO_ROUTER_GLM_WARM_MIN_DECODED", "1"))
AUTO_ROUTER_GLM_HEALTH_TIMEOUT = float(os.environ.get("LOCAL_AGENT_AUTO_ROUTER_GLM_HEALTH_TIMEOUT_SECONDS", "2"))
FETCH_TIMEOUT = int(os.environ.get("LOCAL_AGENT_FETCH_TIMEOUT_SECONDS", "20"))
MAX_FETCH_BYTES = int(os.environ.get("LOCAL_AGENT_MAX_FETCH_BYTES", str(2 * 1024 * 1024)))
PYTHON_TIMEOUT = int(os.environ.get("LOCAL_AGENT_PYTHON_TIMEOUT_SECONDS", "20"))
APPROVAL_WAIT_SECONDS = int(os.environ.get("LOCAL_AGENT_APPROVAL_WAIT_SECONDS", "120"))
PLAYWRIGHT_TIMEOUT_MS = int(os.environ.get("LOCAL_AGENT_PLAYWRIGHT_TIMEOUT_MS", "15000"))
DESKTOP_ENABLED = os.environ.get("LOCAL_AGENT_DESKTOP_ENABLED", "1").lower() not in {"0", "false", "no"}
DESKTOP_TIMEOUT = int(os.environ.get("LOCAL_AGENT_DESKTOP_TIMEOUT_SECONDS", "15"))
DESKTOP_COMMAND_MAX_OUTPUT = int(os.environ.get("LOCAL_AGENT_DESKTOP_COMMAND_MAX_OUTPUT", "6000"))
AUTO_ROUTER_TELEMETRY_LIMIT = max(10, int(os.environ.get("LOCAL_AGENT_AUTO_ROUTER_TELEMETRY_LIMIT", "200")))

LLM_LOCK = Lock()
APPROVAL_LOCK = Lock()
AUTO_ROUTER_TELEMETRY_LOCK = Lock()
AUTO_ROUTER_EVENTS: list[dict] = []
STORAGE.mkdir(parents=True, exist_ok=True)
APPROVALS_DIR = STORAGE / "approvals"
APPROVALS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR = STORAGE / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_DIR = STORAGE / "desktop"
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Action:
    kind: str
    title: str
    input: str
    output: str
    status: str = "completed"


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)

    def text(self) -> str:
        return "\n".join(self.parts)


class BrowserSnapshotParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.title_parts = []
        self.text_parts = []
        self.links = []
        self.current_link = None
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "a":
            self.current_link = {"href": attrs_dict.get("href", ""), "text": []}
        if tag in {"button", "input", "textarea", "select"}:
            label = attrs_dict.get("aria-label") or attrs_dict.get("name") or attrs_dict.get("value") or tag
            self.text_parts.append(f"[control:{tag}] {label}")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.current_link:
            text = clean_text(" ".join(self.current_link["text"])) or self.current_link["href"]
            self.links.append({"text": text[:160], "href": self.current_link["href"]})
            self.current_link = None

    def handle_data(self, data):
        if self.skip:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        if self.current_link is not None:
            self.current_link["text"].append(text)
        self.text_parts.append(text)

    def snapshot(self, url: str) -> dict:
        text = clean_text("\n".join(self.text_parts))
        return {
            "url": url,
            "title": clean_text(" ".join(self.title_parts))[:200],
            "text": text[:3000],
            "links": self.links[:25],
        }


def now() -> int:
    return int(time.time())


def clean_text(text: str) -> str:
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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


def http_json(url: str, payload: dict | None = None, timeout: int = 60, headers: dict | None = None) -> dict:
    data = None
    req_headers = {"User-Agent": "openwebui-local-agent/0.1"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=req_headers)
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def http_bytes(url: str, timeout: int = FETCH_TIMEOUT) -> tuple[bytes, str]:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0 openwebui-local-agent/0.1"})
    with request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "application/octet-stream").split(";")[0]
        chunks = []
        total = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FETCH_BYTES:
                break
            chunks.append(chunk)
        return b"".join(chunks), content_type


def html_to_text(raw: bytes) -> str:
    parser = TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return clean_text(parser.text())


def html_to_snapshot(url: str, raw: bytes) -> dict:
    parser = BrowserSnapshotParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return parser.snapshot(url)


def tika_extract(raw: bytes, content_type: str) -> str:
    req = request.Request(TIKA_URL, data=raw, method="PUT", headers={"Content-Type": content_type})
    with request.urlopen(req, timeout=max(60, FETCH_TIMEOUT)) as resp:
        return clean_text(resp.read().decode("utf-8", errors="replace"))


def fetch_url(url: str) -> str:
    raw, content_type = http_bytes(url)
    if content_type in {"text/html", "application/xhtml+xml"}:
        return html_to_text(raw)
    if content_type.startswith("text/"):
        return clean_text(raw.decode("utf-8", errors="replace"))
    return tika_extract(raw, content_type)


def browser_fixture(path: str) -> bytes | None:
    if path == "/fixtures/browser-start.html":
        return b"""<!doctype html>
<html>
  <head><title>Local Agent Browser Fixture</title></head>
  <body>
    <main>
      <h1>Browser Control Fixture</h1>
      <p>START_MARKER browser control page.</p>
      <a href="/fixtures/browser-done.html">Continue</a>
    </main>
  </body>
</html>
"""
    if path == "/fixtures/browser-done.html":
        return b"""<!doctype html>
<html>
  <head><title>Browser Fixture Complete</title></head>
  <body>
    <main>
      <h1>DONE_MARKER browser click completed</h1>
      <p>The local agent followed the approved link.</p>
    </main>
  </body>
</html>
"""
    return None


def send_html(handler: BaseHTTPRequestHandler, body: bytes):
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def send_binary(handler: BaseHTTPRequestHandler, body: bytes, content_type: str):
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def send_redirect(handler: BaseHTTPRequestHandler, location: str):
    handler.send_response(303)
    handler.send_header("Location", location)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()


def approval_path(approval_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9-]{36}", approval_id):
        raise ValueError("invalid approval id")
    return APPROVALS_DIR / f"{approval_id}.json"


def write_json_atomic(path: Path, payload: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def get_approval(approval_id: str) -> dict | None:
    try:
        path = approval_path(approval_id)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_approvals(status: str | None = None, limit: int = 50) -> list[dict]:
    approvals: list[dict] = []
    for path in APPROVALS_DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if status and item.get("status") != status:
            continue
        approvals.append(item)
    approvals.sort(key=lambda item: int(item.get("updated_at") or item.get("created_at") or 0), reverse=True)
    return approvals[:limit]


def update_approval_status(approval_id: str, status: str) -> dict:
    if status not in {"approved", "denied"}:
        raise ValueError("unsupported approval status")
    with APPROVAL_LOCK:
        approval = get_approval(approval_id)
        if not approval:
            raise FileNotFoundError("approval not found")
        if approval.get("status") == "pending":
            approval["status"] = status
            approval["updated_at"] = now()
        approval["decision"] = status
        write_json_atomic(approval_path(approval_id), approval)
        return approval


def approval_public_url(approval_id: str) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/approvals/{approval_id}"


def create_browser_approval(url: str, overrides: dict, reason: str, action: str, click_text: str | None = None) -> dict:
    parsed = parse.urlparse(url)
    host = parsed.netloc.lower()
    approval = {
        "id": str(uuid.uuid4()),
        "type": "browser",
        "status": "pending",
        "created_at": now(),
        "updated_at": now(),
        "url": url,
        "host": host,
        "approved_hosts": [host],
        "action": action,
        "click_text": click_text or "",
        "reason": reason,
        "requested_by": "local-agent-glm52",
    }
    with APPROVAL_LOCK:
        write_json_atomic(approval_path(approval["id"]), approval)
    return approval


def create_desktop_approval(action: str, command: list[str] | None, reason: str) -> dict:
    approval = {
        "id": str(uuid.uuid4()),
        "type": "desktop",
        "status": "pending",
        "created_at": now(),
        "updated_at": now(),
        "action": action,
        "command": command or [],
        "reason": reason,
        "requested_by": "local-agent-glm52",
    }
    with APPROVAL_LOCK:
        write_json_atomic(approval_path(approval["id"]), approval)
    return approval


def approval_allows_url(approval: dict, url: str) -> tuple[bool, str]:
    if approval.get("status") == "denied":
        return False, "approval_denied"
    if approval.get("status") != "approved":
        return False, f"approval_pending: {approval_public_url(approval.get('id', ''))}"
    parsed = parse.urlparse(url)
    host = parsed.netloc.lower()
    approved_hosts = {str(host).lower() for host in approval.get("approved_hosts", [])}
    if host not in approved_hosts and "*" not in approved_hosts:
        return False, f"approval_required: host {host!r} was not approved"
    return True, "approved_by_interactive_review"


def approval_allows_desktop(approval: dict, action: str, command: list[str] | None = None) -> tuple[bool, str]:
    if approval.get("status") == "denied":
        return False, "approval_denied"
    if approval.get("status") != "approved":
        return False, f"approval_pending: {approval_public_url(approval.get('id', ''))}"
    if approval.get("type") not in {"desktop", None}:
        return False, "approval_type_mismatch"
    if str(approval.get("action") or "") != action:
        return False, "approval_action_mismatch"
    approved_command = approval.get("command") or []
    if action == "command" and list(command or []) != list(approved_command):
        return False, "approval_command_mismatch"
    if command is not None and approved_command and list(command) != approved_command:
        return False, "approval_command_mismatch"
    return True, "approved_by_interactive_review"


def wait_for_approval(approval_id: str, timeout_seconds: int) -> dict | None:
    deadline = time.time() + max(1, timeout_seconds)
    while time.time() < deadline:
        approval = get_approval(approval_id)
        if approval and approval.get("status") in {"approved", "denied"}:
            return approval
        time.sleep(0.5)
    return get_approval(approval_id)


def approval_page_html(approval: dict | None = None) -> bytes:
    if approval is None:
        rows = []
        for item in list_approvals(limit=100):
            status = escape(str(item.get("status", "")))
            item_type = escape(str(item.get("type", "browser")))
            label = escape(str(item.get("action", item_type)))
            target = item.get("url") or " ".join(str(part) for part in item.get("command", []))
            target = escape(str(target))
            rows.append(
                f"<tr><td>{status}</td><td>{item_type}</td><td>{label}</td><td><a href=\"/approvals/{item['id']}\">{escape(item['id'])}</a></td><td>{target}</td></tr>"
            )
        body = """
        <h1>Local Agent Approvals</h1>
        <table>
          <thead><tr><th>Status</th><th>Type</th><th>Action</th><th>ID</th><th>Target</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """.format(rows="\n".join(rows) or "<tr><td colspan=\"5\">No approvals yet.</td></tr>")
    else:
        approval_id = escape(str(approval.get("id", "")))
        approval_type = str(approval.get("type", "browser"))
        status = escape(str(approval.get("status", "")))
        action = escape(str(approval.get("action", "")))
        url = escape(str(approval.get("url", "")))
        host = escape(str(approval.get("host", "")))
        click_text = escape(str(approval.get("click_text", "")))
        reason = escape(str(approval.get("reason", "")))
        command = escape(" ".join(str(part) for part in approval.get("command", [])))
        controls = ""
        if approval.get("status") == "pending":
            controls = f"""
            <form method="post" action="/approvals/{approval_id}/approve"><button class="approve" type="submit">Approve</button></form>
            <form method="post" action="/approvals/{approval_id}/deny"><button class="deny" type="submit">Deny</button></form>
            """
        title = "Desktop Action Approval" if approval_type == "desktop" else "Browser Action Approval"
        target_rows = ""
        if approval_type == "desktop":
            target_rows = f"""
          <dt>Command</dt><dd><code>{command}</code></dd>
            """
        else:
            target_rows = f"""
          <dt>URL</dt><dd><code>{url}</code></dd>
          <dt>Host</dt><dd>{host}</dd>
          <dt>Click text</dt><dd>{click_text}</dd>
            """
        body = f"""
        <p><a href="/approvals">All approvals</a></p>
        <h1>{title}</h1>
        <dl>
          <dt>Status</dt><dd>{status}</dd>
          <dt>Type</dt><dd>{escape(approval_type)}</dd>
          <dt>Action</dt><dd>{action}</dd>
          {target_rows}
          <dt>Reason</dt><dd>{reason}</dd>
          <dt>Resume ID</dt><dd><code>{approval_id}</code></dd>
        </dl>
        <div class="actions">{controls}</div>
        """

    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Local Agent Approvals</title>
    <style>
      body {{ font: 15px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; max-width: 1100px; color: #111827; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border-bottom: 1px solid #d1d5db; padding: 10px 8px; text-align: left; vertical-align: top; }}
      dt {{ font-weight: 700; margin-top: 16px; }}
      dd {{ margin: 4px 0 0; }}
      code {{ background: #f3f4f6; padding: 2px 4px; border-radius: 4px; overflow-wrap: anywhere; }}
      .actions {{ display: flex; gap: 10px; margin-top: 24px; }}
      button {{ border: 1px solid #9ca3af; border-radius: 6px; padding: 8px 14px; background: white; cursor: pointer; }}
      .approve {{ background: #14532d; color: white; border-color: #14532d; }}
      .deny {{ background: #7f1d1d; color: white; border-color: #7f1d1d; }}
    </style>
  </head>
  <body>{body}</body>
</html>
"""
    return html.encode("utf-8")


def screenshot_public_url(screenshot_id: str) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/screenshots/{screenshot_id}.png"


def save_screenshot(body: bytes) -> str:
    screenshot_id = str(uuid.uuid4())
    path = SCREENSHOTS_DIR / f"{screenshot_id}.png"
    path.write_bytes(body)
    return screenshot_id


def search_web(query: str, count: int) -> list[dict]:
    params = parse.urlencode({"q": query, "format": "json", "language": "all"})
    data = http_json(f"{SEARXNG_URL}?{params}", timeout=45)
    results = []
    for item in data.get("results", [])[:count]:
        url = item.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            results.append(
                {
                    "title": clean_text(item.get("title") or url)[:220],
                    "url": url,
                    "snippet": clean_text(item.get("content") or item.get("snippet") or "")[:800],
                }
            )
    return results


def python_code_for(question: str) -> str | None:
    lower = question.lower()
    if "python" not in lower and not any(word in lower for word in ["calculate", "compute", "sum", "average", "mean"]):
        return None
    expr_match = re.search(r"([-+*/(). 0-9]{3,})", question)
    if expr_match and re.search(r"\d", expr_match.group(1)):
        expr = expr_match.group(1).strip()
        if re.fullmatch(r"[-+*/(). 0-9]+", expr):
            return f"print({expr})"
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", question)]
    if nums and ("average" in lower or "mean" in lower):
        return "values = " + repr(nums) + "\nprint(sum(values) / len(values))"
    if nums and "sum" in lower:
        return "values = " + repr(nums) + "\nprint(sum(values))"
    return None


def run_python(code: str) -> str:
    with tempfile.TemporaryDirectory(prefix="openwebui-local-agent-") as tmpdir:
        result = subprocess.run(
            ["python3", "-I", "-c", code],
            cwd=tmpdir,
            text=True,
            capture_output=True,
            timeout=PYTHON_TIMEOUT,
        )
    output = []
    if result.stdout:
        output.append("stdout:\n" + result.stdout.strip())
    if result.stderr:
        output.append("stderr:\n" + result.stderr.strip())
    if result.returncode != 0:
        output.append(f"exit_code: {result.returncode}")
    return "\n\n".join(output).strip() or "(no output)"


def glm_chat(messages: list[dict], max_tokens: int = 512, temperature: float = 0.2) -> str:
    payload = {
        "model": GLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    with LLM_LOCK:
        data = http_json(f"{GLM_BASE_URL}/chat/completions", payload=payload, timeout=GLM_TIMEOUT)
    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


def content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"text", "input_text"}:
                parts.append(str(part.get("text", "")))
            elif "text" in part:
                parts.append(str(part.get("text", "")))
        return "\n".join(parts)
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def user_intent_text(payload: dict) -> str:
    messages = payload.get("messages") or []
    parts = [
        content_text(message.get("content", ""))
        for message in messages
        if isinstance(message, dict) and message.get("role") == "user"
    ]
    return "\n".join(clean_text(part) for part in parts if clean_text(part))


def visible_content_from_reasoning(reasoning_content: str) -> str:
    answer_labels = (
        "Answer:",
        "Summary:",
        "Math:",
        "Code:",
        "Translate:",
        "Translation:",
        "Question:",
        "Questions:",
        "Hint:",
        "Check:",
        "Criteria:",
        "Tradeoffs:",
        "Verify:",
        "Total:",
        "Total Revenue:",
        "Profit:",
        "Total Profit:",
        "Best:",
        "Best Item:",
        "Caveat:",
        "Title:",
        "Draft:",
        "Edit:",
        "Source note:",
        "Recommendation:",
        "Plan:",
        "Result:",
        "Final:",
    )
    preamble_labels = (
        "Role:",
        "Task:",
        "Constraint",
        "Context:",
        "Goal:",
        "Input:",
        "Input text:",
        "Input data:",
        "Keywords to include:",
        "Labels must be:",
        "Reply with",
        "No quotes",
        "No labels",
        "Summary must include",
        "Content requirements",
        "Exactly ",
        "Output format:",
        "Required output",
    )
    answer_blocks = []
    current_answer_block = []
    current_answer_labels = set()
    answer_candidates = []
    visible_lines = []
    for raw_line in reasoning_content.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw_line).strip()
        line = re.sub(r"^\*\*([^*]+?:)\*\*\s*", r"\1 ", line)
        line = re.sub(r"^\*([^*]+?:)\*\s*", r"\1 ", line)
        line = re.sub(r"^Line\s+\d+:\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"^Line\s+\d+\s*\(([^)]+)\):\s*", r"\1: ", line, flags=re.IGNORECASE)
        if not line:
            continue
        matched_label = next((label for label in answer_labels if line.startswith(label)), None)
        if matched_label:
            if matched_label in current_answer_labels and current_answer_block:
                answer_blocks.append(current_answer_block)
                current_answer_block = []
                current_answer_labels = set()
            current_answer_block.append(line)
            current_answer_labels.add(matched_label)
            continue
        if current_answer_block:
            answer_blocks.append(current_answer_block)
            current_answer_block = []
            current_answer_labels = set()
        if any(line.startswith(label) for label in preamble_labels):
            continue
        candidate = re.sub(
            r"^(?:Option\s+[A-Z]|Candidate\s+\d+|Final answer)\s*:\s*",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip()
        candidate = re.sub(
            r"\s*\((?:good|better|best|simple|concise|preferred)\)\s*$",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip()
        candidate = candidate.strip("\"'")
        if candidate and candidate != line:
            answer_candidates.append(candidate)
            continue
        quoted = re.match(r'^"([^"]{12,})"', line)
        if quoted:
            answer_candidates.append(quoted.group(1).strip())
            continue
        visible_lines.append(line)
    if current_answer_block:
        answer_blocks.append(current_answer_block)
    complete_answer_blocks = [block for block in answer_blocks if len(block) >= 2]
    if complete_answer_blocks:
        return "\n".join(complete_answer_blocks[-1])
    if visible_lines and answer_candidates:
        return "\n".join([*visible_lines, *answer_candidates]).strip()
    if visible_lines:
        return "\n".join(visible_lines).strip()
    if answer_candidates:
        return max(answer_candidates, key=len).strip()
    if any(label in reasoning_content for label in ("Role:", "Constraint", "Task:")):
        return ""
    return reasoning_content.strip()


def ensure_visible_chat_content(data: dict) -> dict:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        return data
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict) or message.get("content"):
        return data
    reasoning_content = message.get("reasoning_content") or message.get("reasoning")
    if not isinstance(reasoning_content, str) or not reasoning_content.strip():
        return data
    visible_content = visible_content_from_reasoning(reasoning_content)
    if visible_content:
        message["content"] = visible_content
        data["local_agent_content_fallback"] = "reasoning_content" if message.get("reasoning_content") else "reasoning"
    return data


def auto_router_overrides(payload: dict) -> dict:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    direct = payload.get("local_auto_router") if isinstance(payload.get("local_auto_router"), dict) else {}
    nested = metadata.get("local_auto_router") if isinstance(metadata.get("local_auto_router"), dict) else {}
    return {**nested, **direct}


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def glm_warm_status(overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    if truthy(overrides.get("simulate_glm_cold")):
        return {
            "available": True,
            "warm": False,
            "cached_or_decoded_tokens": 0,
            "reason": "simulated cold GLM slot",
        }
    try:
        base = GLM_BASE_URL.rstrip("/")
        root = base[:-3] if base.endswith("/v1") else base
        slots = http_json(f"{root}/slots", timeout=AUTO_ROUTER_GLM_HEALTH_TIMEOUT)
        if not isinstance(slots, list) or not slots:
            return {"available": True, "warm": False, "cached_or_decoded_tokens": 0, "reason": "no GLM slots reported"}
        decoded_values = []
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            next_tokens = slot.get("next_token") or []
            if isinstance(next_tokens, list):
                for item in next_tokens:
                    if isinstance(item, dict):
                        try:
                            decoded_values.append(int(item.get("n_decoded") or 0))
                        except (TypeError, ValueError):
                            pass
        decoded = max(decoded_values or [0])
        return {
            "available": True,
            "warm": decoded >= AUTO_ROUTER_GLM_WARM_MIN_DECODED,
            "cached_or_decoded_tokens": decoded,
            "reason": "GLM slot has decoded tokens" if decoded else "GLM slot has no decoded tokens yet",
        }
    except Exception as exc:
        return {
            "available": False,
            "warm": False,
            "cached_or_decoded_tokens": 0,
            "reason": f"GLM slot probe failed: {exc}",
        }


def maybe_apply_glm_cold_fallback(route: dict, overrides: dict) -> dict:
    if route.get("route") != "glm" or route.get("forced"):
        return route
    if not AUTO_ROUTER_GLM_COLD_FALLBACK or truthy(overrides.get("allow_cold_glm")):
        return route
    status = glm_warm_status(overrides)
    if status.get("warm"):
        return {**route, "glm_warm_status": status}
    return {
        "route": "fast",
        "target_model": AUTO_ROUTER_FAST_MODEL,
        "target_base_url": AUTO_ROUTER_FAST_BASE_URL,
        "reason": f"GLM cold fallback from {route.get('reason', 'glm route')}",
        "fallback_from_route": route.get("route"),
        "fallback_from_model": route.get("target_model"),
        "glm_warm_status": status,
    }


def select_auto_route(payload: dict, question: str, overrides: dict) -> dict:
    force_route = str(overrides.get("force_route") or "").strip().lower()
    if force_route in {"fast", "instant", "gemma", "gemma4"}:
        return {
            "route": "fast",
            "target_model": AUTO_ROUTER_FAST_MODEL,
            "target_base_url": AUTO_ROUTER_FAST_BASE_URL,
            "reason": "forced fast route",
            "forced": True,
        }
    if force_route in {"code", "coding", "slopcode", "qwen"}:
        return {
            "route": "code",
            "target_model": AUTO_ROUTER_CODE_MODEL,
            "target_base_url": AUTO_ROUTER_CODE_BASE_URL,
            "reason": "forced coding route",
            "forced": True,
        }
    if force_route in {"research", "deep-research", "deep_research", "sources"}:
        return {
            "route": "research",
            "target_model": AUTO_ROUTER_RESEARCH_MODEL,
            "target_base_url": AUTO_ROUTER_RESEARCH_BASE_URL,
            "reason": "forced research route",
            "forced": True,
        }
    if force_route in {"agent", "tool", "tools", "browser", "desktop"}:
        return {
            "route": "agent",
            "target_model": AUTO_ROUTER_AGENT_MODEL,
            "target_base_url": AUTO_ROUTER_AGENT_BASE_URL,
            "reason": "forced tool-agent route",
            "forced": True,
        }
    if force_route in {"glm", "deep", "reasoning", "quality"}:
        return {
            "route": "glm",
            "target_model": GLM_MODEL,
            "target_base_url": GLM_BASE_URL,
            "reason": "forced GLM route",
            "forced": True,
        }

    messages = payload.get("messages") or []
    text = user_intent_text(payload)
    lower = f"{question}\n{text}".lower()
    has_tool_context = any(message.get("role") == "tool" for message in messages if isinstance(message, dict))
    coding_terms = {
        "api",
        "bug",
        "code",
        "code review",
        "coding",
        "csv",
        "dataframe",
        "debug",
        "error",
        "function",
        "jest",
        "javascript",
        "notebook",
        "pandas",
        "patch",
        "python",
        "query",
        "refactor",
        "regex",
        "script",
        "stack trace",
        "sql",
        "spreadsheet",
        "test",
        "typescript",
        "unit test",
    }
    research_terms = {
        "buyer guide",
        "cite",
        "cited",
        "citation",
        "compare products",
        "deep research",
        "due diligence",
        "find sources",
        "latest",
        "literature",
        "literature review",
        "look up",
        "market",
        "market research",
        "news",
        "price",
        "prices",
        "product comparison",
        "reviews",
        "research",
        "source-backed",
        "sources",
        "web search",
        "web research",
    }
    no_search_terms = {
        "do not browse",
        "do not look up",
        "do not search",
        "don't browse",
        "don't look up",
        "don't search",
        "from general knowledge",
        "no browsing",
        "no search",
        "no sources needed",
        "no web search",
        "offline only",
        "without browsing",
        "without looking anything up",
        "without search",
        "without sources",
        "without web search",
    }
    agent_terms = {
        "browser",
        "click",
        "desktop",
        "download",
        "navigate",
        "open page",
        "playwright",
        "run command",
        "screenshot",
        "take a screenshot",
        "tool call",
        "tool-use",
        "upload",
        "use a tool",
        "use the browser",
        "web page",
    }
    no_agent_terms = {
        "do not use browser",
        "do not use desktop",
        "do not use the browser",
        "do not use tools",
        "don't use browser",
        "don't use desktop",
        "don't use the browser",
        "don't use tools",
        "no browser",
        "no browser tools",
        "no desktop",
        "no tool calls",
        "no tools",
        "without browser",
        "without desktop",
        "without tool calls",
        "without tools",
    }
    complex_terms = {
        "analyze",
        "architecture",
        "decision",
        "deep",
        "design",
        "derive",
        "explain why",
        "implement",
        "multi-step",
        "multi step",
        "plan",
        "prove",
        "reason",
        "root cause",
        "research",
        "strategy",
        "tradeoff",
        "tradeoffs",
        "why",
    }
    short_reasoning_terms = {
        "analyze",
        "explain",
        "explain why",
        "reason",
        "why",
    }
    latency_sensitive_terms = {
        "brief",
        "briefly",
        "eli5",
        "in one sentence",
        "in simple terms",
        "one sentence",
        "plain language",
        "quick",
        "quickly",
        "short",
        "simple explanation",
        "two sentences",
    }
    heavyweight_reasoning_terms = {
        "architecture",
        "decision criteria",
        "deep",
        "derive",
        "due diligence",
        "multi-step",
        "multi step",
        "phased plan",
        "private",
        "prove",
        "root cause",
        "sensitive",
        "strategy",
        "tradeoff",
        "tradeoffs",
    }
    no_tools_requested = any(term in lower for term in no_agent_terms)
    no_search_requested = no_tools_requested or any(term in lower for term in no_search_terms)

    if not no_tools_requested and any(term in lower for term in agent_terms):
        return {
            "route": "agent",
            "target_model": AUTO_ROUTER_AGENT_MODEL,
            "target_base_url": AUTO_ROUTER_AGENT_BASE_URL,
            "reason": "tool-agent keyword",
        }
    if not no_search_requested and any(term in lower for term in research_terms):
        return {
            "route": "research",
            "target_model": AUTO_ROUTER_RESEARCH_MODEL,
            "target_base_url": AUTO_ROUTER_RESEARCH_BASE_URL,
            "reason": "research keyword",
        }
    if any(term in lower for term in coding_terms):
        return {
            "route": "code",
            "target_model": AUTO_ROUTER_CODE_MODEL,
            "target_base_url": AUTO_ROUTER_CODE_BASE_URL,
            "reason": "coding keyword",
        }
    if (
        len(text) <= int(overrides.get("short_reasoning_chars") or 420)
        and any(term in lower for term in short_reasoning_terms)
        and any(term in lower for term in latency_sensitive_terms)
        and not any(term in lower for term in heavyweight_reasoning_terms)
        and not has_tool_context
    ):
        return {
            "route": "fast",
            "target_model": AUTO_ROUTER_FAST_MODEL,
            "target_base_url": AUTO_ROUTER_FAST_BASE_URL,
            "reason": "latency-sensitive short reasoning",
        }
    if len(text) > int(overrides.get("long_prompt_chars") or 1200):
        reason = "long prompt"
    elif any(term in lower for term in complex_terms):
        reason = "reasoning keyword"
    elif has_tool_context:
        reason = "tool context"
    else:
        return {
            "route": "fast",
            "target_model": AUTO_ROUTER_FAST_MODEL,
            "target_base_url": AUTO_ROUTER_FAST_BASE_URL,
            "reason": "short everyday prompt",
        }

    return {
        "route": "glm",
        "target_model": GLM_MODEL,
        "target_base_url": GLM_BASE_URL,
        "reason": reason,
    }


def routed_payload(payload: dict, model: str) -> dict:
    allowed_keys = {
        "messages",
        "max_tokens",
        "temperature",
        "top_p",
        "stop",
        "presence_penalty",
        "frequency_penalty",
        "seed",
        "response_format",
    }
    forwarded = {key: payload[key] for key in allowed_keys if key in payload}
    forwarded["model"] = model
    forwarded["stream"] = False
    return forwarded


def completion_response(model: str, content: str, usage: dict | None = None, extra: dict | None = None) -> dict:
    response = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": now(),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    if extra:
        response.update(extra)
    return response


def auto_router_request_shape(payload: dict) -> dict:
    messages = [message for message in payload.get("messages") or [] if isinstance(message, dict)]
    prompt_text = "\n".join(content_text(message.get("content", "")) for message in messages)
    return {
        "message_count": len(messages),
        "prompt_chars": len(prompt_text),
        "has_tool_context": any(message.get("role") == "tool" for message in messages),
        "stream": bool(payload.get("stream")),
    }


def record_auto_router_event(
    route: dict,
    payload: dict,
    overrides: dict,
    *,
    status: str,
    elapsed_ms: float,
    usage: dict | None = None,
    response_model: str | None = None,
    error: str | None = None,
) -> dict:
    event = {
        "id": str(uuid.uuid4()),
        "created": now(),
        "trace_id": str(overrides.get("trace_id") or ""),
        "route": route.get("route"),
        "target_model": route.get("target_model"),
        "target_base_url": route.get("target_base_url"),
        "reason": route.get("reason"),
        "fallback_from_route": route.get("fallback_from_route", ""),
        "fallback_from_model": route.get("fallback_from_model", ""),
        "glm_warm_status": route.get("glm_warm_status") or {},
        "status": status,
        "elapsed_ms": round(float(elapsed_ms), 2),
        "response_model": response_model or "",
        "usage": usage or {},
        "echo_route": bool(overrides.get("echo_route")),
        **auto_router_request_shape(payload),
    }
    if error:
        event["error"] = str(error)[:500]
    with AUTO_ROUTER_TELEMETRY_LOCK:
        AUTO_ROUTER_EVENTS.append(event)
        if len(AUTO_ROUTER_EVENTS) > AUTO_ROUTER_TELEMETRY_LIMIT:
            del AUTO_ROUTER_EVENTS[: len(AUTO_ROUTER_EVENTS) - AUTO_ROUTER_TELEMETRY_LIMIT]
    return event


def list_auto_router_events(query: dict) -> dict:
    try:
        limit = int((query.get("limit") or ["50"])[0])
    except Exception:
        limit = 50
    limit = max(1, min(limit, AUTO_ROUTER_TELEMETRY_LIMIT))
    route_filter = (query.get("route") or [""])[0]
    trace_filter = (query.get("trace_id") or [""])[0]
    with AUTO_ROUTER_TELEMETRY_LOCK:
        events = list(AUTO_ROUTER_EVENTS)
    if route_filter:
        events = [event for event in events if event.get("route") == route_filter]
    if trace_filter:
        events = [event for event in events if event.get("trace_id") == trace_filter]
    events = events[-limit:]
    route_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for event in events:
        route_counts[event.get("route", "")] = route_counts.get(event.get("route", ""), 0) + 1
        status_counts[event.get("status", "")] = status_counts.get(event.get("status", ""), 0) + 1
    return {
        "events": events,
        "count": len(events),
        "limit": AUTO_ROUTER_TELEMETRY_LIMIT,
        "summary": {
            "routes": route_counts,
            "statuses": status_counts,
            "latest_created": max((event.get("created", 0) for event in events), default=0),
        },
    }


def auto_router_chat(payload: dict, question: str) -> dict:
    overrides = auto_router_overrides(payload)
    route = maybe_apply_glm_cold_fallback(select_auto_route(payload, question, overrides), overrides)
    if overrides.get("echo_route"):
        answer = (
            f"route={route['route']}; target_model={route['target_model']}; "
            f"reason={route['reason']}"
        )
        event = record_auto_router_event(
            route,
            payload,
            overrides,
            status="echo",
            elapsed_ms=0,
            usage={"prompt_tokens": 0, "completion_tokens": len(answer.split()), "total_tokens": len(answer.split())},
            response_model=AUTO_ROUTER_MODEL_ID,
        )
        route = {**route, "telemetry_id": event["id"], "trace_id": event.get("trace_id", "")}
        return completion_response(
            AUTO_ROUTER_MODEL_ID,
            answer,
            usage={"prompt_tokens": 0, "completion_tokens": len(answer.split()), "total_tokens": len(answer.split())},
            extra={"local_auto_router": route},
        )

    target_payload = routed_payload(payload, route["target_model"])
    timeout_by_route = {
        "agent": AUTO_ROUTER_AGENT_TIMEOUT,
        "code": AUTO_ROUTER_CODE_TIMEOUT,
        "fast": AUTO_ROUTER_FAST_TIMEOUT,
        "glm": GLM_TIMEOUT,
        "research": AUTO_ROUTER_RESEARCH_TIMEOUT,
    }
    timeout = timeout_by_route.get(route["route"], GLM_TIMEOUT)
    lock = LLM_LOCK if route["route"] == "glm" else None
    started = time.time()
    try:
        if lock:
            with lock:
                data = http_json(f"{route['target_base_url']}/chat/completions", payload=target_payload, timeout=timeout)
        else:
            data = http_json(f"{route['target_base_url']}/chat/completions", payload=target_payload, timeout=timeout)
    except Exception as exc:
        record_auto_router_event(
            route,
            payload,
            overrides,
            status="error",
            elapsed_ms=(time.time() - started) * 1000,
            error=str(exc),
        )
        raise
    event = record_auto_router_event(
        route,
        payload,
        overrides,
        status="ok",
        elapsed_ms=(time.time() - started) * 1000,
        usage=data.get("usage") if isinstance(data.get("usage"), dict) else None,
        response_model=str(data.get("model") or ""),
    )
    route = {**route, "telemetry_id": event["id"], "trace_id": event.get("trace_id", "")}
    data = ensure_visible_chat_content(data)
    data["model"] = AUTO_ROUTER_MODEL_ID
    data["local_auto_router"] = route
    return data


def last_user_message(payload: dict) -> str:
    for message in reversed(payload.get("messages") or []):
        if message.get("role") == "user":
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def system_messages(payload: dict) -> list[str]:
    messages = []
    for message in payload.get("messages") or []:
        if message.get("role") != "system":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            messages.append(content)
        elif isinstance(content, list):
            messages.append("\n".join(part.get("text", "") for part in content if isinstance(part, dict)))
    return [clean_text(message) for message in messages if clean_text(message)]


def message_summaries(payload: dict) -> list[dict]:
    messages = []
    for message in payload.get("messages") or []:
        content = message.get("content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
        else:
            text = json.dumps(content, ensure_ascii=False)
        messages.append({"role": message.get("role", ""), "content": clean_text(text)})
    return messages


def should_search(question: str, overrides: dict) -> bool:
    if "web_search" in overrides:
        return bool(overrides.get("web_search"))
    lower = question.lower()
    return any(word in lower for word in ["search", "web", "latest", "current", "find sources", "look up"])


def should_check_scheduler(question: str, overrides: dict) -> bool:
    if "check_scheduler" in overrides:
        return bool(overrides.get("check_scheduler"))
    return "schedule" in question.lower() or "task" in question.lower()


def should_use_browser(question: str, overrides: dict) -> bool:
    if overrides.get("browser_url"):
        return True
    lower = question.lower()
    return "browser" in lower or "click" in lower or "open this page" in lower


def requested_browser_url(question: str, overrides: dict) -> str | None:
    url = overrides.get("browser_url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    match = re.search(r"https?://[^\s)>\"]+", question)
    return match.group(0).rstrip(".,") if match else None


def allowed_hosts(overrides: dict) -> set[str]:
    hosts = overrides.get("allowed_hosts") or overrides.get("browser_allowed_hosts") or []
    if isinstance(hosts, str):
        hosts = [host.strip() for host in hosts.split(",")]
    return {str(host).strip().lower() for host in hosts if str(host).strip()}


def browser_approval(url: str, overrides: dict, action: str = "snapshot", click_text: str | None = None) -> tuple[bool, str, str | None]:
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "browser tool only supports absolute http(s) URLs", None

    approval_id = str(overrides.get("approval_id") or overrides.get("browser_approval_id") or "").strip()
    if approval_id:
        approval = get_approval(approval_id)
        if not approval:
            return False, f"approval_not_found: {approval_id}", None
        approved, reason = approval_allows_url(approval, url)
        if approved:
            return True, reason, approval_id
        return False, reason, approval_id

    if not overrides.get("allow_browser"):
        reason = "approval_required: browser action needs review"
        approval = create_browser_approval(url, overrides, reason, action, click_text)
        return False, f"{reason}: {approval_public_url(approval['id'])}", approval["id"]
    hosts = allowed_hosts(overrides)
    host = parsed.netloc.lower()
    if "*" not in hosts and host not in hosts:
        reason = f"approval_required: host {host!r} is not in local_agent.allowed_hosts"
        approval = create_browser_approval(url, overrides, reason, action, click_text)
        return False, f"{reason}: {approval_public_url(approval['id'])}", approval["id"]
    return True, "approved", None


def maybe_wait_for_browser_approval(
    url: str,
    overrides: dict,
    reason: str,
    approval_id: str | None,
    action: str,
    click_text: str | None = None,
    progress=None,
) -> tuple[bool, str, dict]:
    if not approval_id or not overrides.get("interactive_approval"):
        return False, reason, overrides

    wait_seconds = int(overrides.get("approval_timeout_seconds") or APPROVAL_WAIT_SECONDS)
    approval_url = approval_public_url(approval_id)
    if progress:
        progress(f"Approval required: {approval_url}\n\n")
    approval = wait_for_approval(approval_id, wait_seconds)
    if not approval:
        return False, f"approval_timeout: {approval_url}", overrides
    approved, approval_reason = approval_allows_url(approval, url)
    if not approved:
        return False, approval_reason, overrides
    approved_overrides = dict(overrides)
    approved_overrides["approval_id"] = approval_id
    approved_overrides["allow_browser"] = True
    approved_overrides["allowed_hosts"] = sorted(set(allowed_hosts(overrides)) | set(approval.get("approved_hosts", [])))
    return True, "approved_by_interactive_review", approved_overrides


def browser_snapshot(url: str) -> dict:
    raw, content_type = http_bytes(url)
    if content_type not in {"text/html", "application/xhtml+xml"}:
        text = clean_text(raw.decode("utf-8", errors="replace")) if content_type.startswith("text/") else f"{len(raw)} bytes of {content_type}"
        return {"url": url, "title": "", "text": text[:3000], "links": []}
    return html_to_snapshot(url, raw)


def format_browser_snapshot(snapshot: dict) -> str:
    lines = [
        f"URL: {snapshot.get('url', '')}",
        f"Title: {snapshot.get('title', '')}",
        "",
        "Visible text:",
        snapshot.get("text", ""),
        "",
        "Links:",
    ]
    for link in snapshot.get("links", []):
        lines.append(f"- {link.get('text', '')}: {link.get('href', '')}")
    return "\n".join(lines).strip()


def wait_for_page_idle(page):
    for state, timeout in [("domcontentloaded", PLAYWRIGHT_TIMEOUT_MS), ("networkidle", 5000)]:
        try:
            page.wait_for_load_state(state, timeout=timeout)
        except Exception:
            pass


def playwright_extract_links(page) -> list[dict]:
    try:
        return page.locator("a").evaluate_all(
            """links => links.slice(0, 25).map(link => ({
                text: (link.innerText || link.textContent || link.href || '').trim().slice(0, 160),
                href: link.href || link.getAttribute('href') || ''
            }))"""
        )
    except Exception:
        return []


def playwright_find_link_url(page, click_text: str) -> str | None:
    text = click_text.strip().lower()
    if not text:
        return None
    try:
        return page.locator("a").evaluate_all(
            """(links, wanted) => {
                for (const link of links) {
                    const label = (link.innerText || link.textContent || '').trim().toLowerCase();
                    if (label.includes(wanted)) {
                        return link.href || link.getAttribute('href') || null;
                    }
                }
                return null;
            }""",
            text,
        )
    except Exception:
        return None


def playwright_snapshot(url: str, click_text: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect(PLAYWRIGHT_WS_URL, timeout=PLAYWRIGHT_TIMEOUT_MS)
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT_MS)
            wait_for_page_idle(page)
            clicked = False
            if click_text:
                page.get_by_text(click_text, exact=False).first.click(timeout=PLAYWRIGHT_TIMEOUT_MS)
                clicked = True
                wait_for_page_idle(page)
            try:
                text = page.locator("body").inner_text(timeout=PLAYWRIGHT_TIMEOUT_MS)
            except Exception:
                text = page.content()
            screenshot_id = save_screenshot(page.screenshot(type="png", full_page=False, timeout=PLAYWRIGHT_TIMEOUT_MS))
            return {
                "url": page.url,
                "title": page.title()[:200],
                "text": clean_text(text)[:4000],
                "links": playwright_extract_links(page),
                "screenshot_id": screenshot_id,
                "screenshot_url": screenshot_public_url(screenshot_id),
                "clicked": clicked,
            }
        finally:
            page.close()
            browser.close()


def format_playwright_snapshot(snapshot: dict) -> str:
    lines = [
        f"URL: {snapshot.get('url', '')}",
        f"Title: {snapshot.get('title', '')}",
        f"Screenshot: {snapshot.get('screenshot_url', '')}",
        "",
        "Rendered text:",
        snapshot.get("text", ""),
        "",
        "Links:",
    ]
    for link in snapshot.get("links", []):
        lines.append(f"- {link.get('text', '')}: {link.get('href', '')}")
    return "\n".join(lines).strip()


def run_playwright_browser_tool(url: str, action: str, click_text: str, overrides: dict) -> Action:
    if action == "snapshot":
        rendered = playwright_snapshot(url)
        return Action(kind="browser", title="Graphical Browser Snapshot", input=url, output=format_playwright_snapshot(rendered))

    if action == "click_text":
        if not click_text:
            return Action(kind="browser", title="Graphical Browser Click", input=url, output="click_text is required", status="failed")
        target = None
        try:
            initial = playwright_snapshot(url)
            target = None
            # Re-open for the actual click after approval checks; this keeps target probing side-effect free.
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.connect(PLAYWRIGHT_WS_URL, timeout=PLAYWRIGHT_TIMEOUT_MS)
                page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT_MS)
                    wait_for_page_idle(page)
                    target = playwright_find_link_url(page, click_text)
                finally:
                    page.close()
                    browser.close()
        except Exception:
            initial = None

        if target:
            approved, reason, approval_id = browser_approval(target, overrides, action, click_text)
            if not approved:
                output = reason
                if approval_id:
                    output += f"\napproval_id: {approval_id}\napproval_url: {approval_public_url(approval_id)}"
                return Action(kind="browser", title="Graphical Browser Click Approval Required", input=target, output=output, status="approval_required")

        rendered = playwright_snapshot(url, click_text=click_text)
        output = (
            f"Clicked text: {click_text}\n"
            f"Start URL: {url}\n"
            f"Final URL: {rendered.get('url', '')}\n"
            f"Screenshot: {rendered.get('screenshot_url', '')}\n\n"
            f"Final rendered snapshot:\n{format_playwright_snapshot(rendered)}"
        )
        if initial:
            output += f"\n\nInitial screenshot: {initial.get('screenshot_url', '')}"
        return Action(kind="browser", title="Graphical Browser Click", input=f"{url}\nclick_text={click_text}", output=output)

    return Action(kind="browser", title="Graphical Browser Tool", input=url, output=f"Unsupported browser_action: {action}", status="failed")


def run_browser_tool(question: str, overrides: dict, progress=None) -> Action:
    url = requested_browser_url(question, overrides)
    if not url:
        return Action(kind="browser", title="Browser Tool", input="", output="No browser_url or URL found.", status="failed")

    action = str(overrides.get("browser_action") or "snapshot")
    click_text = str(overrides.get("click_text") or "").strip()
    approved, reason, approval_id = browser_approval(url, overrides, action, click_text)
    if not approved:
        approved, reason, overrides = maybe_wait_for_browser_approval(
            url, overrides, reason, approval_id, action, click_text, progress=progress
        )
    if not approved:
        output = reason
        if approval_id:
            output += f"\napproval_id: {approval_id}\napproval_url: {approval_public_url(approval_id)}"
        return Action(kind="browser", title="Browser Approval Required", input=url, output=output, status="approval_required")

    if str(overrides.get("browser_backend") or "").lower() == "playwright":
        try:
            return run_playwright_browser_tool(url, action, click_text, overrides)
        except Exception as exc:
            return Action(kind="browser", title="Graphical Browser Tool", input=url, output=str(exc), status="failed")

    snapshot = browser_snapshot(url)
    if action == "snapshot":
        return Action(kind="browser", title="Browser Snapshot", input=url, output=format_browser_snapshot(snapshot))

    if action == "click_text":
        normalized_click_text = click_text.lower()
        if not normalized_click_text:
            return Action(kind="browser", title="Browser Click", input=url, output="click_text is required", status="failed")
        target = None
        for link in snapshot.get("links", []):
            if normalized_click_text in str(link.get("text", "")).lower():
                target = parse.urljoin(url, link.get("href", ""))
                break
        if not target:
            return Action(
                kind="browser",
                title="Browser Click",
                input=f"{url}\nclick_text={overrides.get('click_text')}",
                output="No matching link found.\n\n" + format_browser_snapshot(snapshot),
                status="failed",
            )
        approved, reason, target_approval_id = browser_approval(target, overrides, action, click_text)
        if not approved:
            approved, reason, overrides = maybe_wait_for_browser_approval(
                target, overrides, reason, target_approval_id, action, click_text, progress=progress
            )
        if not approved:
            output = reason
            if target_approval_id:
                output += f"\napproval_id: {target_approval_id}\napproval_url: {approval_public_url(target_approval_id)}"
            return Action(kind="browser", title="Browser Click Approval Required", input=target, output=output, status="approval_required")
        clicked = browser_snapshot(target)
        output = (
            f"Clicked link text: {overrides.get('click_text')}\n"
            f"Start URL: {url}\n"
            f"Final URL: {target}\n\n"
            f"Final snapshot:\n{format_browser_snapshot(clicked)}"
        )
        return Action(kind="browser", title="Browser Click", input=f"{url}\nclick_text={overrides.get('click_text')}", output=output)

    return Action(kind="browser", title="Browser Tool", input=url, output=f"Unsupported browser_action: {action}", status="failed")


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def display_probe(display: str, wayland_display: str, xdg_runtime_dir: str) -> tuple[bool, str]:
    if display and command_exists("xdpyinfo"):
        try:
            result = subprocess.run(
                ["xdpyinfo"],
                text=True,
                capture_output=True,
                timeout=3,
                env=os.environ.copy(),
            )
            if result.returncode == 0:
                first_line = (result.stdout or "").splitlines()[0] if result.stdout else "xdpyinfo ok"
                return True, first_line[:200]
            return False, (result.stderr or result.stdout or f"xdpyinfo exit {result.returncode}").strip()[:300]
        except Exception as exc:
            return False, str(exc)[:300]

    if wayland_display and xdg_runtime_dir:
        wayland_socket = Path(xdg_runtime_dir) / wayland_display
        if wayland_socket.exists():
            return True, f"Wayland socket exists: {wayland_socket}"
        return False, f"Wayland socket not found: {wayland_socket}"

    return False, "DISPLAY and WAYLAND_DISPLAY are unset"


def desktop_capabilities() -> dict:
    display = os.environ.get("DISPLAY", "")
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
    xauthority = os.environ.get("XAUTHORITY", "")
    tools = {
        "xdg-open": command_exists("xdg-open"),
        "xdotool": command_exists("xdotool"),
        "wmctrl": command_exists("wmctrl"),
        "xprop": command_exists("xprop"),
        "xdpyinfo": command_exists("xdpyinfo"),
        "xev": command_exists("xev"),
        "xterm": command_exists("xterm"),
        "gnome-screenshot": command_exists("gnome-screenshot"),
        "grim": command_exists("grim"),
        "scrot": command_exists("scrot"),
        "import": command_exists("import"),
    }
    gui_available, probe = display_probe(display, wayland_display, xdg_runtime_dir)
    return {
        "enabled": DESKTOP_ENABLED,
        "gui_available": gui_available,
        "display_probe": probe,
        "display": display,
        "wayland_display": wayland_display,
        "xdg_runtime_dir": xdg_runtime_dir,
        "xauthority": xauthority,
        "tools": tools,
    }


def format_desktop_status(capabilities: dict) -> str:
    tool_lines = ", ".join(f"{name}={available}" for name, available in capabilities.get("tools", {}).items())
    lines = [
        "Desktop tool status:",
        f"enabled={capabilities.get('enabled')}",
        f"gui_available={capabilities.get('gui_available')}",
        f"DISPLAY={capabilities.get('display') or '(unset)'}",
        f"WAYLAND_DISPLAY={capabilities.get('wayland_display') or '(unset)'}",
        f"XDG_RUNTIME_DIR={capabilities.get('xdg_runtime_dir') or '(unset)'}",
        f"XAUTHORITY={capabilities.get('xauthority') or '(unset)'}",
        f"display_probe={capabilities.get('display_probe') or '(none)'}",
        f"tools: {tool_lines}",
    ]
    if not capabilities.get("gui_available"):
        lines.append("GUI display is not available to the local-agent container; command/status actions still work.")
    return "\n".join(lines)


def should_use_desktop(question: str, overrides: dict) -> bool:
    if overrides.get("desktop_action") or overrides.get("desktop_command"):
        return True
    lower = question.lower()
    return any(phrase in lower for phrase in ["desktop", "local app", "os control", "screen control", "take a screenshot"])


def desktop_command_from_overrides(overrides: dict) -> list[str] | None:
    command = overrides.get("desktop_command")
    if command is None:
        return None
    if isinstance(command, list):
        parts = [str(part) for part in command if str(part)]
    elif isinstance(command, str):
        parts = [part for part in command.strip().split() if part]
    else:
        return None
    return parts or None


def allowed_desktop_actions(overrides: dict) -> set[str]:
    actions = overrides.get("allowed_desktop_actions") or []
    if isinstance(actions, str):
        actions = [part.strip() for part in actions.split(",")]
    return {str(action).strip().lower() for action in actions if str(action).strip()}


def desktop_approval(action: str, command: list[str] | None, overrides: dict) -> tuple[bool, str, str | None]:
    approval_id = str(overrides.get("desktop_approval_id") or overrides.get("approval_id") or "").strip()
    if approval_id:
        approval = get_approval(approval_id)
        if not approval:
            return False, f"approval_not_found: {approval_id}", None
        approved, reason = approval_allows_desktop(approval, action, command)
        if approved:
            return True, reason, approval_id
        return False, reason, approval_id

    read_only = action in {"status", "list_windows"}
    if read_only:
        return True, "read_only", None

    if overrides.get("allow_desktop"):
        allowed = allowed_desktop_actions(overrides)
        if "*" in allowed or action.lower() in allowed:
            return True, "approved", None

    reason = "approval_required: desktop action needs review"
    approval = create_desktop_approval(action, command, reason)
    return False, f"{reason}: {approval_public_url(approval['id'])}", approval["id"]


def maybe_wait_for_desktop_approval(
    action: str,
    command: list[str] | None,
    overrides: dict,
    reason: str,
    approval_id: str | None,
    progress=None,
) -> tuple[bool, str, dict]:
    if not approval_id or not overrides.get("interactive_approval"):
        return False, reason, overrides

    wait_seconds = int(overrides.get("approval_timeout_seconds") or APPROVAL_WAIT_SECONDS)
    approval_url = approval_public_url(approval_id)
    if progress:
        progress(f"Desktop approval required: {approval_url}\n\n")
    approval = wait_for_approval(approval_id, wait_seconds)
    if not approval:
        return False, f"approval_timeout: {approval_url}", overrides
    approved, approval_reason = approval_allows_desktop(approval, action, command)
    if not approved:
        return False, approval_reason, overrides
    approved_overrides = dict(overrides)
    approved_overrides["desktop_approval_id"] = approval_id
    approved_overrides["allow_desktop"] = True
    approved_overrides["allowed_desktop_actions"] = sorted(set(allowed_desktop_actions(overrides)) | {action})
    return True, "approved_by_interactive_review", approved_overrides


def run_desktop_subprocess(command: list[str], timeout: int = DESKTOP_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        cwd=str(DESKTOP_DIR),
        env=os.environ.copy(),
    )


def run_desktop_command(command: list[str]) -> str:
    result = run_desktop_subprocess(command)
    output = []
    if result.stdout:
        output.append("stdout:\n" + result.stdout.strip()[:DESKTOP_COMMAND_MAX_OUTPUT])
    if result.stderr:
        output.append("stderr:\n" + result.stderr.strip()[:DESKTOP_COMMAND_MAX_OUTPUT])
    if result.returncode != 0:
        output.append(f"exit_code: {result.returncode}")
    return "\n\n".join(output).strip() or "(no output)"


def list_desktop_windows() -> str:
    if not desktop_capabilities().get("gui_available"):
        return format_desktop_status(desktop_capabilities())
    for command in (["wmctrl", "-l"], ["xprop", "-root", "_NET_CLIENT_LIST_STACKING"]):
        if command_exists(command[0]):
            try:
                return run_desktop_command(command)
            except Exception as exc:
                return str(exc)
    return "No supported window-listing tool is installed."


def desktop_screenshot() -> str:
    capabilities = desktop_capabilities()
    if not capabilities.get("gui_available"):
        return format_desktop_status(capabilities)

    screenshot_id = str(uuid.uuid4())
    path = SCREENSHOTS_DIR / f"{screenshot_id}.png"
    candidates = []
    if command_exists("gnome-screenshot"):
        candidates.append(["gnome-screenshot", "-f", str(path)])
    if command_exists("grim"):
        candidates.append(["grim", str(path)])
    if command_exists("scrot"):
        candidates.append(["scrot", str(path)])
    if command_exists("import"):
        candidates.append(["import", "-window", "root", str(path)])

    errors = []
    for command in candidates:
        try:
            result = run_desktop_subprocess(command)
            if result.returncode == 0 and path.exists() and path.stat().st_size > 8:
                return f"Desktop screenshot: {screenshot_public_url(screenshot_id)}"
            errors.append(f"{' '.join(command)}: exit={result.returncode}; stderr={result.stderr.strip()[:500]}")
        except Exception as exc:
            errors.append(f"{' '.join(command)}: {exc}")
    return "Desktop screenshot failed.\n" + ("\n".join(errors) if errors else "No supported screenshot tool is installed.")


def run_desktop_tool(question: str, overrides: dict, progress=None) -> Action:
    if not DESKTOP_ENABLED:
        return Action(kind="desktop", title="Desktop Tool", input="", output="Desktop tool is disabled.", status="failed")

    action = str(overrides.get("desktop_action") or "status").strip().lower()
    command = desktop_command_from_overrides(overrides)
    if action == "command" and not command:
        return Action(kind="desktop", title="Desktop Command", input="", output="desktop_command is required.", status="failed")

    approved, reason, approval_id = desktop_approval(action, command, overrides)
    if not approved:
        approved, reason, overrides = maybe_wait_for_desktop_approval(action, command, overrides, reason, approval_id, progress=progress)
    if not approved:
        output = reason
        if approval_id:
            output += f"\napproval_id: {approval_id}\napproval_url: {approval_public_url(approval_id)}"
        return Action(kind="desktop", title="Desktop Approval Required", input=" ".join(command or [action]), output=output, status="approval_required")

    try:
        if action == "status":
            return Action(kind="desktop", title="Desktop Status", input=question, output=format_desktop_status(desktop_capabilities()))
        if action == "list_windows":
            return Action(kind="desktop", title="Desktop Windows", input=question, output=list_desktop_windows())
        if action == "screenshot":
            return Action(kind="desktop", title="Desktop Screenshot", input=question, output=desktop_screenshot())
        if action == "command":
            return Action(kind="desktop", title="Desktop Command", input=" ".join(command or []), output=run_desktop_command(command or []))
        return Action(kind="desktop", title="Desktop Tool", input=action, output=f"Unsupported desktop_action: {action}", status="failed")
    except Exception as exc:
        return Action(kind="desktop", title="Desktop Tool", input=" ".join(command or [action]), output=str(exc), status="failed")


def source_pack(run_dir: Path, run_id: str, question: str, actions: list[Action], answer: str):
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "question": question,
        "created_at": now(),
        "actions": [asdict(action) for action in actions],
        "answer": answer,
    }
    (run_dir / "agent-run.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Agent Run: {run_id}", "", f"Question: {question}", "", "## Actions", ""]
    for index, action in enumerate(actions, start=1):
        lines.extend(
            [
                f"### A{index}. {action.title}",
                f"- Kind: {action.kind}",
                f"- Status: {action.status}",
                "",
                "Input:",
                "",
                f"```text\n{action.input}\n```",
                "",
                "Output:",
                "",
                f"```text\n{action.output}\n```",
                "",
            ]
        )
    lines.extend(["## Final Answer", "", answer])
    (run_dir / "agent-run.md").write_text("\n".join(lines), encoding="utf-8")


def synthesize(question: str, actions: list[Action], overrides: dict) -> str:
    if not actions:
        return "I did not need to call tools for this request."
    if overrides.get("synthesize") is False:
        lines = ["Agent actions completed:"]
        for index, action in enumerate(actions, start=1):
            lines.append(f"- A{index} {action.kind}: {action.output[:500]}")
        return "\n".join(lines)

    evidence = []
    for index, action in enumerate(actions, start=1):
        evidence.append(f"A{index} {action.kind} ({action.title})\nInput: {action.input}\nOutput: {action.output[:1800]}")
    prompt = (
        "You are a local agent. Answer the user using only the tool results below. "
        "Call out any tool failures or uncertainty. Keep the answer concise.\n\n"
        f"User request:\n{question}\n\nTool results:\n" + "\n\n".join(evidence)
    )
    try:
        return glm_chat(
            [
                {"role": "system", "content": "You are a careful local tool-using agent."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=int(overrides.get("max_tokens", 512)),
            temperature=0.2,
        )
    except Exception as exc:
        fallback = "\n".join(f"- {action.kind}: {action.output[:500]}" for action in actions)
        return f"Agent tools completed, but GLM synthesis failed: {exc}\n\n{fallback}"


def run_agent(question: str, overrides: dict | None = None, progress=None) -> str:
    overrides = overrides or {}
    run_id = str(uuid.uuid4())
    run_dir = STORAGE / "runs" / run_id
    actions: list[Action] = []

    def say(message: str):
        if progress:
            progress(message)

    say(f"Agent run `{run_id}` started.\n\n")

    code = overrides.get("python_code") or python_code_for(question)
    if code:
        say("Running local Python tool.\n\n")
        try:
            output = run_python(str(code))
            actions.append(Action(kind="python", title="Run Python", input=str(code), output=output))
        except Exception as exc:
            actions.append(Action(kind="python", title="Run Python", input=str(code), output=str(exc), status="failed"))

    if should_search(question, overrides):
        query = str(overrides.get("query") or question)
        count = int(overrides.get("search_results", 5))
        say(f"Searching web for `{query}`.\n\n")
        try:
            results = search_web(query, count)
            output = "\n".join(f"- {item['title']}: {item['url']}\n  {item['snippet']}" for item in results) or "No results"
            actions.append(Action(kind="web_search", title="Search Web", input=query, output=output))
            if overrides.get("fetch_first") and results:
                first = results[0]["url"]
                say(f"Reading first search result: {first}\n\n")
                text = fetch_url(first)[:3000]
                actions.append(Action(kind="fetch_url", title="Fetch URL", input=first, output=text or "No text extracted"))
        except Exception as exc:
            actions.append(Action(kind="web_search", title="Search Web", input=query, output=str(exc), status="failed"))

    if should_check_scheduler(question, overrides):
        say("Checking local scheduler state.\n\n")
        try:
            state = http_json(f"{SCHEDULER_URL}/health", timeout=20)
            actions.append(Action(kind="scheduler", title="Check Scheduler", input=SCHEDULER_URL, output=json.dumps(state)))
        except Exception as exc:
            actions.append(Action(kind="scheduler", title="Check Scheduler", input=SCHEDULER_URL, output=str(exc), status="failed"))

    if should_use_browser(question, overrides):
        say("Using local browser-control tool.\n\n")
        try:
            actions.append(run_browser_tool(question, overrides, progress=say))
        except Exception as exc:
            actions.append(Action(kind="browser", title="Browser Tool", input=str(overrides.get("browser_url", "")), output=str(exc), status="failed"))

    if should_use_desktop(question, overrides):
        say("Using local desktop-control tool.\n\n")
        try:
            actions.append(run_desktop_tool(question, overrides, progress=say))
        except Exception as exc:
            actions.append(Action(kind="desktop", title="Desktop Tool", input=str(overrides.get("desktop_action", "")), output=str(exc), status="failed"))

    answer = synthesize(question, actions, overrides)
    source_pack(run_dir, run_id, question, actions, answer)
    md_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/agent-run.md"
    json_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/agent-run.json"
    return answer + f"\n\nAgent run: [Markdown]({md_url}) | [JSON]({json_url})"


def chunk_payload(content: str, finish_reason=None, model: str = MODEL_ID) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "created": now(),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": content} if content else {}, "finish_reason": finish_reason}],
    }


def model_cards() -> list[dict]:
    local_agent_card = {
        "id": MODEL_ID,
        "name": MODEL_ID,
        "object": "model",
        "created": now(),
        "owned_by": "local",
        "connection_type": "local",
        "info": {
            "id": MODEL_ID,
            "name": "Local Agent - GLM 5.2",
            "meta": {
                "description": "Local GLM-backed agent with Python, search, scheduler, browser, Playwright, and approval-gated desktop/system tools.",
                "capabilities": {
                    "web_search": True,
                    "code_interpreter": True,
                    "browser": True,
                    "desktop_control": DESKTOP_ENABLED,
                    "requires_approval": True,
                },
            },
        },
    }
    auto_router_card = {
        "id": AUTO_ROUTER_MODEL_ID,
        "name": AUTO_ROUTER_MODEL_ID,
        "object": "model",
        "created": now(),
        "owned_by": "local",
        "connection_type": "local",
        "info": {
            "id": AUTO_ROUTER_MODEL_ID,
            "name": "Local Auto Router",
            "meta": {
                "description": "Local additive auto-router for fast chat, coding, research, tool-agent, and GLM 5.2 reasoning routes.",
                "capabilities": {
                    "auto_routing": True,
                    "fast_model": AUTO_ROUTER_FAST_MODEL,
                    "coding_model": AUTO_ROUTER_CODE_MODEL,
                    "research_model": AUTO_ROUTER_RESEARCH_MODEL,
                    "agent_model": AUTO_ROUTER_AGENT_MODEL,
                    "reasoning_model": GLM_MODEL,
                    "telemetry_endpoint": "/api/auto-router/events",
                    "glm_cold_fallback": AUTO_ROUTER_GLM_COLD_FALLBACK,
                    "glm_warm_min_decoded_tokens": AUTO_ROUTER_GLM_WARM_MIN_DECODED,
                    "local_only": True,
                },
            },
        },
    }
    return [local_agent_card, auto_router_card]


class Handler(BaseHTTPRequestHandler):
    server_version = "openwebui-local-agent/0.2"

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), fmt % args), flush=True)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed_path = parse.urlparse(self.path)
        path = parsed_path.path
        query = parse.parse_qs(parsed_path.query)
        if path == "/health":
            return send_json(
                self,
                200,
                {
                    "status": "ok",
                    "model": MODEL_ID,
                    "desktop": desktop_capabilities(),
                },
            )
        if path == "/approvals":
            return send_html(self, approval_page_html())
        if path == "/api/approvals":
            status = (query.get("status") or [None])[0]
            return send_json(self, 200, {"approvals": list_approvals(status=status)})
        if path == "/api/auto-router/events":
            return send_json(self, 200, list_auto_router_events(query))
        screenshot_match = re.match(r"^/screenshots/([a-f0-9-]{36})\.png$", path)
        if screenshot_match:
            screenshot_path = SCREENSHOTS_DIR / f"{screenshot_match.group(1)}.png"
            if not screenshot_path.exists():
                return send_json(self, 404, {"error": "not found"})
            return send_binary(self, screenshot_path.read_bytes(), "image/png")
        approval_match = re.match(r"^/approvals/([a-f0-9-]{36})$", path)
        if approval_match:
            approval = get_approval(approval_match.group(1))
            if not approval:
                return send_json(self, 404, {"error": "not found"})
            return send_html(self, approval_page_html(approval))
        approval_api_match = re.match(r"^/api/approvals/([a-f0-9-]{36})$", path)
        if approval_api_match:
            approval = get_approval(approval_api_match.group(1))
            if not approval:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"approval": approval})
        fixture = browser_fixture(path)
        if fixture is not None:
            return send_html(self, fixture)
        if path in {"/v1/models", "/models"}:
            cards = model_cards()
            return send_json(
                self,
                200,
                {
                    "object": "list",
                    "data": cards,
                    "models": [
                        {"name": card["id"], "model": card["id"], "type": "model", "info": card["info"]}
                        for card in cards
                    ],
                },
            )
        match = re.match(r"^/runs/([^/]+)/(agent-run\.(?:md|json))$", path)
        if match:
            run_id, filename = match.groups()
            file_path = STORAGE / "runs" / run_id / filename
            if not file_path.exists():
                return send_json(self, 404, {"error": "not found"})
            body = file_path.read_bytes()
            content_type = "application/json" if filename.endswith(".json") else "text/markdown; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        return send_json(self, 404, {"error": "not found"})

    def do_POST(self):
        path = parse.urlparse(self.path).path
        approval_action_match = re.match(r"^/(api/)?approvals/([a-f0-9-]{36})/(approve|deny)$", path)
        if approval_action_match:
            is_api = bool(approval_action_match.group(1))
            approval_id = approval_action_match.group(2)
            decision = "approved" if approval_action_match.group(3) == "approve" else "denied"
            try:
                approval = update_approval_status(approval_id, decision)
            except FileNotFoundError:
                return send_json(self, 404, {"error": "not found"})
            except Exception as exc:
                return send_json(self, 400, {"error": str(exc)})
            if is_api:
                return send_json(self, 200, {"approval": approval})
            return send_redirect(self, f"/approvals/{approval_id}")

        if path not in {"/v1/chat/completions", "/chat/completions"}:
            return send_json(self, 404, {"error": "not found"})
        try:
            payload = read_json(self)
            question = last_user_message(payload).strip()
            if not question:
                return send_json(self, 400, {"error": {"message": "No user message found"}})
            requested_model = payload.get("model") or MODEL_ID
            if requested_model == AUTO_ROUTER_MODEL_ID:
                data = auto_router_chat(payload, question)
                if payload.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    event = "data: " + json.dumps(chunk_payload(content, model=AUTO_ROUTER_MODEL_ID), ensure_ascii=False) + "\n\n"
                    self.wfile.write(event.encode("utf-8"))
                    done = (
                        "data: "
                        + json.dumps(chunk_payload("", "stop", model=AUTO_ROUTER_MODEL_ID), ensure_ascii=False)
                        + "\n\n"
                        + "data: [DONE]\n\n"
                    )
                    self.wfile.write(done.encode("utf-8"))
                    self.wfile.flush()
                    return
                return send_json(self, 200, data)
            overrides = payload.get("local_agent") or payload.get("metadata", {}).get("local_agent") or {}
            if overrides.get("echo_system_messages"):
                answer = "Received system messages:\n" + json.dumps(system_messages(payload), ensure_ascii=False)
                return send_json(
                    self,
                    200,
                    {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                        "object": "chat.completion",
                        "created": now(),
                        "model": MODEL_ID,
                        "choices": [
                            {"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}
                        ],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    },
                )
            if overrides.get("echo_messages"):
                answer = "Received messages:\n" + json.dumps(message_summaries(payload), ensure_ascii=False)
                return send_json(
                    self,
                    200,
                    {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                        "object": "chat.completion",
                        "created": now(),
                        "model": MODEL_ID,
                        "choices": [
                            {"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}
                        ],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    },
                )
            if payload.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                def emit(text: str):
                    event = "data: " + json.dumps(chunk_payload(text), ensure_ascii=False) + "\n\n"
                    self.wfile.write(event.encode("utf-8"))
                    self.wfile.flush()

                answer = run_agent(question, overrides=overrides, progress=emit)
                emit(answer)
                done = "data: " + json.dumps(chunk_payload("", "stop")) + "\n\n" + "data: [DONE]\n\n"
                self.wfile.write(done.encode("utf-8"))
                self.wfile.flush()
                return

            answer = run_agent(question, overrides=overrides)
            return send_json(
                self,
                200,
                {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                    "object": "chat.completion",
                    "created": now(),
                    "model": MODEL_ID,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                },
            )
        except BrokenPipeError:
            return
        except Exception as exc:
            return send_json(self, 500, {"error": {"message": str(exc), "type": "server_error"}})


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"local agent listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
