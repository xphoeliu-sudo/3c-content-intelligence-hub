import os,json,datetime as dt,re,hashlib,warnings
import requests,feedparser
from bs4 import BeautifulSoup,MarkupResemblesLocatorWarning
warnings.filterwarnings('ignore',category=MarkupResemblesLocatorWarning)
from email.utils import parsedate_to_datetime
BASE=os.path.dirname(__file__); DATA=os.path.join(BASE,'data.json'); CFG=os.path.join(BASE,'competitors.json')
H={'User-Agent':'Mozilla/5.0 (3C Wearables Intelligence Hub/5.2)'}; TIMEOUT=25
WEAR=['watch','smartwatch','wearable','fitness','health','sleep','running','training','recovery','wellness','workout','sport','heart','ecg','blood oxygen','galaxy watch','apple watch','garmin watch','forerunner','fenix','fēnix','venu','vivoactive','lily','instinct','epix','cirqa']
NOISE=['aviation','marine','aviator','autopilot','chartplotter','fishfinder','truck','automotive','accessories','support','manual','repair']
FORMATS={'How-to':['how to','tutorial','guide','tips','set up','setup'],'Unboxing':['unboxing','unbox','what’s in the box','first look'], 'Product Demo':['demo','demonstration','hands-on','in action'],'Campaign / Ad':['campaign','advert','advertising','commercial','brand film','campaign film'],'Product Video':['product video','video:'],'Lifestyle':['lifestyle','everyday','wellness','inspiration'],'Health / Fitness':['health','fitness','training','running','sleep','recovery','workout'],'Creator':['creator','influencer','athlete','ambassador'],'Launch Content':['launch','introducing','unveiled','new watch'],'Event Content':['event','keynote','summit','experience']}
def clean(s): return re.sub(r'\s+',' ',BeautifulSoup(str(s or ''),'html.parser').get_text(' ',strip=True)).strip()
def pdate(e):
 for k in ('published','updated'):
  if e.get(k):
   try:return parsedate_to_datetime(e[k]).isoformat()
   except:pass
 return dt.datetime.now(dt.timezone.utc).isoformat()
def get(u): return requests.get(u,headers=H,timeout=TIMEOUT)
def relevant(s):
 t=s.lower(); return not (any(x in t for x in NOISE) and not any(x in t for x in ['watch','wearable','fitness','health'])) and any(x in t for x in WEAR)
def fmt(s):
 t=s.lower()
 for k,v in FORMATS.items():
  if any(x in t for x in v): return k
 return None
def rss(cfg):
 out=[]; seen=set()
 for s in cfg.get('rss_sources',[])+cfg.get('discovery_queries',[]):
  try:
   f=feedparser.parse(get(s['url']).content)
   for e in f.entries[:30]:
    title=clean(e.get('title','')); summary=clean(e.get('summary','')); link=e.get('link',''); blob=title+' '+summary+' '+link
    if not relevant(blob): continue
    if any(x in blob.lower() for x in NOISE) and not fmt(blob): continue
    k=hashlib.sha1((s['brand']+s['market']+title+link).lower().encode()).hexdigest()
    if k in seen: continue
    seen.add(k); out.append({'brand':s['brand'],'market':s['market'],'source_kind':s.get('kind','Discovery'),'content_type':'Wearable Content','title':title,'summary':summary[:900],'url':link,'published':pdate(e)})
  except Exception as ex: print('[RSS ERROR]',s['brand'],s['market'],ex)
 for s in cfg.get('official_pages',[]):
  try:
   soup=BeautifulSoup(get(s['url']).text,'html.parser')
   for a in soup.find_all('a',href=True):
    title=clean(a.get_text(' ',strip=True)); href=a['href']
    if href.startswith('/'): from urllib.parse import urljoin; href=urljoin(s['url'],href)
    blob=title+' '+href; f=fmt(blob)
    if len(title)<5 or not relevant(blob) or not f or any(x in blob.lower() for x in ['support','manual','repair','accessories','specifications','buy','compare']): continue
    k=hashlib.sha1((s['brand']+s['market']+title+href).lower().encode()).hexdigest()
    if k in seen: continue
    seen.add(k); out.append({'brand':s['brand'],'market':s['market'],'source_kind':'Official','content_type':'Wearable Content','title':title,'summary':'','url':href,'published':dt.datetime.now(dt.timezone.utc).isoformat()})
  except Exception as ex: print('[OFFICIAL ERROR]',s['url'],ex)
 return out[:180]
def snap(p):
 try:
  soup=BeautifulSoup(get(p['url']).text,'html.parser')
  for x in soup(['script','style','noscript','svg']): x.decompose()
  text=clean(soup.get_text(' ',strip=True)); title=clean(soup.title.get_text() if soup.title else '')
  h1=clean(' | '.join(x.get_text(' ',strip=True) for x in soup.find_all('h1')[:5])); hs=clean(' | '.join(x.get_text(' ',strip=True) for x in soup.find_all(['h2','h3'])[:20]))
  return {**p,'title':title,'h1':h1,'headings':hs,'text_hash':hashlib.sha256(text.encode()).hexdigest()}
 except Exception as ex: print('[PAGE ERROR]',p['url'],ex); return None
def pages(cfg):
 old={}
 if os.path.exists(DATA):
  try: old={x['url']:x for x in json.load(open(DATA,encoding='utf8')).get('pageSnapshots',[])}
  except: pass
 cur=[x for p in cfg.get('pages',[]) if (x:=snap(p))]
 ch=[]
 for x in cur:
  if x['url'] in old and x['text_hash']!=old[x['url']].get('text_hash'): ch.append({'brand':x['brand'],'market':x['market'],'pageType':x['page_type'],'product':x.get('product',''),'change':'Page content changed since previous snapshot.','whyItMatters':'Review messaging, structure, CTA and modules.','url':x['url'],'confidence':'MEDIUM'})
 return cur,ch
def ai(items,ch):
 from openai import OpenAI
 key=os.getenv('DASHSCOPE_API_KEY')
 if not key: print('DASHSCOPE_API_KEY is not configured.'); return None
 c=OpenAI(api_key=key,base_url='https://dashscope.aliyuncs.com/compatible-mode/v1')
 prompt=f'''You are the daily wearable competitor intelligence analyst for HUAWEI overseas content operations. Monitor ONLY Apple, Samsung and Garmin, Global/Malaysia/UK.
STRICTLY separate: contentMoves=actual How-to, Unboxing, Product Demo, Campaign / Ad, Product Video, Lifestyle, Health / Fitness, Creator, Launch Content, Event Content. marketingMoves=Launch, Campaign, Event, Ambassador, Partnership, Local Activation, Promotion. pageChanges=ONLY supplied PDP/PCP changes. NEVER put a Product Page into contentMoves. Ignore support/manual/accessories/aviation/marine/automotive. No invented facts, dates, people or metrics. If evidence is weak omit it. Return ONLY JSON.
{{"executive":[{{"brand":"","market":"","headline":"","evidence":"","implication":"","priority":"HIGH|MEDIUM|LOW"}}],"contentMoves":[{{"brand":"","market":"","format":"","product":"","title":"","summary":"","date":"","url":"","confidence":"HIGH|MEDIUM"}}],"marketingMoves":[{{"brand":"","market":"","type":"","title":"","summary":"","date":"","url":"","confidence":"HIGH|MEDIUM"}}],"pageChanges":[{{"brand":"","market":"","pageType":"PDP|PCP","product":"","change":"","whyItMatters":"","url":"","confidence":"HIGH|MEDIUM"}}],"opportunities":[{{"priority":"P1|P2|P3","opportunity":"","why":"","competitorExample":""}}],"contentMix":[{{"brand":"","howTo":0,"unboxing":0,"productDemo":0,"campaignAd":0,"productVideo":0,"lifestyle":0,"healthFitness":0,"creator":0,"launch":0,"event":0}}]}}
CONTENT/DISCOVERY:\n{json.dumps(items,ensure_ascii=False)}\nPAGE CHANGES:\n{json.dumps(ch,ensure_ascii=False)}'''
 r=c.responses.create(model='qwen3.5-plus',input=prompt)
 u=getattr(r,'usage',None)
 if u: print('Token usage:',getattr(u,'input_tokens',0),getattr(u,'output_tokens',0),getattr(u,'total_tokens',0))
 t=re.sub(r'^```json\s*|\s*```$','',r.output_text.strip(),flags=re.S); return json.loads(t)
def main():
 print('=== 3C Wearables Intelligence Hub V5.2 ==='); cfg=json.load(open(CFG,encoding='utf8')); items=rss(cfg); print(f'Collected {len(items)} wearable content/discovery items.'); ps,ch=pages(cfg); print(f'Monitored {len(ps)} PDP/PCP pages; page changes: {len(ch)}'); result=ai(items,ch); now=dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat()
 if not result: result=json.load(open(DATA,encoding='utf8')) if os.path.exists(DATA) else {}
 result.update({'updatedAt':now,'timezone':'Asia/Kuala_Lumpur','feedItems':items,'pageSnapshots':ps,'pageChanges':ch}); json.dump(result,open(DATA,'w',encoding='utf8'),ensure_ascii=False,indent=2); print('AI analysis completed successfully.')
if __name__=='__main__': main()
