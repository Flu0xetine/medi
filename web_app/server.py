"""无需第三方依赖的本地网页服务器。"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ae_grading import classify
from web_app.config import frontend_config


STATIC_DIR = Path(__file__).resolve().parent / "static"


class WebHandler(BaseHTTPRequestHandler):
    """提供测试页面和规则引擎API。"""

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send(
                200,
                (STATIC_DIR / "index.html").read_bytes(),
                "text/html; charset=utf-8",
            )
            return
        if self.path == "/api/config":
            self._send_json(200, frontend_config())
            return
        self._send_json(404, {"error": "页面不存在"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/classify":
            self._send_json(404, {"error": "接口不存在"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length).decode("utf-8")
            self._send_json(200, classify(payload))
        except (TypeError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})

    def log_message(self, format: str, *args) -> None:
        """保留简洁请求日志。"""

        print(f"[web] {self.address_string()} {format % args}")


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    """启动本地测试网页。"""

    server = ThreadingHTTPServer((host, port), WebHandler)
    print(f"规则引擎测试页面：http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动A–E规则引擎测试网页")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run(args.host, args.port)
