#!/usr/bin/env python3
import base64
import html
import io
import json
import os
import re
import textwrap
import time
import uuid
import zipfile
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib import parse, request, error


MODEL_ID = os.environ.get("DEEP_RESEARCH_MODEL_ID", "deep-research-glm52")
GLM_MODEL = os.environ.get("DEEP_RESEARCH_MODEL", "glm52-q4-local")
GLM_BASE_URL = os.environ.get("DEEP_RESEARCH_GLM_BASE_URL", "http://127.0.0.1:11441/v1")
SEARXNG_URL = os.environ.get("DEEP_RESEARCH_SEARXNG_URL", "http://127.0.0.1:18080/search")
TIKA_URL = os.environ.get("DEEP_RESEARCH_TIKA_URL", "http://127.0.0.1:9998/tika")
LOCAL_APP_CONNECTOR_URL = os.environ.get("DEEP_RESEARCH_LOCAL_APP_CONNECTOR_URL", "http://127.0.0.1:18042")
PUBLIC_BASE_URL = os.environ.get("DEEP_RESEARCH_PUBLIC_BASE_URL", "http://127.0.0.1:18041")
STORAGE = Path(os.environ.get("DEEP_RESEARCH_STORAGE", "/data"))
MAX_QUERIES = int(os.environ.get("DEEP_RESEARCH_MAX_QUERIES", "12"))
MAX_RESULTS = int(os.environ.get("DEEP_RESEARCH_MAX_RESULTS", "120"))
MAX_SOURCES = int(os.environ.get("DEEP_RESEARCH_MAX_SOURCES", "40"))
MAX_SNIPPETS = int(os.environ.get("DEEP_RESEARCH_MAX_SNIPPETS", "28"))
MAX_TOKENS = int(os.environ.get("DEEP_RESEARCH_MAX_TOKENS", "1600"))
MAX_EXCERPT_CHARS = int(os.environ.get("DEEP_RESEARCH_MAX_EXCERPT_CHARS", "1600"))
MAX_LOCAL_DOCUMENTS = int(os.environ.get("DEEP_RESEARCH_MAX_LOCAL_DOCUMENTS", "20"))
MAX_CONNECTOR_SOURCES = int(os.environ.get("DEEP_RESEARCH_MAX_CONNECTOR_SOURCES", "12"))
MAX_DOCUMENT_CHARS = int(os.environ.get("DEEP_RESEARCH_MAX_DOCUMENT_CHARS", "200000"))
FETCH_TIMEOUT = int(os.environ.get("DEEP_RESEARCH_FETCH_TIMEOUT_SECONDS", "20"))
GLM_TIMEOUT = int(os.environ.get("DEEP_RESEARCH_GLM_TIMEOUT_SECONDS", "21600"))
MAX_FETCH_BYTES = int(os.environ.get("DEEP_RESEARCH_MAX_FETCH_BYTES", str(3 * 1024 * 1024)))

LLM_LOCK = Lock()
STORAGE.mkdir(parents=True, exist_ok=True)


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

    def text(self):
        return "\n".join(self.parts)


@dataclass
class Source:
    sid: str
    title: str
    url: str
    engine: str = ""
    score: float = 0.0
    snippet: str = ""
    fetched: bool = False
    error: str = ""
    text_chars: int = 0
    excerpts: list[str] = None

    def __post_init__(self):
        if self.excerpts is None:
            self.excerpts = []


def now() -> int:
    return int(time.time())


def int_setting(overrides: dict, key: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        value = int(overrides.get(key, default))
    except (TypeError, ValueError):
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(value, maximum)
    return value


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


def send_bytes(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str):
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def http_json(url: str, payload: dict | None = None, timeout: int = 60, headers: dict | None = None) -> dict:
    data = None
    req_headers = {"User-Agent": "openwebui-deep-research/0.1"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=req_headers)
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def http_bytes(url: str, timeout: int = FETCH_TIMEOUT) -> tuple[bytes, str]:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0 openwebui-deep-research/0.1"})
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


def tika_extract(raw: bytes, content_type: str) -> str:
    req = request.Request(TIKA_URL, data=raw, method="PUT", headers={"Content-Type": content_type})
    with request.urlopen(req, timeout=max(60, FETCH_TIMEOUT)) as resp:
        return resp.read().decode("utf-8", errors="replace")


def html_to_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    parser = TextExtractor()
    parser.feed(text)
    return clean_text(parser.text())


def clean_text(text: str) -> str:
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sentence_split(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [clean_text(x) for x in chunks if len(clean_text(x)) > 40]


def terms(question: str) -> set[str]:
    stop = {
        "about", "after", "again", "against", "also", "because", "before", "being", "between", "could", "does",
        "from", "have", "into", "more", "most", "over", "should", "than", "that", "their", "there", "these",
        "this", "through", "what", "when", "where", "which", "while", "with", "would", "your", "deep", "research",
    }
    return {w for w in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,}", question.lower()) if w not in stop}


def score_text(text: str, wanted: set[str]) -> float:
    if not text or not wanted:
        return 0.0
    lower = text.lower()
    hits = sum(1 for term in wanted if term in lower)
    return hits / max(1, len(wanted))


def make_queries(question: str, limit: int) -> list[str]:
    base = clean_text(question)
    variants = [
        base,
        f"{base} primary source",
        f"{base} official documentation",
        f"{base} data report",
        f"{base} analysis",
        f"{base} criticism limitations",
        f"{base} controversy",
        f"{base} recent developments",
        f"{base} statistics",
        f"{base} expert review",
        f"{base} site:gov OR site:edu",
        f"{base} filetype:pdf",
    ]
    result = []
    for query in variants:
        if query not in result:
            result.append(query)
    return result[:limit]


def normalize_sites(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        items = re.split(r"[\s,]+", value)
    elif isinstance(value, list):
        items = value
    else:
        return []

    sites = []
    for item in items:
        text = str(item).strip().lower()
        if not text:
            continue
        parsed = parse.urlparse(text if "://" in text else f"https://{text}")
        host = (parsed.netloc or parsed.path.split("/", 1)[0]).split("@")[-1].split(":", 1)[0]
        host = host.removeprefix("www.")
        if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host) and host not in sites:
            sites.append(host)
    return sites


def source_host(url: str) -> str:
    try:
        host = parse.urlparse(url).netloc.lower().split("@")[-1].split(":", 1)[0]
        return host.removeprefix("www.")
    except Exception:
        return ""


def matches_site(url: str, sites: list[str]) -> bool:
    host = source_host(url)
    return any(host == site or host.endswith(f".{site}") for site in sites)


def source_policy(overrides: dict) -> dict:
    include_sites = normalize_sites(
        overrides.get("sites")
        or overrides.get("include_sites")
        or overrides.get("allowed_sites")
        or overrides.get("domains")
    )
    exclude_sites = normalize_sites(overrides.get("exclude_sites") or overrides.get("blocked_sites"))
    mode = str(overrides.get("site_mode") or overrides.get("source_mode") or "").strip().lower()
    if not mode:
        mode = "restrict" if include_sites and overrides.get("restrict_sites") else "prioritize" if include_sites else "default"
    if mode not in {"default", "restrict", "prioritize"}:
        mode = "default"
    if not include_sites and mode in {"restrict", "prioritize"}:
        mode = "default"
    return {
        "mode": mode,
        "include_sites": include_sites,
        "exclude_sites": exclude_sites,
        "description": (
            "Restrict to listed sites"
            if mode == "restrict"
            else "Prioritize listed sites while allowing the broader web"
            if mode == "prioritize"
            else "Use broad local web search"
        ),
    }


def make_policy_queries(question: str, limit: int, policy: dict) -> list[str]:
    if limit <= 0:
        return []

    include_sites = policy.get("include_sites") or []
    mode = policy.get("mode")
    site_expr = " OR ".join(f"site:{site}" for site in include_sites[:8])

    if include_sites and mode == "restrict":
        base_queries = make_queries(question, limit)
        return [f"{query} {site_expr}" for query in base_queries][:limit]

    if include_sites and mode == "prioritize":
        mixed = []
        for query in make_queries(question, limit):
            mixed.append(f"{query} {site_expr}")
            mixed.append(query)
            if len(mixed) >= limit:
                break
        return mixed[:limit]

    return make_queries(question, limit)


def document_inputs(overrides: dict) -> list[dict]:
    raw = (
        overrides.get("documents")
        or overrides.get("files")
        or overrides.get("local_documents")
        or overrides.get("local_sources")
        or []
    )
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)][:MAX_LOCAL_DOCUMENTS]


def document_text(item: dict) -> str:
    for key in ("text", "content", "body", "markdown"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return clean_text(value)[:MAX_DOCUMENT_CHARS]

    encoded = item.get("content_base64") or item.get("data_base64")
    if isinstance(encoded, str) and encoded.strip():
        try:
            raw = base64.b64decode(encoded, validate=True)
            content_type = str(item.get("content_type") or item.get("mime_type") or "text/plain").split(";")[0]
            if content_type in {"text/html", "application/xhtml+xml"}:
                return html_to_text(raw)[:MAX_DOCUMENT_CHARS]
            if content_type.startswith("text/"):
                return clean_text(raw.decode("utf-8", errors="replace"))[:MAX_DOCUMENT_CHARS]
            return clean_text(tika_extract(raw, content_type))[:MAX_DOCUMENT_CHARS]
        except Exception:
            return ""
    return ""


def document_plan_items(overrides: dict) -> list[dict]:
    items = []
    for index, item in enumerate(document_inputs(overrides), start=1):
        title = clean_text(str(item.get("title") or item.get("name") or item.get("filename") or f"Local document {index}"))
        text = document_text(item)
        if text:
            items.append(
                {
                    "title": title[:220],
                    "chars": len(text),
                    "source": clean_text(str(item.get("url") or item.get("source") or f"local-document://{index}"))[:500],
                }
            )
    return items


def local_document_sources(overrides: dict, wanted: set[str]) -> list[Source]:
    sources = []
    for index, item in enumerate(document_inputs(overrides), start=1):
        text = document_text(item)
        if not text:
            continue
        title = clean_text(str(item.get("title") or item.get("name") or item.get("filename") or f"Local document {index}"))
        source = Source(
            sid=f"D{len(sources) + 1}",
            title=title[:220],
            url=clean_text(str(item.get("url") or item.get("source") or f"local-document://{index}"))[:500],
            engine="local-document",
            score=1.0,
            snippet=text[:800],
            fetched=True,
            text_chars=len(text),
        )
        candidates = sentence_split(text[:MAX_DOCUMENT_CHARS])
        candidates.sort(key=lambda sentence: score_text(sentence, wanted), reverse=True)
        source.excerpts = candidates[:5] or [text[:1000]]
        sources.append(source)
    return sources


def connector_inputs(overrides: dict, question: str) -> list[dict]:
    raw = []
    for key in ("connectors", "apps", "connector_sources", "local_app_connectors"):
        value = overrides.get(key)
        if value:
            raw = value
            break

    explicit = overrides.get("local_app_search")
    if explicit:
        if isinstance(raw, list):
            raw = [*raw, explicit]
        elif raw:
            raw = [raw, explicit]
        else:
            raw = explicit

    if raw is True:
        raw = [{"type": "local_app", "query": question}]
    elif isinstance(raw, dict):
        raw = [raw]
    elif isinstance(raw, str):
        raw = [{"type": "local_app", "query": raw}]
    elif not isinstance(raw, list):
        raw = []

    connectors = []
    for item in raw:
        if item is True:
            item = {"type": "local_app", "query": question}
        elif isinstance(item, str):
            item = {"type": "local_app", "query": item}
        if not isinstance(item, dict):
            continue
        connector_type = str(item.get("type") or item.get("connector") or "local_app").strip().lower()
        if connector_type not in {"local_app", "local-app", "local_app_connector", "local-app-connector"}:
            continue
        query = clean_text(str(item.get("query") or item.get("q") or question))
        if not query:
            continue
        connectors.append(
            {
                "type": "local_app",
                "query": query,
                "limit": max(1, min(MAX_CONNECTOR_SOURCES, int(item.get("limit") or item.get("max_results") or 5))),
                "url": str(item.get("url") or LOCAL_APP_CONNECTOR_URL).rstrip("/"),
            }
        )
        if len(connectors) >= MAX_CONNECTOR_SOURCES:
            break
    return connectors


def connector_plan_items(overrides: dict, question: str) -> list[dict]:
    return [
        {
            "type": item["type"],
            "query": item["query"],
            "limit": item["limit"],
            "url": item["url"],
        }
        for item in connector_inputs(overrides, question)
    ]


def local_app_note_text(connector_url: str, item: dict) -> str:
    note_id = item.get("id")
    if item.get("source") == "local-app-note" and note_id:
        try:
            note = http_json(f"{connector_url}/local-app/notes/{parse.quote(str(note_id))}", timeout=30).get("note", {})
            text = note.get("content") or item.get("snippet") or ""
            tags = note.get("tags") if isinstance(note.get("tags"), list) else []
            return clean_text("\n".join([str(text), " ".join(str(tag) for tag in tags)]))
        except Exception:
            pass
    return clean_text(str(item.get("snippet") or ""))


def connector_sources(overrides: dict, question: str, wanted: set[str]) -> list[Source]:
    sources = []
    seen = set()
    for connector in connector_inputs(overrides, question):
        params = parse.urlencode({"q": connector["query"], "limit": connector["limit"]})
        try:
            items = http_json(f"{connector['url']}/local-app/search?{params}", timeout=30).get("data", [])
        except Exception:
            continue
        for item in items:
            source_key = f"{item.get('source')}:{item.get('id')}"
            if source_key in seen:
                continue
            seen.add(source_key)
            text = local_app_note_text(connector["url"], item)
            if not text:
                continue
            title = clean_text(str(item.get("title") or source_key or "Local app connector item"))[:220]
            url = clean_text(str(item.get("url") or f"local-app://{source_key}"))[:500]
            source = Source(
                sid=f"C{len(sources) + 1}",
                title=title,
                url=url,
                engine=f"local-app-connector:{item.get('source') or 'item'}",
                score=1.0,
                snippet=text[:800],
                fetched=True,
                text_chars=len(text),
            )
            candidates = sentence_split(text[:MAX_DOCUMENT_CHARS])
            candidates.sort(key=lambda sentence: score_text(sentence, wanted), reverse=True)
            source.excerpts = candidates[:5] or [text[:1000]]
            sources.append(source)
            if len(sources) >= MAX_CONNECTOR_SOURCES:
                return sources
    return sources


def build_plan(question: str, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    max_queries = int_setting(overrides, "max_queries", MAX_QUERIES)
    policy = source_policy(overrides)
    raw_queries = overrides.get("queries")
    if isinstance(raw_queries, list) and raw_queries:
        queries = [clean_text(str(query)) for query in raw_queries if clean_text(str(query))][:max_queries]
    else:
        queries = make_policy_queries(question, max_queries, policy)
    return {
        "question": question,
        "created_at": now(),
        "queries": queries,
        "source_policy": policy,
        "local_documents": document_plan_items(overrides),
        "local_connectors": connector_plan_items(overrides, question),
        "limits": {
            "max_queries": max_queries,
            "max_results": int_setting(overrides, "max_results", MAX_RESULTS),
            "max_sources": int_setting(overrides, "max_sources", MAX_SOURCES),
            "max_local_documents": min(MAX_LOCAL_DOCUMENTS, len(document_inputs(overrides))),
            "max_connector_sources": MAX_CONNECTOR_SOURCES,
            "max_document_chars": MAX_DOCUMENT_CHARS,
            "max_snippets": int_setting(overrides, "max_snippets", MAX_SNIPPETS, minimum=1),
            "max_tokens": int_setting(overrides, "max_tokens", MAX_TOKENS, minimum=1, maximum=8192),
            "max_excerpt_chars": int_setting(
                overrides, "max_excerpt_chars", MAX_EXCERPT_CHARS, minimum=80, maximum=10_000
            ),
        },
        "review_checklist": [
            "Confirm the question, constraints, and expected output.",
            "Confirm whether the listed sites should be restricted, prioritized, or ignored.",
            "Confirm whether local documents should be included as private sources.",
            "Confirm whether local app connector sources should be included as private sources.",
            "Increase max_sources or max_tokens for broader reports; lower them for faster local runs.",
        ],
    }


def searxng_search(query: str, count: int) -> list[dict]:
    params = parse.urlencode({"q": query, "format": "json", "language": "all"})
    data = http_json(f"{SEARXNG_URL}?{params}", timeout=45)
    return data.get("results", [])[:count]


def dedupe_sources(results: list[dict], max_sources: int, policy: dict | None = None) -> list[Source]:
    if max_sources <= 0:
        return []

    policy = policy or {}
    mode = policy.get("mode", "default")
    include_sites = policy.get("include_sites") or []
    exclude_sites = policy.get("exclude_sites") or []
    seen = set()
    sources = []
    for item in results:
        url = item.get("url") or item.get("parsed_url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        normalized = re.sub(r"#.*$", "", url)
        if exclude_sites and matches_site(normalized, exclude_sites):
            continue
        if mode == "restrict" and include_sites and not matches_site(normalized, include_sites):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        sid = f"S{len(sources) + 1}"
        sources.append(
            Source(
                sid=sid,
                title=clean_text(item.get("title") or normalized)[:220],
                url=normalized,
                engine=str(item.get("engine") or ""),
                score=float(item.get("score") or 0.0),
                snippet=clean_text(item.get("content") or item.get("snippet") or "")[:800],
            )
        )
        if len(sources) >= max_sources:
            break
    return sources


def fetch_source(source: Source, wanted: set[str]):
    try:
        raw, content_type = http_bytes(source.url)
        if content_type in {"text/html", "application/xhtml+xml"}:
            text = html_to_text(raw)
        elif content_type.startswith("text/"):
            text = clean_text(raw.decode("utf-8", errors="replace"))
        else:
            text = clean_text(tika_extract(raw, content_type))
        source.fetched = bool(text)
        source.text_chars = len(text)
        candidates = sentence_split(text[:200_000])
        candidates.sort(key=lambda sentence: score_text(sentence, wanted), reverse=True)
        source.excerpts = candidates[:5] or ([text[:1000]] if text else [])
    except Exception as exc:
        source.error = str(exc)[:500]


def glm_chat(messages: list[dict], max_tokens: int = 1024, temperature: float = 0.2) -> str:
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


def report_markdown(
    run_id: str,
    question: str,
    plan: dict,
    activity: list[dict],
    sources: list[Source],
    answer: str,
    review: dict | None = None,
    citation_audit: dict | None = None,
) -> str:
    created = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(plan.get("created_at") or now()))
    policy = plan.get("source_policy") or {}
    limits = plan.get("limits") or {}
    lines = [
        f"# Deep Research Report: {run_id}",
        "",
        f"Created: {created}",
        "",
        "## Question",
        "",
        question,
        "",
        "## Research Plan",
        "",
        f"- Source mode: {policy.get('mode', 'default')} ({policy.get('description', 'Use broad local web search')})",
        f"- Include sites: {', '.join(policy.get('include_sites') or []) or '(none)'}",
        f"- Exclude sites: {', '.join(policy.get('exclude_sites') or []) or '(none)'}",
        f"- Limits: {json.dumps(limits, sort_keys=True)}",
        "",
        "### Local Documents",
        "",
    ]
    local_documents = plan.get("local_documents") or []
    if local_documents:
        for document in local_documents:
            lines.append(f"- {document.get('title')} ({document.get('chars')} chars, {document.get('source')})")
    else:
        lines.append("- (none)")
    lines.extend(["", "### Local App Connectors", ""])
    local_connectors = plan.get("local_connectors") or []
    if local_connectors:
        for connector in local_connectors:
            lines.append(
                f"- {connector.get('type')} query `{connector.get('query')}` "
                f"(limit {connector.get('limit')}, {connector.get('url')})"
            )
    else:
        lines.append("- (none)")
    lines.extend([
        "",
        "### Queries",
        "",
    ])
    lines.extend([f"- {query}" for query in plan.get("queries", [])] or ["- (no search queries; local dry run)"])
    lines.extend(["", "## Activity History", ""])
    if activity:
        for event in activity:
            timestamp = time.strftime("%H:%M:%S", time.gmtime(event.get("ts") or now()))
            phase = event.get("phase", "step")
            lines.append(f"- {timestamp} [{phase}] {event.get('message', '')}")
    else:
        lines.append("- (no activity recorded)")
    if review:
        updated_at = int(review.get("updated_at") or 0)
        updated = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(updated_at)) if updated_at else "(unknown)"
        lines.extend(
            [
                "",
                "## Review",
                "",
                f"- Status: {review.get('status', 'reviewed')}",
                f"- Revision count: {review.get('revision_count', 0)}",
                f"- Updated: {updated}",
                f"- Reviewer: {review.get('reviewer') or '(local user)'}",
                f"- Note: {review.get('note') or '(none)'}",
            ]
        )
    if citation_audit:
        lines.extend(
            [
                "",
                "## Citation Audit",
                "",
                f"- Status: {citation_audit.get('status', 'unknown')}",
                f"- Citation count: {citation_audit.get('citation_count', 0)}",
                f"- Valid citations: {', '.join(citation_audit.get('valid_citation_ids') or []) or '(none)'}",
                f"- Invalid citations: {', '.join(citation_audit.get('invalid_citation_ids') or []) or '(none)'}",
                f"- Uncited sources: {', '.join(citation_audit.get('uncited_source_ids') or []) or '(none)'}",
            ]
        )
    lines.extend(["", "## Answer", "", answer, "", "## Sources Used", ""])
    if sources:
        for source in sources:
            status = "fetched" if source.fetched else f"failed: {source.error or 'not fetched'}"
            lines.append(f"- [{source.sid}] {source.title} - {source.url} ({status}, {source.text_chars} chars)")
    else:
        lines.append("- (no sources used)")
    return "\n".join(lines).strip() + "\n"


def html_text_block(text: str) -> str:
    escaped = html.escape(text or "")
    paragraphs = []
    for block in re.split(r"\n{2,}", escaped):
        block = block.strip()
        if not block:
            continue
        paragraphs.append(f"<p>{block.replace(chr(10), '<br>')}</p>")
    return "\n".join(paragraphs) or "<p>No content.</p>"


def report_html(
    run_id: str,
    question: str,
    plan: dict,
    activity: list[dict],
    sources: list[Source],
    answer: str,
    markdown: str,
    review: dict | None = None,
    citation_audit: dict | None = None,
) -> str:
    created = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(plan.get("created_at") or now()))
    policy = plan.get("source_policy") or {}
    limits = plan.get("limits") or {}
    local_documents = plan.get("local_documents") or []
    local_connectors = plan.get("local_connectors") or []
    queries = plan.get("queries") or []
    review = review or {}
    review_status = str(review.get("status") or "unreviewed")

    def link(filename: str, label: str) -> str:
        return f'<a href="{html.escape(filename)}" download>{html.escape(label)}</a>'

    download_links = " ".join(
        [
            link("report.md", "Markdown"),
            link("report.html", "HTML"),
            link("report.docx", "Word DOCX"),
            link("report.doc", "Word DOC"),
            link("report.pdf", "PDF"),
            link("report-bundle.zip", "Bundle ZIP"),
            link("source-pack.json", "JSON"),
            link("citation-audit.json", "Citation Audit"),
            link("activity.json", "Activity"),
        ]
    )

    source_cards = []
    for source in sources:
        status = "Fetched" if source.fetched else f"Failed: {source.error or 'not fetched'}"
        excerpt = source.excerpts[0] if source.excerpts else source.snippet
        source_cards.append(
            "\n".join(
                [
                    '<article class="source-card" data-source-id="' + html.escape(source.sid) + '">',
                    '<div class="source-card__head">',
                    f"<span>{html.escape(source.sid)}</span>",
                    f"<strong>{html.escape(source.title)}</strong>",
                    "</div>",
                    f'<a href="{html.escape(source.url)}">{html.escape(source.url)}</a>',
                    f"<p>{html.escape(status)} · {source.text_chars} chars · {html.escape(source.engine or 'source')}</p>",
                    f"<blockquote>{html.escape((excerpt or '')[:900])}</blockquote>",
                    "</article>",
                ]
            )
        )
    if not source_cards:
        source_cards.append('<p class="empty">No source excerpts were used for this dry-run report.</p>')

    activity_items = []
    for event in activity:
        timestamp = time.strftime("%H:%M:%S", time.gmtime(event.get("ts") or now()))
        activity_items.append(
            '<li><time>'
            + html.escape(timestamp)
            + '</time><span>'
            + html.escape(event.get("phase", "step"))
            + '</span><p>'
            + html.escape(event.get("message", ""))
            + "</p></li>"
        )
    if not activity_items:
        activity_items.append("<li><time>--:--:--</time><span>idle</span><p>No activity recorded.</p></li>")

    plan_rows = [
        ("Source mode", f"{policy.get('mode', 'default')} - {policy.get('description', 'Use broad local web search')}"),
        ("Include sites", ", ".join(policy.get("include_sites") or []) or "(none)"),
        ("Exclude sites", ", ".join(policy.get("exclude_sites") or []) or "(none)"),
        ("Local documents", str(len(local_documents))),
        ("Local app connectors", str(len(local_connectors))),
        ("Limits", json.dumps(limits, sort_keys=True)),
    ]
    plan_table = "\n".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>" for label, value in plan_rows
    )

    review_updated_at = int(review.get("updated_at") or 0)
    review_updated = (
        time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(review_updated_at))
        if review_updated_at
        else "(not reviewed)"
    )
    review_rows = [
        ("Status", review_status),
        ("Revisions", str(review.get("revision_count") or 0)),
        ("Updated", review_updated),
        ("Reviewer", str(review.get("reviewer") or "(local user)")),
        ("Note", str(review.get("note") or "(none)")),
    ]
    review_table = "\n".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>" for label, value in review_rows
    )
    citation_audit = citation_audit or {}
    citation_rows = [
        ("Status", str(citation_audit.get("status") or "unknown")),
        ("Citation count", str(citation_audit.get("citation_count") or 0)),
        ("Valid citations", ", ".join(citation_audit.get("valid_citation_ids") or []) or "(none)"),
        ("Invalid citations", ", ".join(citation_audit.get("invalid_citation_ids") or []) or "(none)"),
        ("Uncited sources", ", ".join(citation_audit.get("uncited_source_ids") or []) or "(none)"),
    ]
    citation_table = "\n".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>" for label, value in citation_rows
    )

    connector_items = "\n".join(
        f"<li>{html.escape(item.get('type', 'local_app'))}: {html.escape(item.get('query', ''))} "
        f"(limit {html.escape(str(item.get('limit', '')))}, {html.escape(item.get('url', ''))})</li>"
        for item in local_connectors
    ) or "<li>(none)</li>"
    document_items = "\n".join(
        f"<li>{html.escape(item.get('title', 'Local document'))} ({html.escape(str(item.get('chars', 0)))} chars)</li>"
        for item in local_documents
    ) or "<li>(none)</li>"
    query_items = "\n".join(f"<li>{html.escape(query)}</li>" for query in queries) or "<li>(no web queries)</li>"

    markdown_escaped = html.escape(markdown)
    return (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\"><title>Deep Research Report</title>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<style>"
        ":root{color-scheme:light;--ink:#151719;--muted:#5a6472;--line:#d9dee7;--bg:#f7f8fa;"
        "--panel:#fff;--accent:#0f766e;--blue:#1d4ed8;--amber:#b45309}"
        "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);"
        "font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.5}"
        "a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}"
        ".shell{display:grid;grid-template-columns:minmax(260px,320px) minmax(0,1fr);min-height:100vh}"
        "aside{border-right:1px solid var(--line);background:#fff;padding:24px;position:sticky;top:0;height:100vh;overflow:auto}"
        "main{padding:32px;max-width:1100px}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);font-weight:700}"
        "h1{font-size:32px;line-height:1.15;margin:8px 0 12px}h2{font-size:20px;margin:0 0 14px}h3{font-size:15px;margin:0 0 8px}"
        ".meta{color:var(--muted);font-size:14px}.download-bar{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}"
        ".download-bar a{border:1px solid var(--line);border-radius:6px;padding:7px 10px;background:#fff;font-size:13px}"
        ".review-badge{display:inline-flex;align-items:center;border:1px solid #99f6e4;background:#e6fffb;color:#0f766e;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:700}"
        "section{margin:0 0 24px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px}"
        "table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-top:1px solid var(--line);padding:9px 0;text-align:left;vertical-align:top}"
        "th{width:150px;color:var(--muted);font-weight:600}.answer p{margin:0 0 12px}.source-list{display:grid;gap:12px}"
        ".source-card{border:1px solid var(--line);border-radius:8px;background:#fff;padding:14px}.source-card__head{display:flex;gap:10px;align-items:flex-start}"
        ".source-card__head span{background:#e6fffb;color:#0f766e;border:1px solid #99f6e4;border-radius:999px;padding:2px 7px;font-size:12px;font-weight:700}"
        ".source-card p,.source-card a{font-size:13px}.source-card blockquote{margin:10px 0 0;border-left:3px solid var(--accent);padding-left:10px;color:#29313b}"
        ".activity-timeline{list-style:none;padding:0;margin:0;display:grid;gap:10px}.activity-timeline li{border-left:3px solid var(--line);padding-left:12px}"
        ".activity-timeline time{font-size:12px;color:var(--muted);margin-right:8px}.activity-timeline span{font-size:12px;color:var(--amber);font-weight:700;text-transform:uppercase}"
        ".raw-markdown{white-space:pre-wrap;word-wrap:break-word;background:#101418;color:#f7f8fa;border-radius:8px;padding:16px;overflow:auto;font-size:13px}"
        ".empty{color:var(--muted)}ul{padding-left:18px;margin-top:8px}@media(max-width:820px){.shell{grid-template-columns:1fr}aside{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line)}main{padding:20px}h1{font-size:25px}}"
        "</style></head><body>"
        f'<div class="shell" data-report-shell="deep-research-report" data-run-id="{html.escape(run_id)}" data-review-status="{html.escape(review_status)}">'
        "<aside>"
        '<div class="eyebrow">Deep Research</div>'
        f"<h1>{html.escape(question[:160] or 'Research report')}</h1>"
        f'<p class="meta">Run {html.escape(run_id)}<br>Created {html.escape(created)}</p>'
        f'<p><span class="review-badge">Review: {html.escape(review_status)}</span></p>'
        f'<nav class="download-bar" aria-label="Downloads">{download_links}</nav>'
        "<section><h2>Plan</h2><table>" + plan_table + "</table></section>"
        '<section><h2>Review</h2><table data-review-panel="deep-research-review">' + review_table + "</table></section>"
        '<section><h2>Citation Audit</h2><table data-citation-audit="deep-research-citations">' + citation_table + "</table></section>"
        "<section><h3>Local Documents</h3><ul>" + document_items + "</ul></section>"
        "<section><h3>Local App Connectors</h3><ul>" + connector_items + "</ul></section>"
        "<section><h3>Queries</h3><ul>" + query_items + "</ul></section>"
        "</aside><main>"
        '<section class="panel answer" id="answer"><h2>Answer</h2>'
        + html_text_block(answer)
        + "</section>"
        '<section class="panel" id="citation-audit"><h2>Citation Audit</h2><table data-citation-audit-panel="deep-research-citations">'
        + citation_table
        + "</table></section>"
        '<section class="panel" id="sources"><h2>Sources Used</h2><div class="source-list">'
        + "\n".join(source_cards)
        + "</div></section>"
        '<section class="panel" id="activity"><h2>Activity History</h2><ol class="activity-timeline">'
        + "\n".join(activity_items)
        + "</ol></section>"
        '<section class="panel" id="raw"><h2>Raw Markdown</h2><pre class="raw-markdown">'
        + markdown_escaped
        + "</pre></section>"
        "</main></div></body></html>\n"
    )


def pdf_escape(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def docx_escape(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(text))
    return html.escape(text, quote=False)


def docx_paragraph(text: str, style: str | None = None) -> str:
    if not text:
        return "<w:p/>"
    style_xml = f'<w:pPr><w:pStyle w:val="{docx_escape(style)}"/></w:pPr>' if style else ""
    return f'<w:p>{style_xml}<w:r><w:t xml:space="preserve">{docx_escape(text)}</w:t></w:r></w:p>'


def report_docx(markdown: str) -> bytes:
    paragraphs = []
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            paragraphs.append(docx_paragraph(""))
        elif line.startswith("# "):
            paragraphs.append(docx_paragraph(line[2:].strip(), "Title"))
        elif line.startswith("## "):
            paragraphs.append(docx_paragraph(line[3:].strip(), "Heading1"))
        elif line.startswith("### "):
            paragraphs.append(docx_paragraph(line[4:].strip(), "Heading2"))
        elif line.startswith("- "):
            paragraphs.append(docx_paragraph(f"• {line[2:].strip()}"))
        else:
            paragraphs.append(docx_paragraph(line))

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraphs)
        + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
        '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
        '<w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>'
        '<w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
        "</w:styles>"
    )
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now()))
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>Deep Research Report</dc:title>"
        "<dc:creator>OpenWebUI Local Deep Research</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>OpenWebUI Local Deep Research</Application>"
        "</Properties>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    document_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", root_rels_xml)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", styles_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels_xml)
    return buffer.getvalue()


def report_pdf(markdown: str) -> bytes:
    wrapped_lines = []
    for line in markdown.splitlines():
        if not line:
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(textwrap.wrap(line, width=92, replace_whitespace=False) or [""])

    pages = [wrapped_lines[index : index + 54] for index in range(0, len(wrapped_lines), 54)] or [[]]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    kids = []
    next_id = 4
    for page_lines in pages:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        kids.append(f"{page_id} 0 R")
        commands = ["BT", "/F1 10 Tf", "54 756 Td", "13 TL"]
        for line in page_lines:
            commands.append(f"({pdf_escape(line)}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> >> "
            f"/MediaBox [0 0 612 792] /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode("ascii")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")
    xref_at = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def source_from_payload(item: dict) -> Source:
    return Source(
        sid=str(item.get("sid") or ""),
        title=str(item.get("title") or "Untitled source"),
        url=str(item.get("url") or ""),
        engine=str(item.get("engine") or ""),
        score=float(item.get("score") or 0.0),
        snippet=str(item.get("snippet") or ""),
        fetched=bool(item.get("fetched")),
        error=str(item.get("error") or ""),
        text_chars=int(item.get("text_chars") or 0),
        excerpts=item.get("excerpts") if isinstance(item.get("excerpts"), list) else [],
    )


def source_pack_markdown(run_id: str, question: str, queries: list[str], sources: list[Source], answer: str) -> str:
    lines = [f"# Source Pack: {run_id}", "", f"Question: {question}", "", "## Queries", ""]
    lines.extend([f"- {query}" for query in queries])
    lines.extend(["", "## Sources", ""])
    for source in sources:
        status = "fetched" if source.fetched else f"failed: {source.error or 'not fetched'}"
        lines.extend([f"### [{source.sid}] {source.title}", f"- URL: {source.url}", f"- Status: {status}", ""])
        if source.snippet:
            lines.extend(["Search snippet:", "", f"> {source.snippet}", ""])
        for excerpt in source.excerpts:
            lines.extend([f"> {excerpt}", ""])
    lines.extend(["## Final Answer", "", answer])
    return "\n".join(lines)


def citation_audit_for_answer(run_id: str, answer: str, sources: list[Source], review: dict | None = None) -> dict:
    source_ids = [source.sid for source in sources if source.sid]
    source_id_set = set(source_ids)
    cited_ids = []
    for match in re.finditer(r"\[S(\d+)\]", answer or ""):
        citation_id = f"S{match.group(1)}"
        if citation_id not in cited_ids:
            cited_ids.append(citation_id)
    valid_ids = [citation_id for citation_id in cited_ids if citation_id in source_id_set]
    invalid_ids = [citation_id for citation_id in cited_ids if citation_id not in source_id_set]
    uncited_ids = [source_id for source_id in source_ids if source_id not in set(cited_ids)]
    cited_sources = [
        {
            "id": source.sid,
            "title": source.title,
            "url": source.url,
            "engine": source.engine,
            "fetched": source.fetched,
            "text_chars": source.text_chars,
            "excerpt_count": len(source.excerpts or []),
        }
        for source in sources
        if source.sid in set(valid_ids)
    ]
    status = "ready" if not invalid_ids else "needs_review"
    return {
        "source": "deep-research-citation-audit",
        "run_id": run_id,
        "generated_at": now(),
        "status": status,
        "review_status": (review or {}).get("status", "unreviewed"),
        "citation_count": len(cited_ids),
        "source_count": len(source_ids),
        "valid_citation_count": len(valid_ids),
        "invalid_citation_count": len(invalid_ids),
        "uncited_source_count": len(uncited_ids),
        "cited_source_ids": cited_ids,
        "valid_citation_ids": valid_ids,
        "invalid_citation_ids": invalid_ids,
        "uncited_source_ids": uncited_ids,
        "all_citations_valid": not invalid_ids,
        "has_citations": bool(cited_ids),
        "cited_sources": cited_sources,
        "privacy": {
            "local_only": True,
            "derived_from_source_pack": True,
            "prompt_bodies_excluded": True,
        },
    }


RUN_BUNDLE_FILES = (
    "report.md",
    "report.html",
    "report.docx",
    "report.doc",
    "report.pdf",
    "source-pack.md",
    "source-pack.json",
    "citation-audit.json",
    "activity.json",
    "revisions.json",
)


def write_run_bundle(run_dir: Path, run_id: str):
    files = []
    for filename in RUN_BUNDLE_FILES:
        file_path = run_dir / filename
        if file_path.exists():
            files.append(
                {
                    "filename": filename,
                    "content_type": RUN_FILE_TYPES.get(filename, "application/octet-stream"),
                    "bytes": file_path.stat().st_size,
                }
            )
    manifest = {
        "source": "deep-research-report-bundle",
        "run_id": run_id,
        "generated_at": now(),
        "files": files,
        "privacy": {
            "local_only": True,
            "includes_source_pack": True,
            "includes_private_local_sources_if_used": True,
            "prompt_bodies_excluded": True,
        },
    }
    bundle_path = run_dir / "report-bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        for item in files:
            archive.write(run_dir / item["filename"], item["filename"])


def write_run_artifacts(run_dir: Path, payload: dict):
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(payload.get("run_id") or run_dir.name)
    question = str(payload.get("question") or "")
    queries = payload.get("queries") if isinstance(payload.get("queries"), list) else []
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {
        "question": question,
        "created_at": payload.get("created_at") or now(),
        "queries": queries,
        "source_policy": source_policy({}),
    }
    activity = payload.get("activity") if isinstance(payload.get("activity"), list) else []
    answer = str(payload.get("answer") or "")
    review = payload.get("review") if isinstance(payload.get("review"), dict) else None
    sources = [source_from_payload(source) for source in payload.get("sources") or [] if isinstance(source, dict)]
    citation_audit = citation_audit_for_answer(run_id, answer, sources, review=review)

    payload["run_id"] = run_id
    payload["question"] = question
    payload["queries"] = queries
    payload["plan"] = plan
    payload["activity"] = activity
    payload["answer"] = answer
    payload["sources"] = [asdict(source) for source in sources]
    payload["citation_audit"] = citation_audit

    (run_dir / "source-pack.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "activity.json").write_text(json.dumps(activity, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "citation-audit.json").write_text(json.dumps(citation_audit, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "source-pack.md").write_text(source_pack_markdown(run_id, question, queries, sources, answer), encoding="utf-8")

    report_md = report_markdown(
        run_id, question, plan, activity, sources, answer, review=review, citation_audit=citation_audit
    )
    (run_dir / "report.md").write_text(report_md, encoding="utf-8")
    html_report = report_html(
        run_id, question, plan, activity, sources, answer, report_md, review=review, citation_audit=citation_audit
    )
    (run_dir / "report.html").write_text(html_report, encoding="utf-8")
    (run_dir / "report.doc").write_text(html_report, encoding="utf-8")
    (run_dir / "report.docx").write_bytes(report_docx(report_md))
    (run_dir / "report.pdf").write_bytes(report_pdf(report_md))
    write_run_bundle(run_dir, run_id)


def source_pack(
    run_dir: Path,
    run_id: str,
    question: str,
    queries: list[str],
    sources: list[Source],
    answer: str,
    plan: dict | None = None,
    activity: list[dict] | None = None,
):
    run_dir.mkdir(parents=True, exist_ok=True)
    plan = plan or {"question": question, "created_at": now(), "queries": queries, "source_policy": source_policy({})}
    activity = activity or []
    payload = {
        "run_id": run_id,
        "question": question,
        "created_at": now(),
        "queries": queries,
        "plan": plan,
        "activity": activity,
        "answer": answer,
        "sources": [asdict(source) for source in sources],
    }
    write_run_artifacts(run_dir, payload)


def runs_root() -> Path:
    path = STORAGE / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_run_summary(run_dir: Path) -> dict | None:
    pack_path = run_dir / "source-pack.json"
    if not pack_path.exists():
        return None
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    run_id = str(pack.get("run_id") or run_dir.name)
    plan = pack.get("plan") or {}
    activity = pack.get("activity") or []
    sources = pack.get("sources") or []
    citation_audit = pack.get("citation_audit") if isinstance(pack.get("citation_audit"), dict) else {}
    created_at = int(pack.get("created_at") or plan.get("created_at") or 0)
    if not created_at:
        try:
            created_at = int(pack_path.stat().st_mtime)
        except OSError:
            created_at = 0
    artifacts = []
    for filename in RUN_FILE_TYPES:
        file_path = run_dir / filename
        if file_path.exists():
            artifacts.append(
                {
                    "filename": filename,
                    "content_type": RUN_FILE_TYPES[filename],
                    "bytes": file_path.stat().st_size,
                    "url": f"{PUBLIC_BASE_URL}/runs/{run_id}/{filename}",
                }
            )
    answer = str(pack.get("answer") or "")
    return {
        "id": run_id,
        "question": clean_text(str(pack.get("question") or plan.get("question") or "")),
        "created_at": created_at,
        "created_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created_at)) if created_at else "",
        "source_mode": (plan.get("source_policy") or {}).get("mode", "default"),
        "source_count": len(sources),
        "activity_count": len(activity),
        "local_document_count": len(plan.get("local_documents") or []),
        "local_connector_count": len(plan.get("local_connectors") or []),
        "review_status": (pack.get("review") or {}).get("status", "unreviewed"),
        "revision_count": int((pack.get("review") or {}).get("revision_count") or 0),
        "citation_audit_status": citation_audit.get("status"),
        "citation_count": int(citation_audit.get("citation_count") or 0),
        "invalid_citation_count": int(citation_audit.get("invalid_citation_count") or 0),
        "answer_preview": clean_text(answer)[:360],
        "artifacts": artifacts,
        "report_url": f"{PUBLIC_BASE_URL}/runs/{run_id}/report.html",
        "source_pack_url": f"{PUBLIC_BASE_URL}/runs/{run_id}/source-pack.json",
        "citation_audit_url": f"{PUBLIC_BASE_URL}/runs/{run_id}/citation-audit.json",
        "review_url": f"{PUBLIC_BASE_URL}/runs/{run_id}/review",
    }


def list_run_summaries(query: str = "", limit: int = 50) -> list[dict]:
    query = clean_text(query).lower()
    terms_ = [term for term in re.split(r"\s+", query) if term]
    summaries = []
    for run_dir in runs_root().iterdir():
        if not run_dir.is_dir():
            continue
        summary = load_run_summary(run_dir)
        if not summary:
            continue
        haystack = " ".join(
            [
                summary.get("id", ""),
                summary.get("question", ""),
                summary.get("answer_preview", ""),
                summary.get("source_mode", ""),
            ]
        ).lower()
        if terms_ and not all(term in haystack for term in terms_):
            continue
        summaries.append(summary)
    summaries.sort(key=lambda item: item.get("created_at") or 0, reverse=True)
    return summaries[: max(1, min(500, int(limit or 50)))]


def report_library_html(runs: list[dict], query: str = "") -> str:
    cards = []
    for item in runs:
        artifacts = " ".join(
            f'<a href="{html.escape(artifact["url"])}">{html.escape(artifact["filename"])}</a>'
            for artifact in item.get("artifacts", [])
        )
        cards.append(
            "\n".join(
                [
                    f'<article class="run-card" data-run-id="{html.escape(item.get("id", ""))}">',
                    '<div class="run-card__main">',
                    f'<time>{html.escape(item.get("created_at_iso", ""))}</time>',
                    f'<h2><a href="{html.escape(item.get("report_url", ""))}">{html.escape(item.get("question", "") or "Untitled research run")}</a></h2>',
                    f'<p>{html.escape(item.get("answer_preview", ""))}</p>',
                    "</div>",
                    '<dl class="run-card__meta">',
                    f'<div><dt>Sources</dt><dd>{html.escape(str(item.get("source_count", 0)))}</dd></div>',
                    f'<div><dt>Events</dt><dd>{html.escape(str(item.get("activity_count", 0)))}</dd></div>',
                    f'<div><dt>Docs</dt><dd>{html.escape(str(item.get("local_document_count", 0)))}</dd></div>',
                    f'<div><dt>Apps</dt><dd>{html.escape(str(item.get("local_connector_count", 0)))}</dd></div>',
                    f'<div><dt>Revisions</dt><dd>{html.escape(str(item.get("revision_count", 0)))}</dd></div>',
                    "</dl>",
                    f'<nav class="artifact-links">{artifacts}</nav>',
                    "</article>",
                ]
            )
        )
    if not cards:
        cards.append('<p class="empty">No research runs match this search.</p>')
    return (
        "<!doctype html>\n"
        '<html><head><meta charset="utf-8"><title>Deep Research Library</title>'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<style>"
        ":root{--ink:#151719;--muted:#5a6472;--line:#d9dee7;--bg:#f7f8fa;--panel:#fff;--accent:#0f766e;--blue:#1d4ed8}"
        "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.5}"
        "main{max-width:1120px;margin:0 auto;padding:32px 20px}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}"
        ".top{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:20px}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);font-weight:700}"
        "h1{margin:4px 0 0;font-size:32px}.search{display:flex;gap:8px}.search input{border:1px solid var(--line);border-radius:6px;padding:8px 10px;min-width:260px}.search button{border:1px solid var(--line);border-radius:6px;background:#fff;padding:8px 12px}"
        ".run-list{display:grid;gap:12px}.run-card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px}"
        ".run-card time{font-size:12px;color:var(--muted)}.run-card h2{font-size:18px;margin:4px 0 8px}.run-card p{margin:0;color:#29313b}.run-card__meta{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:0}.run-card__meta div{border:1px solid var(--line);border-radius:6px;padding:8px;min-width:62px;text-align:center}.run-card__meta dt{font-size:11px;color:var(--muted)}.run-card__meta dd{font-weight:700;margin:0}.artifact-links{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:8px}.artifact-links a{border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:#fff;font-size:13px}.empty{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px;color:var(--muted)}"
        "@media(max-width:760px){.top{display:block}.search{margin-top:14px}.search input{min-width:0;width:100%}.run-card{grid-template-columns:1fr}.run-card__meta{grid-template-columns:repeat(2,1fr)}}"
        "</style></head><body>"
        '<main data-report-library="deep-research-runs">'
        '<div class="top"><div><div class="eyebrow">Deep Research</div><h1>Report Library</h1></div>'
        f'<form class="search" method="get" action="/runs/index.html"><input name="q" value="{html.escape(query)}" placeholder="Search reports"><button type="submit">Search</button></form></div>'
        '<section class="run-list">'
        + "\n".join(cards)
        + "</section></main></body></html>\n"
    )


def delete_run(run_id: str) -> bool:
    run_dir = runs_root() / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        return False
    for child in run_dir.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()
        elif child.is_dir():
            for nested in child.rglob("*"):
                if nested.is_file() or nested.is_symlink():
                    nested.unlink()
            child.rmdir()
    run_dir.rmdir()
    return True


def review_run(run_id: str, payload: dict) -> dict:
    run_dir = runs_root() / run_id
    pack_path = run_dir / "source-pack.json"
    if not run_dir.is_dir() or not pack_path.exists():
        raise FileNotFoundError("run not found")

    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    revised_answer = clean_text(
        str(
            payload.get("revised_answer")
            or payload.get("answer")
            or payload.get("markdown")
            or payload.get("content")
            or ""
        )
    )
    if not revised_answer:
        raise ValueError("review requires a non-empty revised answer")

    note = clean_text(str(payload.get("note") or payload.get("review_note") or ""))[:1000]
    reviewer = clean_text(str(payload.get("reviewer") or "local-user"))[:120]
    revision_id = str(uuid.uuid4())
    updated_at = now()

    revisions_path = run_dir / "revisions.json"
    if revisions_path.exists():
        try:
            revisions = json.loads(revisions_path.read_text(encoding="utf-8"))
            if not isinstance(revisions, list):
                revisions = []
        except json.JSONDecodeError:
            revisions = []
    else:
        revisions = []

    previous_answer = str(pack.get("answer") or "")
    if "original_answer" not in pack:
        pack["original_answer"] = previous_answer

    revision = {
        "id": revision_id,
        "updated_at": updated_at,
        "reviewer": reviewer,
        "note": note,
        "answer_chars": len(revised_answer),
        "previous_answer_preview": clean_text(previous_answer)[:360],
    }
    revisions.append(revision)
    revisions_path.write_text(json.dumps(revisions, indent=2, ensure_ascii=False), encoding="utf-8")

    activity = pack.get("activity") if isinstance(pack.get("activity"), list) else []
    activity.append(
        {
            "ts": updated_at,
            "phase": "review",
            "message": clean_text(f"Reviewed report saved as revision {revision_id}. {note}"),
        }
    )
    pack["activity"] = activity
    pack["answer"] = revised_answer
    pack["review"] = {
        "status": "reviewed",
        "updated_at": updated_at,
        "revision_count": len(revisions),
        "latest_revision_id": revision_id,
        "reviewer": reviewer,
        "note": note,
        "original_answer_preserved": bool(pack.get("original_answer")),
    }

    write_run_artifacts(run_dir, pack)
    return {
        "status": True,
        "review": pack["review"],
        "revision": revision,
        "run": load_run_summary(run_dir),
        "artifacts": {
            "report_md": f"{PUBLIC_BASE_URL}/runs/{run_id}/report.md",
            "report_html": f"{PUBLIC_BASE_URL}/runs/{run_id}/report.html",
            "report_docx": f"{PUBLIC_BASE_URL}/runs/{run_id}/report.docx",
            "report_doc": f"{PUBLIC_BASE_URL}/runs/{run_id}/report.doc",
            "report_pdf": f"{PUBLIC_BASE_URL}/runs/{run_id}/report.pdf",
            "report_bundle": f"{PUBLIC_BASE_URL}/runs/{run_id}/report-bundle.zip",
            "citation_audit": f"{PUBLIC_BASE_URL}/runs/{run_id}/citation-audit.json",
            "revisions": f"{PUBLIC_BASE_URL}/runs/{run_id}/revisions.json",
        },
    }


def synthesize(
    question: str,
    sources: list[Source],
    run_id: str,
    max_tokens: int,
    max_snippets: int,
    max_excerpt_chars: int,
    extractive_only: bool = False,
) -> str:
    evidence = []
    for source in sources:
        if not source.excerpts:
            continue
        for excerpt in source.excerpts[:3]:
            evidence.append(f"[{source.sid}] {source.title}\nURL: {source.url}\nExcerpt: {excerpt[:max_excerpt_chars]}")
        if len(evidence) >= max_snippets:
            break
    if not evidence:
        return "I could not gather enough source text to produce a grounded deep research answer."

    if extractive_only:
        lines = [
            "Answer",
            "",
            f"Local extractive research summary for: {question}",
            "",
            "Evidence",
            "",
        ]
        for source in sources:
            if not source.excerpts:
                continue
            lines.append(f"- [{source.sid}] {source.title}: {source.excerpts[0][:max_excerpt_chars]}")
            if len(lines) >= 2 + (max_snippets * 2):
                break
        lines.extend(
            [
                "",
                "Contradictions or uncertainty",
                "",
                "- This fast extractive mode quotes the available local evidence and does not ask GLM to infer beyond it.",
                "",
                "Sources to inspect",
                "",
            ]
        )
        lines.extend(f"- [{source.sid}] {source.title}: {source.url}" for source in sources[:max_snippets])
        return "\n".join(lines)

    prompt = (
        "You are writing a deep research answer. Use only the provided sources. "
        "Cite claims with source ids like [S1]. Identify disagreements, uncertainty, and source quality issues. "
        "Do not cite a source unless the cited sentence is supported by its excerpt.\n\n"
        f"Question:\n{question}\n\n"
        "Evidence:\n" + "\n\n".join(evidence[:max_snippets]) + "\n\n"
        "Write a concise but thorough answer with sections: Answer, Evidence, Contradictions or uncertainty, Sources to inspect."
    )
    try:
        return glm_chat(
            [
                {"role": "system", "content": "You are a careful research analyst. You always cite sources accurately."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
    except Exception as exc:
        listed = "\n".join(f"- [{s.sid}] {s.title}: {s.url}" for s in sources[:20])
        return (
            "Deep research gathered sources, but GLM synthesis did not complete.\n\n"
            f"Error: {exc}\n\n"
            "Source pack contains the extracted evidence for manual review.\n\n"
            f"{listed}"
        )


def build_research(question: str, progress=None, overrides: dict | None = None) -> str:
    overrides = overrides or {}
    plan = build_plan(question, overrides)
    limits = plan["limits"]
    max_results = limits["max_results"]
    max_sources = limits["max_sources"]
    max_snippets = limits["max_snippets"]
    max_tokens = limits["max_tokens"]
    max_excerpt_chars = limits["max_excerpt_chars"]
    run_id = str(uuid.uuid4())
    run_dir = STORAGE / "runs" / run_id
    activity = []

    def say(message: str, phase: str = "progress"):
        activity.append({"ts": now(), "phase": phase, "message": clean_text(message)})
        if progress:
            progress(message)

    queries = plan["queries"]
    policy = plan["source_policy"]
    wanted = terms(question)
    say(f"Research run `{run_id}` started.\n\n", "start")
    say(
        f"Search plan: {len(queries)} queries, source mode `{policy['mode']}`, up to {max_sources} sources.\n\n",
        "plan",
    )
    document_sources = local_document_sources(overrides, wanted)
    say(f"Loaded {len(document_sources)} local document sources.\n\n", "documents")
    app_sources = connector_sources(overrides, question, wanted)
    say(f"Loaded {len(app_sources)} local app connector sources.\n\n", "connectors")

    results = []
    per_query = max(1, max_results // max(1, len(queries)))
    for index, query in enumerate(queries, start=1):
        say(f"Searching {index}/{len(queries)}: `{query}`\n\n", "search")
        try:
            results.extend(searxng_search(query, per_query))
        except Exception as exc:
            say(f"Search failed for `{query}`: {exc}\n\n", "search_error")

    web_sources = dedupe_sources(results, max_sources, policy)
    say(f"Reading {len(web_sources)} deduplicated web sources.\n\n", "read")
    for index, source in enumerate(web_sources, start=1):
        say(f"Reading {index}/{len(web_sources)} [{source.sid}] {source.title}\n\n", "read")
        fetch_source(source, wanted)

    sources = document_sources + app_sources + web_sources
    sources.sort(key=lambda item: (len(item.excerpts), item.score, item.text_chars), reverse=True)
    for idx, source in enumerate(sources, start=1):
        source.sid = f"S{idx}"

    say("Synthesizing answer with GLM 5.2.\n\n", "synthesize")
    answer = synthesize(
        question,
        sources,
        run_id,
        max_tokens=max_tokens,
        max_snippets=max_snippets,
        max_excerpt_chars=max_excerpt_chars,
        extractive_only=bool(overrides.get("extractive_only")),
    )

    citations = set(re.findall(r"\[S(\d+)\]", answer))
    valid = {str(i) for i in range(1, len(sources) + 1)}
    invalid = sorted(citations - valid)
    if invalid:
        answer += "\n\nCitation verification note: these citation ids were not in the source pack: " + ", ".join(invalid)

    say("Writing source pack, activity log, and downloadable reports.\n\n", "write_artifacts")
    source_pack(run_dir, run_id, question, queries, sources, answer, plan=plan, activity=activity)
    md_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/source-pack.md"
    json_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/source-pack.json"
    report_md_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/report.md"
    report_html_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/report.html"
    report_docx_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/report.docx"
    report_doc_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/report.doc"
    report_pdf_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/report.pdf"
    report_bundle_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/report-bundle.zip"
    citation_audit_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/citation-audit.json"
    activity_url = f"{PUBLIC_BASE_URL}/runs/{run_id}/activity.json"
    answer += (
        f"\n\nSource pack: [Markdown]({md_url}) | [JSON]({json_url})"
        f"\n\nResearch artifacts: [Report Markdown]({report_md_url}) | [HTML]({report_html_url}) | "
        f"[Word DOCX]({report_docx_url}) | [Word DOC]({report_doc_url}) | [PDF]({report_pdf_url}) | "
        f"[Bundle ZIP]({report_bundle_url}) | [Citation Audit]({citation_audit_url}) | [Activity]({activity_url})"
    )
    return answer


def chunk_payload(content: str, finish_reason=None) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "created": now(),
        "model": MODEL_ID,
        "choices": [{"index": 0, "delta": {"content": content} if content else {}, "finish_reason": finish_reason}],
    }


def last_user_message(payload: dict) -> str:
    messages = payload.get("messages") or []
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def documents_from_messages(messages: list[dict]) -> list[dict]:
    documents = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "").lower()
            if part_type not in {"file", "input_file", "document", "local_document"}:
                continue
            text = part.get("text") or part.get("content")
            encoded = part.get("content_base64") or part.get("data_base64")
            if not text and not encoded:
                continue
            documents.append(
                {
                    "title": part.get("title") or part.get("name") or part.get("filename") or f"Message document {len(documents) + 1}",
                    "text": text,
                    "content_base64": encoded,
                    "content_type": part.get("content_type") or part.get("mime_type"),
                    "source": part.get("url") or part.get("source") or f"message-document://{len(documents) + 1}",
                }
            )
    return documents[:MAX_LOCAL_DOCUMENTS]


def merge_message_documents(payload: dict, overrides: dict) -> dict:
    message_documents = documents_from_messages(payload.get("messages") or [])
    if not message_documents:
        return overrides
    merged = dict(overrides)
    existing = document_inputs(merged)
    merged["documents"] = [*existing, *message_documents][:MAX_LOCAL_DOCUMENTS]
    return merged


RUN_FILE_TYPES = {
    "source-pack.md": "text/markdown; charset=utf-8",
    "source-pack.json": "application/json; charset=utf-8",
    "citation-audit.json": "application/json; charset=utf-8",
    "activity.json": "application/json; charset=utf-8",
    "report.md": "text/markdown; charset=utf-8",
    "report.html": "text/html; charset=utf-8",
    "report.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "report.doc": "application/msword; charset=utf-8",
    "report.pdf": "application/pdf",
    "report-bundle.zip": "application/zip",
    "revisions.json": "application/json; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "openwebui-deep-research/0.1"

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
        if path.startswith("/v1/runs"):
            path = path[3:]
        query = parse.parse_qs(parsed.query)
        if path == "/health":
            return send_json(self, 200, {"status": "ok", "model": MODEL_ID})
        if path in {"/v1/models", "/models"}:
            return send_json(
                self,
                200,
                {
                    "object": "list",
                    "data": [{"id": MODEL_ID, "object": "model", "created": now(), "owned_by": "local"}],
                    "models": [{"name": MODEL_ID, "model": MODEL_ID, "type": "model"}],
                },
            )
        if path in {"/runs", "/runs/"}:
            search_query = (query.get("q") or [""])[0]
            limit = int((query.get("limit") or ["50"])[0] or "50")
            return send_json(self, 200, {"data": list_run_summaries(search_query, limit)})
        if path == "/runs/index.html":
            search_query = (query.get("q") or [""])[0]
            limit = int((query.get("limit") or ["100"])[0] or "100")
            html_body = report_library_html(list_run_summaries(search_query, limit), search_query).encode("utf-8")
            return send_bytes(self, 200, html_body, "text/html; charset=utf-8")
        match = re.match(r"^/runs/([^/]+)$", path)
        if match:
            summary = load_run_summary(runs_root() / match.group(1))
            if not summary:
                return send_json(self, 404, {"error": "not found"})
            return send_json(self, 200, {"run": summary})
        match = re.match(r"^/runs/([^/]+)/([a-z0-9-]+\.(?:md|json|html|docx|doc|pdf|zip))$", path)
        if match:
            run_id, filename = match.groups()
            if filename not in RUN_FILE_TYPES:
                return send_json(self, 404, {"error": "not found"})
            file_path = STORAGE / "runs" / run_id / filename
            if not file_path.exists():
                return send_json(self, 404, {"error": "not found"})
            body = file_path.read_bytes()
            return send_bytes(self, 200, body, RUN_FILE_TYPES[filename])
        return send_json(self, 404, {"error": "not found"})

    def do_DELETE(self):
        path = parse.urlparse(self.path).path
        if path.startswith("/v1/runs"):
            path = path[3:]
        match = re.match(r"^/runs/([^/]+)$", path)
        if not match:
            return send_json(self, 404, {"error": "not found"})
        if not delete_run(match.group(1)):
            return send_json(self, 404, {"error": "not found"})
        return send_json(self, 200, {"status": True})

    def do_POST(self):
        path = parse.urlparse(self.path).path
        if path.startswith("/v1/runs"):
            path = path[3:]
        match = re.match(r"^/runs/([0-9a-f-]+)/review$", path)
        if match:
            try:
                return send_json(self, 200, review_run(match.group(1), read_json(self)))
            except FileNotFoundError:
                return send_json(self, 404, {"error": "not found"})
            except ValueError as exc:
                return send_json(self, 400, {"error": {"message": str(exc), "type": "bad_request"}})
            except Exception as exc:
                return send_json(self, 500, {"error": {"message": str(exc), "type": "server_error"}})

        if path in {"/v1/research/plan", "/research/plan"}:
            try:
                payload = read_json(self)
                question = clean_text(payload.get("question") or last_user_message(payload))
                if not question:
                    return send_json(self, 400, {"error": {"message": "No question found"}})
                overrides = payload.get("deep_research") or payload.get("metadata", {}).get("deep_research") or payload
                overrides = merge_message_documents(payload, overrides)
                return send_json(self, 200, {"plan": build_plan(question, overrides)})
            except Exception as exc:
                return send_json(self, 500, {"error": {"message": str(exc), "type": "server_error"}})

        if path not in {"/v1/chat/completions", "/chat/completions"}:
            return send_json(self, 404, {"error": "not found"})

        try:
            payload = read_json(self)
            question = last_user_message(payload).strip()
            if not question:
                return send_json(self, 400, {"error": {"message": "No user message found"}})

            overrides = payload.get("deep_research") or payload.get("metadata", {}).get("deep_research") or {}
            overrides = merge_message_documents(payload, overrides)
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

                answer = build_research(question, progress=emit, overrides=overrides)
                emit(answer)
                done = "data: " + json.dumps(chunk_payload("", "stop")) + "\n\n" + "data: [DONE]\n\n"
                self.wfile.write(done.encode("utf-8"))
                self.wfile.flush()
                return

            answer = build_research(question, overrides=overrides)
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
    host = os.environ.get("DEEP_RESEARCH_HOST", "127.0.0.1")
    port = int(os.environ.get("DEEP_RESEARCH_PORT", "18041"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"deep research sidecar listening on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
