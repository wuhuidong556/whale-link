# -*- coding: utf-8 -*-
"""whale-link：手机 ↔ 电脑 双向小系统（鲸鱼娘）。

一个进程干四件事：
1. 给鲸鱼娘一个网页形象（Live2D）+ 对话（DeepSeek + NachoBot 记忆）+ 语音（edge-tts / faster-whisper）
2. 配对：手机输入 6 位码换 token，之后带 cookie 访问
3. 文件互传：手机传电脑、电脑传手机
4. 反向代理 DSH（http://127.0.0.1:63276），手机浏览器里直接操作电脑上的 DSH

默认只监听局域网，端口 8766。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import secrets
import sys
import shutil
import time
import urllib.request
from pathlib import Path

from aiohttp import WSMsgType, web, ClientSession, TCPConnector, ClientTimeout

import nacho
import memory as memdb
import pc

ROOT = Path(__file__).resolve().parent
PROJ = ROOT.parent
WEB = PROJ / "web"
DATA = PROJ / "data"
FILES = DATA / "files"
DATA.mkdir(exist_ok=True)
FILES.mkdir(exist_ok=True)

CFG_PATH = ROOT / "config.json"
DEFAULT_CFG = {
    "port": 8766,
    "voice": "zh-CN-XiaoyiNeural",
    "rate": "+6%",
    "pitch": "+12Hz",
    "dsh": "http://127.0.0.1:63276",
    "nacho_config": r"D:\NachoBot-0.13.0\NachoBot\config\model_config.toml",
    "llm": {"base_url": "https://api.deepseek.com/v1", "api_key": "", "model": "deepseek-flash"},
    "wol_mac": "",
}
cfg = json.loads(CFG_PATH.read_text(encoding="utf-8")) if CFG_PATH.exists() else dict(DEFAULT_CFG)
cfg = {**DEFAULT_CFG, **cfg}
cfg["llm"] = {**DEFAULT_CFG["llm"], **cfg.get("llm", {})}
if not CFG_PATH.exists():
    CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _key_from_nacho() -> str:
    p = Path(cfg["nacho_config"])
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'name\s*=\s*"Deepseek".*?api_key\s*=\s*"([^"]+)"', txt, re.S)
    return m.group(1) if m else ""


API_KEY = cfg["llm"]["api_key"] or _key_from_nacho()
BASE_URL = cfg["llm"]["base_url"].rstrip("/")
MODEL = cfg["llm"]["model"]

# ---------------- 配对 / 鉴权 ----------------
TOKEN_PATH = DATA / "token.txt"
if TOKEN_PATH.exists():
    TOKEN = TOKEN_PATH.read_text(encoding="utf-8").strip()
else:
    TOKEN = secrets.token_urlsafe(24)
    TOKEN_PATH.write_text(TOKEN, encoding="utf-8")

LOCAL_PATH = DATA / "local.txt"
if LOCAL_PATH.exists():
    LOCAL_TOKEN = LOCAL_PATH.read_text(encoding="utf-8").strip()
else:
    LOCAL_TOKEN = secrets.token_urlsafe(18)
    LOCAL_PATH.write_text(LOCAL_TOKEN, encoding="utf-8")

PAIR = {"code": "", "expires": 0.0}


def new_pair_code() -> str:
    PAIR["code"] = "%06d" % random.randint(0, 999999)
    PAIR["expires"] = time.time() + 600
    (DATA / "pair.txt").write_text(PAIR["code"], encoding="utf-8")
    print("[pair] 手机配对码：%s（10 分钟内有效）" % PAIR["code"], flush=True)
    return PAIR["code"]


@web.middleware
async def no_store(req, handler):
    resp = await handler(req)
    ct = resp.content_type or ""
    if ct.startswith("text/html") or "javascript" in ct:
        resp.headers["Cache-Control"] = "no-store"
    return resp


def authed(req: web.Request) -> bool:
    t = req.query.get("t") or req.cookies.get("wl_token") or req.headers.get("X-WL-Token")
    return t in (TOKEN, LOCAL_TOKEN)


# ---------------- LLM ----------------
_LLM = None
_SYS_CACHE = {"t": 0.0, "v": ""}


def _llm_session():
    global _LLM
    if _LLM is None or _LLM.closed:
        _LLM = ClientSession(connector=TCPConnector(limit=4, ttl_dns_cache=600))
    return _LLM


def _sys_prompt() -> str:
    now = time.time()
    if now - _SYS_CACHE["t"] > 60:
        base = nacho.system_prompt()
        extra = memdb.as_prompt(10, 50)
        _SYS_CACHE["v"] = (base + chr(10) + extra) if extra else base
        _SYS_CACHE["t"] = now
    return _SYS_CACHE["v"]


async def llm_reply(text: str) -> str:
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": _sys_prompt()},
                     {"role": "user", "content": text}],
        "temperature": 0.9,
        "max_tokens": 110,
    }
    headers = {"Authorization": "Bearer " + API_KEY}
    async with _llm_session().post(BASE_URL + "/chat/completions", json=body, headers=headers,
                                   timeout=ClientTimeout(total=40)) as r:
        data = await r.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


# ---------------- TTS ----------------
SAY_DIR = DATA / "say"
SAY_DIR.mkdir(exist_ok=True)


async def tts_bytes(text: str) -> bytes:
    import hashlib
    key = hashlib.sha1((cfg["voice"] + "|" + cfg["rate"] + "|" + cfg["pitch"] + "|" + text).encode("utf-8")).hexdigest()
    fp = SAY_DIR / (key + ".mp3")
    if fp.exists() and fp.stat().st_size > 1000:
        return fp.read_bytes()
    import edge_tts
    comm = edge_tts.Communicate(text, cfg["voice"], rate=cfg["rate"], pitch=cfg["pitch"])
    buf = bytearray()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    out = bytes(buf)
    if len(out) > 1000:
        fp.write_bytes(out)
    return out


# ---------------- STT ----------------
_whisper = {"model": None, "lock": asyncio.Lock()}


async def transcribe(data: bytes) -> str:
    async with _whisper["lock"]:
        if _whisper["model"] is None:
            from faster_whisper import WhisperModel
            _whisper["model"] = WhisperModel(
                "small", device="cpu", compute_type="int8",
                download_root=str(PROJ / "whisper_models"))
        model = _whisper["model"]
    tmp = DATA / ("stt_%d.webm" % int(time.time() * 1000))
    tmp.write_bytes(data)
    try:
        loop = asyncio.get_running_loop()

        def run():
            segs, _ = model.transcribe(str(tmp), language="zh", vad_filter=True, beam_size=3)
            return "".join(s.text for s in segs).strip()

        return await loop.run_in_executor(None, run)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------- 文件 ----------------
def safe_name(name: str) -> str:
    name = os.path.basename(name or "file")
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:120] or "file"


NOTIF = DATA / "phone_notify.jsonl"


async def handle_phone_notify(req: web.Request):
    """安卓端把通知推上来；只留最近 200 条。"""
    if not authed(req):
        raise web.HTTPUnauthorized()
    if req.method == "POST":
        d = await read_json(req)
        item = {
            "ts": int(d.get("ts") or time.time()),
            "app": str(d.get("app") or "")[:40],
            "title": str(d.get("title") or "")[:120],
            "text": str(d.get("text") or "")[:300],
        }
        if not (item["title"] or item["text"]):
            return web.json_response({"ok": False})
        with NOTIF.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + chr(10))
        # 简单裁剪
        lines = NOTIF.read_text(encoding="utf-8").splitlines()[-200:]
        NOTIF.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
        return web.json_response({"ok": True})
    n = min(int(req.query.get("n", 30)), 200)
    items = []
    if NOTIF.exists():
        for line in NOTIF.read_text(encoding="utf-8").splitlines()[-n:]:
            try:
                items.append(json.loads(line))
            except Exception:
                pass
    return web.json_response({"items": list(reversed(items))})


async def handle_files_state(req: web.Request):
    """给手机做增量同步用：名字 -> [size, mtime]。"""
    out = {}
    for p in FILES.iterdir():
        if p.is_file():
            st = p.stat()
            out[p.name] = [st.st_size, int(st.st_mtime)]
    return web.json_response({"files": out})


async def handle_files(req: web.Request):
    if req.method == "GET":
        items = []
        for p in sorted(FILES.iterdir(), key=lambda x: -x.stat().st_mtime):
            if p.is_file():
                st = p.stat()
                items.append({"name": p.name, "size": st.st_size, "mtime": int(st.st_mtime)})
        return web.json_response({"files": items})
    # POST：multipart 或原始字节
    if req.content_type.startswith("multipart/"):
        reader = await req.multipart()
        saved = []
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "file":
                dst = FILES / safe_name(part.filename)
                with dst.open("wb") as f:
                    while True:
                        chunk = await part.read_chunk(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                saved.append(dst.name)
        return web.json_response({"saved": saved})
    name = safe_name(req.query.get("name", "upload.bin"))
    (FILES / name).write_bytes(await req.read())
    return web.json_response({"saved": [name]})


# ---------------- DSH 反向代理 ----------------
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailers", "transfer-encoding", "upgrade", "content-encoding",
       "content-length"}

_DSH = None


def _dsh_session():
    global _DSH
    if _DSH is None or _DSH.closed:
        _DSH = ClientSession(connector=TCPConnector(limit=32), auto_decompress=True)
    return _DSH


async def ws_forward(req: web.Request, tail: str):
    qs = req.query_string
    if cfg.get("dsh_token") and "token=" not in qs:
        qs = (qs + "&" if qs else "") + "token=" + cfg["dsh_token"]
    target = cfg["dsh"].replace("http://", "ws://").rstrip("/") + "/" + tail + (("?" + qs) if qs else "")
    ws_server = web.WebSocketResponse(max_msg_size=0)
    await ws_server.prepare(req)
    cookie = req.headers.get("Cookie")
    headers = {"Cookie": cookie} if cookie else {}
    async with ClientSession() as sess:
        async with sess.ws_connect(target, headers=headers, max_msg_size=0,
                                   autoping=True, heartbeat=None) as ws_client:
            async def pump(a, b):
                async for msg in a:
                    if msg.type == WSMsgType.TEXT:
                        await b.send_str(msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        await b.send_bytes(msg.data)
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.ERROR):
                        break
            await asyncio.gather(pump(ws_server, ws_client), pump(ws_client, ws_server))
    return ws_server


async def proxy_http(req: web.Request):
    """流式反代 DSH：不缓冲、不改内容，只补 token 与 Location 前缀。"""
    tail = req.match_info.get("tail", "")
    if req.headers.get("Upgrade", "").lower() == "websocket":
        return await ws_forward(req, tail)
    qs = req.query_string
    has_cookie = "dsh-auth-" in (req.headers.get("Cookie") or "")
    if cfg.get("dsh_token") and "token=" not in qs and not has_cookie:
        qs = (qs + "&" if qs else "") + "token=" + cfg["dsh_token"]
    target = cfg["dsh"].rstrip("/") + "/" + tail + (("?" + qs) if qs else "")

    headers = {k: v for k, v in req.headers.items() if k.lower() not in HOP | {"host", "cookie"}}
    cookie = req.headers.get("Cookie")
    if cookie:
        headers["Cookie"] = cookie

    async with _dsh_session().request(req.method, target, headers=headers,
                                      allow_redirects=False) as r:
        resp = web.StreamResponse(status=r.status)
        for k, v in r.headers.items():
            lk = k.lower()
            if lk in HOP:
                continue
            if lk == "location" and v.startswith("/"):
                v = "/dsh" + v
            resp.headers[k] = v
        await resp.prepare(req)
        async for chunk in r.content.iter_chunked(65536):
            await resp.write(chunk)
        await resp.write_eof()
        return resp


async def proxy_ws(req: web.Request):
    tail = req.match_info.get("tail", "")
    target = cfg["dsh"].replace("http://", "ws://").rstrip("/") + "/" + tail
    ws_server = web.WebSocketResponse()
    await ws_server.prepare(req)
    async with ClientSession() as s:
        async with s.ws_connect(target) as ws_client:
            async def pump(a, b):
                async for msg in a:
                    if msg.type == WSMsgType.TEXT:
                        await b.send_str(msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        await b.send_bytes(msg.data)
                    else:
                        break
                await b.close()

            await asyncio.gather(pump(ws_server, ws_client), pump(ws_client, ws_server))
    return ws_server



# ---------------- 记忆 ----------------
async def api_memory(req: web.Request):
    n = max(1, min(200, int(req.query.get("n", 30))))
    return web.json_response({"items": memdb.recent(n), "total": len(memdb.all_items())})


async def api_memory_add(req: web.Request):
    d = await read_json(req)
    it = memdb.add(str(d.get("role") or "user"), str(d.get("text") or ""),
                   str(d.get("source") or "phone"))
    return web.json_response({"ok": bool(it), "item": it})


async def api_memory_export(req: web.Request):
    return web.json_response({"version": 1, "items": memdb.all_items()})


async def api_memory_import(req: web.Request):
    d = await read_json(req)
    return web.json_response({"added": memdb.merge(d.get("items") or [])})


async def api_memory_pull(req: web.Request):
    return web.json_response({"added": memdb.pull_dsh()})


# ---------------- 控电脑 ----------------
async def api_pc_action(req: web.Request):
    d = await read_json(req)
    act = str(d.get("act") or "")
    arg = d.get("arg")
    loop = asyncio.get_running_loop()
    if act == "lock":
        return web.json_response({"ok": pc.lock()})
    if act == "volume":
        pc.volume(int(arg or 1)); return web.json_response({"ok": True})
    if act == "media":
        pc.media(str(arg or "play")); return web.json_response({"ok": True})
    if act == "url":
        return web.json_response({"ok": pc.open_url(str(arg or ""))})
    if act == "run":
        return web.json_response({"ok": True, "msg": pc.run_allowed(str(arg or ""))})
    if act == "screen":
        await loop.run_in_executor(None, pc.screen_on); return web.json_response({"ok": True})
    if act == "wake":
        mac = str(d.get("mac") or cfg.get("wol_mac") or "")
        return web.json_response({"ok": pc.wake(mac), "msg": "魔术包已发" if mac else "还没填 wol_mac"})
    if act == "power":
        if str(arg) in ("shutdown", "restart") and str(d.get("confirm") or "") != "确认":
            return web.json_response({"ok": False, "msg": "要关机/重启得带上 confirm=确认"})
        return web.json_response({"ok": pc.power(str(arg or ""))})
    return web.json_response({"ok": False, "msg": "不认识的动作"})


async def api_pc_shot(req: web.Request):
    data = await asyncio.get_running_loop().run_in_executor(None, pc.screenshot)
    if not data:
        return web.json_response({"ok": False, "msg": "截图失败"}, status=500)
    return web.Response(body=data, content_type="image/png",
                        headers={"Cache-Control": "no-store"})


# ---------------- 页面 ----------------
async def index(req: web.Request):
    t = req.query.get("t")
    if t == LOCAL_TOKEN:            # 本机宠物/桌面壳：URL 带长期令牌
        resp = web.FileResponse(WEB / "app.html")
        resp.headers["Cache-Control"] = "no-store"
        resp.set_cookie("wl_token", LOCAL_TOKEN, max_age=86400 * 365, httponly=True, samesite="Lax")
        return resp
    if not authed(req):
        raise web.HTTPFound("/pair")
    resp = web.FileResponse(WEB / "app.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def pair_page(req: web.Request):
    resp = web.FileResponse(WEB / "pair.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def api_pair(req: web.Request):
    data = await req.json()
    code = str(data.get("code", "")).strip()
    if code and code == PAIR["code"] and time.time() < PAIR["expires"]:
        resp = web.json_response({"ok": True, "token": TOKEN})
        resp.set_cookie("wl_token", TOKEN, max_age=86400 * 365, httponly=True, samesite="Lax")
        PAIR["code"] = ""
        return resp
    return web.json_response({"ok": False, "error": "配对码不对或已过期"}, status=403)



GREETINGS = {"你好", "您好", "hi", "hello", "在吗", "在不在", "嗨", "哈喽", "早上好", "晚安"}


async def read_json(req: web.Request):
    """Windows 终端里 curl 可能用 GBK 发中文，这里兼容一下。"""
    raw = await req.read()
    try:
        return json.loads(raw or b"{}")
    except UnicodeDecodeError:
        return json.loads(raw.decode("gbk", errors="ignore"))


async def api_chat_stream(req: web.Request):
    """边生成边说：SSE 逐段推文本，前端按句子即时合成语音。"""
    if not authed(req):
        raise web.HTTPUnauthorized()
    data = await read_json(req)
    text = (data.get("text") or "").strip()
    if not text:
        raise web.HTTPBadRequest()

    resp = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache",
                 "X-Accel-Buffering": "no"})
    await resp.prepare(req)

    async def send(obj):
        line = "data: " + json.dumps(obj, ensure_ascii=False) + chr(10) + chr(10)
        await resp.write(line.encode("utf-8"))

    if text.strip("。！？!? ") in GREETINGS:
        reply = "哼，本鲸鱼在呢。主人今天想让我做点什么？"
        memdb.add("user", text, "phone")
        memdb.add("bot", reply, "phone")
        await send({"d": reply})
        await send({"done": True})
        await resp.write_eof()
        return resp

    pieces = []
    body = {
        "model": MODEL, "stream": True,
        "messages": [{"role": "system", "content": _sys_prompt()},
                     {"role": "user", "content": text}],
        "temperature": 0.9, "max_tokens": 120,
    }
    headers = {"Authorization": "Bearer " + API_KEY}
    t0 = time.time()
    try:
        async with _llm_session().post(BASE_URL + "/chat/completions", json=body,
                                       headers=headers, timeout=ClientTimeout(total=60)) as r:
            tpost = time.time()
            async for raw in r.content:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0]["delta"].get("content") or ""
                except Exception:
                    continue
                if delta:
                    if "tfirst" not in locals():
                        tfirst = time.time()
                        print("[stream] sys=%d head=%.2fs first=%.2fs" % (len(body["messages"][0]["content"]), tpost - t0, tfirst - t0), flush=True)
                    pieces.append(delta)
                    await send({"d": delta})
        reply = "".join(pieces).strip()
        if reply:
            memdb.add("user", text, "phone")
            memdb.add("bot", reply, "phone")
        await send({"done": True})
    except Exception as e:
        await send({"err": str(e)[:80]})
    await resp.write_eof()
    return resp

async def api_dshcheck(req: web.Request):
    """给前端探一下 DSH 反代通不通（401 = token 没配或失效）。"""
    url = cfg["dsh"].rstrip("/") + "/"
    qs = "?token=" + cfg["dsh_token"] if cfg.get("dsh_token") else ""
    try:
        async with ClientSession() as s:
            async with s.get(url + qs, allow_redirects=False, timeout=5) as r:
                return web.json_response({"upstream": r.status, "token": bool(cfg.get("dsh_token"))})
    except Exception as e:
        return web.json_response({"upstream": 0, "error": str(e)[:120], "token": bool(cfg.get("dsh_token"))})


async def api_health(req: web.Request):
    return web.json_response({"ok": True, "model": MODEL, "name": os.environ.get("COMPUTERNAME", "PC")})


async def api_state(req: web.Request):
    if not authed(req):
        raise web.HTTPUnauthorized()
    return web.json_response({"nacho": bool(nacho.snapshot().get("persona")), "files": len(list(FILES.iterdir()))})


async def api_chat(req: web.Request):
    if not authed(req):
        raise web.HTTPUnauthorized()
    data = await read_json(req)
    text = (data.get("text") or "").strip()
    if not text:
        return web.json_response({"reply": ""})
    loop = asyncio.get_running_loop()
    try:
        reply = await llm_reply(text)
    except Exception as e:  # noqa: BLE001
        reply = "脑子卡了一下：%s" % str(e)[:60]
    if reply:
        memdb.add("user", text, "phone")
        memdb.add("bot", reply, "phone")
    return web.json_response({"reply": reply})


async def api_tts(req: web.Request):
    if not authed(req):
        raise web.HTTPUnauthorized()
    text = (req.query.get("text") or "").strip()[:300]
    if not text:
        raise web.HTTPBadRequest()
    data = await tts_bytes(text)
    return web.Response(body=data, content_type="audio/mpeg")


async def api_stt(req: web.Request):
    if not authed(req):
        raise web.HTTPUnauthorized()
    data = await req.read()
    if not data:
        return web.json_response({"text": ""})
    try:
        return web.json_response({"text": await transcribe(data)})
    except Exception as e:  # noqa: BLE001
        return web.json_response({"error": str(e)[:160]}, status=500)


async def api_newcode(req: web.Request):
    """只允许本机调用：生成新配对码。"""
    if req.remote not in ("127.0.0.1", "::1") and not authed(req):
        raise web.HTTPForbidden()
    code = new_pair_code()
    return web.json_response({"code": code, "expires": PAIR["expires"]})


async def api_code(req: web.Request):
    if not authed(req):
        raise web.HTTPUnauthorized()
    return web.json_response({"code": PAIR["code"] or new_pair_code(), "expires": PAIR["expires"]})


async def main():
    app = web.Application(client_max_size=512 * 1024 * 1024, middlewares=[no_store])
    app.router.add_get("/", index)
    app.router.add_get("/pair", pair_page)
    app.router.add_post("/api/pair", api_pair)
    app.router.add_get("/api/health", api_health)
    app.router.add_get("/api/state", api_state)
    app.router.add_get("/api/memory", api_memory)
    app.router.add_post("/api/memory/add", api_memory_add)
    app.router.add_get("/api/memory/export", api_memory_export)
    app.router.add_post("/api/memory/import", api_memory_import)
    app.router.add_post("/api/memory/pull", api_memory_pull)
    app.router.add_post("/api/pc/action", api_pc_action)
    app.router.add_get("/api/pc/shot", api_pc_shot)
    app.router.add_get("/api/dshcheck", api_dshcheck)
    app.router.add_get("/api/code", api_code)
    app.router.add_get("/api/newcode", api_newcode)
    app.router.add_post("/api/chat", api_chat)
    app.router.add_post("/api/chat_stream", api_chat_stream)
    app.router.add_get("/api/tts", api_tts)
    app.router.add_post("/api/stt", api_stt)
    app.router.add_route("*", "/api/files", handle_files)
    app.router.add_get("/api/files/state", handle_files_state)


    async def handle_session(req: web.Request):
        """给 APK 的后台同步取令牌用：能通过鉴权，就把它自己用的令牌还给它。"""
        t = req.query.get("t") or req.cookies.get("wl_token")
        return web.json_response({"token": t or ""})

    app.router.add_get("/api/session", handle_session)
    app.router.add_route("*", "/api/phone/notify", handle_phone_notify)
    app.router.add_get("/api/files/{name}", lambda r: web.FileResponse(FILES / safe_name(r.match_info["name"])))
    app.router.add_get("/dsh", lambda r: web.HTTPFound("/dsh/"))
    app.router.add_route("*", "/dsh/{tail:.*}", proxy_http)
    app.router.add_get("/dshws/{tail:.*}", proxy_ws)
    app.router.add_static("/static", WEB, show_index=False)
    new_pair_code()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", cfg["port"])
    await site.start()
    import socket
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect(("8.8.8.8", 80))
        lan = sk.getsockname()[0]
        sk.close()
    except OSError:
        lan = "127.0.0.1"
    print("=" * 56, flush=True)

    async def console():
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                return
            if line.strip().lower() in ("c", "code", "new"):
                code = new_pair_code()
                print("新的配对码：%s" % code, flush=True)

    asyncio.create_task(console())
    print(" 手机用这个地址：http://%s:%d" % (lan, cfg["port"]), flush=True)
    print(" 配对码：%s（10 分钟内有效）" % PAIR["code"], flush=True)
    print("=" * 56, flush=True)

    async def console():
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                return
            if line.strip().lower() in ("c", "code", "new"):
                code = new_pair_code()
                print("新的配对码：%s" % code, flush=True)

    asyncio.create_task(console())
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
