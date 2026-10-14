"""Recorde e histórico local, independentes da pasta de instalação."""
from datetime import datetime
import json
import os
from pathlib import Path


def data_file():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "AdrianoGames" / "FlappyBird" / "profile.json"


def load_settings(path):
    defaults = {"volume": 0.7, "muted": False, "fullscreen": False}
    try:
        values = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(values, dict):
            return defaults
        volume = values.get("volume")
        if type(volume) in (int, float) and 0 <= volume <= 1:
            defaults["volume"] = volume
        for key in ("muted", "fullscreen"):
            if type(values.get(key)) is bool:
                defaults[key] = values[key]
    except (OSError, ValueError):
        pass
    return defaults


def save_settings(path, settings):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(settings, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def load_profile(path):
    empty = {"high_score": 0, "history": [], "best": []}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return empty
        score = data.get("high_score", 0)
        score = score if type(score) is int and score >= 0 else 0
        def clean_rows(values, limit):
            return [row for item in values if (row := clean_round(item)) is not None][:limit] if isinstance(values, list) else []
        history = clean_rows(data.get("history"), 20)
        best = sorted(clean_rows(data.get("best", history), 20), key=lambda row: row["score"], reverse=True)[:5]
        return {"high_score": max([score] + [row["score"] for row in history + best]), "history": history, "best": best}
    except (OSError, ValueError, TypeError):
        return empty


def clean_round(item):
    if not isinstance(item, dict):
        return None
    points, duration, level = item.get("score"), item.get("duration"), item.get("level")
    if type(points) is not int or points < 0 or type(duration) not in (int, float) or not 0 <= duration < 1_000_000 or type(level) is not int or not 1 <= level <= 6:
        return None
    try:
        datetime.fromisoformat(item["date"])
    except (ValueError, KeyError, TypeError):
        return None
    return {"score": points, "duration": duration, "level": level, "date": item["date"], "result": "interrompida" if item.get("result") == "interrompida" else "concluida"}


def load_record(path):
    return load_profile(path)["high_score"]


def save_record(path, score, history=None, best=None):
    path = Path(path)
    if history is None:
        history = load_profile(path)["history"]
    if best is None:
        best = load_profile(path)["best"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"version": 2, "high_score": score, "history": history[:20], "best": best[:5]}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)
