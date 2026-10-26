"""Instinct for trade over the sea (contact games only): take a surplus across in a boat, barter it at the other
village's stores for goods of the same worth, and sail home with them.

At war, a village with a longship sends a raider instead (one at a time): abroad it goes for the stores, a holmgang
of rune, sail and axe with whoever stands there decides whether it gets anything (sim/holmgang.py), and it sails home
in the longship, which waited for it. A village at war with a boat and the idea of a longship builds one.

Boats could only carry a chit away for good. Now a village with a surplus and a boat sends one trader at a time;
abroad, the trader trades at the stores (sim.actions._trade_at_stores: a silent trade, so it works in any culture) and sails home in the
boat it came in, back to the home it left.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..sim.agent import TICKS_PER_DAY, Agent
from ..sim.items import DESIGNS, item_name

Plan = Dict[str, Any]
SURPLUS = 20  # a store holding this much of one thing has some to spare
CARGO = 8
SEND_EVERY_DAYS = 3  # at most one trader leaves a village in this many days
ABROAD_W, SEND_W = 8.0, 0.9


def abroad_plan(world, a: Agent) -> Plan | None:
    """A trader from over the sea: barter its load, then sail home. A raider: try the stores, then sail home."""
    if a.origin and a.voyage_intent == "raid":
        if not a.stats.get("pillaged_trip"):
            from ..sim import holmgang as HG

            rage = []  # carrying the red mushroom and mead, and two weapons: go in as a berserker
            if HG.weapons(a) >= 2 and a.inventory.get("mushroom") and a.inventory.get("mead") and not HG.raging(world, a):
                rage = [{"do": "eat", "what": "mushroom"}, {"do": "eat", "what": "mead"}]
            return {"goal": "raid the stores here", "thought": "The longship is beached. To the stores, and may the runes favour me.",
                    "steps": rage + [{"do": "pillage"}]}
        if a.stats.get("boat_abroad"):
            from ..sim.actions import _crewmates

            waiting = [o for o in _crewmates(world, a) if not o.stats.get("pillaged_trip")]
            if waiting and world.tick - a.stats.get("pillaged_at", -10 ** 9) < TICKS_PER_DAY:
                return {"goal": "wait for the crew", "thought": f"{waiting[0].name} is still at the stores. We sail together.",
                        "steps": [{"do": "rest"}]}
            return {"goal": "sail home with the plunder", "thought": "Back to the ship, and home over the whale-road.",
                    "steps": [{"do": "sail", "intent": "home"}]}
        return None
    if not a.origin or a.voyage_intent != "trade":
        return None
    if a.stats.get("traded_trip"):
        if not a.stats.get("boat_abroad"):
            return None  # (a trader from an old save, with no boat waiting: it stays)
        return {"goal": "sail home with the trade goods", "thought": "The trade is made. Home, with what I got.",
                "steps": [{"do": "sail", "intent": "home"}]}
    return {"goal": "trade at the stores here", "thought": "I came over the sea to trade. Let's see what they have.",
            "steps": [{"do": "trade", "at": "stores"}]}


def _home_xy(world, a: Agent) -> Tuple[int, int]:
    h = world.structures.get(a.home or "")
    return (h.x, h.y) if h is not None else (a.x, a.y)


def _surplus(world, a: Agent):
    """(store, the good it has most of) for a store near home with some to spare, else None."""
    hx, hy = _home_xy(world, a)
    for pile in world.structures_near(hx, hy, 25, "stockpile"):
        if not pile.functional or not world.same_land(a, pile):
            continue
        spare = sorted(((n, k) for k, n in pile.storage.items() if n >= SURPLUS and (it := world.item(k)) is not None
                        and not it.tool), reverse=True)
        if spare:
            return pile, spare[0][1]
    return None


def boat_plan(world, a: Agent) -> Plan | None:
    """Something to spare and no boat to carry it: build one on the shore."""
    t = world.tick
    memo = world.__dict__.setdefault("_noboat", {})  # a planner's cache: not saved, not the chit's state
    if (a.origin or a.is_child(t) or not (getattr(world, "contact", False) or getattr(world, "fair_soon", False))
            or not a.knows_design("boat")
            or memo.get(a.id, 0) > t or a.reflex_rest.get("nobuild:boat", 0) > t):
        return None
    if any(s.design == "boat" for s in world.structures.values()) or _surplus(world, a) is None:
        memo[a.id] = t + TICKS_PER_DAY
        return None
    from .instinct import _need_steps

    mats = DESIGNS["boat"].material_map
    steps = _need_steps(a, mats, world)
    if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
        memo[a.id] = t + TICKS_PER_DAY
        return None
    hx, hy = _home_xy(world, a)
    return {"goal": "build a boat to trade over the sea",
            "thought": "We have more than we need, and over the sea they have things we don't. We need a boat.",
            "steps": steps[:4] + [{"do": "build", "what": "boat", "near": f"{hx},{hy}"}]}


def send_plan(world, a: Agent) -> Plan | None:
    """A surplus in the stores near home and a boat at hand: take a load over the sea to trade."""
    if a.origin or a.is_child(world.tick) or not getattr(world, "contact", False):
        return None
    last = (getattr(world, "civic", None) or {}).get("trader_sent", -10 ** 9)  # saved with the village
    if world.tick - last < SEND_EVERY_DAYS * TICKS_PER_DAY:
        return None
    if any((o.get("agent") or {}).get("voyage_intent") == "trade" for o in getattr(world, "outbox", [])):
        return None
    boat = next((b for b in world.structures_near(a.x, a.y, 60, "boat") if b.functional and world.same_land(a, b)), None)
    found = _surplus(world, a) if boat is not None else None
    if found:
        pile, k = found
        return {"goal": f"take {item_name(k)} over the sea to trade",
                "thought": f"We have more {item_name(k)} than we need. Over the sea they may have what we don't.",
                "steps": [{"do": "take", "what": k, "qty": CARGO, "target": pile.id},
                          {"do": "sail", "target": boat.id, "intent": "trade"}]}
    return None


def at_war(world) -> bool:
    return any(r.get("state") == "war" for r in getattr(world, "relations", {}).values())


PREP_EVERY_DAYS = 2  # one chit at a time readies itself as a berserker, at most this often
PREP_W = 3.0


def carrying_fare(a: Agent) -> bool:
    """Carrying the red mushroom, mead and two weapons: a berserker in waiting, fare in hand."""
    from ..sim import holmgang as HG

    return a.inventory.get("mushroom", 0) > 0 and a.inventory.get("mead", 0) > 0 and HG.weapons(a) >= 2


def ready(world, a: Agent) -> bool:
    """Two weapons in hand, and the fare in hand or waiting in the stores nearby (a busy chit puts its load away)."""
    from ..sim import holmgang as HG

    return carrying_fare(a) or (HG.weapons(a) >= 2 and _stored_fare(world, a) is not None)


def _stored_fare(world, a: Agent):
    """A store near this chit holding both a red mushroom and mead (a busy chit puts its load away), else None."""
    return next((p for p in world.structures_near(a.x, a.y, 25, "stockpile") if p.functional
                 and p.storage.get("mushroom", 0) > 0 and p.storage.get("mead", 0) > 0), None)


def _war_ship(world, a: Agent):
    """At war, in a contact game, a grown-up of this island with a longship on its land: else None."""
    if a.origin or a.is_child(world.tick) or not getattr(world, "contact", False) or not at_war(world):
        return None
    return next((b for b in world.structures_near(a.x, a.y, max(world.w, world.h), "longship") if b.functional and world.same_land(a, b)), None)


def berserk_prep_plan(world, a: Agent) -> Plan | None:
    """At war, with a longship on the shore or out raiding (or the idea of one): one chit readies itself to raid as a
    berserker. It finds a red mushroom in the woods,
    gets mead (brews it from wild honey at a workshop, or tries honey there if nobody knows how yet), and a second
    weapon. Then raid_plan sends it first."""
    from ..sim import holmgang as HG
    from .instinct import _craft_steps, _need_steps

    if a.origin or a.is_child(world.tick) or not getattr(world, "contact", False) or not at_war(world) or ready(world, a):
        return None  # (or all set: the fare in hand or waiting in the stores)
    if _war_ship(world, a) is None and not a.knows_design("longship"):
        return None  # (the ship is usually away raiding: knowing what a longship is will do)
    t = world.tick
    since, who = (world.civic.get("berserk_prep") or [-10 ** 9, ""])[:2]
    if who != a.id and t - since < PREP_EVERY_DAYS * TICKS_PER_DAY:
        return None  # someone else is readying itself
    if any(ready(world, o) for o in world.agents.values() if not o.origin and o is not a):
        return None  # a berserker is already waiting
    from ..sim.actions import STATION_REACH

    workshop = world.nearest_station(a.x, a.y, "workshop", STATION_REACH)
    steps: List[Dict[str, Any]] = []
    if not a.inventory.get("mushroom"):
        steps += _need_steps(a, {"mushroom": 1}, world) or [{"do": "gather", "what": "mushroom", "qty": 1}]
    if not a.inventory.get("mead"):
        if a.knows_recipe("mead"):
            brew = _craft_steps(a, "mead", 1, world=world)
            if not brew:
                return None
            steps += brew
        elif workshop is not None:  # nobody here knows mead yet: honey at a workshop is the obvious thing to try
            need = max(0, 2 - a.inventory.get("honey", 0))
            steps += ([{"do": "gather", "what": "honey", "qty": need}] if need else []) + [
                {"do": "experiment", "with": ["honey", "honey"], "at": "workshop"}]
        else:
            return None
    if HG.weapons(a) < 2:
        arm = next((s for k in ("spear", "stone_axe") if a.knows_recipe(k) for s in [_craft_steps(a, k, 1, world=world)]
                    if s), None)
        if not arm:
            return None
        steps += arm
    if who != a.id:
        world.civic["berserk_prep"] = [t, a.id]  # (saved with the village; the same chit is offered it again)
    return {"goal": "ready myself as a berserker",
            "thought": "The red mushroom, the mead, an axe in each hand. Over the sea they won't stand against that.",
            "steps": steps[:6]}


def raid_plan(world, a: Agent) -> Plan | None:
    """At war, with a longship at hand: one raider at a time sails over to try the other village's stores (a readied
    berserker first)."""
    if a.origin or a.is_child(world.tick) or not getattr(world, "contact", False) or not at_war(world):
        return None
    if not ready(world, a) and any(ready(world, o) for o in world.agents.values() if not o.origin and o is not a
                            and not o.is_child(world.tick)):
        return None  # our berserker goes
    last = (getattr(world, "civic", None) or {}).get("raider_sent", -10 ** 9)
    if world.tick - last < SEND_EVERY_DAYS * TICKS_PER_DAY:
        return None
    if any((o.get("agent") or {}).get("voyage_intent") == "raid" for o in getattr(world, "outbox", [])):
        return None
    ship = next((b for b in world.structures_near(a.x, a.y, max(world.w, world.h), "longship") if b.functional and world.same_land(a, b)), None)
    if ship is None:
        return None
    from ..sim import holmgang as HG

    fare = []  # two weapons in hand, and the berserker's fare waiting in the stores: take it along
    pile = _stored_fare(world, a) if not carrying_fare(a) and HG.weapons(a) >= 2 else None
    if pile is not None:
        fare = [{"do": "take", "what": k, "qty": 1, "target": pile.id} for k in ("mushroom", "mead")
                if not a.inventory.get(k)]
    return {"goal": "go raiding over the sea",
            "thought": "They are our enemies now. The longship is ready, and the runes are carved.",
            "steps": fare + [{"do": "sail", "target": ship.id, "intent": "raid", "crew": "auto"}]}


def longship_plan(world, a: Agent) -> Plan | None:
    """At war, with a boat but no longship: build one (a sail and a dragon prow) on the shore."""
    t = world.tick
    memo = world.__dict__.setdefault("_nolongship", {})  # a planner's cache: not saved, not the chit's state
    if (a.origin or a.is_child(t) or not getattr(world, "contact", False) or not a.knows_design("longship")
            or memo.get(a.id, 0) > t or a.reflex_rest.get("nobuild:longship", 0) > t or not at_war(world)):
        return None
    if any(s.design == "longship" for s in world.structures.values()):
        memo[a.id] = t + TICKS_PER_DAY
        return None
    from .instinct import _need_steps

    mats = DESIGNS["longship"].material_map
    steps = _need_steps(a, mats, world)
    if not steps and any(a.inventory.get(k, 0) < n for k, n in mats.items()):
        memo[a.id] = t + TICKS_PER_DAY
        return None
    hx, hy = _home_xy(world, a)
    return {"goal": "build a longship",
            "thought": "A boat is for traders. For a war over the sea we need a longship with a sail.",
            "steps": steps[:4] + [{"do": "build", "what": "longship", "near": f"{hx},{hy}"}]}


def options(world, a: Agent, rng) -> List[Tuple[float, Plan]]:
    plan = abroad_plan(world, a)
    if plan:
        return [(ABROAD_W, plan)]
    plan = raid_plan(world, a)
    if plan:
        return [(SEND_W + 1.0 - a.traits.get("caution", 0.5) + (1.0 if ready(world, a) else 0.0), plan)]
    plan = berserk_prep_plan(world, a)
    if plan:
        return [(PREP_W - a.traits.get("caution", 0.5), plan)]  # war is a strong pull: like a tool it needs
    plan = send_plan(world, a) or boat_plan(world, a) or longship_plan(world, a)
    return [(SEND_W + a.traits.get("sociability", 0.5), plan)] if plan else []


def sent(world, who: str = "trader") -> None:
    """A trader (or raider) has set out: the next one waits a few days."""
    world.civic[f"{who}_sent"] = world.tick
