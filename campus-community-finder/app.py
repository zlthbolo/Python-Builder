import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine import cached_conduct, aliases_for, planned_queries, resolve_known
from ui import PAGE

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def respond(self, status, body, mime="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path=urllib.parse.urlsplit(self.path)
        if path.path=="/":
            return self.respond(200,PAGE,"text/html; charset=utf-8")
        if path.path=="/health":
            return self.respond(200,json.dumps({"ok":True,"version":"2.0","streaming":True,"aliasDetection":True}))
        if path.path=="/api/self-test":
            aliases,keys,known=aliases_for("جامعة محمد بن زايد للذكاء الاصطناعي")
            passed=known=="mbzuai" and "MBZUAI" in aliases and len(planned_queries(aliases,"deep",keys))>=20
            return self.respond(200 if passed else 503,json.dumps({"passed":passed,"aliases":aliases[:4],"streamingPath":"/api/search/stream","version":"2.0"},ensure_ascii=False))
        if path.path not in ("/api/search","/api/search/stream"):
            return self.respond(404,json.dumps({"error":"المسار غير موجود"},ensure_ascii=False))
        params=urllib.parse.parse_qs(path.query)
        university=params.get("university",[""])[0].strip()
        mode=params.get("mode",["deep"])[0].lower()
        if not 2<=len(university)<=110 or mode not in ("quick","deep"):
            return self.respond(400,json.dumps({"error":"تحقق من اسم الجامعة ونوع البحث"},ensure_ascii=False))
        if path.path=="/api/search":
            # Compatibility with the v1 JSON endpoint; live UI uses the SSE stream instead.
            events=[]
            try:
                cached_conduct(university,mode,events.append)
                done=next((e for e in reversed(events) if e["type"]=="done"),None)
                if done is None:
                    return self.respond(503,json.dumps({"error":"البحث غير مكتمل"},ensure_ascii=False))
                return self.respond(200,json.dumps({"university":university,"found":done["found"],"queries":done["total"],"results":done["items"],"errors":done["errors"],"partial":done["partial"]},ensure_ascii=False))
            except Exception:
                return self.respond(503,json.dumps({"error":"تعذّر إكمال البحث من المصادر المتاحة"},ensure_ascii=False))
        self.close_connection=True
        try:
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream; charset=utf-8")
            self.send_header("Cache-Control","no-cache, no-transform")
            self.send_header("Connection","close")
            self.send_header("X-Accel-Buffering","no")
            self.send_header("Access-Control-Allow-Origin","same-origin")
            self.end_headers()
            self.wfile.write(b": search stream started\n\n")
            self.wfile.flush()
            def emit(payload):
                wire=("data: "+json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n\n").encode("utf-8")
                self.wfile.write(wire)
                self.wfile.flush()
            try:
                cached_conduct(university,mode,emit)
            except (BrokenPipeError,ConnectionResetError):
                return
            except Exception:
                emit({"type":"error","message":"تعذّر إكمال بعض مراحل البحث؛ حاول مجددًا."})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def log_message(self, format, *args):
        # No user-provided query strings in logs.
        return

if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler)
    print("Campus Community Finder v2 on port",server.server_port,flush=True)
    server.serve_forever()
