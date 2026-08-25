import os,json,datetime as dt,re,hashlib
import requests,feedparser
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime

BASE=os.path.dirname(__file__); DATA=os.path.join(BASE,"data.json")
H={"User-Agent":"Mozilla/5.0 (3C Content Intelligence Hub/2.0)"}

FEEDS=[
("Apple","Global","Official","https://www.apple.com/newsroom/rss-feed.rss"),
("Samsung","Global","Discovery","https://news.google.com/rss/search?q=site%3Anews.samsung.com%2Fglobal%20Samsung%20AI%20OR%20Galaxy%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen"),
("Samsung","Malaysia","Official","https://news.google.com/rss/search?q=site%3Anews.samsung.com%2Fmy%20Samsung%20Galaxy%20when%3A1d&hl=en-US&gl=MY&ceid=MY%3Aen"),
("Garmin","Global","Discovery","https://news.google.com/rss/search?q=site%3Agarmin.com%2Fen-CA%2Fblog%20Garmin%20when%3A7d&hl=en-US&gl=US&ceid=US%3Aen"),
("Garmin","Malaysia","Discovery","https://news.google.com/rss/search?q=site%3Agarmin.com.my%2Fnews%20Garmin%20when%3A7d&hl=en-US&gl=MY&ceid=MY%3Aen"),
("Google","Global","Discovery","https://news.google.com/rss/search?q=Google%20Pixel%20AI%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen"),
("Xiaomi","Global","Discovery","https://news.google.com/rss/search?q=Xiaomi%20smartphone%20wearable%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen"),
("Sony","Global","Discovery","https://news.google.com/rss/search?q=Sony%20headphones%20camera%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen"),
("Bose","Global","Discovery","https://news.google.com/rss/search?q=Bose%20audio%20headphones%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen"),
("YouTube","Global","Discovery","https://news.google.com/rss/search?q=Apple%20Samsung%20Garmin%20YouTube%20campaign%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen"),
("Reddit","Global","Discovery","https://news.google.com/rss/search?q=site%3Areddit.com%20Apple%20Samsung%20Garmin%20watch%20audio%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen")
]

def pdate(e):
    for k in ("published","updated"):
        if e.get(k):
            try:return parsedate_to_datetime(e[k]).isoformat()
            except:pass
    return dt.datetime.now(dt.timezone.utc).isoformat()

def fetch():
    out=[];seen=set()
    for brand,market,kind,url in FEEDS:
        try:
            r=requests.get(url,headers=H,timeout=20)
            feed=feedparser.parse(r.content)
            for e in feed.entries[:15]:
                title=BeautifulSoup(e.get("title",""),"html.parser").get_text(" ",strip=True)
                summary=BeautifulSoup(e.get("summary",""),"html.parser").get_text(" ",strip=True)
                link=e.get("link","")
                key=hashlib.sha1((brand+market+title).lower().encode()).hexdigest()
                if key not in seen:
                    seen.add(key);out.append({"brand":brand,"market":market,"source_kind":kind,"title":title,"summary":summary[:900],"url":link,"published":pdate(e)})
        except Exception as ex: print("feed error",brand,market,ex)
    return out

def ai(items):
    from openai import OpenAI
    key=os.getenv("OPENAI_API_KEY")
    if not key:return None
    client=OpenAI(api_key=key)
    prompt=f"""You are the daily 3C content intelligence analyst for HUAWEI overseas content operations.
Use the collected items below. Prioritise Apple, Samsung and Garmin. Produce ONLY JSON:
{{
"signals":[{{"brand":"","market":"","type":"","priority":"HIGH|MEDIUM|LOW","title":"","summary":"","implication":"","url":""}}],
"seo":[{{"keywordPattern":"","brand":"","market":"","signal":"","opportunity":""}}],
"actions":[{{"priority":"P1|P2|P3","action":"","why":"","examples":""}}],
"contentMix":[{{"brand":"","education":0,"campaign":0,"product":0,"seo":0}}]
}}
Rules: source facts must be traceable to URLs; strategic implications are analysis and must not be presented as facts; do not invent metrics; concise British English; focus on launches, campaigns, PDP/product messaging, SEO/how-to, video/social formats, AI, health, fitness, audio, community and local-market storytelling. Keep up to 10 signals, 10 SEO items and 8 actions.
ITEMS:
{json.dumps(items[:100],ensure_ascii=False)}"""
    res=client.responses.create(model="gpt-5.6",input=prompt)
    txt=re.sub(r"^```json\\s*|\\s*```$","",res.output_text.strip(),flags=re.S)
    return json.loads(txt)

def main():
    items=fetch()
    result=ai(items)
    if result:
        result["updatedAt"]=dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat()
        result["timezone"]="Asia/Kuala_Lumpur";result["feedItems"]=items[:100]
        old=json.load(open(DATA,encoding="utf-8")) if os.path.exists(DATA) else {}
        result["sourceHealth"]=old.get("sourceHealth",[])
        json.dump(result,open(DATA,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    else:
        old=json.load(open(DATA,encoding="utf-8"));old["updatedAt"]=dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat();old["feedItems"]=items[:100]
        json.dump(old,open(DATA,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
if __name__=="__main__":main()
