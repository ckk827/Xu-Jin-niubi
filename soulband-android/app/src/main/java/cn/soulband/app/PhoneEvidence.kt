package cn.soulband.app

import android.app.AppOpsManager
import android.app.KeyguardManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.os.PowerManager
import android.os.Process
import android.os.SystemClock
import org.json.JSONObject

class PhoneEvidence(private val context: Context) {
    private var inactiveSince: Long? = null
    private var lastQuery = 0L
    private var lastInteraction = 0L

    companion object {
        fun hasAccess(c: Context): Boolean = runCatching {
            c.getSystemService(AppOpsManager::class.java)
                .unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), c.packageName) == AppOpsManager.MODE_ALLOWED
        }.getOrDefault(false)
    }

    @Synchronized fun explicitInteraction() { lastInteraction = System.currentTimeMillis(); inactiveSince = null }
    @Synchronized fun resetInactivity() { inactiveSince = null }

    @Synchronized fun snapshot(sequence: Long): JSONObject {
        val now = System.currentTimeMillis()
        val elapsed = SystemClock.elapsedRealtime()
        val interactive = context.getSystemService(PowerManager::class.java).isInteractive
        val locked = context.getSystemService(KeyguardManager::class.java).isKeyguardLocked
        if (!interactive || locked) {
            if (inactiveSince == null) inactiveSince = elapsed
        } else inactiveSince = null

        var available = hasAccess(context)
        if (available) {
            available = runCatching {
                val usage = context.getSystemService(UsageStatsManager::class.java)
                val events = usage.queryEvents(maxOf(now - 120000, lastQuery - 1000), now) ?: return@runCatching false
                val event = UsageEvents.Event()
                while (events.hasNextEvent()) {
                    events.getNextEvent(event)
                    // Deliberately never read packageName, className, extras or app usage details.
                    if (event.eventType == UsageEvents.Event.USER_INTERACTION || event.eventType == UsageEvents.Event.KEYGUARD_HIDDEN) {
                        if (event.timeStamp <= now && event.timeStamp > lastInteraction) {
                            lastInteraction = event.timeStamp
                            inactiveSince = if (!interactive || locked) elapsed else null
                        }
                    }
                }
                lastQuery = now
                true
            }.getOrDefault(false)
        }
        val ownTouch = Store.prefs(context).getLong("own_touch", 0)
        lastInteraction = maxOf(lastInteraction, ownTouch)
        val age = if (lastInteraction in 1..now && now - lastInteraction <= 604800000) (now - lastInteraction) / 1000.0 else null
        return JSONObject().put("sequence", sequence).put("sampled_at_ms", now)
            .put("interactive", interactive).put("locked", locked).put("usage_access", available)
            .put("interaction_age_seconds", age ?: JSONObject.NULL)
            .put("inactive_seconds", inactiveSince?.let { (elapsed - it) / 1000.0 } ?: 0.0)
    }
}
