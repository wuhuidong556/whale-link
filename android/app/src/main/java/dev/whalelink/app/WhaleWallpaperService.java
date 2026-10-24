package dev.whalelink.app;

import android.app.WallpaperManager;
import android.content.ComponentName;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Shader;
import android.os.Handler;
import android.os.Looper;
import android.service.wallpaper.WallpaperService;
import android.view.MotionEvent;
import android.view.SurfaceHolder;

/** 会呼吸的鲸鱼娘壁纸：长按右下角跳进聊天。 */
public class WhaleWallpaperService extends WallpaperService {

    @Override
    public Engine onCreateEngine() { return new WhaleEngine(); }

    class WhaleEngine extends Engine {
        private final Handler h = new Handler(Looper.getMainLooper());
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private Bitmap whale;
        private float t = 0f;
        private boolean visible;
        private long downAt = 0;
        private float downX = 0, downY = 0;

        private final Runnable loop = new Runnable() {
            @Override public void run() {
                draw();
                t += 0.05f;
                h.postDelayed(this, 33);
            }
        };

        @Override public void onCreate(SurfaceHolder sh) {
            super.onCreate(sh);
            whale = BitmapFactory.decodeResource(getResources(), R.drawable.whale);
        }

        @Override public void onVisibilityChanged(boolean v) {
            visible = v;
            h.removeCallbacks(loop);
            if (v) h.post(loop);
        }

        @Override public void onDestroy() {
            h.removeCallbacks(loop);
            super.onDestroy();
        }

        private void draw() {
            SurfaceHolder sh = getSurfaceHolder();
            Canvas c = null;
            try { c = sh.lockCanvas(); } catch (Throwable e) { return; }
            if (c == null) return;
            try {
                int w = c.getWidth(), hh = c.getHeight();
                paint.setShader(new LinearGradient(0, 0, 0, hh,
                        new int[]{0xFFEAF6FF, 0xFFCFE6F7, 0xFFB6D4EA},
                        null, Shader.TileMode.CLAMP));
                c.drawRect(0, 0, w, hh, paint);
                paint.setShader(null);

                if (whale != null) {
                    float bob = (float) Math.sin(t) * hh * 0.006f;
                    float scale = w * 0.62f / whale.getWidth();
                    float bw = whale.getWidth() * scale, bh = whale.getHeight() * scale;
                    float bx = (w - bw) / 2f;
                    float by = hh * 0.60f + bob;
                    RectF dst = new RectF(bx, by, bx + bw, by + bh);
                    paint.setAlpha(235);
                    c.drawBitmap(whale, null, dst, paint);
                    paint.setAlpha(255);

                    // 右下角提示
                    paint.setTextSize(w * 0.032f);
                    paint.setColor(Color.argb(120, 43, 95, 138));
                    String tip = "长按右下角，和鲸鱼娘说句话";
                    float tw = paint.measureText(tip);
                    c.drawText(tip, w - tw - w * 0.04f, hh - hh * 0.06f, paint);
                }
            } finally {
                try { sh.unlockCanvasAndPost(c); } catch (Throwable ignored) {}
            }
        }

        @Override public void onTouchEvent(MotionEvent e) {
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    downAt = System.currentTimeMillis();
                    downX = e.getX(); downY = e.getY();
                    break;
                case MotionEvent.ACTION_UP:
                    long held = System.currentTimeMillis() - downAt;
                    boolean moved = Math.abs(e.getX() - downX) + Math.abs(e.getY() - downY) > 40;
                    float w = getSurfaceHolder().getSurfaceFrame().width();
                    float hh = getSurfaceHolder().getSurfaceFrame().height();
                    boolean corner = downX > w * 0.62f && downY > hh * 0.72f;
                    if (held > 600 && !moved && corner) openChat();
                    break;
            }
        }

        private void openChat() {
            Intent i = new Intent(WhaleWallpaperService.this, MainActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    .putExtra("chat", true);
            startActivity(i);
        }
    }

    /** 方便 App 里直接跳到壁纸选择器。 */
    public static Intent pickerIntent(android.content.Context ctx) {
        return new Intent(WallpaperManager.ACTION_CHANGE_LIVE_WALLPAPER)
                .putExtra(WallpaperManager.EXTRA_LIVE_WALLPAPER_COMPONENT,
                        new ComponentName(ctx, WhaleWallpaperService.class));
    }
}
