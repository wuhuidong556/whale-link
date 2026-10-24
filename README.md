# whale-link · 鲸鱼娘手机↔电脑

一个「自己搭」的双端小系统：电脑上一只 Live2D 鲸鱼娘，手机上同一个她；两边共用记忆、能互传文件，手机还能直接进电脑上的 DeepSeek Harness。

> 只跑在自己的局域网里，不经过任何第三方服务器。默认只监听本机/内网，请勿直接暴露到公网。

## 组成

| 目录 | 作用 |
| --- | --- |
| `server/app.py` | 唯一后端（aiohttp）：配对、对话、TTS、语音识别、文件、DSH 反代 |
| `web/` | 手机页与桌面宠物页（Live2D 模型在 `web/models/ds_whale/`） |
| `pet.py` | Windows 桌面宠物窗口（pywebview，右下角、置顶、无边框） |
| `android/` | 安卓壳 APK（WebView + 首次填地址 + 麦克风权限） |
| `data/` | 配对码、本机长期令牌、上传的文件 |

## 电脑端

```bat
启动鲸鱼娘.vbs      :: 起服务 + 宠物窗口（推荐，无黑框）
start-server.bat    :: 只起服务，浏览器开 http://127.0.0.1:8770
```

首次运行会在 `data/pair.txt` 生成 6 位配对码，手机用它配一次，之后 365 天免配。

## 手机端

1. 手机与电脑连同一个 Wi-Fi。
2. 浏览器打开 `http://<电脑内网IP>:8770`（例如 `http://192.168.0.101:8770`）。
3. 输入配对码 → 进去后有「对话 / 文件 / DSH」三页。
4. 也可以用 `dist/whale-link-0.1.0-debug.apk` 装个壳，首次启动填同一个地址。

## DSH 标签页

手机上看电脑的 DeepSeek Harness，需要两件事：

1. DSH 正在运行（桌面版自带；或自己 `dsh web --port 8780`）。
2. 在 `server/config.json` 里填：

```json
"dsh": "http://127.0.0.1:8780",
"dsh_token": "启动 DSH 时控制台打印的 token"
```

token 就是启动那行 `http://127.0.0.1:63276/?token=XXXX` 里的 `XXXX`。填完重启 whale-link。

反代会自动把你的会话带过去：首次带 token 换 cookie，之后靠 cookie；WebSocket 也走同一前缀。

## 记忆（两边共用一份）

- 所有对话自动写进 `data/memory.jsonl`：手机聊的、电脑聊的、桌面宠物聊的，都在同一个文件里，所以**不存在“两边各记一份再对齐”**——本来就只有一份。
- 每轮对话会把最近 10 条（每条截 50 字）拼进系统提示词，所以换设备也能接上话。
- 「文件 → 记忆」里可以：导出（下载 JSON）、导入（合并去重）、从 DSH 拉取（把 `~/.dsh/soul-md/memory/*.md` 的条目并进来，只读不改它）。
- 两台机器各自跑 whale-link 时，用「导出/导入」互相搬一次即可；同一条不会重复。

## 控电脑（手机上的「电脑」页）

| 按钮 | 背后做什么 |
| --- | --- |
| 截屏 | 全屏截图（DPI 感知，多显示器取主屏） |
| 锁屏 | `LockWorkStation` |
| 音量 ± / 播放暂停 / 下一首 | 系统虚拟键 |
| 唤醒屏幕 | 晃一下鼠标，防屏保 |
| 记事本 | 白名单启动，不是远程 shell |
| 打开网址 | 在电脑默认浏览器里打开 |
| 关机 / 重启 / 取消 | `shutdown /s|/r /t 30`，必须带 `confirm=确认`，30 秒内可取消 |
| 远程开机 | 发 Wake-on-LAN 魔术包；**浏览器自己发不了广播**，要同网段常开设备（路由器/NAS）代发，或在 `config.json` 填 `wol_mac` 后用命令行发 |

## 配置项（server/config.json）

| 键 | 说明 |
| --- | --- |
| `port` | 服务端口，默认 8770 |
| `voice` / `rate` / `pitch` | Edge TTS 音色与语速音高 |
| `dsh` / `dsh_token` | DSH 地址与一次性 token |
| `llm.base_url` / `llm.api_key` / `llm.model` | 对话模型；`api_key` 留空时自动从 NachoBot 的 `model_config.toml` 读 |

## 人设与记忆

- 人设：`server/nacho.py` 的 `PERSONA_SELF`（鲸鱼娘女仆，自称「我」、称呼「主人」，口癖「哼 / 本鲸鱼」，不学猫叫）。
- 记忆：只读 NachoBot 的 `data/NachoBot.db`（最近聊天 + 人物记忆），不改写它。

## 已知限制

- WebView2 不支持窗口真透明，桌面宠物是一块浅蓝渐变卡片。
- 手机浏览器里 Web Speech 用不了（Chrome 走 Google 服务），语音输入走服务端本地 Whisper。
- **雨见浏览器 + 默认输入法**：打开带 Live2D 的完整页后，曾导致整机输入法崩溃（其他 App 也无法打字，重启才恢复）。这不是页面能修的；规避用右下角「纯文字模式」（`?lite=1`，点一次会记在 localStorage），或直接用 APK。
- Wake-on-LAN 需要同网段常开设备代发，浏览器自己发不了 UDP 广播。
- 公网访问没做；要外网用请自己加 Tailscale / Cloudflare Tunnel，并在反向代理上再套一层鉴权。

## 许可

MIT，见 `LICENSE`。
