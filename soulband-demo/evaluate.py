"""Reproducible draft benchmark: real baseline versus the app's optimized prompt."""
import argparse
import asyncio
import copy
import json
from pathlib import Path
import statistics
import time
import engine
import sensing
import storage


def cases():
    state = storage.seed()
    state["mode"] = "ollama"
    state["active_id"] = "p-eval"
    state["proposals"] = [{"id":"p-eval", "version":1, "title":"人工确认场景公约", "status":"active", "approvals":["m1","m2","m3","m4"], "conflicts":[], "clauses":[{"id":"q1", "title":"静音", "kind":"quiet", "text":"每日23:30至07:00保持安静，可以戴耳机使用设备。", "start":"23:30", "end":"07:00", "sources":[]}]}]
    cases = []
    def add(identity, description, changes, statuses, targets):
        value = copy.deepcopy(state)
        changes(value)
        cases.append({"id":identity,"description":description,"state":value,"expected_states":dict(zip(("m1","m2","m3","m4"),statuses)),"expected_targets":targets,"partition":"exploratory_review_required"})
    base = ["resting","active","resting","resting"]
    add("night", "夜间有效持续无操作与活动并存，允许预防性提醒", lambda s:None, base, ["m2"])
    add("day", "下午不得自动扩展静音要求", lambda s:s["clock"].update(time="15:00"), base, [])
    add("unapproved", "未审核公约不提醒", lambda s:s.update(active_id=None), base, [])
    add("missing_phone", "其余休息依据均缺失时不得以缺数据推断休息", lambda s:[m["devices"][1].update(signal="unknown") for m in s["members"] if m["id"]!="m2"], ["unknown","active","unknown","unknown"], [])
    add("cross_device_active", "一台持续无操作、另一台近期操作应为有活动", lambda s:s["members"][0]["devices"][1].update(signal="active"), ["active","active","resting","resting"], ["m1","m2"])
    add("dedupe", "同一静音周期已提醒则不再次自动催促", lambda s:s["reminders"].append({"id":"old", "target":"m2", "cycle":"2026-10-27:23:30-07:00", "clause_id":"q1", "version":"p-eval", "message":"预防提醒", "kind":"auto", "created":0}), base, [])
    add("short_inactivity", "暂时离开不能当作可能休息", lambda s:[d.update(signal="away") for m in s["members"] if m["id"]!="m2" for d in m["devices"]], ["unknown","active","unknown","unknown"], [])
    add("manual_override", "有效本人纠正优先于设备", lambda s:s["members"][1].update(manual={"status":"resting", "activity":"本人休息", "expires":time.time()+3600}), ["resting"]*4, [])
    add("all_active", "没有休息依据时不提醒", lambda s:[d.update(signal="active") for m in s["members"] for d in m["devices"]], ["active"]*4, [])
    add("stale", "原生数据过期则未知", lambda s:[d.update(source="android_live" if d["id"]=="phone" else "windows_live", expires_at=time.time()-10, signal="idle") for m in s["members"] if m["id"]!="m2" for d in m["devices"]], ["unknown","active","unknown","unknown"], [])
    add("temporary_pause", "全员批准的临时安排暂停对应条款", lambda s:s.update(adjustments=[{"id":"a", "version_id":"p-eval", "clause_id":"q1", "status":"approved", "starts":"2026-10-28T00:00", "ends":"2026-10-28T00:30", "approvals":["m1","m2","m3","m4"]}]), base, [])
    add("no_participation", "本人不参与感知且无人工状态则未知", lambda s:[d.update(participating=False) for m in s["members"] if m["id"]!="m2" for d in m["devices"]], ["unknown","active","unknown","unknown"], [])
    return cases


def summarize(rows):
    good = [r for r in rows if "error" not in r]
    return {"cases":len(rows),"errors":len(rows)-len(good),"state_accuracy":sum(r["state_correct"] for r in good)/(4*len(rows)),"exact_decision_accuracy":sum(r["decision_correct"] for r in good)/len(rows),"unwanted_reminders":sum(r["false_reminders"] for r in good),"latency_median_seconds":round(statistics.median(r["seconds"] for r in rows),3)}


async def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--model",default="qwen2.5:7b"); args=parser.parse_args()
    output = Path(__file__).resolve().parents[1]/"output/release-2026-11-08/evaluation"
    output.mkdir(parents=True,exist_ok=True)
    dataset = cases()
    # Freeze the manually authored expectations before any call. Labels need the team's review.
    (output/"cases.json").write_text(json.dumps(dataset,ensure_ascii=False,indent=2),encoding="utf-8")
    rows=[]
    import hashlib
    (output/"engine-used.py").write_bytes(Path(engine.__file__).read_bytes())
    source_hash=hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()
    for index, case in enumerate(dataset):
        for strategy in (("baseline","optimized") if index%2==0 else ("optimized","baseline")):
            state=sensing.prepare(case["state"]); state["model"]=args.model
            started=time.perf_counter()
            row={"case":case["id"],"strategy":strategy,"partition":case["partition"]}
            try:
                if strategy=="baseline":
                    result=await engine.ollama(state,"根据公约、设备和历史判断成员状态及是否提醒。状态active/resting/unknown，决定引用条款和目标成员。",engine.model_payload(state),engine.Analysis,system_text="你是宿舍协同助手。请根据输入输出指定结构的JSON。")
                else:result=await engine.analyze(state)
                inferred={s.member_id:s.status for s in result.states}
                targets={d.target for d in result.decisions}
                expected=set(case["expected_targets"])
                row.update(output=result.model_dump(),state_correct=sum(inferred.get(k)==v for k,v in case["expected_states"].items()),decision_correct=targets==expected,false_reminders=len(targets-expected))
            except (RuntimeError,ValueError) as exc:row["error"]=str(exc)
            row["seconds"]=round(time.perf_counter()-started,3)
            rows.append(row)
            print(case["id"],strategy,"error" if "error" in row else row["decision_correct"],row["seconds"],flush=True)
            report={"model":args.model,"real_ollama":True,"engine_sha256":source_hash,"label_status":"按已确认业务规则人工编写的探索集；作者已见过案例并用于调试，仍需团队独立复核，非盲测或正式验收集", "comparison":"同一模型、底层案例和解码参数，交替先后顺序；baseline精简单步提示，optimized两阶段推断、最小设备字段、适用公约工具数据与结构化决策分支。统计原始模型输出，不将程序发送前拦截算作模型答对。多余目标计数包含无效成员ID。", "results":rows, "summary":{key:summarize([r for r in rows if r["strategy"]==key]) for key in ("baseline","optimized") if any(r["strategy"]==key for r in rows)}}
            (output/"results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__":asyncio.run(main())
