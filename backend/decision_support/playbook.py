"""Versioned starter templates; suitability tags require review by the team's coach."""

CATALOG_VERSION = "starter-2"
PERSONNEL = {"any": "Any personnel", "11": "11 · 1 RB / 1 TE", "12": "12 · 1 RB / 2 TE", "21": "21 · 2 RB / 1 TE"}
FORMATIONS = {"any": "Any formation", "gun_doubles": "Gun doubles", "gun_trips": "Gun trips", "gun_bunch": "Gun bunch", "under_center": "Under center"}
OBJECTIVES = {"balanced": "Balanced", "conversion": "Move the chains", "clock": "Use clock", "explosive": "Seek an explosive play"}


def concept(id, name, action, personnel, formations, distance, coverages, goals, summary, read, counters, min_field=1):
    return dict(id=id, name=name, type=action, personnel=personnel, formations=formations,
                distance_range=distance, preferred_coverages=coverages, goals=goals,
                minimum_field_space=min_field, summary=summary, read=read, counters=counters,
                tag=f"{' / '.join(personnel)} personnel · {' / '.join(FORMATIONS[f] for f in formations)}",
                source="Unreviewed starter coaching template", diagram_key=id)


PLAYBOOK = [
    concept("mesh", "Mesh sit", "PASS", ["11"], ["gun_trips", "gun_doubles"], [3, 10], ["MAN", "COVER_1", "2_MAN"], ["conversion"],
            "Shallow crossing routes with a sit option. Verify spacing and protection against your installed rules.",
            "Read the shallow cross, then the sit option; keep an outlet available.", ["zone", "stick"]),
    concept("zone", "Inside zone", "RUN", ["11", "12"], ["gun_doubles", "under_center"], [1, 6], [], ["clock", "conversion"],
            "A downhill zone run. Box count and blocking rules determine whether your version fits.",
            "Press the installed aiming point and follow the blocking read.", ["flood", "outside_zone"]),
    concept("flood", "Flood concept", "PASS", ["11", "12"], ["gun_bunch", "gun_trips"], [5, 15], ["ZONE", "COVER_3"], ["explosive"],
            "Three levels toward a sideline. Check space, protection, and route spacing.",
            "Read deep to intermediate to flat according to your installed progression.", ["zone", "mesh"], 10),
    concept("outside_zone", "Outside zone", "RUN", ["11", "12"], ["gun_doubles", "under_center"], [1, 10], [], ["clock"],
            "A perimeter zone template that requires coordinated reach blocks.",
            "Press the edge and make the installed one-cut read.", ["counter", "flood"]),
    concept("power", "Power", "RUN", ["12", "21"], ["under_center"], [1, 3], [], ["clock", "conversion"],
            "A gap run with a puller and lead block. Confirm assignments against the defensive front.",
            "Follow the lead block through the installed gap.", ["slant_flat", "counter"]),
    concept("counter", "Counter", "RUN", ["11", "12"], ["gun_doubles", "under_center"], [2, 8], [], ["clock"],
            "A misdirection gap-run template. Pulling rules and backfield timing require installation.",
            "Use the counter step, then follow the pullers through the intended gap.", ["outside_zone", "mesh"]),
    concept("draw", "Draw", "RUN", ["11"], ["gun_doubles", "gun_trips"], [7, 20], [], ["clock"],
            "A delayed handoff template. Long-yardage suitability does not establish conversion value.",
            "Sell the pass set and follow the installed interior blocking read.", ["stick", "verticals"]),
    concept("stick", "Stick", "PASS", ["11", "12"], ["gun_trips", "gun_bunch"], [1, 6], ["ZONE", "COVER_3", "COVER_4"], ["conversion"],
            "A quick stick-and-flat combination with a vertical clear-out.",
            "Read the underneath defender between stick and flat.", ["zone", "verticals"]),
    concept("slant_flat", "Slant-flat", "PASS", ["11", "21"], ["gun_doubles", "under_center"], [1, 5], ["MAN", "COVER_0", "COVER_1"], ["conversion"],
            "A quick inside/outside route combination. Release leverage and timing matter.",
            "Use your installed leverage read between the slant and flat.", ["power", "verticals"]),
    concept("verticals", "Four verticals", "PASS", ["11"], ["gun_doubles", "gun_trips"], [10, 30], ["ZONE", "COVER_3"], ["explosive"],
            "Four vertical lanes. Requires field space and enough protection for the route timing.",
            "Read safety leverage and the installed seam adjustments.", ["draw", "stick"], 15),
    concept("screen", "RB screen", "PASS", ["11", "12"], ["gun_doubles", "gun_trips"], [6, 20], [], [],
            "A delayed back release with blockers in space. Verify timing and eligible-release rules.",
            "Invite the rush, then deliver behind the releasing blockers.", ["zone", "verticals"]),
    concept("sprint_out", "Sprint-out flat", "PASS", ["11", "12"], ["gun_bunch", "under_center"], [1, 4], ["ZONE", "COVER_3"], ["conversion"],
            "A moving-pocket flat/out combination for limited field space.",
            "Secure the edge and read the short out to the flat.", ["power", "zone"]),
]


def get_call(call_id):
    for call in PLAYBOOK:
        if call["id"] == call_id:
            return dict(call)
    raise ValueError("Unknown playbook call")


def default_preferences():
    return dict(personnel="any", formation="any", anticipated_coverage="UNKNOWN", objective="balanced",
                installed_call_ids=[call["id"] for call in PLAYBOOK])


def validate_preferences(data, coverages):
    defaults = default_preferences()
    if not isinstance(data, dict) or set(data) != set(defaults):
        raise ValueError("Provide the complete coaching preferences")
    for key, choices in [("personnel", PERSONNEL), ("formation", FORMATIONS), ("objective", OBJECTIVES),
                         ("anticipated_coverage", coverages)]:
        if not isinstance(data[key], str) or data[key] not in choices:
            raise ValueError(f"Unsupported {key}")
    ids = data["installed_call_ids"]
    known = {call["id"] for call in PLAYBOOK}
    if not isinstance(ids, list) or any(not isinstance(id, str) or id not in known for id in ids) or len(set(ids)) != len(ids):
        raise ValueError("Installed calls must be unique catalog IDs")
    return {**data, "installed_call_ids": sorted(ids)}
