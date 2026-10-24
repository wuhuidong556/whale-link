"""两边共用的一份记忆：就一个 JSONL，谁写了谁就多一行。

手机、电脑、桌面宠物读的都是这个文件，所以「同步」在这里等于「不各存一份」。
对外还能导出/导入，方便和别的机器或别的人设合并。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FILE = DATA / "memory.jsonl"
DSH_MEM = Path.home() / ".dsh" / "soul-md"
MAX_LINE = 400  # 单条截断，避免一条长文撑爆


def _mid(ts: float, role: str, text: str) -> str:
    h = hashlib.sha1(("%.3f|%s|%s" % (ts, role, text)).encode("utf-8")).hexdigest()
    return h[:16]


def _clean(text: str) -> str:
    t = " ".join(str(text or "").split())
    return t[:MAX_LINE]


def add(role: str, text: str, source: str = "whale") -> dict | None:
    t = _clean(text)
    if not t:
        return None
    item = {"id": _mid(time.time(), role, t), "ts": round(time.time(), 3),
            "role": role, "text": t, "source": source}
    DATA.mkdir(parents=True, exist_ok=True)
    with FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def all_items() -> list[dict]:
    if not FILE.exists():
        return []
    out = []
    for line in FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    out.sort(key=lambda x: x.get("ts", 0))
    return out


def recent(n: int = 30) -> list[dict]:
    return all_items()[-n:]


def as_prompt(n: int = 12, chars: int = 60) -> str:
    """给模型看的极简版：最近 n 条，每条截到 chars 字。"""
    lines = []
    for it in recent(n):
        who = "主人" if it.get("role") == "user" else "我"
        txt = it.get("text", "")[:chars]
        lines.append("- %s：%s" % (who, txt))
    return "【最近的对话记忆】\n" + "\n".join(lines) if lines else ""


def merge(items: list[dict]) -> int:
    """按 id 去重合并，返回新进来的条数。"""
    have = {it.get("id") for it in all_items()}
    added = 0
    DATA.mkdir(parents=True, exist_ok=True)
    with FILE.open("a", encoding="utf-8") as f:
        for it in items or []:
            if not isinstance(it, dict):
                continue
            text = _clean(it.get("text", ""))
            if not text:
                continue
            ts = float(it.get("ts") or time.time())
            role = str(it.get("role") or "user")
            mid = str(it.get("id") or _mid(ts, role, text))
            if mid in have:
                continue
            have.add(mid)
            rec = {"id": mid, "ts": round(ts, 3), "role": role,
                   "text": text, "source": str(it.get("source") or "import")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            added += 1
    return added


def pull_dsh(n: int = 40) -> int:
    """把 DSH 人格卡的记忆条目捞进来（只读，不改它的文件）。"""
    if not DSH_MEM.exists():
        return 0
    files = sorted(DSH_MEM.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:4]
    items = []
    for fp in files:
        try:
            txt = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in txt.splitlines():
            s = line.strip(" -*\t")
            if len(s) < 8 or len(s) > 90 or s.startswith(("#", "cd ", "& ", "PS ", "$")):
                continue
            if any(ch in s for ch in ("**", "`", "|", "http", ".md", chr(92))):
                continue
            items.append({"role": "user", "text": s, "source": "dsh:" + fp.stem,
                          "ts": fp.stat().st_mtime})
    return merge(items[-n:] if len(items) > n else items)
