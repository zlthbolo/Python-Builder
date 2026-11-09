import json
import re
import time
import threading
import html
import urllib.request
import urllib.parse
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from ddgs import DDGS

PLATFORMS = {
    "Telegram": "t.me", "WhatsApp": "chat.whatsapp.com",
    "Discord": "discord.gg", "Reddit": "reddit.com",
    "Facebook": "facebook.com", "Instagram": "instagram.com",
    "X": "x.com", "Threads": "threads.net",
    "Snapchat": "snapchat.com", "TikTok": "tiktok.com",
    "YouTube": "youtube.com", "Forums": ""
}
AKA = {
    "mbzuai": {
        "names": ["MBZUAI", "Mohamed bin Zayed University of Artificial Intelligence",
                  "Muhammad Bin Zayed University of Artificial Intelligence",
                  "جامعة محمد بن زايد للذكاء الاصطناعي", "جامعة محمد بن زايد الذكاء الاصطناعي"],
        "keywords": ["artificial intelligence", "machine learning", "computer vision", "NLP", "بكالوريوس الذكاء الاصطناعي", "ماجستير ذكاء اصطناعي"],
        "seeds": [
            ("Discord", "MBZUAI Unofficial", "https://discord.gg/EXnhnsDTHq", "مجتمع طلابي غير رسمي، صفحة الدعوة عُرضت عند الفحص", "https://discord.com/invite/EXnhnsDTHq", "invite-page-verified"),
            ("Discord", "MBZUAI Bachelors", "https://discord.gg/gskaQe9BCY", "طلاب البكالوريوس، صفحة الدعوة عُرضت عند الفحص", "https://discord.com/invite/gskaQe9BCY", "invite-page-verified"),
            ("Telegram", "MBZUAI Eurasia", "https://t.me/mbzuai_eurasia", "مجموعة مرتبطة بمتقدمي الجامعة من أوراسيا", "https://t.me/mbzuai_eurasia", "invite-page-verified"),
            ("WhatsApp", "MBZUAI UG Aspirants 26", "https://chat.whatsapp.com/EJP2ygiOHldL4X8ZIMMSB5", "متقدمو البكالوريوس، رابط معلن في دليل غير رسمي", "https://iglory.notion.site/the-unofficial-complete-guide-to-mbzuai", "public-link-unverified"),
            ("WhatsApp", "MBZUAI Admission Discussion", "https://chat.whatsapp.com/JAP5SYvIRmd2owoscocgqY", "نقاشات القبول، رابط معلن في دليل غير رسمي", "https://iglory.notion.site/the-unofficial-complete-guide-to-mbzuai", "public-link-unverified"),
            ("Reddit", "r/MBZUAI", "https://www.reddit.com/r/MBZUAI/", "منتدى عام للاستفسارات والنقاشات الطلابية", "https://www.reddit.com/r/MBZUAI/", "public-community")
        ]
    }
}
CACHE = {}
CACHE_LOCK = threading.Lock()
ENGINE_GATE = threading.BoundedSemaphore(2)
SEARCH_GATE = threading.BoundedSemaphore(2)
INVITE_HOSTS = {
    "t.me": "Telegram", "telegram.me": "Telegram",
    "chat.whatsapp.com": "WhatsApp",
    "discord.gg": "Discord", "discord.com": "Discord",
    "reddit.com": "Reddit", "www.reddit.com": "Reddit",
    "facebook.com": "Facebook", "www.facebook.com": "Facebook", "m.facebook.com": "Facebook",
    "instagram.com": "Instagram", "www.instagram.com": "Instagram",
    "x.com": "X", "twitter.com": "X",
    "threads.net": "Threads", "threads.com": "Threads",
    "snapchat.com": "Snapchat", "tiktok.com": "TikTok",
    "youtube.com": "YouTube", "youtu.be": "YouTube"
}
INVITE_RE = re.compile(r'https?://(?:www\.)?(?:t\.me|telegram\.me|chat\.whatsapp\.com|discord\.gg|discord\.com/invite|reddit\.com/r)/[^\s<>"\]\)]+', re.I)
STOPWORDS = {"university", "جامعة", "الجامعة", "bin", "بن", "of", "the", "for", "in", "and", "جامعة"}
ALIAS_WORDS = re.compile(r'\b[A-Z]{4,12}\b')
EXCLUDED_ABBREVS = {"UNIVERSITY", "STUDENTS", "ADMISSION", "DISCORD", "WHATSAPP", "FACEBOOK", "SCHOOL", "REDDIT", "THREADS", "GOOGLE", "APPLY", "GROUP", "GROUPS"}

def norm(s):
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    s = re.sub(r'[\u064b-\u065f\u0670\u0640]', '', s)
    return re.sub(r'\s+', ' ', s.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ى","ي").replace("ة","ه")).strip()

def resolve_known(text):
    n = norm(text)
    if "mbzuai" in n or ("محمد بن زايد" in n and ("ذكاء" in n or "اصطناع" in n)) or ("mohamed bin zayed" in n and "intelligence" in n):
        return "mbzuai"
    return None

def wikidata_aliases(query):
    # Public Wikidata lookup; optional. Never assume an unverified result is a correct translation.
    api = "https://www.wikidata.org/w/api.php"
    for lang in (["ar","en"] if re.search(r'[\u0600-\u06ff]', query) else ["en","ar"]):
        try:
            args = urllib.parse.urlencode({"action":"wbsearchentities", "search":query, "language":lang, "limit":3, "format":"json"})
            req = urllib.request.Request(api+"?"+args, headers={"User-Agent":"CampusCommunityFinder/2.0 (public university community discovery)"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.load(resp)
            for item in data.get("search",[])[:3]:
                d = str(item.get("description","")).lower()
                name = str(item.get("label",""))
                if not any(x in d for x in ("university", "higher education", "college", "جامعة")) and not any(x in name.lower() for x in ("university", "جامعة")):
                    continue
                identifier = item.get("id")
                if not identifier: continue
                req2 = urllib.request.Request(api+"?"+urllib.parse.urlencode({"action":"wbgetentities","ids":identifier,"props":"labels|aliases","languages":"ar|en","format":"json"}),headers={"User-Agent":"CampusCommunityFinder/2.0"})
                with urllib.request.urlopen(req2,timeout=3.5) as resp:
                    obj = json.load(resp).get("entities",{}).get(identifier,{})
                options = [name]
                for field in ("labels","aliases"):
                    for lg in ("en","ar"):
                        value=obj.get(field,{}).get(lg,[])
                        if isinstance(value,dict):value=[value]
                        options += [v.get("value","") for v in value if isinstance(v,dict)]
                return [a for a in options if 3<len(a)<125]
        except Exception:
            continue
    return []

def aliases_for(university):
    known=resolve_known(university)
    items=[university]
    keywords=[]
    if known:
        items=AKA[known]["names"]+items
        keywords=AKA[known]["keywords"]
    else:
        items.extend(wikidata_aliases(university))
        # Arabic query variant without the "جامعة" prefix.
        if norm(university).startswith("جامعه "):
            items.append(university.split(" ",1)[1])
    unique=[]
    for a in items:
        if a and norm(a) not in [norm(z) for z in unique]:unique.append(a)
    # Pick a short acronym first and one Arabic and English full name.
    short=[x for x in unique if re.fullmatch(r'[A-Za-z]{3,12}',x)]
    english=[x for x in unique if re.search(r'[a-zA-Z]',x) and x not in short]
    arabic=[x for x in unique if re.search(r'[\u0600-\u06ff]',x)]
    ordered=[]
    for a in [*short,*english,*arabic,*unique]:
        if a not in ordered:ordered.append(a)
    return ordered[:6],keywords,known

def planned_queries(names, mode, keywords):
    focused=names[:3] if mode=="deep" else names[:2]
    platform_order=["Telegram","WhatsApp","Discord","Reddit","Facebook","Instagram","X","Threads","Snapchat","TikTok","YouTube","Forums"]
    jobs=[];seen=set()
    def add(platform,q):
        if q.lower() not in seen:
            jobs.append((platform,q))
            seen.add(q.lower())
    for i, name in enumerate(focused):
        quoted='"'+name+'"'
        platforms=platform_order if (i==0 and mode=="deep") else platform_order[:6]
        if mode=="quick": platforms=platform_order[:6]
        for platform in platforms:
            domain=PLATFORMS[platform]
            q=quoted+((" site:"+domain) if domain else " student forum discussion")
            add(platform,q)
    for name in names[:2 if mode=="quick" else 3]:
        quoted='"'+name+'"'
        add("Community",quoted+" students group discussion")
        add("Community",quoted+" telegram whatsapp discord invite")
        if mode=="deep":
            add("Community",quoted+" undergraduate graduate applicants student community")
            add("Community",quoted+" قروب طلاب دفعة قبول استفسارات")
            add("Community",quoted+" study projects student experience reddit")
    if mode=="deep":
        lead=names[0]
        for phrase in ["discord.gg", "chat.whatsapp.com", "t.me", "reddit", "طلبة", "student discord"]:
            add("Community",'"'+lead+'" '+phrase)
        for subject in keywords[:3]:
            add("Community",'"'+lead+'" '+subject+" students discussion")
    return jobs[:15 if mode=="quick" else 43]

def clean_url(raw):
    try:
        p=urllib.parse.urlsplit(html.unescape(str(raw)).strip().rstrip(".,;"))
        if p.scheme not in ("http","https") or not p.hostname or p.username or p.password: return None
        if len(raw)>1500 or p.port not in (None,80,443): return None
        host=p.hostname.lower().removeprefix("www.")
        path=p.path.rstrip("/") or "/"
        return urllib.parse.urlunsplit(("https",host,path,"",""))
    except (ValueError,TypeError): return None

def platform_for(url):
    try:
        host=urllib.parse.urlsplit(url).hostname or ""
        host=host.lower()
        for domain,platform in INVITE_HOSTS.items():
            if host==domain or host.endswith("."+domain):
                return platform
    except Exception: pass
    return "Web"

def relevance(title,snippet,url,aliases):
    text=norm(title+" "+snippet+" "+url)
    weight=0
    for i,a in enumerate(aliases):
        n=norm(a)
        if n and n in text: weight=max(weight, 9 if i<2 else 7)
    if not weight:
        for a in aliases:
            toks=[t for t in norm(a).split() if len(t)>3 and t not in STOPWORDS]
            if len(toks)>=2 and sum(t in text for t in toks)>=2:
                weight=max(weight,4)
    if not weight:return 0
    joined=norm(title+" "+snippet)
    if any(w in joined for w in ("طلاب","طالب","دفعة","استفسار","group","community","students","applicant","discussion","bachelor","reddit","admission","cohort")):weight+=3
    if platform_for(url) in ("Discord","WhatsApp","Telegram","Reddit"):weight+=3
    return weight

def classify_url(url):
    platform=platform_for(url)
    p=urllib.parse.urlsplit(url)
    if platform in ("Discord","WhatsApp","Telegram"):return "مجموعة / قناة محتملة"
    if platform=="Reddit" and p.path.startswith("/r/") and p.path.count("/")<=3:return "مجتمع عام"
    return "منشور أو صفحة ذات صلة"

def result_item(platform,title,url,desc,source,verification,aliases):
    canonical=clean_url(url)
    if not canonical:return None
    p=platform_for(canonical)
    rank=relevance(title,desc,canonical,aliases)
    if rank<4 and verification not in ("invite-page-verified","public-link-unverified","public-community"):return None
    return {"platform":p if p!="Web" else platform,"title":title[:170],"url":canonical,"snippet":desc[:400],
            "source":source,"kind":classify_url(canonical),"verification":verification,
            "score":rank,"checkedAt":"2026-11-09" if verification in ("invite-page-verified","public-link-unverified","public-community") else None}

def seeds(known,aliases):
    if not known:return []
    out=[]
    for platform,title,url,desc,source,verification in AKA[known]["seeds"]:
        obj=result_item(platform,title,url,desc,source,verification,aliases)
        if obj:out.append(obj)
    return out

def indexed_search(query,mode):
    # Search multiple index backends; free public indexes may throttle requests.
    failures=[]
    for backend in ("auto","bing","google"):
        try:
            with ENGINE_GATE:
                engine=DDGS(timeout=8)
                rows=list(engine.text(query,max_results=5 if mode=="quick" else 7,backend=backend) or [])
            if rows:return rows,None
        except Exception as e:
            failures.append(type(e).__name__)
    return [], (" / ".join(failures) or "no indexed results")

def discover_from_row(row, aliases):
    url=row.get("href") or row.get("url") or ""
    title=str(row.get("title") or "")
    body=str(row.get("body") or "")
    primary=result_item(platform_for(url),title or url,url,body,url,"indexed-unverified",aliases)
    objs=[]
    if primary:objs.append(primary)
    # Links visible inside public snippets can reveal direct invite URLs in outside pages.
    for link in INVITE_RE.findall(html.unescape(body+" "+title)):
        direct=result_item(platform_for(link),"رابط مجموعة مذكور في نتيجة بحث",link,
                           title+" — "+body[:230],url,"linked-unverified",aliases)
        if direct:objs.append(direct)
    return objs

def conduct(university,mode,callback):
    if len(university)>110 or len(university)<2:raise ValueError("اسم الجامعة يجب أن يكون بين حرفين و110 أحرف")
    if mode not in ("quick","deep"):raise ValueError("وضع البحث غير صحيح")
    aliases,keywords,known=aliases_for(university)
    jobs=planned_queries(aliases,mode,keywords)
    query_total=len(jobs)
    results={};errors=[]
    def collect(item):
        if not item:return
        original=results.get(item["url"])
        if original is None or item["score"]>original["score"]:
            results[item["url"]]=item
            callback({"type":"result","item":item,"found":len(results)})
    callback({"type":"aliases","aliases":aliases,"keywords":keywords,"total":query_total,
              "stage":"اكتشاف الاسم واختصارات الجامعة"})
    for item in seeds(known,aliases):collect(item)
    callback({"type":"progress","completed":0,"total":query_total,"found":len(results),
              "stage":"تجهيز المصادر الطلابية العامة"})
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks={pool.submit(indexed_search,q,mode):(platform,q) for platform,q in jobs}
        completed=0
        for fut in as_completed(tasks):
            platform,q=tasks[fut];completed+=1
            try:
                rows,error=fut.result()
                if error:errors.append({"platform":platform,"reason":error})
                for row in rows:
                    for obj in discover_from_row(row,aliases):collect(obj)
            except Exception as exc:
                errors.append({"platform":platform,"reason":type(exc).__name__})
            callback({"type":"progress","completed":completed,"total":query_total,
                      "found":len(results),"stage":"فحص نتائج "+platform,
                      "partial":bool(errors)})
    best=sorted(results.values(),key=lambda x:x["score"],reverse=True)
    callback({"type":"done","completed":query_total,"total":query_total,
              "found":len(best),"items":best,"errors":errors[:7],
              "partial":bool(errors),"disclaimer":"تغطي النتائج الروابط المفهرسة علنًا وبعض روابط جرى فحص صفحاتها سابقًا، ولا تغطي المحادثات الخاصة أو ملايين البيانات."})
    return best

def cached_conduct(university,mode,callback):
    key=(norm(university),mode)
    with CACHE_LOCK:
        old=CACHE.get(key)
    if old and time.monotonic()-old[0]<480:
        for event in old[1]:callback(event)
        return
    events=[]
    def send(event):
        events.append(event)
        callback(event)
    with SEARCH_GATE:
        conduct(university,mode,send)
    with CACHE_LOCK:
        CACHE[key]=(time.monotonic(),events)
        if len(CACHE)>20:
            for k in list(CACHE)[:5]:CACHE.pop(k,None)
