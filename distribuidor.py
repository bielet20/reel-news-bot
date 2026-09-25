"""
distribuidor.py
Distribuye videos publicados en YouTube a Telegram grupos y subreddits de Reddit.
Config persistida en _config/distribucion.json
"""
import json
import os
import threading
import time
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "_config" / "distribucion.json"

HASHTAGS = {
    "tecnologia":     "#tecnología #tech #noticias",
    "ia":             "#IA #inteligenciaartificial #tecnología #noticias",
    "economia":       "#economía #finanzas #noticias",
    "mundo":          "#mundo #noticias #actualidad",
    "politica":       "#política #noticias #actualidad",
    "ciencia":        "#ciencia #noticias",
    "salud":          "#salud #medicina #noticias",
    "deportes":       "#deportes #noticias",
    "entretenimiento":"#entretenimiento #noticias",
    "cripto":         "#crypto #bitcoin #noticias",
}


def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            d = json.loads(CONFIG_FILE.read_text("utf-8"))
            d.setdefault("telegram_grupos", [])
            d.setdefault("telegram_grupos_enabled", True)
            d.setdefault("reddit_subreddits", [])
            d.setdefault("reddit_enabled", False)
            d.setdefault("delay_entre_posts", 8)
            return d
    except Exception:
        pass
    return {
        "telegram_grupos":          [],
        "telegram_grupos_enabled":  True,
        "reddit_subreddits":        [],
        "reddit_enabled":           False,
        "delay_entre_posts":        8,
    }


def save_config(data: dict):
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _broadcast_telegram(titulo: str, yt_url: str, categoria: str):
    cfg = load_config()
    grupos = cfg.get("telegram_grupos", [])
    if not grupos or not cfg.get("telegram_grupos_enabled", True):
        return

    try:
        from telegram_uploader import enviar_mensaje
    except Exception as e:
        print(f"[distribuidor] telegram_uploader no disponible: {e}")
        return

    tags = HASHTAGS.get(categoria.lower() if categoria else "", "#noticias #actualidad #español")
    texto = f"<b>{titulo}</b>\n\n▶️ {yt_url}\n\n{tags}"

    ok = 0
    for grupo in grupos:
        chat_id = grupo.get("chat_id", "") if isinstance(grupo, dict) else str(grupo)
        if not chat_id:
            continue
        try:
            enviar_mensaje(texto, chat_id=chat_id)
            ok += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"[distribuidor] Telegram {chat_id}: {e}")

    print(f"[distribuidor] Telegram grupos: {ok}/{len(grupos)} enviados")


def _post_reddit(titulo: str, yt_url: str):
    cfg = load_config()
    subreddits = cfg.get("reddit_subreddits", [])
    if not subreddits or not cfg.get("reddit_enabled", False):
        return

    creds = {
        "client_id":     os.environ.get("REDDIT_CLIENT_ID", ""),
        "client_secret": os.environ.get("REDDIT_CLIENT_SECRET", ""),
        "username":      os.environ.get("REDDIT_USERNAME", ""),
        "password":      os.environ.get("REDDIT_PASSWORD", ""),
    }
    if not all(creds.values()):
        print("[distribuidor] Reddit: faltan REDDIT_CLIENT_ID / CLIENT_SECRET / USERNAME / PASSWORD en .env")
        return

    try:
        import praw
    except ImportError:
        print("[distribuidor] Reddit: instala praw → pip install praw")
        return

    try:
        reddit = praw.Reddit(
            **creds,
            user_agent=f"ReelNewsBot/1.0 by u/{creds['username']}",
        )
    except Exception as e:
        print(f"[distribuidor] Reddit auth error: {e}")
        return

    delay = max(5, cfg.get("delay_entre_posts", 8))
    ok = 0
    for sub_name in subreddits:
        sub_name = sub_name.lstrip("r/").strip()
        if not sub_name:
            continue
        try:
            reddit.subreddit(sub_name).submit(titulo, url=yt_url)
            ok += 1
            print(f"[distribuidor] Reddit: posteado en r/{sub_name}")
            time.sleep(delay)
        except Exception as e:
            print(f"[distribuidor] Reddit r/{sub_name}: {e}")

    print(f"[distribuidor] Reddit: {ok}/{len(subreddits)} publicados")


def distribuir(titulo: str, yt_url: str, categoria: str = ""):
    """Llama en background tras publicar en YouTube. No bloquea el hilo principal."""
    if not yt_url:
        return
    threading.Thread(
        target=_run,
        args=(titulo, yt_url, categoria),
        daemon=True,
    ).start()


def _run(titulo: str, yt_url: str, categoria: str):
    _broadcast_telegram(titulo, yt_url, categoria)
    _post_reddit(titulo, yt_url)
