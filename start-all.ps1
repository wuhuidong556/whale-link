# 鲸鱼娘一键启动：DSH(8780) -> whale-link(8770) -> 桌面宠物
$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSCommandPath
$log  = Join-Path $root 'start-all.log'
$py   = 'C:\Users\74187\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe'
$dsh  = 'D:\deepseek\resources\runtime\cli\bin\dsh.cmd'
function Log($m) { "$(Get-Date -Format 'HH:mm:ss') $m" | Tee-Object -FilePath $log -Append }

function Test-Port($p) {
  $c = New-Object Net.Sockets.TcpClient
  try { $c.Connect('127.0.0.1', $p); $true } catch { $false } finally { $c.Close() }
}

# 1) DSH web：没起就起一个，并把新 token 写进 config.json
if (-not (Test-Port 8780)) {
  Log 'start dsh web :8780'
  $out = Join-Path $root 'dsh8780.out'
  Remove-Item $out -ErrorAction SilentlyContinue
  Start-Process -FilePath $dsh -ArgumentList '--profile','web','--port','8780','--no-open' `
    -WorkingDirectory $root -RedirectStandardOutput $out -RedirectStandardError (Join-Path $root 'dsh8780.err') -WindowStyle Hidden
  for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Milliseconds 700; if (Test-Path $out) { if ((Get-Content $out -Raw) -match 'token=([A-Za-z0-9_\-]+)') { break } } }
  $tok = $null
  if ((Get-Content $out -Raw) -match 'token=([A-Za-z0-9_\-]+)') { $tok = $Matches[1] }
  if ($tok) {
    $cfgPath = Join-Path $root 'server\config.json'
    $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
    $cfg.dsh_token = $tok
    $cfg | ConvertTo-Json -Depth 8 | Set-Content $cfgPath -Encoding utf8
    Log "dsh token updated: $($tok.Substring(0,8))..."
  } else { Log 'dsh token not captured' }
}

# 2) whale-link
if (-not (Test-Port 8770)) {
  Log 'start whale-link :8770'
  Start-Process -FilePath $py -ArgumentList 'server\app.py' -WorkingDirectory $root -WindowStyle Hidden
  Start-Sleep -Seconds 3
}

# 3) 桌面宠物
$pet = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match 'pet\.py' }
if (-not $pet) {
  Log 'start pet'
  Start-Process -FilePath $py -ArgumentList 'pet.py' -WorkingDirectory $root -WindowStyle Hidden
}
# 4) 开机问候（异步播放，不挡住启动）
try {
  $wav = Join-Path $root 'welcome-boot.mp3'
  if (Test-Path $wav) {
    Start-Job -ScriptBlock {
      param($f)
      $w = New-Object -ComObject WMPlayer.OCX
      $w.URL = $f
      $w.controls.play()
      Start-Sleep -Seconds 4
      $w.controls.stop()
    } -ArgumentList $wav | Out-Null
    Log 'boot greeting played'
  }
} catch { Log 'boot greeting failed' }

Log 'ready'
