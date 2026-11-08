package cn.soulband.app

import android.app.*
import android.content.*
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class CollectorService : Service() {
    companion object { @Volatile var collecting = false; private set }
    private val worker = Executors.newSingleThreadScheduledExecutor()
    private lateinit var evidence: PhoneEvidence
    private var base = ""
    private var token = ""
    @Volatile private var running = false
    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == Intent.ACTION_USER_PRESENT) evidence.explicitInteraction()
            if (intent?.action == Intent.ACTION_SCREEN_ON) evidence.resetInactivity()
            // SCREEN_ON alone never counts as a user interaction.
        }
    }

    override fun onCreate() {
        super.onCreate()
        evidence = PhoneEvidence(this)
        val filter = IntentFilter().apply { addAction(Intent.ACTION_SCREEN_ON); addAction(Intent.ACTION_SCREEN_OFF); addAction(Intent.ACTION_USER_PRESENT) }
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, filter, RECEIVER_NOT_EXPORTED)
        else registerReceiver(receiver, filter)
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("collection", "设备状态采集", NotificationManager.IMPORTANCE_LOW))
        manager.createNotificationChannel(NotificationChannel("reminders", "宿舍公约提醒", NotificationManager.IMPORTANCE_DEFAULT))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "pause") { stopSelf(); return START_NOT_STICKY }
        if (running) return START_NOT_STICKY
        base = Store.get(this, "base")
        token = Store.get(this, "token")
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val pause = PendingIntent.getService(this, 1, Intent(this, CollectorService::class.java).setAction("pause"), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val notification = Notification.Builder(this, "collection").setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("宿伴 · 正在采集手机状态").setContentText("仅上传粗粒度状态，点击查看；可随时暂停")
            .setOngoing(true).setContentIntent(open).addAction(Notification.Action.Builder(null, "暂停", pause).build()).build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        else startForeground(1, notification)
        if (base.isBlank() || token.isBlank()) { stopSelf(); return START_NOT_STICKY }
        running = true
        collecting = true
        Store.put(this, "running", "true")
        worker.scheduleWithFixedDelay({ collect() }, 0, 15, TimeUnit.SECONDS)
        return START_NOT_STICKY
    }

    private fun collect() {
        if (!running) return
        try {
            val snapshot = evidence.snapshot(Store.nextSequence(this))
            if (!running) return
            val result = Api.request(base, "/api/mobile/heartbeat", token, snapshot)
            if (result.optBoolean("accepted")) {
                val time = SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date())
                Store.put(this, "status", "最近上报 $time · ${result.optString("signal")}\n亮屏：${snapshot.getBoolean("interactive")} · 锁屏：${snapshot.getBoolean("locked")}\n使用情况数据：${if (snapshot.getBoolean("usage_access")) "可用" else "未授权或不可用"}")
                Store.prefs(this).edit().putLong("last_success", System.currentTimeMillis()).apply()
            }
            if (running) deliverReminders()
        } catch (e: Exception) {
            Store.put(this, "status", "上报失败：${e.message?.take(160)}\n断线或停止上报超过有效期后，电脑端显示未知。")
        }
    }

    private fun deliverReminders() {
        val data = Api.request(base, "/api/mobile/inbox", token)
        val items = data.getJSONArray("items")
        val seen = Store.prefs(this).getStringSet("shown", emptySet())!!.toMutableSet()
        for (i in 0 until items.length()) {
            val item = items.getJSONObject(i)
            val id = item.getString("id")
            // Receipt records client reception, not visibility or user agreement.
            if (!seen.contains("received-$id")) {
                Api.request(base, "/api/reminders/$id/delivered", token, JSONObject().put("device", "phone"))
                seen.add("received-$id")
            }
            if (item.getBoolean("read")) getSystemService(NotificationManager::class.java).cancel("soulband-$id", 2)
            if (!item.getBoolean("read") && !seen.contains(id)) {
                val open = PendingIntent.getActivity(this, id.hashCode(), Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
                val n = Notification.Builder(this, "reminders").setSmallIcon(android.R.drawable.ic_dialog_info)
                    .setContentTitle("宿伴 · 公约提醒").setContentText(item.getString("message"))
                    .setStyle(Notification.BigTextStyle().bigText(item.getString("message")))
                    .setContentIntent(open).setAutoCancel(true).build()
                val manager = getSystemService(NotificationManager::class.java)
                if (manager.areNotificationsEnabled()) {
                    manager.notify("soulband-$id", 2, n)
                    seen.add(id)
                }
            }
        }
        Store.prefs(this).edit().putStringSet("shown", seen.takeLastSafe(100)).apply()
    }

    private fun Set<String>.takeLastSafe(count: Int): Set<String> = toList().takeLast(count).toSet()

    override fun onDestroy() {
        running = false
        collecting = false
        Store.put(this, "running", "false")
        Store.put(this, "status", "采集已暂停。如网络不可达，宿主数据将在有效期后变为未知。")
        runCatching { unregisterReceiver(receiver) }
        worker.execute {
            runCatching {
                if (base.isNotEmpty() && token.isNotEmpty()) Api.request(base, "/api/mobile/pause", token, JSONObject().put("sequence", Store.nextSequence(this)))
            }
        }
        worker.shutdown()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
    override fun onBind(intent: Intent?): IBinder? = null
}
