# db_json.py
import os
import json
import threading
import time
from typing import Dict, Any, List, Optional
from markov_chains import MarkovChains

DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "db.json")
os.makedirs(DATA_DIR, exist_ok=True)
_lock = threading.RLock()

DEFAULT_GUILD = {
    "toggledActivity": True,
    "channelId": None,
    "webhook": None,
    "sendingPercentage": 0.10,
    "collectionPercentage": 0.50,
    "replyPercentage": 0.80,
    # stored entries: {"text","authorId","messageId","weight","source"}
    "texts": [],
    "markov_wordlist": {},
    "banned": False,
    "trackedUsers": {},
    "disabledMentionUserIds": [],
    "dm_learn_users": {}
}

def _load_all() -> Dict[str, Any]:
    if not os.path.exists(DB_PATH):
        return {}
    with _lock:
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

def _atomic_write_with_retries(raw: Dict[str, Any], attempts: int = 6, base_delay: float = 0.05):
    tmp = DB_PATH + ".tmp"
    for attempt in range(attempts):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, DB_PATH)
            return True
        except PermissionError:
            time.sleep(base_delay * (2 ** attempt))
        except Exception:
            try:
                time.sleep(base_delay)
            except Exception:
                pass
    try:
        os.replace(tmp, DB_PATH)
        return True
    except Exception:
        return False

def _save_all_bg(raw: Dict[str, Any]):
    try:
        copy_raw = json.loads(json.dumps(raw))
    except Exception:
        copy_raw = raw
    t = threading.Thread(target=_atomic_write_with_retries, args=(copy_raw,), daemon=True)
    t.start()

class GuildDB:
    def __init__(self, guild_id: str, raw: Dict[str, Any], manager_raw: Dict[str, Any]):
        self.guild_id = guild_id
        self._raw = raw
        self._manager_raw = manager_raw
        for k, v in DEFAULT_GUILD.items():
            if k not in self._raw:
                self._raw[k] = json.loads(json.dumps(v)) if isinstance(v, (dict, list)) else v
        self.markov = MarkovChains(self._raw.get("markov_wordlist", {}))

    # getters
    def toggled_activity(self) -> bool:
        return bool(self._raw.get("toggledActivity", True))

    def get_channel(self) -> Optional[int]:
        return self._raw.get("channelId")

    def get_webhook(self) -> Optional[str]:
        return self._raw.get("webhook")

    def get_texts_length(self) -> int:
        return len(self._raw.get("texts", []))

    def get_sending_percentage(self) -> float:
        return float(self._raw.get("sendingPercentage", 0.10))

    def get_collection_percentage(self) -> float:
        return float(self._raw.get("collectionPercentage", 0.50))

    def get_reply_percentage(self) -> float:
        return float(self._raw.get("replyPercentage", 0.80))

    def get_texts(self) -> List[Dict[str, Any]]:
        return self._raw.get("texts", [])

    # actions
    def add_text(self, text: str, author_id: str, message_id: str, weight: int = 1, source: str = "channel"):
        entry = {
            "text": text,
            "authorId": author_id,
            "messageId": message_id,
            "weight": int(weight),
            "source": source
        }
        self._raw.setdefault("texts", []).append(entry)

        # update markov in-memory quickly according to weight
        try:
            w = max(1, int(weight))
        except Exception:
            w = 1
        for _ in range(w):
            try:
                self.markov._pick_sentence_words(text)
            except Exception:
                pass

        self._raw["markov_wordlist"] = self.markov.word_list
        _save_all_bg(self._manager_raw)

    def save_markov(self):
        self._raw["markov_wordlist"] = self.markov.word_list
        _save_all_bg(self._manager_raw)

    # setters
    def set_channel(self, channel_id: Optional[int]):
        self._raw["channelId"] = channel_id
        _save_all_bg(self._manager_raw)

    def set_webhook(self, webhook_url: Optional[str]):
        self._raw["webhook"] = webhook_url
        _save_all_bg(self._manager_raw)

    def set_toggled_activity(self, v: bool):
        self._raw["toggledActivity"] = bool(v)
        _save_all_bg(self._manager_raw)

    # checks
    def is_banned(self) -> bool:
        return bool(self._raw.get("banned", False))

    def is_track_allowed(self, user_id: str) -> bool:
        return bool(self._raw.get("trackedUsers", {}).get(user_id, True))

class DBManager:
    def __init__(self):
        self._raw = _load_all()
        self._cache: Dict[str, GuildDB] = {}

    def fetch(self, guild_id: str) -> GuildDB:
        gid = str(guild_id)
        if gid not in self._raw:
            self._raw[gid] = json.loads(json.dumps(DEFAULT_GUILD))
            _save_all_bg(self._raw)
        if gid not in self._cache:
            self._cache[gid] = GuildDB(gid, self._raw[gid], self._raw)
        return self._cache[gid]

    def is_banned(self, guild_id: str) -> bool:
        gid = str(guild_id)
        return bool(self._raw.get(gid, {}).get("banned", False))

db = DBManager()
