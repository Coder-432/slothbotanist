"""SlothBotanist v7: pantry-only apothecary grounded in SerpApi, written by a local Qwen."""
import asyncio
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from serpapi import Client

from apothecary_core import (
    SAFETY_NOTICE, UI_ONLY_ENGINES, CooldownLedger, DiskCache, Source,
    allergen_hits, build_engine_plan, build_messages, cache_stats, extract_seasonality,
    candidate_names_from_lens, dedupe_sources, extract_sources, is_auth_error, is_param_rejection,
    is_rate_limit, pantry_violations, partition_pantry, resolve_allergies,
    resolve_citations,
)

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
MODEL_ID = os.getenv("HUGGINGFACE_MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")  # tunnel URL, needed for Google Lens uploads
OFFLINE = os.getenv("SLOTH_OFFLINE", "0") == "1"                # serve only from the disk cache
ZERO_TRACE = os.getenv("SERPAPI_ZERO_TRACE", "0") == "1"        # enterprise-only SerpApi feature
SASL_FLAGS = os.getenv("SERPAPI_SASL", "1") == "1"              # _sasl=1 + _saslop=1; auto-dropped once if SerpApi rejects them
NO_CACHE = os.getenv("SERPAPI_NO_CACHE", "0") == "1"            # force live (uncached) SerpApi results
SKIP_MODEL = os.getenv("SLOTH_SKIP_MODEL", "0") == "1"          # for tests / demos without a GPU
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

serp_client: Optional[Client] = Client(api_key=SERPAPI_KEY) if SERPAPI_KEY else None
cooldowns = CooldownLedger(duration=10.0)
cache = DiskCache()
state: Dict[str, Any] = {"pipe": None, "auth_failed": False}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not SKIP_MODEL:
        import torch
        from transformers import pipeline
        print(f"Loading local model {MODEL_ID} ...")
        state["pipe"] = await run_in_threadpool(
            lambda: pipeline(
                "text-generation",
                model=MODEL_ID,
                torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
                device_map="auto",
            )
        )
        print("Model ready.")
    yield


app = FastAPI(title="SlothBotanist", version="7.0.0", lifespan=lifespan)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


class ApothecaryRequest(BaseModel):
    pantry_items: List[str] = Field(min_length=1)
    wellness_goal: str = Field(min_length=2)
    identified_herbs: List[str] = []          # from /api/scan-herb
    allergies: List[str] = []                 # free text, e.g. ["tree nuts", "ragweed", "kiwi"]
    location: str = "United States"
    gl: str = "us"
    hl: str = "en"
    google_domain: str = "google.com"


# ---------------------------------------------------------------------------
# SerpApi node
# ---------------------------------------------------------------------------

usage = {"brews": 0, "withheld": 0}


async def run_engine(engine: str, engine_params: Dict[str, Any], cfg: ApothecaryRequest) -> Dict[str, Any]:
    started = time.time()
    params: Dict[str, Any] = {"engine": engine, **engine_params}
    if engine.startswith("google") and engine not in ("google_trends_trending_now", "google_trends"):
        params.update(location=cfg.location, gl=cfg.gl, hl=cfg.hl, google_domain=cfg.google_domain)
    if ZERO_TRACE:
        params["zero_trace"] = "true"
    if NO_CACHE:
        params["no_cache"] = "true"
    if SASL_FLAGS:
        params["_sasl"] = 1
        params["_saslop"] = 1

    def report(status: str, result: Optional[Dict[str, Any]] = None, **extra: Any) -> Dict[str, Any]:
        return {"engine": engine, "status": status, "ms": int((time.time() - started) * 1000),
                "result": result or {}, **extra}

    cached = cache.get(engine, params)
    if OFFLINE or serp_client is None:
        return report("cache_hit" if cached else "offline_miss", cached)
    if state["auth_failed"]:
        # The key was rejected (401). Do not spend more requests on it; serve the cache if there is one.
        return report("auth_error", cached) if cached else report("auth_error", message="SerpApi rejected the API key (401).")
    if cooldowns.active(engine):
        return report("cooldown", cached) if cached else report("cooldown")
    try:
        # no_cache is deliberately not set: SerpApi's own cache is free and fast.
        try:
            result = await run_in_threadpool(lambda: serp_client.search(params))
            data = dict(result)
            if "error" in data:
                raise RuntimeError(str(data["error"]))
        except Exception as first:  # noqa: BLE001
            # 429s are NEVER retried: trip the cooldown and fall through to cache/error.
            # The only retry is when SerpApi rejects the _sasl flags themselves, and then
            # we retry exactly once without them.
            if not (SASL_FLAGS and is_param_rejection(str(first))):
                raise
            params.pop("_sasl", None)
            params.pop("_saslop", None)
            result = await run_in_threadpool(lambda: serp_client.search(params))
            data = dict(result)
            if "error" in data:
                raise RuntimeError(str(data["error"]))
        cache.put(engine, params, data)
        return report("success", data, search_id=data.get("search_metadata", {}).get("id"))
    except Exception as e:  # noqa: BLE001
        if is_auth_error(str(e)):
            state["auth_failed"] = True       # a bad key will not fix itself: stop calling until restart
        elif is_rate_limit(str(e)):
            cooldowns.trip(engine)            # 429s are never retried
        if cached:
            return report("fallback_cache", cached, message=str(e))
        return report("error", message=str(e))


def card_insights(engine: str, result: Dict[str, Any]) -> List[str]:
    out = []
    kg = result.get("knowledge_graph")
    if isinstance(kg, dict) and kg:
        out.append(f"({engine}) {kg.get('title', '')}: {str(kg.get('description', ''))[:300]}")
    ab = result.get("answer_box")
    if isinstance(ab, dict) and ab:
        out.append(f"({engine}) {str(ab.get('answer') or ab.get('snippet') or '')[:300]}")
    return [x for x in out if len(x) > 20]


def generate(messages: List[Dict[str, str]]) -> str:
    pipe = state["pipe"]
    if pipe is None:
        return ""
    prompt = pipe.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    out = pipe(prompt, max_new_tokens=900, temperature=0.6, do_sample=True,
               pad_token_id=pipe.tokenizer.eos_token_id)
    return out[0]["generated_text"][len(prompt):].strip()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/brew")
async def brew(data: ApothecaryRequest):
    # 1. Allergies are enforced in code: blocked items never reach the search queries or the model.
    allergies = resolve_allergies(data.allergies)
    pantry, blocked, cautions = partition_pantry([*data.pantry_items, *data.identified_herbs], allergies)
    if not pantry:
        raise HTTPException(400, {"error": "Every pantry item conflicts with the listed allergies.",
                                  "blocked_items": blocked})

    # 2. Fan out to every engine in parallel; each has its own tailored query.
    plan = build_engine_plan(pantry, data.wellness_goal, gl=data.gl, hl=data.hl, allergies=list(allergies))
    nodes = await asyncio.gather(*(run_engine(e, p, data) for e, p in plan.items()))

    raw_sources: List[Source] = []
    insights: List[str] = []
    engine_report = []
    archive_ids = []
    visuals = []
    seasonality = None
    for n in nodes:
        engine_report.append({k: n[k] for k in ("engine", "status", "ms") if k in n} |
                             ({"message": n["message"]} if "message" in n else {}))
        if n.get("search_id"):
            archive_ids.append(n["search_id"])
        if not n["result"]:
            continue
        if n["engine"] == "google_trends":
            seasonality = extract_seasonality(n["result"])
            if seasonality:
                insights += [f"Search interest in {s['query']} peaks in {s['peak_month']} (last 12 months)"
                             for s in seasonality["series"]]
            continue
        found = extract_sources(n["engine"], n["result"], limit=4)
        if n["engine"] in UI_ONLY_ENGINES:
            visuals += [s.to_dict() for s in found]
            continue
        raw_sources += found
        insights += card_insights(n["engine"], n["result"])

    sources = dedupe_sources(raw_sources)  # per request, never global
    if not sources:
        messages_seen = " ".join(str(n.get("message", "")) for n in nodes)
        if state["auth_failed"] or is_auth_error(messages_seen):
            raise HTTPException(401, "SerpApi rejected the API key. Check SERPAPI_KEY, then restart the server.")
        if is_rate_limit(messages_seen) or any(n["status"] == "cooldown" for n in nodes):
            raise HTTPException(429, "SerpApi is rate limiting this key or the monthly searches are used up. "
                                     "Wait a minute and try again; nothing was retried automatically.")
        raise HTTPException(503, "No search results available (check SERPAPI_KEY or the offline cache).")

    allergy_names = list(allergies)
    messages = build_messages(pantry, data.wellness_goal, sources, insights, allergies=allergy_names)
    text = await run_in_threadpool(generate, messages)
    if not text:
        raise HTTPException(503, "Local model not loaded (SLOTH_SKIP_MODEL=1?).")

    # 3. Output check: any allergen term in the recipe triggers one regeneration, then withholding.
    regenerated = False
    hits = allergen_hits(text, allergies)
    if hits:
        regenerated = True
        rule = ("A previous draft mentioned forbidden allergens (" + ", ".join(h.split(":")[1] for h in hits)
                + "). Rewrite the recipes without them and do not name them.")
        text = await run_in_threadpool(
            generate, build_messages(pantry, data.wellness_goal, sources, insights,
                                     allergies=allergy_names, extra_rule=rule))
        hits = allergen_hits(text, allergies)

    usage["brews"] += 1
    allergy_report = {"checked": allergy_names, "blocked_items": blocked,
                      "cross_reactivity_cautions": cautions, "output_hits": hits,
                      "regenerated": regenerated}
    if hits:
        usage["withheld"] += 1
        return {"status": "withheld", "elixirs": None, "allergies": allergy_report,
                "message": "The local model kept mentioning an allergen, so no recipe is shown. Try again or remove items.",
                "safety_notice": SAFETY_NOTICE}

    text, cited = resolve_citations(text, sources)
    return {
        "allergies": allergy_report,
        "status": "success",
        "elixirs": text,
        "citations": [s.to_dict() for s in cited],
        "all_sources": [s.to_dict() for s in sources],
        "visuals": visuals,
        "seasonality": seasonality,
        "pantry_violations": pantry_violations(text, pantry),   # empty list == zero-shopping proven
        "engine_report": engine_report,
        "archive_ledger_ids": archive_ids,
        "safety_notice": SAFETY_NOTICE,
    }


@app.post("/api/scan-herb")
async def scan_herb(file: Optional[UploadFile] = File(None), image_url: Optional[str] = Form(None)):
    """Google Lens: identify an unknown herb. Lens needs a PUBLIC image URL, so an upload is
    served from /uploads via PUBLIC_BASE_URL (e.g. an ngrok or Cloudflare tunnel)."""
    saved: Optional[Path] = None
    try:
        if file is not None:
            if not PUBLIC_BASE_URL:
                raise HTTPException(400, "Set PUBLIC_BASE_URL to a public tunnel URL, or pass image_url instead.")
            ext = Path(file.filename or "").suffix.lower() or ".jpg"
            if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise HTTPException(400, "Unsupported image type.")
            saved = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
            saved.write_bytes(await file.read())
            image_url = f"{PUBLIC_BASE_URL}/uploads/{saved.name}"
        if not image_url:
            raise HTTPException(400, "Provide a file or image_url.")
        if serp_client is None:
            raise HTTPException(503, "SERPAPI_KEY not set.")
        params = {"engine": "google_lens", "url": image_url}
        if ZERO_TRACE:
            params["zero_trace"] = "true"
        result = dict(await run_in_threadpool(lambda: serp_client.search(params)))
        names = candidate_names_from_lens(result)
        return {"status": "success", "candidates": names,
                "next_step": "Send the confirmed name in identified_herbs on /api/brew.",
                "search_id": result.get("search_metadata", {}).get("id")}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Visual scanning failed: {e}")
    finally:
        if saved and saved.exists():
            saved.unlink(missing_ok=True)  # remove after Lens has fetched it


@app.get("/api/archive/{search_id}")
async def archive(search_id: str):
    # Be forgiving about what was pasted: quotes, spaces, or several ids from "Copy ids". Use the first id.
    found = re.search(r"[A-Za-z0-9_-]{6,64}", search_id.replace("%20", " "))
    if not found:
        raise HTTPException(400, "That does not look like a search id. Paste one id, for example 64f1a2b3c4d5e6f708192a3b.")
    search_id = found.group(0)
    if serp_client is None:
        raise HTTPException(503, "SERPAPI_KEY not set.")
    try:
        fn = getattr(serp_client, "search_archive", None)
        if fn is not None:
            data = await run_in_threadpool(lambda: dict(fn({"search_id": search_id})))
        else:
            r = await run_in_threadpool(lambda: requests.get(
                f"https://serpapi.com/searches/{search_id}.json", params={"api_key": SERPAPI_KEY}, timeout=10))
            data = r.json()
        return {"status": "success", "archive_data": data}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Archive lookup failed: {e}")


@app.get("/api/telemetry")
async def telemetry():
    if serp_client is None:
        raise HTTPException(503, "SERPAPI_KEY not set.")
    try:
        fn = getattr(serp_client, "account", None) or getattr(serp_client, "get_account")
        acct = await run_in_threadpool(lambda: dict(fn()))
        # The account record includes the API key and email; never send those to a browser.
        safe = {k: v for k, v in acct.items() if not any(w in k.lower() for w in ("key", "email", "token", "secret"))}
        return {"status": "success", "telemetry": safe}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Telemetry failed: {e}")


@app.get("/api/locations")
async def locations(q: str = Query(..., min_length=2)):
    try:
        r = await run_in_threadpool(lambda: requests.get(
            "https://serpapi.com/locations.json", params={"q": q, "limit": 10}, timeout=10))
        return {"status": "success", "locations": r.json()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Locations lookup failed: {e}")


@app.get("/api/extract")
async def extract(url: str = Query(...)):
    if not re.match(r"https?://[^\s]+$", url.strip(), re.I):
        raise HTTPException(400, "Please paste a web link that starts with http:// or https://.")
    url = url.strip()
    if serp_client is None:
        raise HTTPException(503, "SERPAPI_KEY not set.")
    try:
        params = {"engine": "extract", "url": url}
        result = dict(await run_in_threadpool(lambda: serp_client.search(params)))
        return {"status": "success", "extracted": result}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Extraction error: {e}")


@app.get("/api/stats")
async def stats():
    """Quantified usage: cached searches, unique listings, per-engine counts."""
    return {"status": "success", **await run_in_threadpool(cache_stats, cache),
            "brews": usage["brews"], "withheld_for_allergens": usage["withheld"]}


@app.get("/api/health")
async def health():
    return {"model_loaded": state["pipe"] is not None, "serpapi_key": bool(SERPAPI_KEY) and not state["auth_failed"],
            "offline": OFFLINE}


# The front end (static/index.html, style.css, app.js). Mounted last so every /api route wins.
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")
