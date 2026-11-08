package cn.soulband.app

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.View
import android.widget.*
import org.json.JSONObject
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var root: LinearLayout
    private lateinit var host: EditText
    private lateinit var code: EditText
    private lateinit var allowHttp: CheckBox
    private lateinit var status: TextView
    private lateinit var binding: TextView
    private lateinit var permissions: TextView
    private lateinit var inbox: LinearLayout
    private val purple = Color.rgb(123, 101, 206)
    private val muted = Color.rgb(125, 118, 144)
    private var loadingInbox = false
    private val ticker = object : Runnable {
        override fun run() { updateStatus(); handler.postDelayed(this, 3000) }
    }

    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    private fun text(value: String, size: Float = 14f, color: Int = muted) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color); setLineSpacing(dp(4).toFloat(), 1f)
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) }
    }
    private fun shape(color: Int, radius: Int = 18) = GradientDrawable().apply { setColor(color); cornerRadius = dp(radius).toFloat() }
    private fun card(title: String): LinearLayout {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = shape(Color.WHITE)
            setPadding(dp(20), dp(20), dp(20), dp(14))
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(18) }
        }
        box.addView(text(title, 18f, Color.rgb(68, 57, 88)).apply { setTypeface(null, Typeface.BOLD) })
        root.addView(box)
        return box
    }
    private fun button(box: LinearLayout, title: String, secondary: Boolean = false, action: () -> Unit) {
        box.addView(Button(this).apply {
            text = title; textSize = 14f; isAllCaps = false
            setTextColor(if (secondary) purple else Color.WHITE)
            background = shape(if (secondary) Color.rgb(242, 237, 251) else purple, 12)
            layoutParams = LinearLayout.LayoutParams(-1, dp(48)).apply { bottomMargin = dp(12) }
            setOnClickListener { action() }
        })
    }
    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.rgb(246, 247, 251)
        val scroll = ScrollView(this).apply { setBackgroundColor(Color.rgb(246, 247, 251)); isFillViewport = true }
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(24), dp(20), dp(24)) }
        scroll.addView(root)
        setContentView(scroll)
        scroll.setOnApplyWindowInsetsListener { _, inset ->
            root.setPadding(dp(20), dp(20) + inset.systemWindowInsetTop, dp(20), dp(24) + inset.systemWindowInsetBottom)
            inset
        }
        root.addView(text("SOULBAND · ANDROID", 11f, purple))
        root.addView(text("宿伴，随身的一点默契。", 27f, Color.rgb(58, 48, 78)).apply { setTypeface(null, Typeface.BOLD) })
        root.addView(text("原生业务与采集测试版 v0.4\n在你授权后，只传达必要的设备状态。"))
        val business = card("寝室业务")
        button(business, "进入公约、协商与公共事务") {
            if (Store.get(this, "token").isBlank()) toast("请先用电脑提供的配对码绑定本人身份")
            else startActivity(Intent(this, BusinessActivity::class.java))
        }

        val connect = card("01  连接我们的寝室")
        connect.addView(text("手机与电脑连接同一局域网，在电脑为你的身份生成一次性配对码。"))
        host = EditText(this).apply { hint = "宿主地址，如 http://局域网IP:8765"; setText(Store.get(this@MainActivity, "base")); inputType = 17; setSingleLine() }
        connect.addView(host, LinearLayout.LayoutParams(-1, dp(58)))
        allowHttp = CheckBox(this).apply { text = "允许局域网 HTTP 测试（传输未加密，仅用于样例）"; textSize = 12f; isChecked = Store.prefs(this@MainActivity).getBoolean("allow_http", false) }
        connect.addView(allowHttp)
        code = EditText(this).apply { hint = "电脑显示的 10 位配对码"; setSingleLine(); filters = arrayOf(android.text.InputFilter.LengthFilter(10)) }
        connect.addView(code, LinearLayout.LayoutParams(-1, dp(58)))
        button(connect, "使用配对码绑定这台手机") { pair() }
        binding = text(""); connect.addView(binding)

        val access = card("02  由你决定是否授权")
        access.addView(text("使用情况访问权限用于读取必要交互事件。不会上传应用名称、使用明细、屏幕或按键内容。单纯亮屏不会被当作明确操作。"))
        permissions = text(""); access.addView(permissions)
        button(access, "打开使用情况访问权限", true) {
            runCatching { startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS, Uri.parse("package:$packageName"))) }
                .onFailure { toast("请到系统设置中为宿伴开启使用情况访问权限") }
        }
        button(access, "允许提醒通知", true) {
            if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 12)
            else startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
        }

        val collection = card("03  手机状态，由你掌控")
        collection.addView(text("采集开启时显示常驻服务通知，可从这里或通知栏暂停。每次上报新采样，过期数据不补装成当前状态。"))
        status = text(""); collection.addView(status)
        button(collection, "开始采集并接收提醒") {
            if (Store.get(this, "token").isBlank()) toast("请先连接并配对")
            else runCatching { startForegroundService(Intent(this, CollectorService::class.java)) }.onFailure { toast(it.message ?: "无法启动采集服务") }
        }
        button(collection, "暂停采集", true) {
            val stopped = stopService(Intent(this, CollectorService::class.java))
            if (!stopped) Store.put(this, "running", "false")
            updateStatus()
            toast("已请求暂停；离线时电脑端会在数据过期后显示未知")
        }
        collection.addView(text("后台定时会受系统省电与网络影响，不能保证屏幕关闭时每次即时上报。最近上报时间可供检查。", 12f))

        val messages = card("04  给我的公约提醒")
        messages.addView(text("仅接收发给已绑定成员且目标包含手机的提醒；请在电脑端将通知偏好设为“手机”或“两端”。"))
        button(messages, "刷新我的提醒", true) { loadInbox() }
        inbox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        messages.addView(inbox)
        root.addView(text("公约、诉求、审批、事务和私密表达可从顶部寝室业务进入。\n设备活动是提示依据，不是已经睡着或违反公约的证据。", 12f))
    }

    private fun pair() {
        val address = host.text.toString()
        val pairing = code.text.toString().trim().uppercase()
        val allow = allowHttp.isChecked
        if (pairing.length != 10) { toast("请输入电脑显示的 10 位配对码"); return }
        stopService(Intent(this, CollectorService::class.java))
        binding.text = "正在验证连接与配对码…"
        worker.execute {
            try {
                val base = Api.validateBase(address, allow)
                val result = Api.request(base, "/api/mobile/pair", body = JSONObject().put("code", pairing).put("installation_id", Store.installation(this)))
                val saved = Store.prefs(this).edit().putString("base", base).putString("token", result.getString("token"))
                    .putString("member_name", result.getString("member_name")).putString("member_id", result.getString("member_id"))
                    .putBoolean("allow_http", allow).putLong("sequence", 0).putStringSet("shown", emptySet()).commit()
                check(saved) { "无法保存配对凭据，请重新配对" }
                runOnUiThread { code.setText(""); updateStatus(); toast("配对成功，请授权并主动开启采集") }
            } catch (e: Exception) { runOnUiThread { binding.text = "配对失败：${e.message}" } }
        }
    }

    private fun updateStatus() {
        if (!::status.isInitialized) return
        binding.text = if (Store.get(this, "token").isEmpty()) "尚未配对" else "已绑定：${Store.get(this, "member_name")}\n${Store.get(this, "base")}"
        val notify = getSystemService(android.app.NotificationManager::class.java).areNotificationsEnabled()
        permissions.text = "使用情况访问：${if (PhoneEvidence.hasAccess(this)) "已授权" else "未授权"}\n通知：${if (notify) "已允许" else "未允许，无法显示提醒通知"}"
        status.text = "${if (CollectorService.collecting) "采集服务已请求开启" else "采集未开启 / 已暂停"}\n${Store.get(this, "status").ifEmpty { "开启后显示最近上报与设备状态。" }}"
    }

    private fun loadInbox() {
        if (loadingInbox || Store.get(this, "token").isEmpty()) return
        loadingInbox = true
        val base = Store.get(this, "base")
        val token = Store.get(this, "token")
        worker.execute {
            try {
                val items = Api.request(base, "/api/mobile/inbox", token).getJSONArray("items")
                runOnUiThread {
                    inbox.removeAllViews()
                    if (items.length() == 0) inbox.addView(text("暂时没有发给手机的提醒。"))
                    for (i in items.length()-1 downTo 0) {
                        val item = items.getJSONObject(i)
                        inbox.addView(text("${item.getString("time")} · ${if (item.getBoolean("read")) "已读" else "未读"}\n${item.getString("message")}", 14f, Color.rgb(103, 84, 136)))
                        if (!item.getBoolean("read")) button(inbox, "我已读到", true) {
                            worker.execute {
                                runCatching { Api.request(base, "/api/mobile/inbox/${item.getString("id")}/read", token, JSONObject()) }
                                    .onSuccess { runOnUiThread { loadInbox() } }
                                    .onFailure { runOnUiThread { toast(it.message ?: "标记失败") } }
                            }
                        }
                    }
                    loadingInbox = false
                }
            } catch (e: Exception) { runOnUiThread { inbox.removeAllViews(); inbox.addView(text("获取失败：${e.message}")); loadingInbox = false } }
        }
    }

    override fun onUserInteraction() {
        super.onUserInteraction()
        Store.prefs(this).edit().putLong("own_touch", System.currentTimeMillis()).apply()
    }
    override fun onResume() { super.onResume(); handler.post(ticker); loadInbox() }
    override fun onPause() { handler.removeCallbacks(ticker); super.onPause() }
    override fun onDestroy() { handler.removeCallbacks(ticker); worker.shutdown(); super.onDestroy() }
}
