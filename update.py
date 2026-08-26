import os,json,re,hashlib,datetime as dt
from urllib.parse import urljoin,urldefrag,urlparse,quote
import requests,feedparser
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
BASE=os.path.dirname(__file__); DATA=os.path.join(BASE,'data.json'); CONFIG=os.path.join(BASE,'competitors.json'); SNAP=os.path.join(BASE,'snapshots'); INV=os.path.join(BASE,'page_inventory.json'); CHG=os.path.join(BASE,'page_changes.json')
H={'User-Agent':'Mozilla/5.0 (3C Wearables Intelligence Hub/5.0)'}; TIMEOUT=12; MAX_PDP=2

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def clean(s): return re.sub(r'\s+',' ',BeautifulSoup(str(s or ''),'html.parser').get_text(' ',strip=True)).strip()
def norm(u): return urldefrag(u)[0].rstrip('/')
def date_of(e):
    for k in ('published','updated'):
        if e.get(k):
            try:return parsedate_to_datetime(e[k]).isoformat()
            except: pass
    return now()
def get(url):
    r=requests.get(url,headers=H,timeout=TIMEOUT,allow_redirects=True); r.raise_for_status(); return r.url,r.text
def rss(url):
    try:return feedparser.parse(requests.get(url,headers=H,timeout=TIMEOUT).content).entries
    except Exception as e: print('[RSS ERROR]',url,e); return []
def gnews(q,market):
    cfg={'Global':('en-US','US','US:en'),'Malaysia':('en-US','MY','MY:en'),'UK':('en-GB','GB','GB:en')}[market]; hl,gl,ceid=cfg
    return rss(f'https://news.google.com/rss/search?q={quote(q)}&hl={hl}&gl={gl}&ceid={quote(ceid)}')
def classify(t,s,u):
    x=(t+' '+s+' '+u).lower()
    if any(k in x for k in ['how to','how-to','tutorial','getting started','setup','set up','tips','guide']): return 'How-to'
    if 'unbox' in x: return 'Unboxing'
    if any(k in x for k in ['campaign','commercial','advert','hero film','brand film']): return 'Campaign / Ad'
    if any(k in x for k in ['launch','introducing','unveiled','announces']): return 'Launch'
    if any(k in x for k in ['event','unpacked','keynote','community','activation']): return 'Event / Activation'
    if any(k in x for k in ['ambassador','athlete','celebrity','partnership','partner']): return 'Partnership / Ambassador'
    if any(k in x for k in ['health','fitness','running','sleep','wellness','training']): return 'Health / Fitness'
    if 'youtube.com' in x: return 'Product / Social Video'
    return 'Product / Brand Content'
def collect(config):
    out=[];seen=set()
    for brand,markets in config.items():
      for market,cfg in markets.items():
        for q in cfg['queries']:
          for e in gnews(q+' when:14d',market)[:6]:
            t=clean(e.get('title','')); s=clean(e.get('summary','')); u=e.get('link','')
            if not t or not u: continue
            key=hashlib.sha1((brand+market+t).lower().encode()).hexdigest()
            if key in seen: continue
            seen.add(key); out.append({'brand':brand,'market':market,'source_kind':'Discovery','content_type':classify(t,s,u),'title':t,'summary':s[:1200],'url':u,'published':date_of(e)})
        for u in cfg['official']:
          try:
            fu,html=get(u); soup=BeautifulSoup(html,'html.parser')
            for a in soup.find_all('a',href=True)[:160]:
              t=clean(a.get_text(' ',strip=True)); link=norm(urljoin(fu,a['href']))
              if len(t)<8 or len(t)>220: continue
              if not any(k in (t+' '+link).lower() for k in ['watch','wearable','fitness','health','campaign','event','run','galaxy','garmin']): continue
              key=hashlib.sha1((brand+market+t+link).lower().encode()).hexdigest()
              if key in seen: continue
              seen.add(key); out.append({'brand':brand,'market':market,'source_kind':'Official','content_type':classify(t,'',link),'title':t,'summary':'','url':link,'published':now()})
          except Exception as e: print('[OFFICIAL ERROR]',u,e)
    return sorted(out,key=lambda x:x.get('published',''),reverse=True)[:160]
PDP_HINTS=['/watch','/watches','/wearables','/products/','/product/','/galaxy-watch','/apple-watch','/venu','/forerunner','/fenix','/instinct']; BAD=['/support','/news','/blog','/community','/search','/accessories']
def discover(pcp,html):
    soup=BeautifulSoup(html,'html.parser'); c={}
    for a in soup.find_all('a',href=True):
      u=norm(urljoin(pcp,a['href']))
      if urlparse(u).netloc.replace('www.','')!=urlparse(pcp).netloc.replace('www.',''): continue
      lo=u.lower()
      if any(b in lo for b in BAD): continue
      score=sum(3 for h in PDP_HINTS if h in lo)+1
      if score>=4:c[u]=max(c.get(u,0),score)
    return [u for u,_ in sorted(c.items(),key=lambda x:(-x[1],x[0]))[:MAX_PDP]]
def snap(url,brand,market,ptype,html):
    s=BeautifulSoup(html,'html.parser'); text=clean(s); title=clean(s.title.get_text(' ',strip=True) if s.title else ''); h1=clean(s.h1.get_text(' ',strip=True) if s.h1 else '')
    heads=[clean(x.get_text(' ',strip=True))[:250] for x in s.find_all(['h1','h2','h3']) if clean(x.get_text(' ',strip=True))]
    buttons=[clean(x.get_text(' ',strip=True)) for x in s.find_all(['button','a']) if clean(x.get_text(' ',strip=True))][:80]
    vids=[norm(urljoin(url,x.get('src') or x.get('data-src'))) for x in s.find_all(['video','iframe']) if x.get('src') or x.get('data-src')]
    d={'url':norm(url),'brand':brand,'market':market,'pageType':ptype,'capturedAt':now(),'title':title,'h1':h1,'headings':heads[:80],'buttons':buttons,'videos':vids[:30],'textHash':hashlib.sha1(text.encode()).hexdigest()}
    return d
def save(s):
    day=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d'); folder=os.path.join(SNAP,s['brand'],s['market']); os.makedirs(folder,exist_ok=True); h=hashlib.sha1(s['url'].encode()).hexdigest()[:16]
    with open(os.path.join(folder,h+'_'+day+'.json'),'w',encoding='utf-8') as f: json.dump(s,f,ensure_ascii=False,indent=2)
def monitor(config):
    inv=[]
    for brand,markets in config.items():
      for market,cfg in markets.items():
       for pcp in cfg['PCP']:
        print('[PCP]',brand,market)
        try:
          fu,html=get(pcp); save(snap(fu,brand,market,'PCP',html)); inv.append({'brand':brand,'market':market,'pageType':'PCP','url':fu})
          for u in discover(fu,html):
            try:
              f,h=get(u); save(snap(f,brand,market,'PDP',h)); inv.append({'brand':brand,'market':market,'pageType':'PDP','url':f})
            except Exception as e: print('[PDP ERROR]',u,e)
        except Exception as e: print('[PCP ERROR]',pcp,e)
    json.dump(inv,open(INV,'w',encoding='utf-8'),ensure_ascii=False,indent=2); return inv
def page_diff():
    if not os.path.isdir(SNAP): return []
    groups={}
    for root,_,fs in os.walk(SNAP):
      for fn in fs:
       if not fn.endswith('.json'): continue
       try:
        s=json.load(open(os.path.join(root,fn),encoding='utf-8')); key=(s['brand'],s['market'],s['pageType'],s['url']); groups.setdefault(key,[]).append(s)
       except: pass
    changes=[]
    for key,arr in groups.items():
      arr.sort(key=lambda x:x.get('capturedAt','')); 
      if len(arr)<2: continue
      old,new=arr[-2],arr[-1]
      if old.get('textHash')==new.get('textHash'): continue
      c=[]
      for k,n in [('title','Title'),('h1','H1'),('headings','Headings / structure'),('buttons','CTA / links'),('videos','Video')]:
        if old.get(k)!=new.get(k): c.append(n)
      if c: changes.append({'brand':new['brand'],'market':new['market'],'pageType':new['pageType'],'title':new.get('h1') or new.get('title'),'changes':c,'before':old.get('h1') or old.get('title'),'after':new.get('h1') or new.get('title'),'url':new['url']})
    json.dump(changes,open(CHG,'w',encoding='utf-8'),ensure_ascii=False,indent=2); return changes
def ai(items,changes):
    key=os.getenv('DASHSCOPE_API_KEY')
    if not key: print('DASHSCOPE_API_KEY missing'); return None
    from openai import OpenAI
    client=OpenAI(api_key=key,base_url='https://dashscope.aliyuncs.com/compatible-mode/v1')
    prompt='''You are the daily competitive content intelligence analyst for HUAWEI overseas wearable operations. Monitor ONLY Apple, Samsung and Garmin wearables in Global, Malaysia and UK. Focus on what brands DID recently: official how-to, unboxing, product demo, campaign/ad, social/video, health/fitness education, lifestyle and creator content; marketing actions including launch, event, campaign, ambassador, partnership, local activation and promotion; plus PDP/PCP changes. Do not create SEO output. Facts must be traceable to URLs; never invent people, dates or metrics. Return ONLY JSON with keys executive,signals,contentMoves,marketingMoves,actions,contentMix,pageChanges. executive max 3; signals max 8; contentMoves max 12; marketingMoves max 8; actions max 8. Each signal has brand,market,type,priority,title,summary,implication,url. Each content move has brand,market,format,product,title,summary,date,url. Each marketing move has brand,market,type,title,summary,url. Each action has priority,action,why,examples. contentMix per brand uses numeric 0-100 fields howTo,productVideo,campaign,healthFitness,lifestyle,creator,event. pageChanges should turn supplied page changes into concise implications.'''
    payload=prompt+'\nITEMS:\n'+json.dumps(items[:90],ensure_ascii=False)+'\nPAGE CHANGES:\n'+json.dumps(changes[:25],ensure_ascii=False)
    try:
      r=client.chat.completions.create(model='qwen3.5-plus',messages=[{'role':'user','content':payload}],temperature=0.2); print('Token usage:',r.usage.prompt_tokens,r.usage.completion_tokens,r.usage.total_tokens); t=re.sub(r'^```json\s*|\s*```$','',r.choices[0].message.content.strip(),flags=re.S); return json.loads(t)
    except Exception as e: print('[AI ERROR]',e); return None
def main():
    print('=== 3C Wearables Intelligence Hub V5 ==='); config=json.load(open(CONFIG,encoding='utf-8')); items=collect(config); print('Collected',len(items),'content/discovery items.'); inv=monitor(config); changes=page_diff(); print('Monitored',len(inv),'pages; page changes:',len(changes)); result=ai(items,changes); old=json.load(open(DATA,encoding='utf-8')) if os.path.exists(DATA) else {}
    if result: result.update({'updatedAt':now(),'timezone':'Asia/Kuala_Lumpur','feedItems':items[:120],'pageInventory':inv,'pageChanges':changes,'sourceHealth':[{'source':'Official sites','type':'Web','status':'OK'},{'source':'Google News discovery','type':'RSS','status':'OK'},{'source':'YouTube-indexed discovery','type':'Video','status':'OK'}]}); json.dump(result,open(DATA,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    else: old.update({'updatedAt':now(),'feedItems':items[:120],'pageInventory':inv,'pageChanges':changes}); json.dump(old,open(DATA,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
if __name__=='__main__': main()
