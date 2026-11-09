"""Executable limits of a reviewed quiet clause, shared by every reminder path."""
from datetime import date, datetime, timedelta
import re

import storage as db


def scope(clause, members):
    """Keep old daily clauses usable; fail closed on unrepresented conditions."""
    weekdays = set(clause.get("weekdays", range(7)))
    targets = set(clause.get("member_ids") or members)
    issue = ""
    text = clause.get("text", "")
    # Recognise the common legacy wording too, so editing only the text cannot
    # silently turn a weekday agreement into an everyday agreement.
    workweek = r"(?:星期|周)一\s*(?:至|到|[-—~～])\s*(?:星期|周)?五|工作日"
    weekend = r"周末|(?:星期|周)六\s*(?:、|和|及|至|到)\s*(?:星期|周)?[日天]"
    if re.search(workweek, text):
        weekdays &= set(range(5))
    elif re.search(weekend, text):
        match = re.search(weekend, text)
        suffix = text[match.end():match.end() + 12]
        weekdays &= set(range(5)) if re.search(r"不|除外|无需", suffix) else {5, 6}
    elif re.search(r"星期|每周|周[一二三四五六日天]|礼拜", text):
        issue = "正文含尚未结构化的星期条件，请修订为明确的星期范围"
    remaining = re.sub(workweek, "", text)
    remaining = re.sub(weekend + r"[^，。；;]*", "", remaining)
    if (clause.get("automation", "automatic") == "manual" or clause.get("exceptions")
            or re.search(r"除非|如果|节假日|法定假日|考试|特殊情况|仅当|除.{1,20}外", remaining)):
        issue = "含需人工确认的例外，保留文字公约，不自动提醒"
    if re.search(r"仅|只对|只限|限于", remaining) and not clause.get("member_ids") and not re.search(workweek, text):
        issue = "正文含尚未结构化的适用范围，请修订或设为仅文字约定"
    if not targets <= set(members):
        issue = "适用成员不在当前寝室中"
    if re.search(r"\d{4}[-年]\d{1,2}[-月]\d{1,2}", text) and not (clause.get("starts_on") or clause.get("ends_on")):
        issue = "正文含尚未结构化的日期条件，请补充适用日期范围"
    return {"weekdays": sorted(weekdays), "member_ids": sorted(targets), "issue": issue}


def window(state, clause, now=None):
    """Dates/weekdays refer to the start day of a midnight-spanning window."""
    current = now or db.business_now(state)
    start, end, hhmm = clause["start"], clause["end"], current.strftime("%H:%M")
    day = current.date()
    if start < end:
        inside = start <= hhmm < end
    else:
        inside = hhmm >= start or hhmm < end
        if hhmm < end:
            day -= timedelta(days=1)
    limits = scope(clause, [m["id"] for m in state["members"]])
    inside = inside and not limits["issue"] and day.weekday() in limits["weekdays"]
    if clause.get("starts_on"):
        inside = inside and day >= date.fromisoformat(clause["starts_on"])
    if clause.get("ends_on"):
        inside = inside and day <= date.fromisoformat(clause["ends_on"])
    paused = any(a["status"] == "approved" and a["version_id"] == state["active_id"]
                 and a["clause_id"] == clause["id"]
                 and datetime.fromisoformat(a["starts"]) <= current < datetime.fromisoformat(a["ends"])
                 for a in state.get("adjustments", []))
    return bool(inside and not paused), f"{day.isoformat()}:{start}-{end}"


def resumed_at(state, clause, now=None):
    """Latest end of an approved pause in this currently open quiet window."""
    current = now or db.business_now(state)
    inside, cycle = window(state, clause, current)
    if not inside:
        return None
    start = datetime.fromisoformat(cycle[:10] + "T" + clause["start"])
    ends = [datetime.fromisoformat(a["ends"]) for a in state.get("adjustments", [])
            if a["status"] == "approved" and a["version_id"] == state["active_id"]
            and a["clause_id"] == clause["id"]
            and start < datetime.fromisoformat(a["ends"]) <= current]
    return max(ends) if ends else None
