#!/usr/bin/env python3
"""For docker/e2e.sh: a scripted OpenAI-compatible chat model.

    scripted_model.py SCRIPT.json [PORT]

The n-th request of a conversation gets step n of SCRIPT: tool calls, or a final text. A
subagent whose first message contains CHILD gets CHILD's steps instead. Each request is
logged to $LOG_DIR."""
import json, os, sys, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = os.environ.get("LOG_DIR", "/probe")
SCRIPT = json.load(open(sys.argv[1]))
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8999


CHILD = [{"calls": [{"name": "bash", "args": {"command": "echo from-child"}}]}, {"text": "child done"}]


def step_for(messages):
    n = sum(1 for m in messages if m.get("role") == "assistant")
    users = [m for m in messages if m.get("role") == "user"]
    script = CHILD if users and "CHILD" in str(users[0].get("content")) else SCRIPT
    return script[min(n, len(script) - 1)]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "scripted", "object": "model"}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with open(os.path.join(LOG, f"req-{time.time_ns()}.json"), "w") as fh:
            json.dump(req, fh, indent=1)
        msgs = req.get("messages", [])
        # a title/utility request has no tools: answer with text
        step = step_for(msgs) if req.get("tools") else {"text": "Spike"}
        calls = [{"index": i, "id": "call_" + uuid.uuid4().hex[:8], "type": "function",
                  "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                 for i, c in enumerate(step.get("calls", []))]
        text = step.get("text", "")
        finish = "tool_calls" if calls else "stop"
        if req.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            def send(obj):
                self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n"); self.wfile.flush()
            base = {"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "scripted"}
            send({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": text or None,
                  **({"tool_calls": calls} if calls else {})}, "finish_reason": None}]})
            send({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                  "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
            return
        msg = {"role": "assistant", "content": text or None}
        if calls:
            msg["tool_calls"] = [{k: v for k, v in c.items() if k != "index"} for c in calls]
        body = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": "scripted",
                           "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                           "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
