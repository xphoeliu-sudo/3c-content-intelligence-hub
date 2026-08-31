import os,json,re,hashlib,datetime as dt,warnings
from urllib.parse import urljoin,quote
import requests,feedparser
from bs4 import BeautifulSoup,MarkupResemblesLocatorWarning
warnings.filterwarnings("ignore",category=MarkupResemblesLocatorWarning)
BASE=os.path.dirname(__file__); DATA=os.path.join(BASE,"data.json"); CONFIG=os.path.join(BASE,"sources.json")
SCREEN_DIR=os.path.join(BASE,"assets","screenshots"); os.makedirs(SCREEN_DIR,exist_ok=True)
H={"User-Agent":"Mozilla/5.0 3C-Wearables-Intelligence-V6"}; TIMEOUT=20; NOW=dt.datetime.now(dt.timezone.utc); KUALA=dt.timezone(dt.timedelta(hours=8))
WATCH=["watch","smartwatch","wearable","fitness tracker","smart band","smart ring","health wearable","fitness","health","sleep","running","training","recovery","wellness","workout","sport","heart","ecg","blood oxygen","galaxy watch","apple watch","forerunner","fēnix","fenix","venu","vivoactive","lily","instinct","epix","cirqa","airpods","buds","earbuds","headphones","smart glasses","ai glasses"]
TECH=["ai","health","fitness","training","sleep","recovery","sensor","ecg","blood oxygen","heart rate","battery","gps","audio","glasses","ring","tablet","phone"]
NOISE=["aviation","marine","chartplotter","fishfinder","autopilot","truck","automotive","repair","manual","support","careers","investor","financial results"]
def clean(s): return re.sub(r"\s+"," ",BeautifulSoup(str(s or ""), "html.parser").get_text(" ",strip=True)).strip()
def iso(): return dt.datetime.now(dt.timezone.utc).astimezone(KUALA).isoformat()
def fetch(u,t=TIMEOUT):
    r=requests.get(u,headers=H,timeout=t,allow_redirects=True); r.raise_for_status(); return r
def relevant(t,nonwear=False):
    t=t.lower()
    if any(n in t for n in NOISE) and not any(x in t for x in WATCH): return False
    return any(x in t for x in (WATCH+TECH if nonwear else WATCH))
def classify(t,s="",u=""):
    x=(t+" "+s+" "+u).lower()
    for terms,label in [(["unboxing","unbox"],"Unboxing"),(["how to","how-to","tutorial","setup"],"How-to"),(["campaign","commercial","advert","brand film"],"Campaign / Ad"),(["launch","unveiled","introducing"],"Launch"),(["athlete","ambassador","creator","influencer"],"Creator / Athlete"),(["demo","demonstration","hands-on"],"Product Demo"),(["event","keynote","unpacked"],"Event"),(["review","first look"],"Review / First Look")]:
        if any(k in x for k in terms): return label
    return "Product / Brand Content"
def entrydate(e):
    for k in ("published","updated"):
        if e.get(k):
            try:
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(e[k]).isoformat()
            except: pass
    return NOW.isoformat()
def dedupe(items):
    seen=set();out=[]
    for x in items:
        k=hashlib.sha1((x.get("brand","")+x.get("market","")+x.get("title","")+x.get("url","")).lower().encode()).hexdigest()
        if k not in seen: seen.add(k);out.append(x)
    return out
def rss(url,brand,market,source="Discovery",allow_nonwear=False,max_items=20):
    out=[]
    try:
        f=feedparser.parse(fetch(url).content)
        for e in f.entries[:max_items]:
            t=clean(e.get("title",""));s=clean(e.get("summary",""));u=e.get("link","")
            if relevant(t+" "+s+" "+u,allow_nonwear):
                out.append({"brand":brand,"market":market,"source_type":source,"title":t,"summary":s[:700],"url":u,"date":entrydate(e),"format":classify(t,s,u)})
    except Exception as ex: print("[RSS ERROR]",brand,market,ex)
    return out
def gnews(q,brand,market):
    return rss("https://news.google.com/rss/search?q="+quote(q)+"&hl=en-US&gl=US&ceid=US:en",brand,market,"Discovery",True,20)
def official(src):
    out=[]
    try:
        soup=BeautifulSoup(fetch(src["url"]).text,"html.parser")
        for a in soup.find_all("a",href=True):
            t=clean(a.get_text(" ",strip=True));u=urljoin(src["url"],a["href"]);blob=(t+" "+u).lower()
            if len(t)<6 or not relevant(blob,src.get("allow_nonwearable",False)): continue
            if any(k in blob for k in ["support","manual","repair","careers","investor"]): continue
            out.append({"brand":src["brand"],"market":src["market"],"source_type":"Official","title":t,"summary":"","url":u,"date":iso(),"format":classify(t,"",u)})
    except Exception as ex: print("[OFFICIAL ERROR]",src["brand"],src["market"],ex)
    return out
def youtube(q,brand,market,n=8):
    out=[]
    try:
        import yt_dlp
        opts={"quiet":True,"skip_download":True,"extract_flat":True,"playlistend":n,"ignoreerrors":True}
        with yt_dlp.YoutubeDL(opts) as y:
            info=y.extract_info("ytsearch"+str(n)+":"+q,download=False)
        for e in (info.get("entries") or []):
            if not e or not e.get("id"): continue
            t=clean(e.get("title",""));u="https://www.youtube.com/watch?v="+e["id"]
            if not relevant(t,True): continue
            out.append({"brand":brand,"market":market,"source_type":"YouTube","platform":"YouTube","title":t,"summary":"","url":u,"thumbnail":f"https://i.ytimg.com/vi/{e['id']}/hqdefault.jpg","date":e.get("upload_date","") or iso(),"format":classify(t,"",u),"embed":u})
    except Exception as ex: print("[YOUTUBE ERROR]",brand,market,ex)
    return out
def social():
    out=[]
    for b,m,q in [("Apple","Global","Apple official Apple Watch"),("Samsung","Global","Samsung official Galaxy Watch"),("Garmin","Global","Garmin official smartwatch fitness"),("Apple","Malaysia","Apple Malaysia Apple Watch"),("Samsung","Malaysia","Samsung Malaysia Galaxy Watch"),("Garmin","Malaysia","Garmin Malaysia smartwatch")]:
        out+=youtube(q,b,m,8)
    for b,m in [("Apple","Global"),("Samsung","Global"),("Garmin","Global"),("Apple","Malaysia"),("Samsung","Malaysia"),("Garmin","Malaysia")]:
        out+=gnews(f'"{b}" Instagram OR TikTok watch OR wearable OR earbuds when:7d',b,m)
    return dedupe(out)[:80]
def page(url,brand,market,ptype,product):
    try:
        r=fetch(url,30);s=BeautifulSoup(r.text,"html.parser");text=clean(s.get_text(" ",strip=True))
        title=clean(s.title.get_text() if s.title else "")
        h1=[clean(x.get_text(" ",strip=True)) for x in s.find_all("h1")[:5]]
        h2=[clean(x.get_text(" ",strip=True)) for x in s.find_all(["h2","h3"])[:30]]
        vids=[urljoin(url,v.get("src") or v.get("data-src")) for v in s.find_all(["video","iframe","source"]) if v.get("src") or v.get("data-src")]
        links=[]
        for a in s.find_all("a",href=True):
            t=clean(a.get_text(" ",strip=True))
            if any(k in t.lower() for k in ["buy","shop","learn","compare","video","how to","guide"]): links.append({"text":t[:120],"url":urljoin(url,a["href"])})
        h=hashlib.sha256((title+"|"+clean(" ".join(h1))+"|"+clean(" ".join(h2))+"|"+text[:30000]).encode()).hexdigest()
        return {"brand":brand,"market":market,"page_type":ptype,"product":product,"url":url,"title":title,"h1":h1,"headings":h2,"videos":vids[:15],"commerce_links":links[:30],"text_excerpt":text[:5000],"hash":h}
    except Exception as ex: print("[PAGE ERROR]",brand,market,url,ex)
def screenshot(url,key):
    path=os.path.join(SCREEN_DIR,key+".png")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b=p.chromium.launch();pg=b.new_page(viewport={"width":1440,"height":900})
            pg.goto(url,wait_until="domcontentloaded",timeout=45000);pg.wait_for_timeout(2500);pg.screenshot(path=path,full_page=True);b.close()
        return "assets/screenshots/"+key+".png"
    except Exception as ex: print("[SCREENSHOT ERROR]",url,ex); return ""
def pages(config,old):
    out=[];changes=[]; oldmap={x.get("url"):x for x in old.get("pageSnapshots",[])}
    for p in config["pages"]:
        x=page(p["url"],p["brand"],p["market"],p["page_type"],p["product"])
        if not x: continue
        key=hashlib.md5(p["url"].encode()).hexdigest()[:12];x["screenshot"]=screenshot(p["url"],key)
        if oldmap.get(p["url"]) and oldmap[p["url"]].get("hash")!=x["hash"]:
            changes.append({"brand":p["brand"],"market":p["market"],"page_type":p["page_type"],"product":p["product"],"url":p["url"],"screenshot":x["screenshot"],"changeSummary":"Page content structure or copy changed since the previous snapshot."})
        out.append(x)
    return out,changes
def collect_market(c):
    a=[]
    for s in c["rss_sources"]: a+=rss(s["url"],s["brand"],s["market"],s["source_type"],s.get("allow_nonwearable",False))
    for s in c["official_hubs"]: a+=official(s)
    for q in c["discovery_queries"]: a+=gnews(q["query"],q["brand"],q["market"])
    return dedupe(a)
def filter_evidence(items):
    scored=[]
    for x in items:
        t=(x["title"]+" "+x["summary"]).lower();score=0
        if any(k in t for k in ["launch","new","introducing","unveiled"]):score+=3
        if any(k in t for k in WATCH):score+=3
        if any(k in t for k in ["campaign","commercial","advert","athlete","ambassador","event"]):score+=2
        if x["source_type"] in ["Official","YouTube"]:score+=2
        if score>=3:scored.append((score,x))
    scored.sort(key=lambda z:z[0],reverse=True);return [x for _,x in scored[:60]]
def ai(evidence,changes,socialx,amazon):
    key=os.getenv("DASHSCOPE_API_KEY")
    if not key:return None
    try:
        from openai import OpenAI
        c=OpenAI(api_key=key,base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        prompt=f"""You are a factual competitive intelligence analyst for HUAWEI overseas 3C content operations.
Primary competitors: Apple, Samsung, Garmin. Wearables are the core.
Market/product: Global. Product pages: Global, China, Malaysia, UK.
Amazon/social: wearables first, but include clearly high-interest new/trending tech.
Do not score anything. Do not invent facts, dates, people, engagement or rankings. Source facts must be traceable to URLs.
Return ONLY JSON:
{{
"marketMoves":[{{"brand":"","type":"New Product|Technology Update|Launch Event|Marketing Action","title":"","summary":"","date":"","url":"","whyItMatters":""}}],
"pageInsights":[{{"brand":"","market":"","pageType":"PCP|PDP","product":"","structure":[],"sellingCopy":[],"commerceContent":[],"videoContent":[],"changeSummary":"","url":"","screenshot":""}}],
"pageChanges":[{{"brand":"","market":"","pageType":"","product":"","changeSummary":"","sellingImpact":"","url":"","screenshot":""}}],
"amazonWatch":[{{"scope":"Wearables|Trending Tech|Apple on Amazon","title":"","summary":"","product":"","url":"","whyItMatters":""}}],
"socialWatch":[{{"brand":"","market":"","platform":"YouTube|Instagram|TikTok","title":"","format":"","product":"","date":"","url":"","thumbnail":"","whyItMatters":""}}],
"keyTakeaways":[]
}}
EVIDENCE:{json.dumps(evidence,ensure_ascii=False)}
PAGE CHANGES:{json.dumps(changes,ensure_ascii=False)}
SOCIAL:{json.dumps(socialx[:60],ensure_ascii=False)}
AMAZON:{json.dumps(amazon[:30],ensure_ascii=False)}"""
        r=c.chat.completions.create(model="qwen3.5-plus",messages=[{"role":"user","content":prompt}],temperature=0.1)
        txt=re.sub(r"^```json\s*|\s*```$","",r.choices[0].message.content.strip(),flags=re.S)
        u=getattr(r,"usage",None)
        if u: print("Token usage:",getattr(u,"prompt_tokens",0),getattr(u,"completion_tokens",0),getattr(u,"total_tokens",0))
        return json.loads(txt)
    except Exception as ex: print("[AI ERROR]",ex);return None
def main():
    print("=== 3C Wearables Competitive Intelligence V6 ===")
    c=json.load(open(CONFIG,encoding="utf-8"));old=json.load(open(DATA,encoding="utf-8")) if os.path.exists(DATA) else {}
    raw=collect_market(c);evidence=filter_evidence(raw);print(f"Collected {len(raw)} raw market/product items; reduced to {len(evidence)} AI evidence items.")
    ps,changes=pages(c,old);print(f"Monitored {len(ps)} product pages; page changes: {len(changes)}")
    sx=social();print(f"Collected {len(sx)} social items.")
    am=[] 
    for q in c["amazon_queries"]: am+=gnews(q["query"],"Amazon","Global")
    am=dedupe(am)[:30];print(f"Collected {len(am)} Amazon/trending discovery items.")
    result=ai(evidence,changes,sx,am) or old
    result.update({"updatedAt":iso(),"timezone":"Asia/Kuala_Lumpur","rawMarketItems":raw[:120],"pageSnapshots":ps,"pageChanges":changes,"socialRaw":sx[:80],"amazonRaw":am[:30]})
    json.dump(result,open(DATA,"w",encoding="utf-8"),ensure_ascii=False,indent=2);print("V6 update completed.")
if __name__=="__main__":main()
