import tempfile

from apothecary_core import (
    CooldownLedger, DiskCache, Source, build_engine_plan, build_messages,
    candidate_names_from_lens, dedupe_sources, extract_sources, is_rate_limit,
    pantry_violations, resolve_citations,
)


def test_plan_uses_engine_specific_params():
    plan = build_engine_plan(["ginger", "lemon"], "sore throat", gl="us")
    assert "search_query" in plan["youtube"] and "q" not in plan["youtube"]
    assert plan["google_trends_trending_now"]["geo"] == "US"
    assert "q" not in plan["google_trends_trending_now"]
    qs = {v["q"] for k, v in plan.items() if "q" in v}
    assert len(qs) == len([v for v in plan.values() if "q" in v])  # every query differs


def test_extract_and_dedupe_per_request():
    res = {"organic_results": [
        {"title": "A", "link": "https://www.x.com/a/", "snippet": "one"},
        {"title": "A again", "link": "https://x.com/a", "snippet": "dup"},
        {"title": "B", "link": "https://y.com/b", "snippet": "two"},
    ]}
    s = extract_sources("google", res)
    d = dedupe_sources(s)
    assert [x.id for x in d] == ["S1", "S2"]
    # second request is independent: nothing global to leak
    assert len(dedupe_sources(extract_sources("google", res))) == 2


def test_extract_handles_garbage():
    assert extract_sources("google", {}) == []
    assert extract_sources("nope", {"organic_results": []}) == []
    assert extract_sources("google", {"organic_results": ["x", {"snippet": "no title"}]}) == []


def test_trends_has_no_link_but_still_extracts():
    res = {"trending_searches": [{"query": "cold brew hibiscus", "categories": ["Food"]}]}
    s = extract_sources("google_trends_trending_now", res)
    assert s[0].title == "cold brew hibiscus" and s[0].snippet == "Food"


def test_resolve_citations_strips_invented_ids():
    srcs = [Source("S1", "google", "t", "u", "s")]
    text, cited = resolve_citations("Steep 10 min [S1]. Also good [S9] .", srcs)
    assert "[S9]" not in text and "[S1]" in text
    assert [c.id for c in cited] == ["S1"]


def test_pantry_violations():
    pantry = ["fresh ginger", "lemon peel", "cinnamon sticks"]
    assert pantry_violations("Simmer ginger and cinnamon with lemon and honey", pantry) == []
    assert pantry_violations("Add turmeric and fennel", pantry) == ["fennel", "turmeric"]


def test_lens_candidates():
    r = {"visual_matches": [{"title": "Mentha spicata"}, {"title": "Spearmint"}]}
    assert candidate_names_from_lens(r) == ["Mentha spicata", "Spearmint"]


def test_cooldown_expires():
    t = [100.0]
    led = CooldownLedger(10.0, clock=lambda: t[0])
    led.trip("google")
    assert led.active("google")
    t[0] = 111.0
    assert not led.active("google")
    assert not led.active("youtube")


def test_rate_limit_detection():
    assert is_rate_limit("HTTP 429 Too Many Requests")
    assert not is_rate_limit("Invalid API key")


def test_disk_cache_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        c = DiskCache(d)
        p = {"q": "ginger"}
        assert c.get("google", p) is None
        c.put("google", p, {"organic_results": []})
        assert c.get("google", p) == {"organic_results": []}


def test_param_rejection_is_not_a_rate_limit():
    from apothecary_core import is_param_rejection
    assert is_param_rejection("Invalid parameter _sasl")
    assert not is_param_rejection("HTTP 429 Too Many Requests _sasl")  # 429s are never retried
    assert not is_param_rejection("Invalid API key")


def test_cache_stats_and_weekly_summary():
    from apothecary_core import cache_stats, weekly_scan_summary, flag_safety
    with tempfile.TemporaryDirectory() as d:
        c = DiskCache(d)
        c.put("google", {"q": "a"}, {"organic_results": [
            {"title": "A", "link": "https://x.com/a", "snippet": "s"},
            {"title": "B", "link": "https://x.com/b", "snippet": "s"}]})
        c.put("google", {"q": "b"}, {"organic_results": [
            {"title": "A", "link": "https://www.x.com/a/", "snippet": "dup"}]})
        st = cache_stats(c)
        assert st["cached_searches"] == 2 and st["unique_listings"] == 2
    news = [Source("S1", "google_news", "FDA recall of herbal tea", "u1", "contaminated batch"),
            Source("S2", "google_news", "Ginger latte trend", "u2", "cafes love it")]
    assert len(flag_safety(news)) == 1
    summ = weekly_scan_summary({"ginger": news, "mint": []})
    assert summ["headline"] == "1 of 2 news listings across 2 herbs carry a safety signal"


def test_allergy_resolution_and_aliases():
    from apothecary_core import resolve_allergies
    r = resolve_allergies(["Tree nuts", "gluten allergy", "kiwi", "nuts"])
    assert {"tree nut", "wheat/gluten", "kiwi", "peanut"} <= set(r)
    assert r["kiwi"].get("custom")


def test_partition_blocks_allergens_and_flags_cross_reactivity():
    from apothecary_core import partition_pantry, resolve_allergies
    pantry = ["fresh ginger", "almond milk", "walnuts", "nutmeg", "oat milk", "chamomile tea", "kiwi slices"]
    al = resolve_allergies(["tree nuts", "ragweed", "kiwi"])
    usable, blocked, cautions = partition_pantry(pantry, al)
    assert {b["item"] for b in blocked} == {"almond milk", "walnuts", "kiwi slices"}
    assert "nutmeg" in usable and "oat milk" in usable   # nutmeg is not a tree nut; plant milk is not dairy
    assert [c["item"] for c in cautions] == ["chamomile tea"]
    assert cautions[0]["allergy"] == "ragweed"


def test_dairy_allergy_allows_plant_milk_but_blocks_butter():
    from apothecary_core import partition_pantry, resolve_allergies
    usable, blocked, _ = partition_pantry(["oat milk", "coconut cream", "butter", "whole milk"],
                                          resolve_allergies(["dairy"]))
    assert usable == ["oat milk", "coconut cream"]
    assert {b["item"] for b in blocked} == {"butter", "whole milk"}


def test_allergen_hits_in_generated_text():
    from apothecary_core import allergen_hits, resolve_allergies
    al = resolve_allergies(["tree nuts", "dairy"])
    assert allergen_hits("Simmer ginger with nutmeg and oat milk.", al) == []
    assert allergen_hits("Top with crushed Almonds and a splash of milk.", al) == ["dairy:milk", "tree nut:almond"]


def test_allergies_reach_safety_queries_and_prompt():
    plan = build_engine_plan(["ginger"], "cold", allergies=["ragweed"])
    assert "ragweed" in plan["google_scholar"]["q"] and "ragweed" in plan["google_news"]["q"]
    body = build_messages(["ginger"], "cold", [], [], allergies=["ragweed"])[1]["content"]
    assert "ALLERGIES" in body and "ragweed" in body


def test_seasonality_peak_month():
    from datetime import datetime, timezone
    from apothecary_core import extract_seasonality
    pts = []
    for m in range(1, 13):
        for day in (3, 17):
            ts = int(datetime(2025, m, day, tzinfo=timezone.utc).timestamp())
            pts.append({"timestamp": str(ts), "values": [
                {"query": "elderberry", "extracted_value": 90 if m == 10 else 20}]})
    out = extract_seasonality({"interest_over_time": {"timeline_data": pts}})
    s = out["series"][0]
    assert s["query"] == "elderberry" and s["peak_month"] == "October"
    assert s["monthly"][9] == 90.0 and len(s["monthly"]) == 12


def test_seasonality_needs_enough_data_and_survives_garbage():
    from apothecary_core import extract_seasonality
    assert extract_seasonality({}) is None
    assert extract_seasonality({"interest_over_time": {"timeline_data": [
        {"timestamp": "bad", "values": [{"query": "x", "extracted_value": 5}]}]}}) is None
    plan = build_engine_plan(["ginger", "mint", "lemon"], "cold")
    assert plan["google_trends"]["q"] == "ginger, mint" and plan["google_trends"]["data_type"] == "TIMESERIES"


def test_prompt_contains_only_known_ids_and_pantry():
    srcs = dedupe_sources(extract_sources("google", {"organic_results": [
        {"title": "T", "link": "https://a.com", "snippet": "s"}]}))
    msgs = build_messages(["ginger"], "colds", srcs, [])
    body = msgs[1]["content"]
    assert "[S1]" in body and "ginger" in body and "Heritage Elixir" in body


def test_real_response_shapes_from_docs():
    news = extract_sources("google_news", {"news_results": [
        {"title": "Ginger and warfarin", "link": "https://n.com/a", "source": {"name": "Health Daily"}, "date": "2 days ago"},
        {"highlight": {"title": "Grouped story", "link": "https://n.com/b", "source": {"name": "BBC"}}},
    ]})
    assert [s.title for s in news] == ["Ginger and warfarin", "Grouped story"]
    assert news[0].snippet == "Health Daily" and news[1].url == "https://n.com/b"
    trend = extract_sources("google_trends_trending_now", {"trending_searches": [
        {"query": "elderberry syrup", "categories": [{"id": 5, "name": "Health"}, {"id": 9, "name": "Food"}]}]})
    assert trend[0].snippet == "Health, Food"
    pat = extract_sources("google_patents", {"organic_results": [
        {"title": "Extraction", "patent_link": "https://p.google/x", "snippet": "a method"}]})
    assert pat[0].url == "https://p.google/x"
    sch = extract_sources("google_scholar", {"organic_results": [
        {"title": "Study", "link": "https://s.org/1", "publication_info": {"summary": "A Smith - 2020"}}]})
    assert sch[0].snippet == "A Smith - 2020"


def test_auth_errors_are_not_rate_limits():
    from apothecary_core import is_auth_error, is_rate_limit
    assert is_auth_error("401 Client Error: Unauthorized for url") and is_auth_error("Invalid API key. Your API key should be here: ...")
    assert not is_auth_error("429 Too Many Requests") and not is_auth_error("Connection reset")
    assert is_rate_limit("429 Too Many Requests") and not is_rate_limit("401 Unauthorized")


if __name__ == "__main__":
    import inspect, sys, traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for n, f in tests:
        try:
            f()
        except Exception:  # noqa: BLE001
            fails += 1
            print("FAIL", n)
            traceback.print_exc()
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
