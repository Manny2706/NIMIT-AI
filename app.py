import json
import mimetypes
import os
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


# def build_fallback_signals(transcript: str) -> list[dict[str, str]]:
#     lower = transcript.lower()
#     signals: list[dict[str, str]] = []

#     if any(phrase in lower for phrase in ["interesting", "send me", "pricing deck", "follow up", "circle back", "what's next"]):
#         signals.append(
#             {
#                 "type": "buying_interest",
#                 "quote": "Send me a pricing deck and I'll get back to you.",
#                 "tip": "Ask about their timeline now",
#             }
#         )

#     if any(phrase in lower for phrase in ["steep", "too expensive", "too much", "budget", "cost"]):
#         signals.append(
#             {
#                 "type": "pricing_objection",
#                 "quote": "That seems steep.",
#                 "tip": "Anchor value before discounting",
#             }
#         )

#     if any(phrase in lower for phrase in ["confused", "not sure", "how does", "clarify", "explain"]):
#         signals.append(
#             {
#                 "type": "confusion",
#                 "quote": "Could you clarify how this works?",
#                 "tip": "Slow down and restate the simple version",
#             }
#         )

#     if not signals:
#         quote = transcript.strip().splitlines()[0][:120] if transcript.strip() else ""
#         signals.append(
#             {
#                 "type": "neutral",
#                 "quote": quote,
#                 "tip": "Probe for a concrete next step",
#             }
#         )

#     return signals


def parse_json_payload(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].strip()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Model did not return valid JSON") from exc

    signals = payload.get("signals")
    if not isinstance(signals, list):
        raise ValueError("Missing signals array")

    clean_signals: list[dict[str, str]] = []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        signal_type = str(signal.get("type", "")).strip()
        quote = str(signal.get("quote", "")).strip()
        tip = str(signal.get("tip", "")).strip()
        if signal_type and quote and tip:
            clean_signals.append({"type": signal_type, "quote": quote, "tip": tip})

    return {"signals": clean_signals}


def analyse_with_llm(transcript: str) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

    if not api_key:
        # return {"signals": build_fallback_signals(transcript)}
        print("Warning: No API key found, returning empty signals")
        return {"signals": []}

    prompt = (
        "You are a sales call analyst. Read the transcript and identify concise signals such as "
        "buying_interest, pricing_objection, confusion, risk, or next_step. Return only valid JSON "
        "matching this exact shape: {\"signals\":[{\"type\":\"...\",\"quote\":\"...\",\"tip\":\"...\"}]}. "
        "Use short quotes copied from the transcript. Include one-line coaching tips. No markdown, no prose."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": transcript},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    request_data = json.dumps(payload).encode("utf-8")
    request_object = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=request_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:8000"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "NimitAI Transcript Signals"),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request_object, timeout=60) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter request failed: {exc.code} {error_body}") from exc

    content = response_payload["choices"][0]["message"]["content"].strip()
    return parse_json_payload(content)


class AppHandler(BaseHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.end_headers()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_text(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            index_path = ROOT / "templates" / "index.html"
            self._send_text(HTTPStatus.OK, index_path.read_bytes(), "text/html; charset=utf-8")
            return

        if self.path.startswith("/static/"):
            relative = self.path.removeprefix("/static/")
            asset_path = ROOT / "static" / relative
            if not asset_path.is_file():
                self._send_text(HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
                return
            content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
            self._send_text(HTTPStatus.OK, asset_path.read_bytes(), content_type)
            return

        self._send_text(HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        if self.path != "/analyse":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
            return

        transcript = str(body.get("transcript", "")).strip()
        if not transcript:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "transcript is required"})
            return

        try:
            result = analyse_with_llm(transcript)
        except Exception as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._send_json(HTTPStatus.OK, result)


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AppHandler)
    print(f"Serving on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
    
