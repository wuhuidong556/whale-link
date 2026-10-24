package dev.whalelink.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.media.MediaPlayer;
import android.os.Build;
import android.os.IBinder;

/** 开机时说一句「主人，欢迎回来」。播完自己退场。 */
public class WelcomeSoundService extends Service {

    private MediaPlayer mp;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(new NotificationChannel("whale-boot", "开机问候",
                    NotificationManager.IMPORTANCE_LOW));
        }
        Notification n = new Notification.Builder(this, "whale-boot")
                .setContentTitle("鲸鱼娘")
                .setContentText("正在说：主人，欢迎回来")
                .setSmallIcon(android.R.drawable.ic_lock_silent_mode_off)
                .setOngoing(true)
                .build();
        startForeground(89, n);

        try {
            mp = MediaPlayer.create(this, R.raw.welcome);
            if (mp == null) { stopSelf(); return START_NOT_STICKY; }
            mp.setOnCompletionListener(m -> stopSelf());
            mp.start();
        } catch (Throwable e) {
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        try { if (mp != null) { mp.release(); mp = null; } } catch (Throwable ignored) {}
        super.onDestroy();
    }
}
