"""Berserkers and longship crews. A berserker (red mushroom and mead in it, a weapon in each hand) throws two signs in
a holmgang, and nobody who isn't raging too can beat it outright. A raiding longship carries a crew of up to 3
friends, never so many that fewer than half the island stays home; they land together, each raids for itself, and the
captain sails them all home."""

import asyncio
import random

from chits.brain import prompt as P
from chits.brain import voyages as VOY
from chits.brain.parse import parse_plan
from chits.sim import actions
from chits.sim import holmgang as HG
from chits.sim.items import match_recipe
from test_buildings import run_step, village
from test_trade_voyage import _do, _put


def _pair():
    w, (a, b) = village()
    b.x, b.y = a.x + 1, a.y
    return w, a, b


def _rage(w, a, weapons=("stone_axe", "spear")):
    a.stats["mushroom_t"] = a.stats["mead_t"] = w.tick
    for k in weapons:
        a.inventory[k] = a.inventory.get(k, 0) + 1


def test_a_berserker_throws_two_signs_and_never_loses_a_round():
    for t in HG.THROWS:
        mine = HG.hands(t, True)
        assert len(set(mine)) == 2 and mine[0] == t
        outcomes = [(HG._beats(mine, (o,)), HG._beats((o,), mine)) for o in HG.THROWS]
        assert not any(lost for _, lost in outcomes)  # never loses a round
        assert sum(won for won, _ in outcomes) == 2  # wins two in three, ties the third
    w, a, b = _pair()
    _rage(w, a)
    energy = a.energy
    for theirs in HG.THROWS:
        res = HG.play(w, a, b, ["rune"], [theirs])
        if theirs == "rune" and res["winner"] is b:  # only a tie every round can hold it off
            assert all(r["win"] == "" for r in res["rounds"])
        if theirs != "rune":
            assert res["winner"] is a and all(r["win"] in ("", a.id) for r in res["rounds"])
        _rage(w, a, ())
    res = HG.play(w, a, b, ["axe"], ["sail"])
    assert res["winner"] is a
    assert res["berserk"][a.id] and "berserker, a weapon in each hand" in HG.tale(res, a, b)
    assert "mushroom_t" not in a.stats and a.energy < energy  # the rage is spent, and so is the berserker


def test_the_rage_needs_the_mushroom_and_the_mead_within_a_day_and_two_weapons():
    w, a, b = _pair()
    w.tick = 1000
    a.inventory.update({"stone_axe": 1, "spear": 1})
    assert not HG.berserk(w, a)
    a.stats["mushroom_t"] = w.tick
    assert not HG.raging(w, a)  # the mushroom alone isn't enough
    a.stats["mead_t"] = w.tick - HG.BERSERK_TICKS - 1
    assert not HG.raging(w, a)  # nor mead drunk yesterday
    a.stats["mead_t"] = w.tick
    assert HG.berserk(w, a)
    a.inventory["spear"] = 0
    assert HG.raging(w, a) and not HG.berserk(w, a)  # one weapon: raging, but no berserker
    a.inventory["iron_axe"] = 1
    assert HG.berserk(w, a)
    w.tick += HG.BERSERK_TICKS + 1
    assert not HG.raging(w, a)  # it wears off


def test_eating_the_mushroom_and_drinking_mead_brings_the_rage_on():
    w, a, b = _pair()
    a.inventory.update({"mushroom": 1, "mead": 1, "stone_axe": 1, "spear": 1})
    assert run_step(w, a, {"do": "eat", "what": "red mushroom"}) == actions.DONE
    assert not HG.raging(w, a) and "rage" not in P.scene(w, a)
    assert run_step(w, a, {"do": "eat", "what": "mead"}) == actions.DONE
    assert HG.berserk(w, a) and not a.inventory.get("mushroom") and not a.inventory.get("mead")
    [ev] = [e for e in w.events if e.kind == "berserk"]
    assert "berserker's rage" in ev.text
    assert "A berserker's rage is in you, and a weapon in each hand" in P.scene(w, a)
    assert "in a berserker's rage, a weapon in each hand" in P.scene(w, b)  # others can see it
    assert "A berserker's rage is in you; a weapon in each hand" in P.compact_scene(w, a)  # (small models too)


def test_mushrooms_and_honey_are_foraged_and_honey_brews_mead():
    w, a, b = _pair()
    for kind in ("mushroom", "honey"):
        assert run_step(w, a, {"do": "gather", "what": kind, "qty": 2}) == actions.DONE, kind
        assert a.inventory.get(kind) == 2, kind
    assert match_recipe({"honey": 2}, "workshop").key == "mead"
    assert match_recipe({"honey": 2}, None) is None


def _isles(tmp_path, monkeypatch, n=8):
    monkeypatch.setenv("CHITS_PER_WORLD", str(n))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=5, mode="rivals")
    for w in rt.worlds.values():
        w.contact = True
        w.relation("B" if w.id == "A" else "A")["state"] = "war"
        for o in w.agents.values():
            o.hunger = o.energy = o.warmth = 95.0
    return rt


def _close(rt):
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_a_longship_crew_sails_lands_raids_and_comes_home_together(tmp_path, monkeypatch):
    rt = _isles(tmp_path, monkeypatch)
    wa, wb = rt.worlds["A"], rt.worlds["B"]
    adults = [o for o in wa.agents.values() if not o.is_child(wa.tick)]
    cap = adults[0]
    hut = _put(wa, cap, "hut", (cap.x, cap.y))
    cap.home = hut.id
    ship = _put(wa, cap, "longship", (cap.x, cap.y))
    cap.x, cap.y = ship.x, ship.y + 1
    for o in wa.agents.values():
        if o is not cap:
            o.x, o.y = cap.x + 2, cap.y
            o.like(cap.id, 30)
    grudge = adults[-1]
    grudge.like(cap.id, -80)  # holds a grudge against the captain: won't sail with them
    home_pop = sum(1 for o in wa.agents.values() if not o.origin)
    [(_, plan)] = VOY.options(wa, cap, random.Random(1))
    assert _do(wa, cap, plan["steps"][0]) == actions.DONE
    [voyage] = wa.outbox
    crew_ids = {c["id"] for c in voyage["crew"]}
    crew_names = {c["name"] for c in voyage["crew"]}  # (abroad, an id that clashes gets a suffix: names travel)
    assert 1 <= len(crew_ids) <= actions.CREW_MAX and grudge.id not in crew_ids
    assert home_pop - 1 - len(crew_ids) >= home_pop // 2  # at least half stay home
    [ev] = [e for e in wa.events if e.kind == "voyage"]
    assert "with a crew of" in ev.text

    wa.tick = voyage["arrive_tick"]
    rt._deliver_boats()
    raiders = [o for o in wb.agents.values() if o.origin == "A"]
    captain = next(o for o in raiders if o.stats.get("longship_abroad"))
    crew = [o for o in raiders if o is not captain]
    assert {o.name for o in crew} == crew_names
    assert all(max(abs(o.x - captain.x), abs(o.y - captain.y)) <= 4 for o in crew)  # landed together
    assert "I wait for" in actions.advance(wb, crew[0], {"do": "sail", "intent": "home"})  # not without the captain

    host = next(o for o in wb.agents.values() if not o.origin and not o.is_child(wb.tick))
    stores = _put(wb, host, "stockpile", (host.x + 2, host.y))
    stores.storage.update({"stone": 60, "wood": 60})
    for o in wb.agents.values():
        if o.origin != "A":
            o.x, o.y = 2, 2  # (nobody home: unguarded stores)
    for o in raiders:
        o.x, o.y = stores.x, stores.y - 1
    assert _do(wb, captain, {"do": "pillage"}) == actions.DONE
    [(_, plan)] = VOY.options(wb, captain, random.Random(1))
    assert plan["goal"] == "wait for the crew"  # the crew is still to raid
    for o in crew:
        assert _do(wb, o, {"do": "pillage"}) == actions.DONE
        assert sum(o.inventory.get(k, 0) for k in ("stone", "wood")) == actions.LOOT  # (the captain's load is bigger)
    [(_, plan)] = VOY.options(wb, captain, random.Random(1))
    assert plan["steps"] == [{"do": "sail", "intent": "home"}]
    assert _do(wb, captain, plan["steps"][0]) == actions.DONE
    assert not [o for o in wb.agents.values() if o.origin == "A"]  # all aboard
    [back] = wb.outbox
    boats = sum(1 for s in wa.structures.values() if s.design == "boat")
    wb.tick = back["arrive_tick"]
    rt._deliver_boats()
    assert sum(1 for s in wa.structures.values() if s.design == "longship") == 1  # one ship, beached by the captain
    assert sum(1 for s in wa.structures.values() if s.design == "boat") == boats  # (the crew beach nothing)
    for i in [cap.id] + list(crew_ids):  # (home again under the ids their kin know them by)
        o = wa.agents[i]
        assert not o.origin and not o.stats.get("crew") and o.voyage_intent == "home"
    raids = [e for e in wa.events if e.kind == "raid"]
    assert len(raids) == 1 + len(crew_ids) and all("longship laden with plunder" in e.text for e in raids)
    _close(rt)


def test_a_crew_left_without_its_captain_takes_the_helm(tmp_path, monkeypatch):
    rt = _isles(tmp_path, monkeypatch)
    wb = rt.worlds["B"]
    a = next(iter(wb.agents.values()))
    a.origin, a.homeland, a.voyage_intent, a.stats["crew"] = "A", "A", "raid", 1
    assert actions.advance(wb, a, {"do": "sail", "intent": "home"}) == actions.DONE  # no captain here: it sails
    [back] = wb.outbox
    assert back["agent"]["stats"]["longship_abroad"] == 1 and back["agent"]["voyage_intent"] == "home"
    assert "crew" not in back["agent"]["stats"]
    _close(rt)


def test_a_models_crew_survives_the_parser():
    p = parse_plan('{"thought":"t","goal":"g","plan":[{"do":"sail","intent":"raid","crew":["Astrid","Bjorn",{"x":1},'
                   '"Leif","Ulf"]},{"do":"sail","intent":"raid","crew":"auto"}]}')
    assert p["steps"][0]["crew"] == ["Astrid", "Bjorn", "Leif"] and p["steps"][1]["crew"] == "auto"


def test_named_crew_only_and_no_grudge_holders():
    w, ags = village(n=8)
    cap = ags[0]
    for o in ags[1:]:
        o.x, o.y = cap.x + 1, cap.y
    ags[1].like(cap.id, -10)
    picked = actions._pick_crew(w, cap, [ags[1].name, ags[2].name])
    assert picked == [ags[2]]  # ags[1] holds a grudge
    assert actions._pick_crew(w, cap, None) == []
    assert len(actions._pick_crew(w, cap, "auto")) == actions.CREW_MAX


def test_a_small_village_keeps_at_least_half_its_people_home():
    w, ags = village(n=4)
    cap = ags[0]
    for o in ags[1:]:
        o.x, o.y = cap.x + 1, cap.y
    assert len(actions._pick_crew(w, cap, "auto")) == 1  # 2 sail, 2 stay


def test_a_runestone_ward_is_the_counter_to_a_berserker():
    from test_buildings import put

    w, a, b = _pair()
    put(w, "runestone", b, (b.x, b.y))
    w.tick += 1
    b.origin = ""
    a.origin = "B"  # a raider: the stone wards b, not a
    _rage(w, a)
    res = HG.play(w, a, b, ["rune"], ["rune"])  # every round a tie, and the ward gives each to b
    assert res["winner"] is b and all(r["ward"] for r in res["rounds"])
