import os, json, re, hashlib
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

BASE=os.path.dirname(__file__)
CONFIG=os.path.join(BASE,'competitors.json')
SNAP=os.path.join(BASE,'snapshots')
OUT=os.path.join(BASE,'page_inventory.json')

HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147 Safari/537.36'}
REQUEST_TIMEOUT=12
MAX_PDP_PER_PCP=2
MAX_WORKERS=4
MIN_TEXT_LENGTH=250

PDP_HINTS=['/shop/','/buy/','/products/','/product/','/p/','/watch-','/watch/','/galaxy-watch','/galaxy-watches','/forerunner','/fenix','/venu','/vivoactive','/epix','/marq','/instinct','/descent','/lily','/approach','/wearables/']
BAD_HINTS=['/support','/newsroom','/blog','/community','/accessories','/compare','/comparison','/service','/repair','/search','/help','/stores','/where-to-buy']


def norm(url):
    url,_=urldefrag(url)
    return url.rstrip('/')

def same_domain(a,b):
    return urlparse(a).netloc.lower().replace('www.','') == urlparse(b).netloc.lower().replace('www.','')

def fetch(url):
    print(f'[REQUEST] {url}', flush=True)
    r=requests.get(url,headers=HEADERS,timeout=REQUEST_TIMEOUT,allow_redirects=True)
    r.raise_for_status()
    print(f'[OK] {r.status_code} {r.url} ({len(r.text)} chars)', flush=True)
    return r.url,r.text

def clean(soup):
    soup=BeautifulSoup(str(soup),'html.parser')
    for tag in soup(['script','style','noscript','svg','template']): tag.decompose()
    return re.sub(r'\s+',' ',' '.join(soup.stripped_strings)).strip()

def score(url,text):
    u=url.lower(); sc=0
    if any(x in u for x in PDP_HINTS): sc+=3
    if any(x in u for x in BAD_HINTS): sc-=6
    if text and len(text.strip())>5: sc+=1
    if re.search(r'/[a-z0-9-]{5,}$',u): sc+=1
    return sc

def discover(pcp,html):
    soup=BeautifulSoup(html,'html.parser'); cand={}
    for a in soup.find_all('a',href=True):
        u=norm(urljoin(pcp,a['href']))
        if not u.startswith(('http://','https://')) or not same_domain(pcp,u): continue
        t=' '.join(a.stripped_strings)
        sc=score(u,t)
        if sc>=3: cand[u]=max(sc,cand.get(u,0))
    return [u for u,_ in sorted(cand.items(),key=lambda z:(-z[1],z[0]))[:MAX_PDP_PER_PCP]]

def snapshot(url,html,brand,market,category,page_type):
    soup=BeautifulSoup(html,'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    h1=' '.join(soup.h1.stripped_strings) if soup.h1 else ''
    headings=[]
    for h in soup.find_all(['h1','h2','h3']):
        t=' '.join(h.stripped_strings)
        if t and t not in headings: headings.append(t[:300])
    buttons=[]
    keys=['buy','shop','learn','compare','add','order','discover','explore','purchase','view','more','购买','选购','了解','比较']
    for el in soup.find_all(['button','a']):
        t=' '.join(el.stripped_strings)
        if not t or len(t)>120: continue
        if any(k in t.lower() for k in keys) and t not in buttons: buttons.append(t)
    videos=[]
    for el in soup.find_all(['video','iframe']):
        src=el.get('src') or el.get('data-src') or ''
        if src: videos.append(norm(urljoin(url,src)))
    text=clean(soup)
    modules=[]
    rules={
      'comparison':['compare','comparison','比较'], 'faq':['faq','frequently asked','常见问题'],
      'health_fitness':['health','fitness','健康','运动'], 'battery':['battery','电池','续航'],
      'camera':['camera','相机','摄影'], 'ai':['ai','artificial intelligence','智能','人工智能'],
      'design_display':['design','display','屏幕','设计'], 'accessories':['accessor','配件'],
      'ecosystem':['connect','ecosystem','生态'], 'video':['video','视频']}
    lower=' '.join(headings).lower()
    for name,words in rules.items():
        if any(w in lower for w in words): modules.append(name)
    if videos: modules.append('video')
    return {'url':norm(url),'brand':brand,'market':market,'category':category,'pageType':page_type,'capturedAt':datetime.now(timezone.utc).isoformat(),'title':title[:500],'h1':h1[:500],'headings':headings[:100],'buttons':buttons[:50],'videos':videos[:50],'modules':list(dict.fromkeys(modules)),'text':text[:30000],'textHash':hashlib.sha1(text.encode()).hexdigest()}

def save(s):
    day=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    h=hashlib.sha1(s['url'].encode()).hexdigest()[:16]
    folder=os.path.join(SNAP,s['brand'],s['market'],s['category'])
    os.makedirs(folder,exist_ok=True)
    with open(os.path.join(folder,f'{h}_{day}.json'),'w',encoding='utf-8') as f: json.dump(s,f,ensure_ascii=False,indent=2)

def process_pcp(job):
    brand,market,category,pcp=job
    inv=[]
    try:
        final,html=fetch(pcp)
        ps=snapshot(final,html,brand,market,category,'PCP'); save(ps)
        inv.append({'brand':brand,'market':market,'category':category,'pageType':'PCP','url':final,'title':ps['title']})
        urls=discover(final,html)
        print(f'[DISCOVERED] {len(urls)} PDP candidates for {brand} | {market} | {category}',flush=True)
        def one(u):
            try:
                fu,fh=fetch(u); tx=clean(BeautifulSoup(fh,'html.parser'))
                if len(tx)<MIN_TEXT_LENGTH: return None
                ss=snapshot(fu,fh,brand,market,category,'PDP'); save(ss)
                return {'brand':brand,'market':market,'category':category,'pageType':'PDP','url':fu,'title':ss['title']}
            except Exception as e:
                print(f'[PDP ERROR] {u} :: {e}',flush=True); return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            for fut in as_completed([pool.submit(one,u) for u in urls]):
                r=fut.result()
                if r: inv.append(r)
    except Exception as e:
        print(f'[PCP ERROR] {brand} | {market} | {category} | {pcp} :: {e}',flush=True)
    return inv

def main():
    print('=== 3C Wearables PDP / PCP Monitor V4 ===',flush=True)
    with open(CONFIG,encoding='utf-8') as f: config=json.load(f)
    jobs=[]
    for brand,markets in config.items():
        if brand not in ['Apple','Samsung','Garmin']: continue
        for market,categories in markets.items():
            for category,urls in categories.items():
                for url in urls: jobs.append((brand,market,category,url))
    print(f'PCP targets: {len(jobs)} | Markets: Global, Malaysia, UK | Category: Wearables | Max PDP per PCP: {MAX_PDP_PER_PCP}',flush=True)
    inventory=[]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures=[pool.submit(process_pcp,j) for j in jobs]
        for i,f in enumerate(as_completed(futures),1):
            inventory.extend(f.result())
            print(f'[PROGRESS] {i}/{len(futures)} PCP targets complete; inventory={len(inventory)}',flush=True)
    with open(OUT,'w',encoding='utf-8') as f: json.dump(inventory,f,ensure_ascii=False,indent=2)
    print(f'Page monitoring completed. Inventory: {len(inventory)} pages.',flush=True)

if __name__=='__main__': main()
