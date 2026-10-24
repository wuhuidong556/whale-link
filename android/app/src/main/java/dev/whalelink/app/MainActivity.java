package dev.whalelink.app;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.CookieManager;
import android.widget.Toast;

/** 一个壳：把 whale-link 的网页装进 WebView，首次启动填服务器地址。 */
public class MainActivity extends Activity {

    private static final int REQ_DIR = 21;
    private static final int REQ_NOTIF = 22;

    private WebView web;
    private boolean wantChat = false;
    private SharedPreferences sp;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        sp = getSharedPreferences("whale", MODE_PRIVATE);

        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.RECORD_AUDIO}, 1);
        }
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIF);
        }

        web = new WebView(this);
        setContentView(web, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView v, String u) {
                // 页面把 cookie 种上以后，直接从 cookie 里取令牌，不用等 JS 传
                try {
                    String ck = CookieManager.getInstance().getCookie(u);
                    if (ck != null) {
                        for (String part : ck.split(";")) {
                            String t = part.trim();
                            if (t.startsWith("wl_token=")) {
                                String tok = t.substring("wl_token=".length());
                                if (!tok.isEmpty()) sp.edit().putString("token", tok).apply();
                            }
                        }
                    }
                } catch (Throwable ignored) {}
                if (wantChat) {
                    wantChat = false;
                    web.evaluateJavascript(
                            "(function(){var i=document.getElementById('say');if(i)i.focus();})()", null);
                }
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> request.grant(request.getResources()));
            }
        });
        web.addJavascriptInterface(new Bridge(), "Native");

        wantChat = getIntent() != null && getIntent().getBooleanExtra("chat", false);
        String url = sp.getString("url", "");
        if (url.isEmpty()) {
            web.loadUrl("file:///android_asset/setup.html");
        } else {
            rememberToken(url);
            // 每次带一个构建号，避免 WebView 拿旧页面
            String u2 = url + (url.contains("?") ? "&" : "?") + "v=9";
            web.loadUrl(u2);
        }
    }

    /** 从 url 里抽出 ?t= 存起来，给后台同步用。 */
    private void rememberToken(String url) {
        try {
            Uri u = Uri.parse(url);
            String t = u.getQueryParameter("t");
            if (t != null && !t.isEmpty()) sp.edit().putString("token", t).apply();
        } catch (Exception ignored) {}
    }

    class Bridge {
        @JavascriptInterface
        public String getUrl() { return sp.getString("url", ""); }

        @JavascriptInterface
        public void saveUrl(String url) {
            if (url == null) return;
            String u = url.trim();
            if (!u.startsWith("http")) u = "http://" + u;
            if (!u.endsWith("/")) u = u + "/";
            final String target = u;
            sp.edit().putString("url", target).apply();
            rememberToken(target);
            runOnUiThread(() -> web.loadUrl(target));
        }

        @JavascriptInterface
        public void reset() {
            sp.edit().remove("url").apply();
            runOnUiThread(() -> web.loadUrl("file:///android_asset/setup.html"));
        }

        @JavascriptInterface
        public void toast(String msg) {
            runOnUiThread(() -> Toast.makeText(MainActivity.this, msg, Toast.LENGTH_SHORT).show());
        }

        /** 让用户挑一个手机文件夹做同步目录。 */
        @JavascriptInterface
        public void pickFolder() {
            runOnUiThread(() -> {
                Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
                i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                        | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                        | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
                startActivityForResult(i, REQ_DIR);
            });
        }

        @JavascriptInterface
        public boolean bootSoundOn() {
            return sp.getBoolean("boot_sound", true);
        }

        @JavascriptInterface
        public void setBootSound(boolean on) {
            sp.edit().putBoolean("boot_sound", on).apply();
        }

        @JavascriptInterface
        public void testBootSound() {
            Intent i = new Intent(MainActivity.this, WelcomeSoundService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(i);
            else startService(i);
        }

        @JavascriptInterface
        public String openWallpaper() {
            runOnUiThread(() -> {
                try {
                    startActivity(WhaleWallpaperService.pickerIntent(MainActivity.this));
                } catch (Exception e) {
                    toast("请在系统「壁纸 → 动态壁纸」里选鲸鱼娘");
                }
            });
            return "在系统选择器里点「设置壁纸」";
        }

        @JavascriptInterface
        public boolean petEnabled() {
            return sp.getBoolean("pet_on", false);
        }

        @JavascriptInterface
        public boolean canOverlay() {
            return Build.VERSION.SDK_INT < 23 || android.provider.Settings.canDrawOverlays(MainActivity.this);
        }

        @JavascriptInterface
        public void openOverlaySettings() {
            runOnUiThread(() -> {
                try {
                    Intent i = new Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            android.net.Uri.parse("package:" + getPackageName()));
                    startActivity(i);
                } catch (Exception e) {
                    toast("请在设置里搜「显示在其他应用上层」并允许鲸鱼娘");
                }
            });
        }

        @JavascriptInterface
        public String startPet() {
            if (!canOverlay()) return "先允许「显示在其他应用上层」";
            sp.edit().putBoolean("pet_on", true).apply();
            Intent i = new Intent(MainActivity.this, PetOverlayService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(i);
            else startService(i);
            return "鲸鱼娘已经上桌面了（可拖动，长按隐藏）";
        }

        @JavascriptInterface
        public void stopPet() {
            sp.edit().putBoolean("pet_on", false).apply();
            stopService(new Intent(MainActivity.this, PetOverlayService.class));
        }

        @JavascriptInterface
        public void setToken(String t) {
            if (t != null && !t.isEmpty()) sp.edit().putString("token", t).apply();
        }

        @JavascriptInterface
        public void startSync() {
            if (sp.getString("sync_dir", "").isEmpty()) {
                toast("先选一个手机文件夹");
                return;
            }
            if (sp.getString("token", "").isEmpty()) {
                toast("缺令牌：请从电脑上带 ?t= 的地址打开一次");
                return;
            }
            Intent i = new Intent(MainActivity.this, SyncService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(i);
            else startService(i);
            toast("后台同步已启动");
        }

        @JavascriptInterface
        public void stopSync() {
            startService(new Intent(MainActivity.this, SyncService.class).setAction(SyncService.ACTION_STOP));
            toast("已停止同步");
        }

        @JavascriptInterface
        public void openNotifySettings() {
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS"));
                } catch (Exception e) {
                    toast("打不开系统设置，请在设置里搜「通知使用权」");
                }
            });
        }

        @JavascriptInterface
        public String testNotify() {
            String base = sp.getString("url", "");
            String token = sp.getString("token", "");
            if (base.isEmpty()) return "没有服务器地址";
            if (token.isEmpty()) return "没有令牌：先用带 ?t= 的地址打开一次";
            try {
                java.net.HttpURLConnection c = (java.net.HttpURLConnection)
                        new java.net.URL(base.replaceAll("/+$", "") + "/api/phone/notify").openConnection();
                c.setDoOutput(true);
                c.setRequestMethod("POST");
                c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                c.setRequestProperty("X-WL-Token", token);
                c.setConnectTimeout(5000);
                c.setReadTimeout(8000);
                String body = "{\"ts\":" + (System.currentTimeMillis() / 1000)
                        + ",\"app\":\"鲸鱼娘自检\",\"title\":\"链路测试\",\"text\":\"这条是手机 App 直接发的\"}";
                java.io.OutputStream os = c.getOutputStream();
                os.write(body.getBytes("UTF-8"));
                os.close();
                int code = c.getResponseCode();
                return code == 200 ? "已发送，去电脑页看" : "服务器返回 " + code;
            } catch (Exception e) {
                return "失败：" + e.getClass().getSimpleName();
            }
        }

        @JavascriptInterface
        public boolean notifyEnabled() {
            String flat = android.provider.Settings.Secure.getString(
                    getContentResolver(), "enabled_notification_listeners");
            return flat != null && flat.contains(getPackageName());
        }

        @JavascriptInterface
        public void setPushNotify(boolean on) {
            sp.edit().putBoolean("push_notify", on).apply();
        }

        @JavascriptInterface
        public String syncStatus() {
            String dir = sp.getString("sync_dir", "");
            long at = sp.getLong("sync_at", 0);
            if (dir.isEmpty()) return "未选择文件夹";
            return (at == 0 ? "还没同步过" : "上次同步：" + android.text.format.DateFormat.format("HH:mm:ss", at))
                    + " · " + Uri.parse(dir).getLastPathSegment();
        }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == REQ_DIR && res == RESULT_OK && data != null && data.getData() != null) {
            Uri uri = data.getData();
            int flags = data.getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION
                    | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            try {
                getContentResolver().takePersistableUriPermission(uri, flags);
            } catch (Exception ignored) {}
            sp.edit().putString("sync_dir", uri.toString()).apply();
            Toast.makeText(this, "文件夹已选定，可以开始同步", Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
