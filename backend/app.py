from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from analytics import ai_context_payload, dashboard_payload, load_dataset


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")


def _extract_response_text(response_json: dict) -> str:
    if response_json.get("output_text"):
        return response_json["output_text"]

    output_items = response_json.get("output", [])
    chunks: list[str] = []
    for item in output_items:
        for content in item.get("content", []):
            text_value = content.get("text")
            if text_value:
                chunks.append(text_value)
    return "\n".join(chunks).strip()


def generate_ai_insights(dataset: dict, question: str | None = None) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "available": False,
            "message": "OPENAI_API_KEY is not set. Add it to your environment to enable AI insights.",
        }

    snapshot = ai_context_payload(dataset)
    prompt = (
        "You are helping summarize a synthetic healthcare analytics dashboard. "
        "Use only the provided data snapshot. "
        "Explain the most important patterns in short bullet points and mention one follow-up question worth exploring.\n\n"
        f"Question: {question or 'What should a viewer notice first in this dashboard?'}\n\n"
        f"Data snapshot:\n{json.dumps(snapshot, indent=2)}"
    )

    payload = {
        "model": DEFAULT_MODEL,
        "instructions": (
            "Respond clearly for a data dashboard. Keep it concise, factual, and easy to read. "
            "Do not claim medical certainty because the data is synthetic."
        ),
        "input": prompt,
        "max_output_tokens": 350,
    }

    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=45) as response:
            response_json = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return {
            "available": False,
            "message": f"OpenAI API request failed with HTTP {error.code}.",
            "detail": detail,
        }
    except URLError as error:
        return {
            "available": False,
            "message": "Unable to reach the OpenAI API.",
            "detail": str(error.reason),
        }

    text = _extract_response_text(response_json)
    return {
        "available": True,
        "model": DEFAULT_MODEL,
        "insights": text or "The API returned an empty response.",
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json({"status": "ok"})
            return

        if self.path == "/api/dashboard":
            dataset = load_dataset()
            self._send_json(dashboard_payload(dataset))
            return

        if self.path in {"/", "/index.html"}:
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/ai-insights":
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON body"}, status=HTTPStatus.BAD_REQUEST)
            return

        dataset = load_dataset()
        result = generate_ai_insights(dataset, question=body.get("question"))
        status = HTTPStatus.OK if result.get("available", True) else HTTPStatus.SERVICE_UNAVAILABLE
        self._send_json(result, status=status)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the healthcare analytics dashboard server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind. Default: 8000")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard available at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
