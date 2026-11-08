package cn.soulband.app

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Color
import android.os.Bundle
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors

/** Native business UI. All mutations go through the same authenticated host API. */
class BusinessActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private lateinit var root: LinearLayout
    private var state = JSONObject()
    private var page = "概览"
    private var busy = false
    private var privateReply = ""
    private val owner get() = Store.get(this, "member_id")
    private val purple = Color.rgb(123, 101, 206)
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    private fun array(key: String) = state.optJSONArray(key) ?: JSONArray()
    private fun objects(a: JSONArray): List<JSONObject> = (0 until a.length()).map { a.getJSONObject(it) }
    private fun name(id: String) = objects(array("members")).firstOrNull { it.getString("id") == id }?.getString("name") ?: id
    private fun recordStatus(value: String) = mapOf("active" to "已生效", "draft" to "待审核", "archived" to "已归档", "revoked" to "已撤销", "expired" to "已到期", "pending" to "待审批", "approved" to "已同意", "rejected" to "已拒绝", "public" to "寝室公开", "private" to "仅本人")[value] ?: value
    private fun activityStatus(value: String) = mapOf("active" to "有活动", "resting" to "可能休息", "unknown" to "未知", "idle" to "持续无操作", "away" to "短暂无操作", "simulation" to "人工模拟", "windows_live" to "Windows 实测", "android_live" to "Android 实测")[value] ?: value
    private fun label(value: String, size: Float = 15f) = TextView(this).apply { text = value; textSize = size; setTextColor(Color.rgb(65, 55, 80)); setPadding(0, dp(10), 0, dp(10)); setTextIsSelectable(true) }
    private fun note(value: String) { root.addView(label(value)) }
    private fun button(title: String, action: () -> Unit) { root.addView(Button(this).apply { text = title; isAllCaps = false; setTextColor(purple); setOnClickListener { if (!busy) action() } }) }
    private fun heading(value: String) { root.addView(label(value, 21f)) }
    private fun call(path: String, body: JSONObject? = null, method: String = if (body == null) "GET" else "POST") = Api.request(Store.get(this, "base"), "/api$path", Store.get(this, "token"), body, method)
    private fun json(vararg pairs: Pair<String, Any?>) = JSONObject().apply { pairs.forEach { put(it.first, it.second ?: JSONObject.NULL) } }
    private fun toast(value: String) = Toast.makeText(this, value, Toast.LENGTH_LONG).show()
    private fun execute(task: () -> JSONObject, done: (JSONObject) -> Unit = { reload() }) {
        if (busy) return
        busy = true
        title = "宿伴 · 正在处理"
        worker.execute {
            try { val result = task(); runOnUiThread { busy = false; title = "宿伴 · $page"; if (!isFinishing && !isDestroyed) done(result) } }
            catch (e: Exception) { runOnUiThread { busy = false; title = "宿伴 · $page"; if (!isFinishing && !isDestroyed) AlertDialog.Builder(this).setTitle("操作未完成").setMessage(e.message).setPositiveButton("知道了", null).show() } }
        }
    }
    private fun mutate(path: String, body: JSONObject = JSONObject(), method: String = "POST") { execute({ call(path, body, method) }) }
    private fun reload() { execute({ call("/state") }) { state = it; render() } }
    private fun choose(title: String, values: List<Pair<String, String>>, action: (String) -> Unit) {
        if (values.isEmpty()) { toast("暂时没有可选记录"); return }
        AlertDialog.Builder(this).setTitle(title).setItems(values.map { it.second }.toTypedArray()) { _, which -> action(values[which].first) }.setNegativeButton("取消", null).show()
    }
    private fun form(title: String, fields: List<Pair<String, String>>, action: (List<String>) -> Unit) {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(10), dp(20), dp(10)) }
        val inputs = fields.map { (hint, value) ->
            box.addView(label(hint, 13f))
            EditText(this).apply { setText(value); minLines = if (hint.contains("内容") || hint.contains("表达") || hint.contains("条款")) 3 else 1; maxLines = 8; box.addView(this) }
        }
        val scroll = ScrollView(this).apply { addView(box) }
        val dialog = AlertDialog.Builder(this).setTitle(title).setView(scroll).setPositiveButton("确认", null).setNegativeButton("取消", null).create()
        dialog.setOnShowListener { dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { action(inputs.map { it.text.toString().trim() }); dialog.dismiss() } }
        dialog.show()
    }
    private fun preview(title: String, text: String, confirmed: ((String) -> Unit)? = null) {
        if (confirmed == null) AlertDialog.Builder(this).setTitle(title).setMessage(text).setPositiveButton("知道了", null).show()
        else form(title, listOf("检查将提交的内容" to text)) { confirmed(it[0]) }
    }

    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); reload() }
    private fun render() {
        val scroll = ScrollView(this).apply { setBackgroundColor(Color.rgb(247, 245, 251)) }
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(24), dp(20), dp(32)) }
        scroll.addView(root); setContentView(scroll)
        scroll.setOnApplyWindowInsetsListener { _, inset -> root.setPadding(dp(20), dp(20) + inset.systemWindowInsetTop, dp(20), dp(24) + inset.systemWindowInsetBottom); inset }
        heading("${name(owner)}的寝室 · $page")
        note(if (state.optString("mode") == "demo") "演示模拟 · 生成与判断不是真实大模型" else "Ollama · 真实模型模式（调用失败不会改用模拟）")
        val tabs = Spinner(this).apply {
            val items = listOf("概览", "诉求与公约", "临时安排", "反馈协商", "公共事务", "模型助手", "私密表达")
            adapter = ArrayAdapter(this@BusinessActivity, android.R.layout.simple_spinner_dropdown_item, items)
            setSelection(items.indexOf(page))
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onNothingSelected(parent: AdapterView<*>?) {}
                override fun onItemSelected(parent: AdapterView<*>?, view: android.view.View?, position: Int, id: Long) { if (page != items[position]) { page = items[position]; privateReply = ""; render() } }
            }
        }; root.addView(tabs)
        button("刷新共享记录") { reload() }
        when (page) {
            "概览" -> overview()
            "诉求与公约" -> covenant()
            "临时安排" -> adjustments()
            "反馈协商" -> feedback()
            "公共事务" -> affairs()
            "模型助手" -> assistant()
            "私密表达" -> privateHelp()
        }
    }
    private fun overview() {
        val analysis = state.optJSONObject("analysis")
        objects(array("members")).forEach { m ->
            val activity = analysis?.optJSONArray("states")?.let { objects(it).firstOrNull { a -> a.getString("member_id") == m.getString("id") } }
            heading(m.getString("name") + " · " + activityStatus(activity?.optString("status") ?: "待判断"))
            note(activity?.optString("reason") ?: "尚无当前判断")
            objects(m.getJSONArray("devices")).forEach { d -> note("${d.getString("label")} · ${activityStatus(d.optString("signal"))} · ${activityStatus(d.optString("source", "simulation"))} · ${if (d.optBoolean("participating", true)) "参与" else "不参与"}") }
        }
        button("现在进行活动与提醒判断") { mutate("/analyze") }
        button("纠正本人状态与选填活动") {
            choose("本人状态", listOf("active" to "我还在活动", "resting" to "我在休息", "unknown" to "暂不确定", "clear" to "清除人工状态")) { status ->
                form("具体活动（选填，有效 30 分钟）", listOf("活动" to "")) { mutate("/manual", json("status" to status, "activity" to it[0]), "PUT") }
            }
        }
        button("设置通知设备") { choose("通知策略", listOf("all" to "两端", "active" to "优先活动设备", "pc" to "电脑", "phone" to "手机")) { mutate("/notification-preference", json("strategy" to it), "PUT") } }
        button("修改本人昵称") { form("本人昵称", listOf("昵称" to name(owner))) { mutate("/profile", json("name" to it[0]), "PUT") } }
        button("选择参与感知的设备") { choose("参与设备", listOf("both" to "电脑和手机", "pc" to "仅电脑", "phone" to "仅手机", "none" to "均不参与")) { v -> mutate("/participation", json("devices" to JSONArray(if (v == "both") listOf("pc", "phone") else if (v == "none") emptyList<String>() else listOf(v))), "PUT") } }
        heading("我的提醒")
        objects(array("reminders")).reversed().forEach { r ->
            note("${r.optString("time")} · ${r.optString("message")}\n${if (r.optBoolean("read")) "成员已读" else r.optString("status")}")
            if (!r.optBoolean("read")) button("我已读到 · ${r.getString("id")}") { mutate("/reminders/${r.getString("id")}/read") }
        }
    }
    private fun covenant() {
        button("整理我的自然语言诉求") {
            form("原始需求", listOf("内容" to "")) { values -> execute({ call("/needs/prepare", json("text" to values[0])) }) { prepared ->
                preview("检查需求卡；${prepared.optJSONArray("questions")}", prepared.getString("text")) { checked ->
                    choose("需求公开范围", listOf("public" to "寝室公开并参与公约", "private" to "仅本人保存")) { visibility -> mutate("/needs", json("text" to checked, "visibility" to visibility)) }
                }
            } }
        }
        heading("需求记录")
        objects(array("demands")).forEach { note("${name(it.getString("member_id"))} · ${recordStatus(it.optString("visibility", "public"))}\n${it.getString("text")}") }
        button("综合公开需求生成公约草案") { mutate("/proposals/generate") }
        val versions = objects(array("proposals"))
        versions.reversed().forEach { p ->
            heading("v${p.getInt("version")} · ${p.getString("title")} · ${recordStatus(p.getString("status"))}")
            objects(p.getJSONArray("clauses")).forEach { note("${it.getString("title")}\n${it.getString("text")}\n${it.optString("start", "")} — ${it.optString("end", "")}") }
            note("已确认：${p.getJSONArray("approvals")}\n待协商：${p.getJSONArray("conflicts")}")
            if (p == versions.lastOrNull()) {
                button("本人确认此版本 v${p.getInt("version")}") { mutate("/proposals/${p.getString("id")}/approve") }
                button("人工修订为新版本（需重新确认）") { revise(p) }
            }
        }
        button("本人同意撤销当前公约（全员同意才撤销）") { mutate("/covenant/revoke-request") }
    }
    private fun revise(p: JSONObject) {
        val clauses = objects(p.getJSONArray("clauses"))
        val fields = mutableListOf("公约标题" to p.getString("title"))
        clauses.forEach { c -> fields.add("条款：${c.getString("title")}" to c.getString("text")); if (c.getString("kind") == "quiet") { fields.add("开始 HH:MM" to c.getString("start")); fields.add("结束 HH:MM" to c.getString("end")) } }
        fields.add("截止时间 YYYY-MM-DDTHH:MM（可留空）" to if (p.isNull("valid_until")) "" else p.optString("valid_until"))
        fields.add("待解决冲突（每行一条，解决后才清空）" to (0 until p.getJSONArray("conflicts").length()).joinToString("\n") { p.getJSONArray("conflicts").getString(it) })
        form("修订仅生成待审核新版本", fields) { values ->
            var i = 1
            val edited = JSONArray()
            clauses.forEach { old -> val c = JSONObject(old.toString()); c.put("text", values[i++]); if (c.getString("kind") == "quiet") { c.put("start", values[i++]); c.put("end", values[i++]) }; edited.put(c) }
            mutate("/proposals/${p.getString("id")}/revise", json("title" to values[0], "valid_until" to values[i].ifBlank { null }, "clauses" to edited, "conflicts" to JSONArray(values.last().lines().filter { it.isNotBlank() })))
        }
    }
    private fun adjustments() {
        note("全员批准后，仅在指定业务时间暂停选中静音条款，最长 24 小时；到期自动恢复。")
        val p = objects(array("proposals")).firstOrNull { it.getString("id") == state.optString("active_id") }
        button("申请临时调整") {
            val clauses = p?.let { objects(it.getJSONArray("clauses")).filter { c -> c.getString("kind") == "quiet" } } ?: emptyList()
            choose("选择静音条款", clauses.map { it.getString("id") to it.getString("title") }) { clause ->
                val clock = state.getJSONObject("clock")
                form("临时安排", listOf("原因（公开）" to "", "开始 YYYY-MM-DDTHH:MM" to "${clock.getString("date")}T${clock.getString("time")}", "结束 YYYY-MM-DDTHH:MM" to "")) { mutate("/adjustments", json("clause_id" to clause, "reason" to it[0], "starts" to it[1], "ends" to it[2])) }
            }
        }
        objects(array("adjustments")).forEach { a ->
            heading(a.getString("reason")); note("${a.getString("starts")} 至 ${a.getString("ends")}\n${a.getString("status")} · ${a.getJSONArray("approvals")}")
            if (a.getString("status") == "pending") { button("同意安排 ${a.getString("id")}") { mutate("/adjustments/${a.getString("id")}/vote", json("approve" to true)) }; button("拒绝安排 ${a.getString("id")}") { mutate("/adjustments/${a.getString("id")}/vote", json("approve" to false)) } }
        }
    }
    private fun feedback() {
        button("原提醒已改善 / 仍希望安静") {
            choose("涉及的其他成员", objects(array("members")).filter { it.getString("id") != owner }.map { it.getString("id") to it.getString("name") }) { target ->
                choose("本人实际回访", listOf("improved" to "已改善", "still" to "仍希望安静")) { result -> mutate("/feedback", json("target" to target, "result" to result)) }
            }
        }
        button("其他异议：先预览中性内容") {
            choose("问题类型", listOf("quiet" to "安静", "duties" to "分工", "other" to "其他")) { category ->
                form("仅将确认后的中性内容公开", listOf("原始表达" to "")) { values -> execute({ call("/opinions/preview", json("category" to category, "text" to values[0])) }) { r ->
                    preview("检查将公开的内容", r.getString("neutral")) { mutate("/opinions", json("category" to category, "neutral" to it)) }
                } }
            }
        }
        objects(array("negotiations")).forEach { n ->
            heading(n.getString("title")); note(n.getString("status")); note(n.optString("suggestion", "还没有调整建议"))
            button("整理协商建议 ${n.getString("id")}") { mutate("/negotiations/${n.getString("id")}/suggest") }
        }
    }
    private fun affairs() {
        button("创建公共任务") { choose("负责人", objects(array("members")).map { it.getString("id") to it.getString("name") }) { who -> form("任务", listOf("内容" to "", "到期日期" to state.getJSONObject("clock").getString("date"), "完成标准" to "")) { mutate("/tasks", json("title" to it[0], "owner" to who, "due" to it[1], "standard" to it[2])) } } }
        button("按成员顺序排班") { form("轮值", listOf("开始 YYYY-MM-DD" to state.getJSONObject("clock").getString("date"), "天数 1—31" to "7")) { values ->
            val days = values[1].toIntOrNull(); if (days == null) toast("天数需为整数") else mutate("/tasks/rota", json("start" to values[0], "days" to days, "members" to JSONArray(objects(array("members")).map { it.getString("id") })))
        } }
        heading("任务与值日")
        val tasks = objects(array("tasks"))
        tasks.forEach { t ->
            note("${t.getString("title")} · ${name(t.getString("owner"))}\n${t.getString("due")} · ${if (t.getBoolean("done")) "已完成" else "待完成"}\n${t.optString("standard")}")
            if (t.getString("owner") == owner) {
                button("切换完成状态 ${t.getString("id")}") { mutate("/tasks/${t.getString("id")}/toggle") }
                if (!t.getBoolean("done")) button("申请互换 ${t.getString("id")}") { choose("对方未完成任务", tasks.filter { it.getString("owner") != owner && !it.getBoolean("done") }.map { it.getString("id") to "${name(it.getString("owner"))} · ${it.getString("title")} · ${it.getString("due")}" }) { mutate("/swaps", json("task_id" to t.getString("id"), "other_task_id" to it)) } }
            }
        }
        objects(array("swaps")).forEach { s -> note("${name(s.getString("requester"))} → ${name(s.getString("target"))} · ${s.getString("status")}"); if (s.getString("target") == owner && s.getString("status") == "pending") {
            button("同意互换 ${s.getString("id")}") { mutate("/swaps/${s.getString("id")}/vote", json("approve" to true)) }; button("拒绝互换 ${s.getString("id")}") { mutate("/swaps/${s.getString("id")}/vote", json("approve" to false)) }
        } }
        heading("公共费用（仅记账，无支付）")
        button("记录账单与参与人") {
            val people = objects(array("members")); val checked = BooleanArray(people.size) { true }
            AlertDialog.Builder(this).setTitle("选择参与分账的成员").setMultiChoiceItems(people.map { it.getString("name") }.toTypedArray(), checked) { _, n, v -> checked[n] = v }.setPositiveButton("下一步") { _, _ ->
                form("记账", listOf("名称" to "", "金额（元）" to "")) { mutate("/bills", json("title" to it[0], "amount" to it[1], "participants" to JSONArray(people.filterIndexed { i, _ -> checked[i] }.map { it.getString("id") }))) }
            }.setNegativeButton("取消", null).show()
        }
        objects(array("bills")).reversed().forEach { b ->
            note("${b.getString("title")} · ${b.getInt("total_cents")} 分\n" + objects(b.getJSONArray("shares")).joinToString("\n") { "${name(it.getString("member_id"))}：${it.getInt("cents")} 分" })
            if (objects(b.getJSONArray("shares")).any { it.getString("member_id") == owner }) button("确认本人已结清 ${b.getString("id")}") { mutate("/bills/${b.getString("id")}/settle") }
        }
    }
    private fun assistant() {
        note("受控工具先查真实记录；模型建议完成任务后，需要本人再次确认。")
        button("查询公约 / 值日 / 费用") { form("向模型提问", listOf("内容" to "")) { values -> execute({ call("/assistant", json("text" to values[0])) }) { r ->
            if (r.has("confirm_task_id")) AlertDialog.Builder(this).setTitle("确认任务更新").setMessage(r.getString("reply")).setPositiveButton("确认完成") { _, _ -> mutate("/tasks/${r.getString("confirm_task_id")}/complete") }.setNegativeButton("取消", null).show()
            else preview("${r.optString("tool")} 工具结果", r.getString("reply"))
        } } }
    }
    private fun privateHelp() {
        note("原文仅用于本次整理，不保存到业务数据库；模型会收到输入。私密结果不会自动发送。离开页面清除本地显示。")
        button("整理我的私密表达") { choose("语气", listOf("gentle" to "温和", "friendly" to "友好", "direct" to "直接")) { style ->
            form("私密表达", listOf("内容" to "")) { values -> execute({ call("/private", json("text" to values[0], "style" to style)) }) { privateReply = it.getString("reply"); render() } }
        } }
        if (privateReply.isNotEmpty()) { note(privateReply); button("本人检查后转为公开诉求") { preview("请确认将公开的内容", privateReply) { mutate("/needs", json("text" to it.take(1500), "visibility" to "public")) } }; button("清除本次私密结果") { privateReply = ""; render() } }
    }
    override fun onStop() { privateReply = ""; if (::root.isInitialized && page == "私密表达") render(); super.onStop() }
    override fun onUserInteraction() { super.onUserInteraction(); Store.prefs(this).edit().putLong("own_touch", System.currentTimeMillis()).apply() }
    override fun onDestroy() { worker.shutdown(); super.onDestroy() }
}
