package dev.whalelink.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

/** 开机后把桌面鲸鱼娘拉起来（用户开过开关才起）。 */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context ctx, Intent intent) {
        String a = intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(a)
                && !"android.intent.action.QUICKBOOT_POWERON".equals(a)
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(a)) return;
        SharedPreferences sp = ctx.getSharedPreferences("whale", Context.MODE_PRIVATE);

        if (sp.getBoolean("boot_sound", true)) {
            Intent snd = new Intent(ctx, WelcomeSoundService.class);
            if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(snd);
            else ctx.startService(snd);
        }

        if (!sp.getBoolean("pet_on", false)) return;
        Intent i = new Intent(ctx, PetOverlayService.class);
        if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i);
        else ctx.startService(i);
    }
}
