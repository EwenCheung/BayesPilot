import json,os,sys,numpy as np,collections,urllib.request
sys.path.insert(0,'/Users/ewencheung/Documents/GitHub/techjam-track4/techjam-conversational-search-main')
from evaluator.local_evaluator import intent_card, coarse_category
SC=os.path.dirname(os.path.abspath(__file__)); R='/Users/ewencheung/Documents/GitHub/techjam-track4/'
key=os.environ['SOCLAAS_API_KEY']; API=os.environ['SOCLAAS_BASE_URL']
M=np.load(SC+'/emb.npy'); ids=json.load(open(SC+'/emb_ids.json')); pos={a:i for i,a in enumerate(ids)}
prods={}
for l in open(R+'assets/catalog.jsonl'):
    p=json.loads(l); prods[p['parent_asin']]=p
ccat={a:coarse_category([str(v) for v in p.get('categories') or []]) for a,p in prods.items()}
bycat=collections.defaultdict(list)
for a,c in ccat.items(): bycat[c].append(a)
rows=[json.loads(l) for l in open(R+'techjam-conversational-search-main/data/public_set.jsonl')]
def embed(t):
    o=[]
    for i in range(0,len(t),48):
        b=json.dumps({"model":"bge-m3","input":t[i:i+48]}).encode()
        rq=urllib.request.Request(API+"/embeddings",b,{"Authorization":"Bearer "+key,"Content-Type":"application/json"})
        o+=[e['embedding'] for e in json.load(urllib.request.urlopen(rq,timeout=180))['data']]
    V=np.array(o,dtype=np.float32); return V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-9)
Qs={}; targets=[]; pools=[]; scen=[]
full=[]; partial=[]
for r in rows:
    t=r['ground_truth']['parent_asin']; c=intent_card(prods[t])
    full.append(f"{ccat[t]}. Requirements: "+"; ".join(c['hard_constraints']+c['soft_preferences'])[:1500])
    partial.append(f"{ccat[t]}"[:1500])          # turn-1 browsing: category only
    targets.append(t); pools.append([a for a in bycat[ccat[t]] if a in pos]); scen.append(r['scenario_type'])
Qs['full-card']=embed(full); Qs['category-only']=embed(partial)
def ev(orders,name):
    h=sum(1 for o,t in zip(orders,targets) if t in o[:10]); m=np.mean([1/(o.index(t)+1) if t in o[:10] else 0 for o,t in zip(orders,targets)])
    r1=sum(1 for o,t in zip(orders,targets) if o and o[0]==t)
    print(f"  {name:32s} hit@10 {h/200:.3f}  MRR {m:.4f}  rank1 {r1:3d}"); return h/200,m
for qn,Q in Qs.items():
    print(f"--- query = {qn} ---")
    for w in [0.0,0.01,0.02,0.03,0.05,0.08,0.15,0.3,999]:
        orders=[]
        for qi,p in enumerate(pools):
            idx=np.array([pos[a] for a in p]); sc=M[idx]@Q[qi]
            lp=np.log1p(np.array([prods[a].get('rating_number') or 0 for a in p],dtype=np.float32))
            z=lp if w==999 else sc+w*lp
            orders.append([p[i] for i in np.argsort(-z)])
        ev(orders, "popularity ONLY" if w==999 else f"dense + {w}*log(pop)")
