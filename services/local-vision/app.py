#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Lock
from urllib import parse, request

from PIL import Image


MODEL_ID = os.environ.get("LOCAL_VISION_MODEL_ID", "local-vision-moondream2")
HF_MODEL = os.environ.get("LOCAL_VISION_HF_MODEL", "vikhyatk/moondream2")
HF_REVISION = os.environ.get("LOCAL_VISION_HF_REVISION", "2025-01-09")
HOST = os.environ.get("LOCAL_VISION_HOST", "127.0.0.1")
PORT = int(os.environ.get("LOCAL_VISION_PORT", "18044"))
OPENWEBUI_BASE_URL = os.environ.get("LOCAL_VISION_OPENWEBUI_BASE_URL", "http://127.0.0.1:8080")
LOCAL_FILES_ONLY = os.environ.get("LOCAL_VISION_LOCAL_FILES_ONLY", "1").lower() not in {"0", "false", "no"}
MAX_IMAGE_BYTES = int(os.environ.get("LOCAL_VISION_MAX_IMAGE_BYTES", str(12 * 1024 * 1024)))
MODEL_LOAD_TIMEOUT_HINT = int(os.environ.get("LOCAL_VISION_LOAD_TIMEOUT_HINT_SECONDS", "600"))
DEVICE_SETTING = os.environ.get("LOCAL_VISION_DEVICE", "cpu").lower()
ENABLE_OCR = os.environ.get("LOCAL_VISION_ENABLE_OCR", "1").lower() not in {"0", "false", "no"}
OCR_MIN_CONFIDENCE = float(os.environ.get("LOCAL_VISION_OCR_MIN_CONFIDENCE", "0.45"))
OCR_MAX_CHARS = int(os.environ.get("LOCAL_VISION_OCR_MAX_CHARS", "2200"))
OLLAMA_ENABLED = os.environ.get("LOCAL_VISION_OLLAMA_ENABLED", "1").lower() not in {"0", "false", "no"}
OLLAMA_MODEL_ID = os.environ.get("LOCAL_VISION_OLLAMA_MODEL_ID", "local-vision-gemma4-12b")
OLLAMA_MODEL = os.environ.get("LOCAL_VISION_OLLAMA_MODEL", "gemma4:12b")
OLLAMA_URL = os.environ.get("LOCAL_VISION_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("LOCAL_VISION_OLLAMA_TIMEOUT_SECONDS", "600"))

MODEL = None
DEVICE = "cpu"
MODEL_LOCK = Lock()
OCR_ENGINE = None
OCR_ERROR = None
OCR_LOCK = Lock()


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float | None
    box: tuple[float, float, float, float] | None


def now() -> int:
    return int(time.time())


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


def model_card() -> dict:
    return {
        "id": MODEL_ID,
        "name": MODEL_ID,
        "object": "model",
        "created": now(),
        "owned_by": "local",
        "connection_type": "local",
        "info": {
            "id": MODEL_ID,
            "name": "Local Vision - Moondream2 + OCR",
            "meta": {
                "description": "Local Moondream2 image understanding model with OCR assist for OpenWebUI.",
                "capabilities": {
                    "vision": True,
                    "file_upload": True,
                    "file_context": False,
                    "web_search": False,
                    "image_generation": False,
                    "code_interpreter": False,
                    "ocr": ENABLE_OCR,
                },
            },
        },
    }


def ollama_model_card() -> dict:
    return {
        "id": OLLAMA_MODEL_ID,
        "name": OLLAMA_MODEL_ID,
        "object": "model",
        "created": now(),
        "owned_by": "local",
        "connection_type": "local",
        "info": {
            "id": OLLAMA_MODEL_ID,
            "name": f"Local Vision - {OLLAMA_MODEL}",
            "meta": {
                "description": (
                    f"Local Ollama vision model backed by {OLLAMA_MODEL}, exposed additively for stronger visual reasoning."
                ),
                "capabilities": {
                    "vision": True,
                    "file_upload": True,
                    "file_context": False,
                    "web_search": False,
                    "image_generation": False,
                    "code_interpreter": False,
                    "ocr": ENABLE_OCR,
                },
                "backend": "ollama",
                "backend_model": OLLAMA_MODEL,
            },
        },
    }


def model_cards() -> list[dict]:
    cards = [model_card()]
    if OLLAMA_ENABLED:
        cards.append(ollama_model_card())
    return cards


def load_model():
    global MODEL, DEVICE
    if MODEL is not None:
        return MODEL

    with MODEL_LOCK:
        if MODEL is not None:
            return MODEL

        import torch
        from transformers import AutoModelForCausalLM
        from transformers import PreTrainedModel

        if not hasattr(PreTrainedModel, "all_tied_weights_keys"):
            PreTrainedModel.all_tied_weights_keys = property(lambda self: {})

        if DEVICE_SETTING == "auto":
            DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        elif DEVICE_SETTING == "cuda" and not torch.cuda.is_available():
            DEVICE = "cpu"
        elif DEVICE_SETTING in {"cpu", "cuda"}:
            DEVICE = DEVICE_SETTING
        else:
            DEVICE = "cpu"

        kwargs = {
            "revision": HF_REVISION,
            "trust_remote_code": True,
            "local_files_only": LOCAL_FILES_ONLY,
        }
        if DEVICE == "cuda":
            kwargs["torch_dtype"] = torch.float16
        else:
            kwargs["torch_dtype"] = torch.float32

        model = AutoModelForCausalLM.from_pretrained(HF_MODEL, **kwargs)
        model = model.to(DEVICE).eval()
        MODEL = model
        return MODEL


def load_ocr_engine():
    global OCR_ENGINE, OCR_ERROR
    if not ENABLE_OCR:
        OCR_ERROR = "disabled"
        return None
    if OCR_ENGINE is not None:
        return OCR_ENGINE

    with OCR_LOCK:
        if OCR_ENGINE is not None:
            return OCR_ENGINE
        try:
            from rapidocr_onnxruntime import RapidOCR

            OCR_ENGINE = RapidOCR()
            OCR_ERROR = None
            return OCR_ENGINE
        except Exception as exc:
            OCR_ERROR = str(exc)
            return None


def box_bounds(raw_box) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_box, (list, tuple)) or not raw_box:
        return None

    points = []
    for point in raw_box:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue
    if points:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return min(xs), min(ys), max(xs), max(ys)

    if len(raw_box) >= 4:
        try:
            x1, y1, x2, y2 = (float(raw_box[index]) for index in range(4))
            return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
        except (TypeError, ValueError):
            return None
    return None


def normalize_ocr_item(item) -> OcrLine | None:
    text = None
    score = None
    box = None

    if isinstance(item, dict):
        text = item.get("text") or item.get("rec_text") or item.get("label")
        raw_score = item.get("score", item.get("confidence", item.get("rec_score")))
        raw_box = item.get("box") or item.get("bbox") or item.get("points")
    elif isinstance(item, (list, tuple)):
        raw_box = item[0] if item else None
        if len(item) >= 3:
            text = item[1]
            raw_score = item[2]
        elif len(item) >= 2:
            if isinstance(item[0], str):
                text = item[0]
                raw_score = item[1]
            else:
                text = item[1]
                raw_score = None
        else:
            return None
    else:
        return None

    if not isinstance(text, str):
        return None
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    try:
        score = float(raw_score) if raw_score is not None else None
    except (TypeError, ValueError):
        score = None
    if score is not None and score < OCR_MIN_CONFIDENCE:
        return None

    box = box_bounds(raw_box)
    return OcrLine(text=text, score=score, box=box)


def normalize_ocr_result(result) -> list[OcrLine]:
    if isinstance(result, tuple) and result:
        result = result[0]
    if not isinstance(result, list):
        return []
    lines = [line for line in (normalize_ocr_item(item) for item in result) if line is not None]
    lines.sort(key=lambda line: ((line.box or (0, 0, 0, 0))[1], (line.box or (0, 0, 0, 0))[0]))
    return lines


def extract_ocr_lines(image: Image.Image) -> list[OcrLine]:
    engine = load_ocr_engine()
    if engine is None:
        return []

    import numpy as np

    with OCR_LOCK:
        result, _elapsed = engine(np.array(image.convert("RGB")))
    return normalize_ocr_result(result)


def question_wants_ocr(question: str) -> bool:
    if not question:
        return False
    lowered = question.lower()
    keywords = {
        "barcode",
        "chart",
        "code",
        "diagram",
        "extract",
        "field",
        "graph",
        "highest",
        "id",
        "incident",
        "invoice",
        "label",
        "largest",
        "max",
        "month",
        "number",
        "ocr",
        "read",
        "receipt",
        "screenshot",
        "serial",
        "shown",
        "table",
        "target",
        "text",
        "ticket",
        "transcribe",
        "value",
        "visible",
    }
    return any(keyword in lowered for keyword in keywords)


def question_wants_color_square(question: str) -> bool:
    lowered = question.lower()
    return "color" in lowered and "square" in lowered


def named_color_from_rgb(red: int, green: int, blue: int) -> str | None:
    channels = {"red": red, "green": green, "blue": blue}
    name, value = max(channels.items(), key=lambda item: item[1])
    if value < 80:
        return None
    sorted_values = sorted(channels.values(), reverse=True)
    if len(sorted_values) >= 2 and sorted_values[0] - sorted_values[1] < 35:
        return None
    return name.capitalize()


def dominant_non_background_color(image: Image.Image) -> str | None:
    rgb = image.convert("RGB")
    width, height = rgb.size
    left = max(0, width // 5)
    right = min(width, width - left)
    top = max(0, height // 5)
    bottom = min(height, height - top)
    pixels = []
    for y in range(top, bottom):
        for x in range(left, right):
            red, green, blue = rgb.getpixel((x, y))
            if red > 240 and green > 240 and blue > 240:
                continue
            pixels.append((red, green, blue))
    if not pixels:
        return None

    red = round(sum(pixel[0] for pixel in pixels) / len(pixels))
    green = round(sum(pixel[1] for pixel in pixels) / len(pixels))
    blue = round(sum(pixel[2] for pixel in pixels) / len(pixels))
    return named_color_from_rgb(red, green, blue)


def answer_color_square_question(question: str, images: list[Image.Image]) -> str | None:
    if not question_wants_color_square(question):
        return None

    colors = [dominant_non_background_color(image) for image in images]
    if not colors or any(color is None for color in colors):
        return None
    if len(colors) == 1:
        return colors[0] or None
    return "\n".join(f"Image {index}: {color}" for index, color in enumerate(colors, start=1) if color)


def ocr_text(lines: list[OcrLine]) -> str:
    text = "\n".join(line.text for line in lines)
    if len(text) <= OCR_MAX_CHARS:
        return text
    return text[:OCR_MAX_CHARS].rsplit("\n", 1)[0].strip()


def normalized_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def field_value_after_label(lines: list[OcrLine], label: str) -> str | None:
    normalized_label = normalized_text(label)
    for index, line in enumerate(lines):
        if normalized_text(line.text) != normalized_label:
            continue
        label_box = line.box
        candidates: list[tuple[float, str]] = []
        for next_line in lines[index + 1 : index + 8]:
            text = next_line.text.strip()
            if not text:
                continue
            if label_box and next_line.box:
                lx1, ly1, lx2, ly2 = label_box
                nx1, ny1, nx2, ny2 = next_line.box
                same_column = abs(((nx1 + nx2) / 2) - ((lx1 + lx2) / 2)) <= max(120, (lx2 - lx1) * 1.3)
                below = ny1 >= ly1
                if same_column and below:
                    candidates.append((ny1 - ly1, text))
            else:
                candidates.append((float(len(candidates)), text))
        if candidates:
            candidates.sort(key=lambda candidate: candidate[0])
            return candidates[0][1]
    return None


CODE_PATTERN = re.compile(r"\b[A-Z]{2,}[A-Z0-9]*[-_ ]?\d{2,}\b")


def code_candidates(text: str) -> list[str]:
    candidates = []
    for match in CODE_PATTERN.finditer(text.upper()):
        candidate = re.sub(r"\s+", "", match.group(0).replace("_", "-"))
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def answer_code_question(question: str, lines: list[OcrLine]) -> str | None:
    lowered = question.lower()
    text = ocr_text(lines)
    if "target code" in lowered:
        value = field_value_after_label(lines, "target code")
        if value:
            candidates = code_candidates(value)
            return candidates[0] if candidates else value

    if "code" in lowered or "serial" in lowered or "ticket" in lowered or "id" in lowered:
        for line in lines:
            if normalized_text(line.text).startswith("code "):
                candidates = code_candidates(line.text)
                if candidates:
                    return candidates[-1]
        candidates = code_candidates(text)
        if candidates:
            return candidates[0]
    return None


def center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2, (y1 + y2) / 2


def answer_highest_labeled_value(question: str, lines: list[OcrLine]) -> str | None:
    lowered = question.lower()
    if not any(word in lowered for word in ("highest", "largest", "maximum", "max", "most")):
        return None

    month_names = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}
    labels: list[tuple[str, tuple[float, float, float, float]]] = []
    numbers: list[tuple[float, tuple[float, float, float, float]]] = []

    for line in lines:
        if not line.box:
            continue
        cleaned = re.sub(r"[^A-Za-z0-9.]", "", line.text)
        lowered_cleaned = cleaned.lower()
        upper_cleaned = cleaned.upper()
        if lowered_cleaned in month_names or re.fullmatch(r"Q[1-4]", upper_cleaned):
            labels.append((cleaned, line.box))
        if re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
            numbers.append((float(cleaned), line.box))

    if not labels or not numbers:
        return None

    values_by_label: list[tuple[float, str]] = []
    for label, label_box in labels:
        label_x, label_y = center(label_box)
        close_numbers = []
        for value, number_box in numbers:
            number_x, number_y = center(number_box)
            if number_y >= label_y:
                continue
            x_distance = abs(number_x - label_x)
            if x_distance <= 52:
                close_numbers.append((x_distance, value))
        if close_numbers:
            close_numbers.sort(key=lambda candidate: candidate[0])
            values_by_label.append((close_numbers[0][1], label))

    if not values_by_label:
        return None
    values_by_label.sort(key=lambda item: item[0], reverse=True)
    return values_by_label[0][1]


def answer_from_ocr(question: str, lines: list[OcrLine]) -> str | None:
    if not lines:
        return None

    for answerer in (answer_code_question, answer_highest_labeled_value):
        answer = answerer(question, lines)
        if answer:
            return answer

    lowered = question.lower()
    if any(phrase in lowered for phrase in ("read all", "extract text", "transcribe", "what text")):
        text = ocr_text(lines)
        return text or None
    return None


def assisted_question(question: str, lines: list[OcrLine], image_index: int | None = None) -> str:
    text = ocr_text(lines)
    if not text:
        return question
    prefix = "Detected OCR text"
    if image_index is not None:
        prefix += f" for image {image_index}"
    if question:
        return f"{question}\n\n{prefix}:\n{text}\n\nUse the OCR text when it is relevant. Answer concisely."
    return f"{prefix}:\n{text}\n\nDescribe the image and mention relevant detected text."


def parse_data_url(url: str) -> bytes:
    match = re.match(r"^data:([^;,]+)?(;base64)?,(.*)$", url, re.DOTALL)
    if not match:
        raise ValueError("invalid data URL")
    is_base64 = bool(match.group(2))
    payload = match.group(3)
    if is_base64:
        raw = base64.b64decode(payload)
    else:
        raw = parse.unquote_to_bytes(payload)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image is too large")
    return raw


def read_limited(resp) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = resp.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            raise ValueError("image is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_image_bytes(url: str) -> bytes:
    if url.startswith("data:"):
        return parse_data_url(url)
    if url.startswith("/"):
        url = OPENWEBUI_BASE_URL.rstrip("/") + url
    if url.startswith("file://"):
        path = Path(parse.urlparse(url).path)
        raw = path.read_bytes()
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("image is too large")
        return raw
    if url.startswith(("http://", "https://")):
        req = request.Request(url, headers={"User-Agent": "openwebui-local-vision/0.1"})
        with request.urlopen(req, timeout=60) as resp:
            return read_limited(resp)
    path = Path(url)
    if path.exists():
        raw = path.read_bytes()
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("image is too large")
        return raw
    raise ValueError("unsupported image URL")


def image_from_url(url: str) -> Image.Image:
    raw = fetch_image_bytes(url)
    image = Image.open(BytesIO(raw))
    return image.convert("RGB")


def image_to_png_base64(image: Image.Image) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def post_json(url: str, payload: dict, timeout: int) -> dict:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json", "User-Agent": "openwebui-local-vision/0.3"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body.decode("utf-8") or "{}")


def content_to_text_and_images(messages: list[dict]) -> tuple[str, list[str]]:
    question_parts: list[str] = []
    image_urls: list[str] = []

    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            question_parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type")
                if part_type in {"text", "input_text"}:
                    text = part.get("text")
                    if isinstance(text, str):
                        question_parts.append(text)
                elif part_type in {"image_url", "input_image"}:
                    raw = part.get("image_url") or part.get("image")
                    if isinstance(raw, dict):
                        raw = raw.get("url")
                    if isinstance(raw, str):
                        image_urls.append(raw)
        if question_parts or image_urls:
            break

    question = "\n".join(part.strip() for part in reversed(question_parts) if part.strip()).strip()
    return question, image_urls


def answer_single_image_question(model, image: Image.Image, question: str, max_tokens: int) -> str:
    settings = {"max_tokens": max_tokens}

    with MODEL_LOCK:
        if question:
            result = model.query(image, question, settings=settings)
            answer = result.get("answer", "")
        else:
            result = model.caption(image, length="normal", settings=settings)
            answer = result.get("caption", "")

    answer = str(answer).strip()
    if not answer:
        answer = "I could not produce an image answer."
    return answer


def answer_image_question(question: str, image_urls: list[str], max_tokens: int) -> str:
    images = [image_from_url(url) for url in image_urls]
    color_answer = answer_color_square_question(question, images)
    if color_answer:
        return color_answer

    wants_ocr = question_wants_ocr(question)
    ocr_lines_by_image = [extract_ocr_lines(image) if wants_ocr else [] for image in images]

    if len(images) == 1:
        ocr_answer = answer_from_ocr(question, ocr_lines_by_image[0]) if wants_ocr else None
        if ocr_answer:
            return ocr_answer

    model = load_model()

    if len(images) == 1:
        prompt = assisted_question(question, ocr_lines_by_image[0]) if wants_ocr else question
        return answer_single_image_question(model, images[0], prompt, max_tokens)

    answers = []
    per_image_tokens = max(16, min(128, max_tokens // max(1, len(images))))
    for index, image in enumerate(images, start=1):
        if question:
            per_image_question = f"{question}\nAnswer for image {index} only."
        else:
            per_image_question = ""
        if wants_ocr:
            per_image_question = assisted_question(per_image_question, ocr_lines_by_image[index - 1], index)
        answer = answer_single_image_question(model, image, per_image_question, per_image_tokens)
        answers.append(f"Image {index}: {answer}")
    return "\n".join(answers)


def answer_ollama_image_question(question: str, image_urls: list[str], max_tokens: int) -> str:
    images = [image_from_url(url) for url in image_urls]
    wants_ocr = question_wants_ocr(question)
    ocr_lines_by_image = [extract_ocr_lines(image) if wants_ocr else [] for image in images]

    if len(images) == 1:
        ocr_answer = answer_from_ocr(question, ocr_lines_by_image[0]) if wants_ocr else None
        if ocr_answer:
            return ocr_answer

    prompt = question or "Describe the image."
    if wants_ocr:
        if len(images) == 1:
            prompt = assisted_question(prompt, ocr_lines_by_image[0])
        else:
            ocr_blocks = []
            for index, lines in enumerate(ocr_lines_by_image, start=1):
                text = ocr_text(lines)
                if text:
                    ocr_blocks.append(f"Image {index}:\n{text}")
            if ocr_blocks:
                prompt = (
                    f"{prompt}\n\nDetected OCR text:\n"
                    + "\n\n".join(ocr_blocks)
                    + "\n\nUse the OCR text when it is relevant. Answer concisely."
                )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_to_png_base64(image) for image in images],
            }
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "num_predict": max(16, min(max_tokens, 1024)),
        },
    }
    data = post_json(f"{OLLAMA_URL}/api/chat", payload, OLLAMA_TIMEOUT_SECONDS)
    message = data.get("message") if isinstance(data, dict) else None
    answer = ""
    if isinstance(message, dict):
        answer = str(message.get("content") or "").strip()
    if not answer and isinstance(data, dict):
        answer = str(data.get("response") or "").strip()
    if not answer:
        answer = "I could not produce an image answer."
    return answer


def backend_for_model(model_id: str) -> str | None:
    if model_id == MODEL_ID:
        return "moondream"
    if OLLAMA_ENABLED and model_id == OLLAMA_MODEL_ID:
        return "ollama"
    return None


def chunk_payload(content: str, model_id: str, finish_reason=None) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "created": now(),
        "model": model_id,
        "choices": [{"index": 0, "delta": {"content": content} if content else {}, "finish_reason": finish_reason}],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "openwebui-local-vision/0.3"

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), fmt % args), flush=True)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = parse.urlparse(self.path).path
        if path == "/health":
            return send_json(
                self,
                200,
                {
                    "status": "ok",
                    "model": MODEL_ID,
                    "backend": HF_MODEL,
                    "revision": HF_REVISION,
                    "loaded": MODEL is not None,
                    "device": DEVICE,
                    "models": [card["id"] for card in model_cards()],
                    "ollama": {
                        "enabled": OLLAMA_ENABLED,
                        "model_id": OLLAMA_MODEL_ID if OLLAMA_ENABLED else None,
                        "backend_model": OLLAMA_MODEL if OLLAMA_ENABLED else None,
                        "url": OLLAMA_URL if OLLAMA_ENABLED else None,
                    },
                    "ocr": {
                        "enabled": ENABLE_OCR,
                        "loaded": OCR_ENGINE is not None,
                        "backend": "rapidocr-onnxruntime" if ENABLE_OCR else None,
                        "error": OCR_ERROR,
                    },
                    "load_timeout_hint_seconds": MODEL_LOAD_TIMEOUT_HINT,
                },
            )
        if path in {"/v1/models", "/models"}:
            cards = model_cards()
            return send_json(self, 200, {"object": "list", "data": cards, "models": cards})
        return send_json(self, 404, {"error": "not found"})

    def do_POST(self):
        path = parse.urlparse(self.path).path
        if path not in {"/v1/chat/completions", "/chat/completions"}:
            return send_json(self, 404, {"error": "not found"})

        try:
            payload = read_json(self)
            requested_model = str(payload.get("model") or MODEL_ID)
            backend = backend_for_model(requested_model)
            if backend is None:
                return send_json(
                    self,
                    404,
                    {
                        "error": {
                            "message": f"unknown local vision model {requested_model!r}",
                            "type": "model_not_found",
                        }
                    },
                )

            question, image_urls = content_to_text_and_images(payload.get("messages") or [])
            if not image_urls:
                return send_json(
                    self,
                    400,
                    {
                        "error": {
                            "message": f"{requested_model} requires at least one image_url or input_image content part"
                        }
                    },
                )

            max_tokens = int(payload.get("max_tokens") or 128)
            capped_tokens = max(8, min(max_tokens, 1024))
            if backend == "ollama":
                answer = answer_ollama_image_question(question, image_urls, capped_tokens)
            else:
                answer = answer_image_question(question, image_urls, min(capped_tokens, 512))

            if payload.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                event = "data: " + json.dumps(chunk_payload(answer, requested_model), ensure_ascii=False) + "\n\n"
                self.wfile.write(event.encode("utf-8"))
                done = "data: " + json.dumps(chunk_payload("", requested_model, "stop")) + "\n\n" + "data: [DONE]\n\n"
                self.wfile.write(done.encode("utf-8"))
                self.wfile.flush()
                return

            return send_json(
                self,
                200,
                {
                    "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                    "object": "chat.completion",
                    "created": now(),
                    "model": requested_model,
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
    print(f"local vision listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
