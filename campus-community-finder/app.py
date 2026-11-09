import json, os, time, threading, urllib.parse, html
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from ddgs import DDGS

SITES = {
"Telegram":"t.me","WhatsApp":"chat.whatsapp.com","Discord":"discord.gg",
"Reddit":"reddit.com","Facebook":"facebook.com/groups","Instagram":"instagram.com",
"X":"x.com","Threads":"threads.net","Snapchat":"snapchat.com",
"TikTok":"tiktok.com","YouTube":"youtube.com","Forums":""
}
CACHE = {}
LOCK = threading.Lock()
SEM = threading.BoundedSemaphore(2)
PAGE = """<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>مستكشف مجتمعات الجامعات</title><style>body{font-family:system-ui;background:#0e1629;color:#ecf1fc;margin:0;padding:28px}main{max-width:1000px;margin:auto}h1{font-size:30px}p{color:#a9b7ce}input,select,button{font:inherit;border-radius:12px;padding:14px;border:1px solid #445673;background:#192740;color:white}input{width:min(500px,90%)}button{background:#7159ed;cursor:pointer}button:disabled{opacity:.5}.panel,.item{border:1px solid #35445e;background:#142038;border-radius:14px;padding:18px;margin:12px 0}.item a{color:#9dcaff;overflow-wrap:anywhere}.tag{background:#243857;border-radius:8px;padding:3px 9px;margin:5px;display:inline-block}small{color:#adbad0}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}</style><main><h1>🔎 مستكشف مجتمعات طلاب الجامعات</h1><p>بحث في الروابط والنقاشات العامة عبر 12 منصة. لا يفتح المجموعات الخاصة أو المحادثات المحمية.</p><section class="panel"><div class="row"><input id="uni" placeholder="اسم الجامعة بالعربية أو الإنجليزية"><select id="mode"><option value="quick">سريع</option><option value="deep">معمق</option></select><button id="go" onclick="run()">بحث</button></div><p id="status"></p></section><div id="results"></div></main><script>
function esc(s){return String(s??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]))}
async function run(){let u=document.getElementById('uni').value.trim(),m=document.getElementById('mode').value;if(!u)return;let b=document.getElementById('go');b.disabled=true;document.getElementById('status').textContent='يجري البحث في المصادر العامة...';document.getElementById('results').innerHTML='';try{let r=await fetch('/api/search?university='+encodeURIComponent(u)+'&mode='+m),d=await r.json();if(!r.ok)throw Error(d.error||'تعذّر الاتصال بمصادر البحث');document.getElementById('status').textContent='تم العثور على '+d.found+' نتيجة مرشحة عبر '+d.queries+' استعلامًا'+(d.errors?.length?'؛ بعض المصادر لم تستجب':'');document.getElementById('results').innerHTML=d.results.map(x=>'<article class="item"><span class="tag">'+esc(x.platform)+'</span><h3>'+esc(x.title)+'</h3><p>'+esc(x.snippet)+'</p><a href="'+esc(x.url)+'" target="_blank" rel="noopener noreferrer">'+esc(x.url)+'</a><p><small>مرشح من فهرس بحث عام؛ لم يُتحقق من نشاط المجموعة أو صلاحية الدعوة.</small></p></article>').join('')||'<p>لم أجد روابط مفهرسة بهذه الاستعلامات. جرّب الاسم الإنجليزي أو المختصر.</p>'}catch(e){document.getElementById('status').textContent=e.message}finally{b.disabled=false}}
</script></html>"""

def find(university,mode):
    if not 2 <= len(university) <= 110: raise ValueError("اكتب اسم جامعة صحيحًا، من حرفين إلى 110 أحرف.")
    if mode not in ("quick","deep"):raise ValueError("وضع البحث غير صحيح")
    key=(university.casefold(),mode)
    with LOCK:
        old=CACHE.get(key)
        if old and time.monotonic()-old[0]<600:return old[1]
    queries=[]
    for platform,domain in SITES.items():
        query=f'"{university}" '+(f'site:{domain} ' if domain else '')+'(students OR طلاب OR دفعة OR community)'
        queries.append((platform,query))
        if mode=="deep":
            queries.append((platform,f'"{university}" '+(f'site:{domain} ' if domain else '')+'(group OR ملتقى OR مشاريع OR قسم OR batch)'))
    if mode=="deep":
        queries += [("Telegram",f'"{university}" "t.me/"'),("WhatsApp",f'"{university}" "chat.whatsapp.com/"'),("Discord",f'"{university}" "discord.gg/"'),("Forums",f'"{university}" "student forum"')]
    results={}; errors=[]
    def search(item):
        platform,q=item
        try:
            with SEM:
                rows=DDGS(timeout=9).text(q,max_results=4 if mode=="quick" else 6,safesearch="moderate") or []
            return platform,rows,None
        except Exception as e:return platform,[],type(e).__name__
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(search,q) for q in queries]):
            platform,rows,error=f.result()
            if error:errors.append(platform+": "+error)
            for r in rows:
                raw=r.get("href") or r.get("url") or ""
                try:
                    p=urllib.parse.urlsplit(raw)
                    if p.scheme not in ("http","https") or not p.hostname or p.username or p.password:continue
                    if len(raw)>1500:continue
                    host=p.hostname.lower().removeprefix("www.")
                    domain=SITES.get(platform)
                    if domain and not (host==domain or host.endswith("."+domain) or (platform=="Discord" and host=="discord.com") or (platform=="Telegram" and host=="telegram.me") or (platform=="X" and host=="twitter.com") or (platform=="Threads" and host=="threads.com")):continue
                    url=urllib.parse.urlunsplit(("https",p.netloc,p.path,"",""))
                except (ValueError,TypeError):continue
                title=str(r.get("title") or "")[:220]
                snippet=str(r.get("body") or "")[:380]
                score=5*int(university.lower() in (title+" "+snippet).lower())+sum(w.lower() in (title+" "+snippet).lower() for w in university.split() if len(w)>2)
                if url not in results or results[url]["score"]<score:
                    results[url]={"platform":platform,"title":title,"snippet":snippet,"url":url,"score":score}
    result={"university":university,"found":len(results),"queries":len(queries),"results":sorted(results.values(),key=lambda r:r["score"],reverse=True),"errors":errors,"partial":bool(errors)}
    with LOCK:
        CACHE[key]=(time.monotonic(),result)
        if len(CACHE)>30:CACHE.clear()
    return result

class Handler(BaseHTTPRequestHandler):
    def respond(self,status,body,mime):
        body=body.encode()
        self.send_response(status);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(body)));self.send_header("X-Content-Type-Options","nosniff");self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=urllib.parse.urlsplit(self.path)
        if path.path=="/":return self.respond(200,PAGE,"text/html; charset=utf-8")
        if path.path=="/health":return self.respond(200,'{"ok":true}',"application/json")
        if path.path!="/api/search":return self.respond(404,"Not found","text/plain")
        q=urllib.parse.parse_qs(path.query)
        try:
            university=q.get("university",[""])[0].strip()
            result=find(university,q.get("mode",["quick"])[0])
            return self.respond(200,json.dumps(result,ensure_ascii=False),"application/json; charset=utf-8")
        except ValueError as e:return self.respond(400,json.dumps({"error":str(e)},ensure_ascii=False),"application/json")
        except Exception:return self.respond(503,'{"error":"تعذّر إكمال البحث الآن"}',"application/json")
    def log_message(self,*args):pass
if __name__=="__main__":
    ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),Handler).serve_forever()
