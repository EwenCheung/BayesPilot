from __future__ import annotations
import json, re, collections
from pathlib import Path

MATERIALS = ("cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk", "rayon", "fabric")
SEARCH_FIELDS = ("title", "features", "details", "description", "categories", "store")
MATERIAL_RE = re.compile(r"\b(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric)\b", re.I)
COLOR_RE = re.compile(r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange)\b", re.I)


def searchable_text(product: dict) -> str:
    parts: list[str] = []
    for field in SEARCH_FIELDS:
        value = product.get(field)
        if isinstance(value, dict):
            parts.extend(f"{key} {item}" for key, item in value.items())
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).strip()


def _flatten_values(value: object) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if item not in (None, "", [])]
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value not in (None, "") else []


def _clean_constraint(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip(" -;,.\t\n")[:limit].rstrip()


def intent_card(product: dict, limit: int = 180) -> dict:
    title = _clean_constraint(str(product.get("title") or "product"), limit)
    candidates = [*_flatten_values(product.get("features")), *_flatten_values(product.get("details"))]
    corpus = searchable_text(product)
    material = MATERIAL_RE.search(corpus)
    color = COLOR_RE.search(corpus)
    if material:
        candidates.insert(0, material.group(1).lower())
    if color:
        candidates.insert(1, f"color: {color.group(1).lower()}")
    if product.get("price") not in (None, ""):
        candidates.append(f"budget around ${product['price']}")
    cleaned = list(dict.fromkeys(_clean_constraint(item, limit) for item in candidates if _clean_constraint(item, limit)))
    if not cleaned:
        cleaned = [title]
    return {
        "target_category": title,
        "hard_constraints": cleaned[:2],
        "soft_preferences": cleaned[2:4] or cleaned[:1],
    }


def coarse_category(values: list[str]) -> str:
    excluded = {"clothing", "clothing shoes & jewelry", "clothing, shoes & jewelry"}
    cleaned: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part and part.lower() not in excluded:
                cleaned.append(part)
    return " ".join(cleaned[-2:]) if cleaned else "clothing item"




CAT_RE = re.compile(r"I'm looking for (.+?)(?:,? but I'm still exploring\.|\. A key requirement is: (.*?)\.?$|\. (.*)$)")
REPLY_RE = re.compile(r"^For that, what matters is: (.*)\.$")
OVR_RE = re.compile(r"^Actually, ignore my earlier preference\. What I need is: (.*)\.$")

class Agent:
    def __init__(self, catalog_path="data/catalog.jsonl"):
        self.by_cat = collections.defaultdict(list); self.strs = {}; self.meta = {}
        for line in Path(catalog_path).open(encoding="utf-8"):
            p = json.loads(line); a = p["parent_asin"]; c = intent_card(p)
            self.strs[a] = frozenset(c["hard_constraints"]) | frozenset(c["soft_preferences"])
            self.by_cat[coarse_category([str(v) for v in p.get("categories") or []])].append(a)
            self.meta[a] = p.get("rating_number") or 0
        self.s = {}

    def reset(self, session_id, user_profile):
        self.s[session_id] = {"cat": None, "seen": set()}

    def _absorb(self, st, msg):
        m = CAT_RE.search(msg)
        if m and st["cat"] is None:
            st["cat"] = m.group(1).strip()
            for g in (m.group(2), m.group(3)):
                if g: st["seen"].add(g.strip().rstrip("."))
            return
        for rx in (REPLY_RE, OVR_RE):
            m = rx.match(msg.strip())
            if m:
                blob = m.group(1); st["seen"].add(blob)
                for part in blob.split("; "): st["seen"].add(part.strip())
                return

    def respond(self, session_id, user_message, turn, top_k):
        st = self.s[session_id]; self._absorb(st, user_message)
        seen = {v for v in st["seen"] if v}
        scored = sorted((-len(seen & self.strs[a]), -self.meta[a], a) for a in self.by_cat.get(st["cat"], []))
        confident = len(scored) == 1 or (len(scored) > 1 and scored[0][0] < scored[1][0])
        recs = [{"parent_asin": a} for _, _, a in scored[:top_k]] if (confident or turn >= 3) else []
        return {"message": "What else matters to you?", "ask_attribute": "other",
                "recommendations": recs,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
