import json,os,sys,time,urllib.request,numpy as np
from concurrent.futures import ThreadPoolExecutor
key=os.environ['SOCLAAS_API_KEY']; API=os.environ['SOCLAAS_BASE_URL']
SC=os.path.dirname(os.path.abspath(__file__))
R='/Users/ewencheung/Documents/GitHub/techjam-track4/'
want=set(json.load(open(SC+'/pool_asins.json')))
prods={}
for l in open(R+'assets/catalog.jsonl'):
    p=json.loads(l)
    if p['parent_asin'] in want: prods[p['parent_asin']]=p
def blob(p):
    parts=[str(p.get('title') or '')]
    parts+=[str(x) for x in (p.get('features') or [])][:8]
    parts+=[f"{k}: {v}" for k,v in list((p.get('details') or {}).items())[:10]]
    parts.append(" > ".join(str(x) for x in (p.get('categories') or [])))
    return " | ".join(x for x in parts if x)[:2000]
ids=sorted(prods); texts=[blob(prods[a]) for a in ids]
print(len(ids),'to embed',flush=True)
def go(i):
    ch=texts[i:i+48]
    for attempt in range(4):
        try:
            body=json.dumps({"model":"bge-m3","input":ch}).encode()
            rq=urllib.request.Request(API+"/embeddings",body,{"Authorization":"Bearer "+key,"Content-Type":"application/json"})
            d=json.load(urllib.request.urlopen(rq,timeout=180))
            return i,[e['embedding'] for e in d['data']]
        except Exception as e:
            if attempt==3: print('FAIL',i,e,flush=True); return i,[[0.0]*1024]*len(ch)
            time.sleep(2*(attempt+1))
idx=list(range(0,len(texts),48)); out={}
t0=time.time()
with ThreadPoolExecutor(12) as ex:
    for n,(i,v) in enumerate(ex.map(go,idx)):
        out[i]=v
        if n%50==0: print(f'{n}/{len(idx)} {time.time()-t0:.0f}s',flush=True)
M=np.zeros((len(ids),1024),dtype=np.float32)
for i,v in out.items(): M[i:i+len(v)]=np.array(v,dtype=np.float32)
M/= (np.linalg.norm(M,axis=1,keepdims=True)+1e-9)
np.save(SC+'/emb.npy',M); json.dump(ids,open(SC+'/emb_ids.json','w'))
print('done %.0fs'%(time.time()-t0), M.shape)
