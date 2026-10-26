"""Instinct berserkers: at war, with a longship on the shore, one chit at a time readies itself as a berserker (a red
mushroom from the woods, mead brewed from wild honey at a workshop, a second weapon), and the raid waits for it."""

import random

from chits.brain import voyages as VOY
from chits.sim import actions
from chits.sim import holmgang as HG
from test_trade_voyage import _do, _put
from test_viking_crews import _close, _isles


def _home(rt, wid="A"):
    w = rt.worlds[wid]
    adults = [o for o in w.agents.values() if not o.is_child(w.tick)]
    a = adults[0]
    ship = _put(w, a, "longship", (a.x, a.y))
    shop = _put(w, a, "workshop", (a.x, a.y))
    a.x, a.y = shop.x - 1, shop.y
    a.inventory.clear()
    a.learn("recipe:spear", "insight", w.tick)
    a.learn("recipe:sharp_stone", "insight", w.tick)  # (instinct chits know both early)
    return w, a, adults, ship, shop


def test_at_war_one_chit_readies_itself_and_finds_out_how_to_brew_mead(tmp_path, monkeypatch):
    rt = _isles(tmp_path, monkeypatch)
    w, a, adults, ship, shop = _home(rt)
    a.inventory.update({"stone_axe": 1})
    plan = VOY.berserk_prep_plan(w, a)
    assert plan and plan["goal"] == "ready myself as a berserker"
    dos = [s["do"] for s in plan["steps"]]
    assert dos[0] == "gather" and plan["steps"][0]["what"] == "mushroom"
    assert {"do": "experiment", "with": ["honey", "honey"], "at": "workshop"} in plan["steps"]  # nobody knows mead yet
    b = adults[1]
    b.learn("recipe:spear", "insight", w.tick)
    b.learn("recipe:sharp_stone", "insight", w.tick)
    b.inventory["stone_axe"] = 1
    assert VOY.berserk_prep_plan(w, b) is None  # one at a time (b could ready itself too)
    w.civic.pop("berserk_prep")
    assert VOY.berserk_prep_plan(w, b) is not None
    w.civic["berserk_prep"] = [w.tick, a.id]
    assert VOY.berserk_prep_plan(w, a) is not None  # (still offered to the one readying itself)

    for _ in range(3):  # (a plan holds at most 6 steps: the next one picks up where it left off)
        for step in plan["steps"]:
            assert _do(w, a, step, limit=3000) == actions.DONE, step
        plan = VOY.berserk_prep_plan(w, a)
        if plan is None:
            break
    assert a.knows_recipe("mead") and VOY.ready(w, a), a.inventory  # discovered, and armed with axe and spear
    assert HG.weapons(a) >= 2

    # the raid waits for its berserker
    other = adults[1]
    assert VOY.raid_plan(w, other) is None
    [(_, plan)] = VOY.options(w, a, random.Random(1))
    assert plan["steps"][0]["do"] == "sail" and plan["steps"][0]["intent"] == "raid"
    _close(rt)


def test_no_berserkers_in_peace_or_without_a_longship(tmp_path, monkeypatch):
    rt = _isles(tmp_path, monkeypatch)
    w, a, adults, ship, shop = _home(rt)
    w.relation("B")["state"] = "peace"
    assert VOY.berserk_prep_plan(w, a) is None
    w.relation("B")["state"] = "war"
    w.structures.pop(ship.id)
    assert VOY.berserk_prep_plan(w, a) is None
    w.contact = False
    assert VOY.berserk_prep_plan(w, a) is None
    _close(rt)


def test_a_chit_that_knows_mead_brews_it_and_the_berserker_wins_abroad(tmp_path, monkeypatch):
    rt = _isles(tmp_path, monkeypatch)
    w, a, adults, ship, shop = _home(rt)
    a.learn("recipe:mead", "insight", w.tick)
    a.inventory.update({"stone_axe": 1, "spear": 1})
    plan = VOY.berserk_prep_plan(w, a)
    assert not any(s["do"] == "experiment" for s in plan["steps"])
    assert any(s["do"] == "craft" and s["what"] == "mead" for s in plan["steps"])
    for step in plan["steps"]:
        assert _do(w, a, step, limit=3000) == actions.DONE, step
    assert VOY.ready(w, a)

    # over the sea: it eats the fare before going for the stores, and wins
    wb = rt.worlds["B"]
    raider = next(o for o in wb.agents.values() if not o.is_child(wb.tick))
    host = next(o for o in wb.agents.values() if o is not raider and not o.is_child(wb.tick))
    raider.origin, raider.homeland, raider.voyage_intent = "A", "A", "raid"
    raider.inventory = dict(a.inventory)
    stores = _put(wb, host, "stockpile", (host.x + 2, host.y))
    stores.storage.update({"stone": 30})
    for o in wb.agents.values():
        if o is not host and o is not raider:
            o.x, o.y = 2, 2
    raider.x, raider.y = host.x, host.y + 1
    [(_, plan)] = VOY.options(wb, raider, random.Random(1))
    assert [s["do"] for s in plan["steps"]] == ["eat", "eat", "pillage"]
    for step in plan["steps"]:
        assert _do(wb, raider, step) == actions.DONE, step
    [ev] = [e for e in wb.events if e.kind == "pillage"]
    assert ev.data["won"] and "berserker" in ev.text
    _close(rt)


def test_a_raider_abroad_raids_before_helping_the_locals(tmp_path, monkeypatch):
    from chits.brain.instinct import Instinct

    rt = _isles(tmp_path, monkeypatch)
    wb = rt.worlds["B"]
    raider = next(o for o in wb.agents.values() if not o.is_child(wb.tick))
    raider.origin, raider.homeland, raider.voyage_intent = "A", "A", "raid"
    raider.stats.update({"boat_abroad": 1, "longship_abroad": 1})
    raider.hunger = raider.energy = raider.warmth = 90.0
    wb.tick = 240 + 100  # (midday)
    plan = Instinct().plan(wb, raider)
    assert plan["goal"] == "raid the stores here" and plan["steps"][-1] == {"do": "pillage"}
    _close(rt)


def test_the_fare_put_away_in_the_stores_still_makes_a_berserker_and_the_raid_waits_for_it(tmp_path, monkeypatch):
    rt = _isles(tmp_path, monkeypatch)
    w, a, adults, ship, shop = _home(rt)
    pile = _put(w, a, "stockpile", (a.x, a.y))
    pile.storage.update({"mushroom": 1, "mead": 1})  # (a busy chit put its load away)
    a.inventory.update({"stone_axe": 1, "spear": 1})
    other = adults[1]
    other.x, other.y = a.x, a.y
    other.inventory = {"stone_axe": 1}
    assert VOY.ready(w, a) and not VOY.ready(w, other)
    assert VOY.raid_plan(w, other) is None  # one weapon: it waits for the one with two
    plan = VOY.raid_plan(w, a)
    assert [s["do"] for s in plan["steps"]] == ["take", "take", "sail"]
    assert {s["what"] for s in plan["steps"][:2]} == {"mushroom", "mead"}
    _close(rt)


def test_the_raid_finds_its_longship_anywhere_on_the_island(tmp_path, monkeypatch):
    rt = _isles(tmp_path, monkeypatch)
    w, a, adults, ship, shop = _home(rt)
    far = next(((x, y) for y in range(w.h) for x in range(w.w) if max(abs(x - ship.x), abs(y - ship.y)) > 70
                and w.passable(x, y) and w.same_land(a, ship) and w.same_land_xy(a, x, y)), None)
    assert far, "the island is big enough to beach a ship far from home"
    a.x, a.y = far  # (a ship comes home wherever it lands on the coast, often far from the village)
    plan = VOY.raid_plan(w, a)
    assert plan and plan["steps"][-1]["target"] == ship.id
    _close(rt)
