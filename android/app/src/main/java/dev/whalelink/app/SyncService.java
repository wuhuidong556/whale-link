package dev.whalelink.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;
import android.provider.DocumentsContract;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 前台服务：在用户选定的手机文件夹与电脑 data/files 之间做双向增量同步。
 * 只用 SAF（DocumentsContract），不依赖 androidx，包体保持小。
 */
public class SyncService extends Service {

    static final String CH = "wl_sync";
    static final int NID = 7;
    static final String ACTION_STOP = "dev.whalelink.app.STOP_SYNC";

    private volatile boolean running = true;
    private SharedPreferences sp;
    private long round = 0;
    private String lastMsg = "准备中…";

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            running = false;
            stopSelf();
            return START_NOT_STICKY;
        }
        sp = getSharedPreferences("whale", MODE_PRIVATE);
        createChannel();
        startForeground(NID, buildNotif("同步已启动", "正在连接电脑…"));

        new Thread(() -> {
            while (running) {
                try {
                    lastMsg = syncOnce();
                } catch (Exception e) {
                    lastMsg = "出错：" + e.getClass().getSimpleName();
                }
                updateNotif();
                for (int i = 0; i < 20 && running; i++) {
                    try { Thread.sleep(1000); } catch (InterruptedException ignored) {}
                }
            }
            stopForeground(true);
        }, "wl-sync").start();
        return START_STICKY;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            NotificationChannel c = new NotificationChannel(CH, "文件同步", NotificationManager.IMPORTANCE_LOW);
            c.setDescription("手机与电脑之间的文件增量同步");
            nm.createNotificationChannel(c);
        }
    }

    private Notification buildNotif(String title, String text) {
        PendingIntent pi = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent ps = PendingIntent.getService(this, 1,
                new Intent(this, SyncService.class).setAction(ACTION_STOP),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);

        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CH) : new Notification.Builder(this);
        return b.setContentTitle(title).setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentIntent(pi)
                .addAction(new Notification.Action.Builder(null, "停止同步", ps).build())
                .setOngoing(true).build();
    }

    private void updateNotif() {
        String t = new SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(new Date());
        getSystemService(NotificationManager.class).notify(NID, buildNotif("文件同步 · " + t, lastMsg));
    }

    /* ------------------------- 一轮 ------------------------- */

    private static class Item {
        String docId, name, mime;
        long size, mtime;
    }

    private String syncOnce() throws Exception {
        String base = sp.getString("url", "");
        String token = sp.getString("token", "");
        String tree = sp.getString("sync_dir", "");
        if (base.isEmpty() || token.isEmpty() || tree.isEmpty()) return "缺服务器地址 / 令牌 / 文件夹";

        Uri treeUri = Uri.parse(tree);
        int nDown = 0, nUp = 0;

        Map<String, long[]> remote = fetchState(base, token);
        List<Item> local = listLocal(treeUri);
        JSONObject seen = new JSONObject(sp.getString("sync_seen", "{}"));

        // 电脑 → 手机
        for (Map.Entry<String, long[]> e : remote.entrySet()) {
            String name = e.getKey();
            long rTime = e.getValue()[1] * 1000L;
            Item l = find(local, name);
            if (l != null && rTime <= l.mtime + 2000) continue;
            if (download(base, token, name, treeUri) != null) {
                nDown++;
                seen.put(name, System.currentTimeMillis());
            }
        }

        // 手机 → 电脑（只传改过的）
        for (Item it : local) {
            long lastSync = seen.optLong(it.name, 0);
            if (lastSync == 0 || it.mtime > lastSync + 2000) {
                long[] r = remote.get(it.name);
                if (r == null || it.mtime > r[1] * 1000L + 2000) {
                    if (upload(base, token, it, treeUri)) nUp++;
                }
                seen.put(it.name, System.currentTimeMillis());
            }
        }

        sp.edit().putString("sync_seen", seen.toString())
          .putLong("sync_at", System.currentTimeMillis()).apply();
        round++;
        return "第 " + round + " 轮：下载 " + nDown + "，上传 " + nUp + "（电脑 " + remote.size() + " 个）";
    }

    private static Item find(List<Item> list, String name) {
        for (Item i : list) if (i.name.equals(name)) return i;
        return null;
    }

    private List<Item> listLocal(Uri treeUri) {
        List<Item> out = new ArrayList<>();
        String rootId = DocumentsContract.getTreeDocumentId(treeUri);
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, rootId);
        String[] cols = {
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                DocumentsContract.Document.COLUMN_MIME_TYPE,
                DocumentsContract.Document.COLUMN_SIZE,
                DocumentsContract.Document.COLUMN_LAST_MODIFIED
        };
        Cursor c = null;
        try {
            c = getContentResolver().query(children, cols, null, null, null);
            while (c != null && c.moveToNext()) {
                String mime = c.getString(2);
                if (mime != null && mime.equals(DocumentsContract.Document.MIME_TYPE_DIR)) continue;
                Item it = new Item();
                it.docId = c.getString(0);
                it.name = c.getString(1);
                it.mime = mime;
                it.size = c.isNull(3) ? 0 : c.getLong(3);
                it.mtime = c.isNull(4) ? 0 : c.getLong(4);
                if (it.name != null) out.add(it);
            }
        } catch (Exception ignored) {
        } finally {
            if (c != null) c.close();
        }
        return out;
    }

    private Map<String, long[]> fetchState(String base, String token) throws Exception {
        String url = base.replaceAll("/+$", "") + "/api/files/state";
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestProperty("X-WL-Token", token);
        c.setConnectTimeout(6000);
        c.setReadTimeout(10000);
        String body = new String(readAll(c.getInputStream()), "UTF-8");
        JSONObject j = new JSONObject(body).getJSONObject("files");
        Map<String, long[]> out = new HashMap<>();
        for (Iterator<String> it = j.keys(); it.hasNext(); ) {
            String k = it.next();
            out.put(k, new long[]{j.getJSONArray(k).getLong(0), j.getJSONArray(k).getLong(1)});
        }
        return out;
    }

    /** 下载并覆盖同名文件；返回新文件 uri，失败 null。 */
    private Uri download(String base, String token, String name, Uri treeUri) {
        try {
            String url = base.replaceAll("/+$", "") + "/api/files/" + URLEncoder.encode(name, "UTF-8");
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setRequestProperty("X-WL-Token", token);
            c.setConnectTimeout(6000);
            c.setReadTimeout(30000);
            if (c.getResponseCode() != 200) return null;
            byte[] data = readAll(c.getInputStream());
            String mime = c.getContentType() == null ? "application/octet-stream" : c.getContentType();

            String rootId = DocumentsContract.getTreeDocumentId(treeUri);
            Uri parent = DocumentsContract.buildDocumentUriUsingTree(treeUri, rootId);
            for (Item it : listLocal(treeUri)) {
                if (name.equals(it.name)) {
                    DocumentsContract.deleteDocument(getContentResolver(),
                            DocumentsContract.buildDocumentUriUsingTree(treeUri, it.docId));
                }
            }
            Uri dst = DocumentsContract.createDocument(getContentResolver(), parent, mime, name);
            if (dst == null) return null;
            OutputStream os = getContentResolver().openOutputStream(dst);
            if (os == null) return null;
            os.write(data);
            os.close();
            return dst;
        } catch (Exception e) {
            return null;
        }
    }

    private boolean upload(String base, String token, Item it, Uri treeUri) {
        try {
            String url = base.replaceAll("/+$", "") + "/api/files?name=" + URLEncoder.encode(it.name, "UTF-8");
            HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
            c.setDoOutput(true);
            c.setRequestMethod("POST");
            c.setRequestProperty("X-WL-Token", token);
            c.setRequestProperty("Content-Type", "application/octet-stream");
            c.setConnectTimeout(6000);
            c.setReadTimeout(30000);
            InputStream in = getContentResolver().openInputStream(
                    DocumentsContract.buildDocumentUriUsingTree(treeUri, it.docId));
            if (in == null) return false;
            OutputStream os = c.getOutputStream();
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) os.write(buf, 0, n);
            os.close();
            in.close();
            return c.getResponseCode() == 200;
        } catch (Exception e) {
            return false;
        }
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        byte[] buf = new byte[65536];
        int n;
        while ((n = in.read(buf)) > 0) bo.write(buf, 0, n);
        in.close();
        return bo.toByteArray();
    }
}
