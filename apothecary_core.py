"""SlothBotanist core logic: pure functions with no network or model dependencies.

Everything here is unit-testable offline. main.py wires it to SerpApi and Qwen.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

# ---------------------------------------------------------------------------
# Engine plan: each engine has a different JOB and gets its own tailored query.
# ---------------------------------------------------------------------------

ENGINE_ROLES: Dict[str, str] = {
    "google": "General herbal preparation methods",
    "google_scholar": "Research evidence and safety",
    "google_books": "Heritage: traditional herbals and historical texts",
    "google_patents": "Heritage: historical extraction methods",
    "google_news": "Safety alerts and interaction warnings",
    "youtube": "Preparation technique videos",
    "google_trends_trending_now": "Modern: what functional drinks are trending",
    "google_trends": "Modern: seasonality of interest in your herbs (not sent as sources)",
    "duckduckgo": "Independent second opinion on methods",
    "google_images": "Visuals for the UI (not sent to the model)",
}

# Engines whose results are shown to the user but not fed to the LLM.
UI_ONLY_ENGINES = {"google_images"}


def build_engine_plan(
    pantry: List[str], goal: str, gl: str = "us", hl: str = "en",
    allergies: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return {engine: params} with a purpose-built query per engine.

    Uses the correct query parameter name per engine (YouTube takes
    ``search_query``; Trends Trending Now takes ``geo`` and no query).
    """
    items = [p.strip() for p in pantry if p and p.strip()]
    top = " ".join(items[:4])
    goal = goal.strip()
    plan: Dict[str, Dict[str, Any]] = {
        "google": {"q": f"{goal} herbal tea recipe {top}"},
        "google_scholar": {"q": f"{goal} {top} herbal clinical evidence"},
        "google_books": {"q": f"traditional herbal decoction {goal} {top}"},
        "google_patents": {"q": f"herbal infusion extraction {top}"},
        "google_news": {"q": f"{top} herbal safety interaction warning"},
        "youtube": {"search_query": f"how to make {top} {goal} drink"},
        "google_trends_trending_now": {"geo": gl.upper(), "hl": hl},
        # Seasonality of interest in the user's own herbs (shown in the UI and used by Modern Refresh).
        "google_trends": {"q": ", ".join(items[:2]) or goal, "data_type": "TIMESERIES", "date": "today 12-m"},
        "duckduckgo": {"q": f"{goal} home remedy {top} drink"},
        "google_images": {"q": f"{top} herbal drink"},
    }
    if allergies:
        # Safety engines also look for allergy and cross-reactivity evidence, so the Cautions
        # line is backed by real citations.
        allergy_words = " ".join(allergies)
        plan["google_scholar"]["q"] += f" allergy cross-reactivity {allergy_words}"
        plan["google_news"]["q"] += f" allergy {allergy_words}"
    return plan


# ---------------------------------------------------------------------------
# Result extraction: normalise every engine's JSON into one Source shape.
# ---------------------------------------------------------------------------

@dataclass
class Source:
    id: str
    engine: str
    title: str
    url: str
    snippet: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def _first(d: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, dict):          # e.g. google_news "source": {"name": "..."}
            v = v.get("name") or v.get("title") or ""
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# (result list key, title keys, url keys, snippet keys) per engine.
# NOTE: confirm key names against a real response for each engine.
_EXTRACTORS = {
    "google": ("organic_results", ("title",), ("link",), ("snippet",)),
    "google_scholar": ("organic_results", ("title",), ("link", "resources"), ("snippet",)),
    "google_books": ("organic_results", ("title",), ("link",), ("description", "snippet")),
    "google_patents": ("organic_results", ("title",), ("patent_link", "link", "pdf"), ("snippet", "abstract")),
    "google_news": ("news_results", ("title",), ("link",), ("snippet", "source")),  # source is {"name": ...}
    "youtube": ("video_results", ("title",), ("link",), ("description", "snippet")),
    "duckduckgo": ("organic_results", ("title",), ("link",), ("snippet",)),
    "google_images": ("images_results", ("title",), ("link", "original"), ("source",)),
    "google_trends_trending_now": ("trending_searches", ("query",), ("link",), ("categories",)),
}


def extract_sources(engine: str, result: Dict[str, Any], limit: int = 4) -> List[Source]:
    spec = _EXTRACTORS.get(engine)
    if not spec or not isinstance(result, dict):
        return []
    list_key, title_keys, url_keys, snippet_keys = spec
    rows = result.get(list_key) or []
    out: List[Source] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        # Grouped news items keep their lead article under "highlight".
        inner = row.get("highlight") if isinstance(row.get("highlight"), dict) else {}
        title = _first(row, *title_keys) or _first(inner, *title_keys)
        url = _first(row, *url_keys) or _first(inner, *url_keys)
        snippet = _first(row, *snippet_keys) or _first(inner, *snippet_keys)
        if not snippet:
            cats = row.get("categories")
            if isinstance(cats, list):
                snippet = ", ".join(str(c.get("name", "")) if isinstance(c, dict) else str(c) for c in cats).strip(", ")
        if not snippet and isinstance(row.get("publication_info"), dict):
            snippet = str(row["publication_info"].get("summary") or "")
        if not snippet and engine == "google_news":
            snippet = " ".join(x for x in (_first(row, "source"), _first(row, "date")) if x)
        if not title:
            continue
        out.append(Source(id="", engine=engine, title=title, url=url, snippet=snippet))
        if len(out) >= limit:
            break
    return out


def _norm_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), "", "", ""))


def dedupe_sources(sources: Iterable[Source]) -> List[Source]:
    """Per-request dedupe by normalised URL, falling back to normalised title.
    Assigns stable ids S1, S2, ... after deduplication."""
    seen = set()
    out: List[Source] = []
    for s in sources:
        key = _norm_url(s.url) or re.sub(r"\W+", " ", s.title.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    for i, s in enumerate(out, 1):
        s.id = f"S{i}"
    return out


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

SAFETY_NOTICE = (
    "Educational only, not medical advice. Check with a clinician or pharmacist "
    "before using herbs if you are pregnant, nursing, on medication, have a "
    "medical condition, or have allergies. Stop if you react badly."
)

PANTRY_STAPLES = {"water", "ice", "salt", "pepper", "sugar", "honey", "oil", "milk"}


def format_context(sources: List[Source], max_chars_per_source: int = 280) -> str:
    lines = []
    for s in sources:
        if s.engine in UI_ONLY_ENGINES:
            continue
        role = ENGINE_ROLES.get(s.engine, s.engine)
        snippet = s.snippet[:max_chars_per_source]
        lines.append(f"[{s.id}] ({role}) {s.title}: {snippet}")
    return "\n".join(lines)


def build_messages(
    pantry: List[str], goal: str, sources: List[Source], insights: List[str],
    allergies: Optional[List[str]] = None, extra_rule: str = "",
) -> List[Dict[str, str]]:
    system = (
        "You are SlothBotanist, a careful master apothecary who only uses what "
        "the user already has. You never suggest buying anything. You never "
        "claim a drink cures or treats disease; say 'traditionally used for'."
    )
    allergy_line = (f"\nALLERGIES (never use, mention or substitute in any of these): {', '.join(allergies)}"
                    if allergies else "")
    user = f"""PANTRY (the ONLY allowed ingredients, plus water and ice): {', '.join(pantry)}{allergy_line}
GOAL: {goal}{(chr(10) + extra_rule) if extra_rule else ''}

SOURCES (cite them as [S1], [S2]; cite only ids listed here, never invent one):
{format_context(sources)}

{('KNOWLEDGE CARDS:' + chr(10) + chr(10).join(insights)) if insights else ''}

TASK: write exactly two sections.
## 📜 Heritage Elixir
A slow decoction or long infusion rooted in the traditional sources. Give amounts, method, time.
## 🌿 Modern Refresh
A quick cold-brew, infused water or smoothie. Give amounts and method.
Rules: use ONLY pantry items; if a source suggests something not in the pantry,
substitute a pantry item and say so. Cite a source id after any claim taken from
a source. End with a 'Cautions' line drawing on safety sources if any."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ---------------------------------------------------------------------------
# Post-generation checks: citations and the zero-shopping rule
# ---------------------------------------------------------------------------

_CITE_RE = re.compile(r"\[(S\d+)\]")


def resolve_citations(text: str, sources: List[Source]):
    """Return (cleaned_text, cited_sources). Unknown ids are removed so the
    model can never cite a source that does not exist."""
    valid = {s.id: s for s in sources}
    cited: List[Source] = []

    def repl(m: "re.Match[str]") -> str:
        sid = m.group(1)
        if sid in valid:
            if valid[sid] not in cited:
                cited.append(valid[sid])
            return m.group(0)
        return ""

    cleaned = _CITE_RE.sub(repl, text)
    cleaned = re.sub(r"[ \t]+([.,;])", r"\1", cleaned)
    return cleaned, cited


HERB_VOCAB = {
    "ginger", "turmeric", "cinnamon", "clove", "cloves", "cardamom", "mint",
    "peppermint", "chamomile", "lavender", "thyme", "rosemary", "sage", "basil",
    "lemon", "lime", "orange", "apple", "honey", "garlic", "fennel", "anise",
    "hibiscus", "elderberry", "echinacea", "ginseng", "licorice", "nettle",
    "cucumber", "mango", "pineapple", "spinach", "kale", "matcha", "oats",
    "nutmeg", "saffron", "vanilla", "cayenne", "pomegranate", "berries",
    "blueberries", "strawberries", "lemongrass", "dandelion", "valerian",
}


def pantry_violations(text: str, pantry: List[str]) -> List[str]:
    """Known ingredients mentioned in the output that are not in the pantry.
    Lets the API prove (or flag) the zero-shopping constraint instead of just
    asking the model nicely."""
    allowed = {w for p in pantry for w in re.findall(r"[a-z]+", p.lower())} | PANTRY_STAPLES
    allowed |= {w.rstrip("s") for w in allowed} | {w + "s" for w in allowed}
    mentioned = set(re.findall(r"[a-z]+", text.lower()))
    return sorted(w for w in HERB_VOCAB if w in mentioned and w not in allowed)


# ---------------------------------------------------------------------------
# Allergies: enforced in code, never left to the model
# ---------------------------------------------------------------------------

_PLANT_DAIRY = r"\b(?:oat|almond|soy|soya|coconut|rice|cashew|hemp|pea)\s+(?:milk|cream|butter|yogurt|yoghurt)\b"

ALLERGENS: Dict[str, Dict[str, Any]] = {
    "peanut": {"terms": ["peanut", "groundnut"]},
    "tree nut": {"terms": ["almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut",
                           "macadamia", "brazil nut", "pine nut", "tree nut", "chestnut"]},
    "dairy": {"terms": ["milk", "butter", "cream", "cheese", "yogurt", "yoghurt", "ghee",
                        "whey", "casein", "kefir"], "ignore": _PLANT_DAIRY},
    "egg": {"terms": ["egg", "albumen", "mayonnaise"]},
    "soy": {"terms": ["soy", "soya", "soybean", "tofu", "tempeh", "miso", "edamame"]},
    "wheat/gluten": {"terms": ["wheat", "gluten", "barley", "rye", "flour", "bread", "malt",
                               "semolina", "spelt"]},
    "sesame": {"terms": ["sesame", "tahini"]},
    "shellfish": {"terms": ["shrimp", "crab", "lobster", "prawn", "shellfish", "crayfish"]},
    "fish": {"terms": ["fish", "salmon", "tuna", "cod", "anchovy", "anchovies"]},
    "mustard": {"terms": ["mustard"]},
    "celery": {"terms": ["celery", "celeriac"]},
    # Pollen/latex allergies have no direct terms; they only trigger cross-reactivity cautions.
    "ragweed": {"terms": [], "cross": ["chamomile", "echinacea", "dandelion", "yarrow", "feverfew",
                                       "calendula", "sunflower", "chrysanthemum", "melon", "banana"]},
    "birch pollen": {"terms": [], "cross": ["apple", "carrot", "hazelnut", "almond", "cherry",
                                            "pear", "celery"]},
    "latex": {"terms": [], "cross": ["banana", "avocado", "kiwi", "chestnut"]},
    "mugwort": {"terms": [], "cross": ["celery", "fennel", "anise", "sage", "coriander"]},
}

ALLERGY_ALIASES: Dict[str, List[str]] = {
    "peanuts": ["peanut"], "nuts": ["peanut", "tree nut"], "nut": ["peanut", "tree nut"],
    "tree nuts": ["tree nut"], "treenut": ["tree nut"], "lactose": ["dairy"], "milk": ["dairy"],
    "eggs": ["egg"], "soya": ["soy"], "wheat": ["wheat/gluten"], "gluten": ["wheat/gluten"],
    "celiac": ["wheat/gluten"], "coeliac": ["wheat/gluten"], "seafood": ["shellfish", "fish"],
    "sesame seeds": ["sesame"], "pollen": ["ragweed", "birch pollen"], "hay fever": ["ragweed", "birch pollen"],
    "birch": ["birch pollen"],
}


def resolve_allergies(raw: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Map free-text allergies to known groups. Anything unrecognised becomes a custom
    allergen, so a user typing 'kiwi' still gets kiwi blocked."""
    out: Dict[str, Dict[str, Any]] = {}
    for a in raw:
        key = re.sub(r"\s+", " ", re.sub(r"[^a-z/ ]", " ", (a or "").lower())).strip()
        key = re.sub(r"\s*allergy$", "", key)
        if not key:
            continue
        names = ALLERGY_ALIASES.get(key) or ([key] if key in ALLERGENS else None)
        if names:
            for n in names:
                out[n] = ALLERGENS[n]
        else:
            out[key] = {"terms": [key], "custom": True}
    return out


def _word_match(term: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(term)}(?:s|es)?\b", text) is not None


def _text_for(allergen: Dict[str, Any], text: str) -> str:
    ign = allergen.get("ignore")
    return re.sub(ign, " ", text) if ign else text


def partition_pantry(pantry: List[str], allergies: Dict[str, Dict[str, Any]]):
    """Return (usable, blocked, cautions). Blocked items never reach the model."""
    usable: List[str] = []
    blocked: List[Dict[str, str]] = []
    cautions: List[Dict[str, str]] = []
    for item in pantry:
        low = item.lower()
        hit = None
        for name, al in allergies.items():
            t = _text_for(al, low)
            term = next((x for x in al.get("terms", []) if _word_match(x, t)), None)
            if term:
                hit = {"item": item, "allergy": name, "matched": term}
                break
        if hit:
            blocked.append(hit)
            continue
        usable.append(item)
        for name, al in allergies.items():
            term = next((x for x in al.get("cross", []) if _word_match(x, low)), None)
            if term:
                cautions.append({"item": item, "allergy": name, "matched": term})
    return usable, blocked, cautions


def allergen_hits(text: str, allergies: Dict[str, Dict[str, Any]]) -> List[str]:
    """Allergen terms found anywhere in the generated recipe. Deliberately conservative:
    even 'contains no almonds' counts, because a false alarm only costs a regeneration."""
    low = text.lower()
    hits = []
    for name, al in allergies.items():
        t = _text_for(al, low)
        for term in al.get("terms", []):
            if _word_match(term, t):
                hits.append(f"{name}:{term}")
    return sorted(set(hits))


MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


def extract_seasonality(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Turn a google_trends TIMESERIES response into per-herb monthly averages and a peak month.
    Needs at least 6 distinct months of data per query, otherwise it says nothing."""
    from datetime import datetime, timezone

    timeline = ((result or {}).get("interest_over_time") or {}).get("timeline_data") or []
    by_query: Dict[str, Dict[int, List[float]]] = {}
    for point in timeline:
        try:
            month = datetime.fromtimestamp(int(point.get("timestamp")), tz=timezone.utc).month
        except (TypeError, ValueError, OSError):
            continue
        for v in point.get("values") or []:
            q, val = v.get("query"), v.get("extracted_value")
            if q is None or not isinstance(val, (int, float)):
                continue
            by_query.setdefault(q, {}).setdefault(month, []).append(float(val))
    series = []
    for q, months in by_query.items():
        avg = {m: sum(v) / len(v) for m, v in months.items()}
        if len(avg) < 6:
            continue
        peak = max(avg, key=avg.get)
        series.append({"query": q, "peak_month": MONTH_NAMES[peak - 1],
                       "monthly": [round(avg.get(m, 0.0), 1) for m in range(1, 13)]})
    return {"series": series} if series else None


def candidate_names_from_lens(result: Dict[str, Any], limit: int = 5) -> List[str]:
    """Pull plant-name candidates from a Google Lens response."""
    names: List[str] = []
    for key in ("knowledge_graph", "visual_matches"):
        rows = result.get(key) or []
        if isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            title = _first(row, "title") if isinstance(row, dict) else ""
            if title and title not in names:
                names.append(title)
            if len(names) >= limit:
                return names
    return names


# ---------------------------------------------------------------------------
# Resilience: cooldowns only for real rate limits, plus an on-disk cache
# ---------------------------------------------------------------------------

class CooldownLedger:
    def __init__(self, duration: float = 10.0, clock: Callable[[], float] = time.time):
        self.duration = duration
        self.clock = clock
        self._hits: Dict[str, float] = {}

    def trip(self, engine: str) -> None:
        self._hits[engine] = self.clock()

    def active(self, engine: str) -> bool:
        t = self._hits.get(engine)
        return t is not None and (self.clock() - t) < self.duration


def is_auth_error(message: str) -> bool:
    """A rejected API key (HTTP 401/403). Retrying cannot help, so callers stop and tell the user."""
    m = message.lower()
    return "401" in m or "unauthorized" in m or "invalid api key" in m or "invalid_api_key" in m or "forbidden" in m and "api" in m


def is_rate_limit(message: str) -> bool:
    m = message.lower()
    return "429" in m or "rate limit" in m or "too many requests" in m or "run out of searches" in m


class DiskCache:
    """Tiny JSON cache so a recorded demo keeps working with no network."""

    def __init__(self, directory: str = ".sloth_cache"):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(engine: str, params: Dict[str, Any]) -> str:
        blob = json.dumps({"e": engine, "p": params}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:24]

    def get(self, engine: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        f = self.dir / f"{self.key(engine, params)}.json"
        if f.exists():
            try:
                data = json.loads(f.read_text())
            except (OSError, ValueError):
                return None
            if isinstance(data, dict) and "result" in data:
                return data["result"]
        return None

    def put(self, engine: str, params: Dict[str, Any], result: Dict[str, Any]) -> None:
        f = self.dir / f"{self.key(engine, params)}.json"
        try:
            f.write_text(json.dumps({"engine": engine, "result": result}, default=str))
        except OSError:
            pass

    def entries(self):
        """Yield (engine, result) for every cached search."""
        for f in self.dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and "engine" in data and "result" in data:
                yield data["engine"], data["result"]


def is_param_rejection(message: str) -> bool:
    """True when SerpApi rejected a parameter (not a rate limit)."""
    m = message.lower()
    return not is_rate_limit(m) and ("_sasl" in m or "invalid parameter" in m or "unsupported parameter" in m)


def cache_stats(cache: DiskCache) -> Dict[str, Any]:
    """Quantify the cache: searches run, unique listings seen, per-engine counts."""
    searches = 0
    by_engine: Dict[str, int] = {}
    seen = set()
    for engine, result in cache.entries():
        searches += 1
        by_engine[engine] = by_engine.get(engine, 0) + 1
        for s in extract_sources(engine, result, limit=50):
            seen.add(_norm_url(s.url) or s.title.lower())
    return {"cached_searches": searches, "unique_listings": len(seen), "by_engine": by_engine}


# ---------------------------------------------------------------------------
# Safety scan: turn news results into a measurable finding ("N of M flagged")
# ---------------------------------------------------------------------------

WARNING_TERMS = (
    "recall", "interaction", "contraindicat", "toxic", "warning", "adverse",
    "liver", "pregnan", "allerg", "fda", "contaminat",
)


def flag_safety(sources: List[Source]) -> List[Dict[str, Any]]:
    flagged = []
    for s in sources:
        text = f"{s.title} {s.snippet}".lower()
        hits = [t for t in WARNING_TERMS if t in text]
        if hits:
            flagged.append({**s.to_dict(), "terms": hits})
    return flagged


def weekly_scan_summary(per_herb: Dict[str, List[Source]]) -> Dict[str, Any]:
    """Aggregate a per-herb news scan into a headline finding."""
    total = sum(len(v) for v in per_herb.values())
    herbs = {}
    flagged_total = 0
    for herb, srcs in per_herb.items():
        fl = flag_safety(srcs)
        flagged_total += len(fl)
        herbs[herb] = {"listings": len(srcs), "flagged": len(fl), "items": fl}
    return {
        "herbs_scanned": len(per_herb),
        "total_listings": total,
        "flagged_listings": flagged_total,
        "headline": f"{flagged_total} of {total} news listings across {len(per_herb)} herbs carry a safety signal",
        "herbs": herbs,
    }
