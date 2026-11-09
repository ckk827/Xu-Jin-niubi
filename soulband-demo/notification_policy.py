"""Messages remain history; expired authorization must not produce a later popup."""
import engine
import sensing
import quiet_rules


def deliverable(state, reminder):
    context = sensing.prepare(state)
    active = engine.active_proposal(context)
    if not active or reminder.get("version") != active["id"]:
        return False
    clause = next((c for c in active["clauses"] if c["id"] == reminder.get("clause_id") and c["kind"] == "quiet"), None)
    if not clause:
        return False
    inside, cycle = engine.quiet_window(context, clause)
    eligible = quiet_rules.scope(clause, [m["id"] for m in state["members"]])["member_ids"]
    return inside and reminder.get("target") in eligible and cycle == reminder.get("cycle")
