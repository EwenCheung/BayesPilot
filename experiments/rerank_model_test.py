import json,os,sys,time,random,urllib.request,collections,re
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,'/Users/ewencheung/Documents/GitHub/techjam-track4/techjam-conversational-search-main')
from evaluator.local_evaluator import intent_card, coarse_category
key=os.environ['SOCLAAS_API_KEY']; API=os.environ['SOCLAAS_BASE_URL']
R='/Users/ewencheung/Documents/GitHub/techjam-track4/'
prods={}
for l in open(R+'assets/catalog.jsonl'):
    p=json.loads(l); prods[p['parent_asin']]=p
ccat={a:coarse_category([str(v) for v in p.get('categories') or []]) for a,p in prods.items()}
bycat=collections.defaultdict(list)
for a,c in ccat.items(): bycat[c].append(a)
rows=[json.loads(l) for l in open(R+'techjam-conversational-search-main/data/public_set.jsonl')]
cases=[]
for r in rows:
    t=r['ground_truth']['parent_asin']
    pool=sorted(bycat[ccat[t]], key=lambda a:-(prods[a].get('rating_number') or 0))[:10]
    if t not in pool: continue
    c=intent_card(prods[t])
    cases.append((t,pool,ccat[t],"; ".join(c['hard_constraints']+c['soft_preferences'])[:400]))
random.Random(0).shuffle(cases); cases=cases[:60]
basemrr=sum(1/(p.index(t)+1) for t,p,_,_ in cases)/len(cases)
print(f"{len(cases)} sessions (popularity already hit top-10). Baseline MRR={basemrr:.4f}, rank1={sum(1 for t,p,_,_ in cases if p[0]==t)}")
def desc(a):
    p=prods[a]
    return (str(p.get('title') or '')+" || "+" ".join(str(x) for x in (p.get('features') or [])[:4])
            +" || "+" ".join(f"{k}:{v}" for k,v in list((p.get('details') or {}).items())[:5]))[:420]
def one(args):
    model,(tgt,pool,cat,need)=args
    items="\n".join(f"[{i+1}] {desc(a)}" for i,a in enumerate(pool))
    pr=(f"A shopper wants: {cat}. Their stated requirements: {need}\n\nRank these {len(pool)} products best to worst.\n{items}\n\nReply ONLY the ranking like [3] > [1] > [7]. No explanation.")
    body=json.dumps({"model":model,"messages":[{"role":"user","content":pr}],"max_tokens":300,"temperature":0}).encode()
    rq=urllib.request.Request(API+"/chat/completions",body,{"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    try:
        d=json.load(urllib.request.urlopen(rq,timeout=90))
        order=[int(x) for x in re.findall(r'\[(\d+)\]',d['choices'][0]['message']['content'])]
        seen=set(); out=[]
        for i in order:
            if 1<=i<=len(pool) and i not in seen: seen.add(i); out.append(pool[i-1])
        out+=[a for a in pool if a not in out]
        u=d.get('usage',{}); return out.index(tgt)+1,(u.get('prompt_tokens',0)+u.get('completion_tokens',0))
    except Exception:
        return pool.index(tgt)+1,0
for model in ["llama3.1:8b","ornith1.5:35b","qwen3.6:35b"]:
    t0=time.time()
    with ThreadPoolExecutor(8) as ex: res=list(ex.map(one,[(model,c) for c in cases]))
    mrr=sum(1/r for r,_ in res)/len(res); r1=sum(1 for r,_ in res if r==1)
    print(f"{model:15s} MRR {mrr:.4f} ({mrr-basemrr:+.4f})  rank1 {r1}/{len(cases)}  {(time.time()-t0)/len(cases):.2f}s/call(8-par) {sum(t for _,t in res)//len(res)} tok")
