"""Does dense retrieval lift the PARAPHRASE-PROOF floor?
Condition: no template/spec-phrase matching allowed. Only category + semantics + popularity.
"""
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

def embed(texts):
    out=[]
    for i in range(0,len(texts),48):
        body=json.dumps({"model":"bge-m3","input":texts[i:i+48]}).encode()
        rq=urllib.request.Request(API+"/embeddings",body,{"Authorization":"Bearer "+key,"Content-Type":"application/json"})
        d=json.load(urllib.request.urlopen(rq,timeout=180))
        out+=[e['embedding'] for e in d['data']]
    V=np.array(out,dtype=np.float32); return V/(np.linalg.norm(V,axis=1,keepdims=True)+1e-9)

# realistic post-elicitation query: category + all 4 constraints as natural language
queries=[]; targets=[]; pools=[]
for r in rows:
    t=r['ground_truth']['parent_asin']; c=intent_card(prods[t])
    q=f"{ccat[t]}. Requirements: " + "; ".join(c['hard_constraints']+c['soft_preferences'])
    queries.append(q[:1500]); targets.append(t); pools.append([a for a in bycat[ccat[t]] if a in pos])
Q=embed(queries)

def rrf(*ranklists,k=60):
    s=collections.defaultdict(float)
    for rl in ranklists:
        for i,a in enumerate(rl): s[a]+=1.0/(k+i+1)
    return [a for a,_ in sorted(s.items(),key=lambda x:-x[1])]

def report(name, orders):
    hit=sum(1 for o,t in zip(orders,targets) if t in o[:10])
    mrr=np.mean([1/(o.index(t)+1) if t in o[:10] else 0 for o,t in zip(orders,targets)])
    r1=sum(1 for o,t in zip(orders,targets) if o[:1]==[t])
    print(f"{name:34s} hit@10 {hit/len(targets):.3f}  MRR {mrr:.4f}  rank1 {r1}/{len(targets)}")

pop=[sorted(p,key=lambda a:-(prods[a].get('rating_number') or 0)) for p in pools]
dense=[]
for qi,p in enumerate(pools):
    idx=np.array([pos[a] for a in p]); sc=M[idx]@Q[qi]
    dense.append([p[i] for i in np.argsort(-sc)])
report("popularity only", pop)
report("bge-m3 dense only", dense)
report("RRF(dense, popularity)", [rrf(d,pp) for d,pp in zip(dense,pop)])
# log-popularity as a soft prior on dense score
mix=[]
for qi,p in enumerate(pools):
    idx=np.array([pos[a] for a in p]); sc=M[idx]@Q[qi]
    lp=np.log1p(np.array([prods[a].get('rating_number') or 0 for a in p]))
    z=sc+0.03*lp
    mix.append([p[i] for i in np.argsort(-z)])
report("dense + 0.03*log(popularity)", mix)
