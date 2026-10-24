@echo off
chcp 65001 >nul
echo 正在向本机的鲸鱼娘要一个新的配对码...
powershell -NoProfile -Command "$r = Invoke-RestMethod -Uri http://127.0.0.1:8770/api/newcode; Write-Host ('新配对码：' + $r.code + '（10 分钟内有效）')"
echo.
pause
