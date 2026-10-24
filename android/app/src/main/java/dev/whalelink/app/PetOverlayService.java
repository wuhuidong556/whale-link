package dev.whalelink.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.PixelFormat;
import android.os.Build;
import android.os.IBinder;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.ImageView;

/** 桌面悬浮的鲸鱼娘：开机自启、可拖动、点一下进 App、长按隐藏。 */
public class PetOverlayService extends Service {

    private WindowManager wm;
    private ImageView view;
    private WindowManager.LayoutParams lp;
    private SharedPreferences sp;

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        sp = getSharedPreferences("whale", MODE_PRIVATE);
        startForegroundNotice();
        wm = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        if (!show()) stopSelf();
    }

    private void startForegroundNotice() {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(new NotificationChannel("whale-pet", "鲸鱼娘在桌面上",
                    NotificationManager.IMPORTANCE_MIN));
        }
        Notification n = new Notification.Builder(this, "whale-pet")
                .setContentTitle("鲸鱼娘在桌面上")
                .setContentText("点通知回到 App；桌面上可拖动")
                .setSmallIcon(android.R.drawable.ic_menu_view)
                .setOngoing(true)
                .build();
        startForeground(88, n);
    }

    private boolean show() {
        if (Build.VERSION.SDK_INT >= 23 && !android.provider.Settings.canDrawOverlays(this)) return false;
        view = new ImageView(this);
        view.setImageResource(R.drawable.whale);
        int size = (int) (getResources().getDisplayMetrics().widthPixels * 0.30);
        lp = new WindowManager.LayoutParams(
                size, (int) (size * 436f / 360f),
                Build.VERSION.SDK_INT >= 26
                        ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                        : WindowManager.LayoutParams.TYPE_PHONE,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.x = sp.getInt("pet_x", getResources().getDisplayMetrics().widthPixels - size - 8);
        lp.y = sp.getInt("pet_y", (int) (getResources().getDisplayMetrics().heightPixels * 0.55));

        view.setOnTouchListener(new View.OnTouchListener() {
            int downX, downY, startX, startY;
            long downAt;

            @Override
            public boolean onTouch(View v, MotionEvent e) {
                switch (e.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        downX = (int) e.getRawX(); downY = (int) e.getRawY();
                        startX = lp.x; startY = lp.y;
                        downAt = System.currentTimeMillis();
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        lp.x = startX + (int) e.getRawX() - downX;
                        lp.y = startY + (int) e.getRawY() - downY;
                        wm.updateViewLayout(view, lp);
                        return true;
                    case MotionEvent.ACTION_UP:
                        long held = System.currentTimeMillis() - downAt;
                        int moved = Math.abs((int) e.getRawX() - downX) + Math.abs((int) e.getRawY() - downY);
                        sp.edit().putInt("pet_x", lp.x).putInt("pet_y", lp.y).apply();
                        if (moved < 12) {
                            if (held > 700) {           // 长按：先藏起来
                                sp.edit().putBoolean("pet_on", false).apply();
                                stopSelf();
                            } else {                    // 轻点：回 App
                                Intent i = new Intent(PetOverlayService.this, MainActivity.class);
                                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
                                startActivity(i);
                            }
                        }
                        return true;
                }
                return false;
            }
        });

        wm.addView(view, lp);
        return true;
    }

    @Override
    public void onDestroy() {
        try { if (view != null) wm.removeView(view); } catch (Throwable ignored) {}
        super.onDestroy();
    }
}
