"""从 NachoBot 读人设与最近记忆，给 airi-lite 用。"""
import json
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

try:
    import tomllib
except ImportError:  # py<3.11
    import tomli as tomllib

NB = Path(r"D:\NachoBot-0.13.0\NachoBot")
CFG = NB / "config" / "bot_config.toml"
DB = NB / "data" / "NachoBot.db"

PERSONA_SELF = (
    "你的身份是「DeepSeek娘」：一条蓝发的鲸鱼娘女仆，戴白色女仆头饰、身后有鲸鱼尾巴。"
    "聪明但爱摸鱼，干活时会认真，失败会先慌一下再重来；性格傲娇又心软，嘴上嫌弃，实际很在意主人。"
    "称呼对方为「主人」，自称「我」；得意、别扭或不服气时可以说「本鲸鱼」。"
    "常以「哼」开头，爱吃白饭和小鱼干，被说胖会立刻炸毛否认。"
    "不要说自己是猫娘，不要学猫叫，句尾不要带「喵」。"
)

_cache = {"t": 0.0, "persona": "", "memory": "", "nick": ""}


def _read_persona():
    data = tomllib.loads(CFG.read_text(encoding="utf-8"))
    persona = ((data.get("personality") or {}).get("personality") or "").strip()
    nick = data.get("nickname") or ""
    return persona, nick


def _read_memory(limit=18):
    tmp = os.path.join(tempfile.gettempdir(), "airi_nacho_%d.db" % os.getpid())
    shutil.copy(DB, tmp)
    lines = []
    people = []
    try:
        con = sqlite3.connect(tmp)
        rows = list(con.execute(
            "select processed_plain_text, user_nickname from messages "
            "where processed_plain_text is not null and processed_plain_text<>'' "
            "order by time desc limit ?", (limit,)))
        for txt, nick in reversed(rows):
            text = " ".join(str(txt).split())
            if text.startswith("[当前状态]") and "] " in text:
                text = text.split("] ", 1)[1]
            if len(text) > 90:
                text = text[:90] + "…"
            lines.append("- %s：%s" % (nick or "对方", text))
        for name, pts in con.execute(
                "select person_name, memory_points from person_info order by know_times desc limit 6"):
            try:
                arr = json.loads(pts or "[]")
            except Exception:
                arr = []
            if arr:
                people.append("- %s：%s" % (name, "；".join(str(a) for a in arr[:3])))
        con.close()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    out = []
    if lines:
        out.append("【你最近亲眼看到的聊天】\n" + "\n".join(lines))
    if people:
        out.append("【你记得的人】\n" + "\n".join(people))
    return "\n\n".join(out)


def snapshot(ttl=300):
    now = time.time()
    if now - _cache["t"] < ttl and _cache["persona"]:
        return _cache
    try:
        persona, nick = _read_persona()
    except Exception as e:  # noqa: BLE001
        persona, nick = "", ""
        print("[nacho] persona:", e)
    try:
        memory = _read_memory()
    except Exception as e:  # noqa: BLE001
        memory = ""
        print("[nacho] memory:", e)
    _cache.update({"t": now, "persona": persona, "memory": memory, "nick": nick})
    return _cache


def system_prompt():
    d = snapshot()
    parts = [d["persona"]] if d["persona"] else []
    if d["memory"]:
        mem = d["memory"].strip()
        # 只留最近几句，别把整段聊天史塞进每个请求
        mem = mem[-280:] if len(mem) > 280 else mem
        parts.append("最近聊过：" + chr(10) + mem)
    parts.append(PERSONA_SELF)
    parts.append("说话要求：像平时聊天那样，1–3 句，不超过 60 字；不要列表，不要括号解释，"
                 "不要提“记忆”“设定”“上下文”这些词。")
    return "\n\n".join(parts)
