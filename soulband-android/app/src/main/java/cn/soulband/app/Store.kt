package cn.soulband.app

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URI
import java.util.UUID

object Store {
    fun prefs(c: Context) = c.applicationContext.getSharedPreferences("soulband", Context.MODE_PRIVATE)
    fun get(c: Context, key: String) = prefs(c).getString(key, "") ?: ""
    fun put(c: Context, key: String, value: String) { prefs(c).edit().putString(key, value).apply() }
    @Synchronized fun nextSequence(c: Context): Long {
        val p = prefs(c)
        val n = p.getLong("sequence", 0) + 1
        check(p.edit().putLong("sequence", n).commit()) { "无法保存采样序号" }
        return n
    }
    fun installation(c: Context): String {
        if (get(c, "installation").isEmpty()) put(c, "installation", UUID.randomUUID().toString())
        return get(c, "installation")
    }
}

object Api {
    fun validateBase(value: String, allowHttp: Boolean): String {
        val uri = URI(value.trim().trimEnd('/'))
        require(uri.scheme in listOf("http", "https") && !uri.host.isNullOrEmpty() && uri.userInfo == null && uri.query == null && uri.fragment == null && uri.path.orEmpty() in listOf("", "/")) { "请输入 http(s)://宿主机地址:端口，不要附带路径或凭据" }
        if (uri.scheme == "http") {
            require(allowHttp) { "局域网 HTTP 测试需要明确勾选同意" }
            require(InetAddress.getAllByName(uri.host).all { it.isSiteLocalAddress || it.isLoopbackAddress || it.isLinkLocalAddress }) { "HTTP 测试只允许局域网地址；外部服务请使用 HTTPS" }
        }
        return uri.toString().trimEnd('/')
    }
    fun request(base: String, path: String, token: String = "", body: JSONObject? = null, method: String = if (body == null) "GET" else "POST"): JSONObject {
        val connection = URI(base + path).toURL().openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 6000
            connection.readTimeout = 180000
            connection.instanceFollowRedirects = false
            connection.setRequestProperty("Accept", "application/json")
            if (token.isNotEmpty()) connection.setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                connection.requestMethod = method
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            if (code !in 200..299) {
                val detail = runCatching { JSONObject(text).optString("detail", "HTTP $code") }.getOrDefault("HTTP $code")
                throw IllegalStateException(detail.take(200))
            }
            return JSONObject(text)
        } finally { connection.disconnect() }
    }
}
