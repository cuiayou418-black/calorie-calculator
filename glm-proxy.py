#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轻食卡 · 智谱 GLM 本地转发代理（仅用 Python 标准库）

智谱开放平台接口未开放浏览器跨域（CORS），网页无法直接调用。
本代理只做透明转发：页面 -> 本地代理 -> open.bigmodel.cn -> 原样回传。

- 只监听 127.0.0.1，不对外暴露
- 不保存、不打印 API Key 与照片内容
- 透传上游状态码与错误体，便于页面区分 401 / 429 等错误

用法：
    python glm-proxy.py                 # 默认 8787 端口
    python glm-proxy.py --port 9000     # 自定义端口（需同步修改页面接口地址）

默认使用 DeepSeek 时不需要本脚本。
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
UPSTREAM_PATH = "/api/paas/v4/chat/completions"
TIMEOUT = 90

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Max-Age": "86400",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "QingShiKaProxy/1.0"

    def log_message(self, fmt, *args):
        # 只记录请求行，绝不记录请求头/正文（其中含 API Key 与照片）
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _cors(self):
        for key, value in CORS_HEADERS.items():
            self.send_header(key, value)

    def _send(self, status, payload, content_type="application/json; charset=utf-8"):
        if isinstance(payload, bytes):
            data = payload
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain; charset=utf-8")

    def do_GET(self):
        if self.path.rstrip("/") in ("", "/health"):
            self._send(200, {"ok": True, "upstream": UPSTREAM, "post_to": UPSTREAM_PATH})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != UPSTREAM_PATH:
            self._send(404, {"error": "unexpected path", "expected": UPSTREAM_PATH})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self._send(400, {"error": "empty request body"})
            return
        body = self.rfile.read(length)

        auth = self.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            self._send(401, {"error": "missing Authorization: Bearer <API_KEY>"})
            return

        request = urllib.request.Request(
            UPSTREAM,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": auth,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                self._send(
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", "application/json"),
                )
        except urllib.error.HTTPError as exc:
            # 透传上游状态码与错误体，便于前端给出对应的友好提示
            self._send(
                exc.code,
                exc.read(),
                exc.headers.get("Content-Type", "application/json"),
            )
        except urllib.error.URLError as exc:
            self._send(502, {"error": "upstream unreachable", "detail": str(exc.reason)})
        except Exception as exc:  # noqa: BLE001 - 代理需保证任何异常都有响应
            self._send(502, {"error": "proxy error", "detail": str(exc)})


def main():
    parser = argparse.ArgumentParser(description="轻食卡 · 智谱 GLM 本地转发代理")
    parser.add_argument("--port", type=int, default=8787, help="监听端口，默认 8787")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("轻食卡 GLM 代理已启动")
    print("  页面接口地址： http://localhost:%d%s" % (args.port, UPSTREAM_PATH))
    print("  转发上游：     " + UPSTREAM)
    print("  按 Ctrl+C 停止（识别期间请保持本窗口打开）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        server.shutdown()


if __name__ == "__main__":
    main()
