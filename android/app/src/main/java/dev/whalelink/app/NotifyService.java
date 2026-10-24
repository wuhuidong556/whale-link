package dev.whalelink.app;

import android.content.SharedPreferences;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * 把手机通知推到电脑。需要用户在系统设置里手动授予「通知使用权」。
 * 只推标题/正文/应用名，不读图片、不回点、不自动打开。
 */
public class NotifyService extends NotificationListenerService {

    @Override
    public void onListenerConnected() {
        super.onListenerConnected();
        // 连上就先发一条“就绪”，这样电脑端立刻能确认链路通没通
        try {
            SharedPreferences sp = getSharedPreferences("whale", MODE_PRIVATE);
            String base = sp.getString("url", "");
            String token = sp.getString("token", "");
            if (base.isEmpty() || token.isEmpty()) return;
            JSONObject o = new JSONObject();
            o.put("ts", System.currentTimeMillis() / 1000);
            o.put("app", "鲸鱼娘自检");
            o.put("title", "通知监听已连接");
            o.put("text", "这条只代表系统把通知交给了 App");
            final String body = o.toString();
            new Thread(() -> post(base.replaceAll("/+$", "") + "/api/phone/notify", token, body), "wl-ready").start();
        } catch (Exception ignored) {}
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        try {
            if (sbn == null || sbn.getNotification() == null) return;
            String pkg = sbn.getPackageName();
            if (pkg.equals(getPackageName())) return;                 // 自己发的不推
            if ((sbn.getNotification().flags & android.app.Notification.FLAG_GROUP_SUMMARY) != 0) return;

            SharedPreferences sp = getSharedPreferences("whale", MODE_PRIVATE);
            if (!sp.getBoolean("push_notify", true)) return;
            String base = sp.getString("url", "");
            String token = sp.getString("token", "");
            if (base.isEmpty() || token.isEmpty()) return;

            android.os.Bundle ex = sbn.getNotification().extras;
            String title = ex == null ? "" : str(ex.getCharSequence(android.app.Notification.EXTRA_TITLE));
            String text = ex == null ? "" : str(ex.getCharSequence(android.app.Notification.EXTRA_TEXT));
            if (title.isEmpty() && text.isEmpty()) return;

            String app = pkg;
            try {
                android.content.pm.ApplicationInfo ai =
                        getPackageManager().getApplicationInfo(pkg, 0);
                app = String.valueOf(getPackageManager().getApplicationLabel(ai));
            } catch (Exception ignored) {}

            JSONObject o = new JSONObject();
            o.put("ts", sbn.getPostTime() / 1000);
            o.put("app", app);
            o.put("title", title);
            o.put("text", text);

            final String url = base.replaceAll("/+$", "") + "/api/phone/notify";
            final String body = o.toString();
            final String tk = token;
            new Thread(() -> post(url, tk, body), "wl-notify").start();
        } catch (Exception ignored) {}
    }

    private static String str(CharSequence cs) {
        return cs == null ? "" : cs.toString().trim();
    }

    private void post(String url, String token, String body) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setDoOutput(true);
            c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            c.setRequestProperty("X-WL-Token", token);
            c.setConnectTimeout(5000);
            c.setReadTimeout(8000);
            OutputStream os = c.getOutputStream();
            os.write(body.getBytes("UTF-8"));
            os.close();
            c.getResponseCode();
        } catch (Exception ignored) {}
    }
}
