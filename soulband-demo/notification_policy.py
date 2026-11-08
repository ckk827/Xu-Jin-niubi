"""Messages remain history; expired authorization must not produce a later popup."""
import engine
import sensing


def deliverable(state, reminder):
    context = sensing.prepare(state)
    active = engine.active_proposal(context)
    if not active or reminder.get("version") != active["id"]:
        return False
    clause = next((c for c in active["clauses"] if c["id"] == reminder.get("clause_id") and c["kind"] == "quiet"), None)
    if not clause:
        return False
    inside, cycle = engine.quiet_window(context, clause)
    return inside and cycle == reminder.get("cycle")
