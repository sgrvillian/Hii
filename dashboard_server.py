# -*- coding: utf-8 -*-
"""
🔴 XIRUS MODZ 🔵 - Dashboard Server & Telegram Controller
Auth-Free Web UI + Full Telegram Inline Bot + 1-Sec Live Sync
"""

import asyncio
import json
import os
import re
import time
from typing import Dict, List, Any, Optional
from aiohttp import web
import aiohttp

# ==================== ⚙️ CORE CONFIGURATION ⚙️ ====================
TELEGRAM_TOKEN = "8944983211:AAFqePkbS-ecIs9P5pI7tJT_Y_h-T0g8J2Y"
ADMIN_ID = "7692008537"  # Real Owner ID

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")
ACCOUNTS_FILE = "accounts.json"
STOPPED_FILE = "stopped_accounts.json"
TG_USERS_FILE = "tg_users.json"

EXP_TABLE: Dict[int, int] = {
    1: 0, 2: 48, 3: 202, 4: 544, 5: 1012, 6: 1844, 7: 2792, 8: 3800,
    9: 4870, 10: 6004, 11: 7192, 12: 8448, 13: 9760, 14: 11140, 15: 12566,
    16: 14060, 17: 15610, 18: 17224, 19: 18902, 20: 20632, 21: 22424, 22: 24278,
    23: 26192, 24: 28166, 25: 30200, 26: 32294, 27: 34448, 28: 37804, 29: 41274,
    30: 44870, 31: 48582, 32: 53394, 33: 58566, 34: 64096, 35: 69994, 36: 76460,
    37: 83506, 38: 91128, 39: 99322, 40: 108092, 41: 120144, 42: 133266, 43: 147472,
    44: 162760, 45: 179126, 46: 196572, 47: 215368, 48: 235516, 49: 257010, 50: 279860,
    51: 304056, 52: 348318, 53: 394982, 54: 444044, 55: 495508, 56: 549364, 57: 633756,
    58: 721744, 59: 813336, 60: 908522, 61: 1041438, 62: 1180352, 63: 1325266,
    64: 1476184, 65: 1634300, 66: 1840946, 67: 2056594, 68: 2281242, 69: 2514880,
    70: 2757530, 71: 3059506, 72: 3372284, 73: 3699456, 74: 4041030, 75: 4397002,
    76: 4829104, 77: 5282204, 78: 5756304, 79: 6251408, 80: 6776502, 81: 7381324,
    82: 8043154, 83: 8752982, 84: 9510808, 85: 10316338, 86: 11277190, 87: 12291748,
    88: 13360304, 89: 14482858, 90: 15659418, 91: 17026708, 92: 18453950, 93: 19941280,
    94: 21488570, 95: 23095858, 96: 24763138, 97: 26490428, 98: 28378704, 99: 30124996,
    100: 32032884
}

def calculate_level_progress(level: int, current_exp: int) -> Dict[str, Any]:
    level = max(1, level)
    next_level = min(100, level + 1)
    base_exp = EXP_TABLE.get(level, 0)
    target_exp = EXP_TABLE.get(next_level, base_exp + 50000)
    needed_for_level = max(1, target_exp - base_exp)
    earned_in_level = max(0, current_exp - base_exp)
    remaining_exp = max(0, target_exp - current_exp)
    progress_pct = min(100.0, max(0.0, (earned_in_level / needed_for_level) * 100.0))
    return {
        "next_level": next_level,
        "base_exp": base_exp,
        "target_exp": target_exp,
        "needed_for_level": needed_for_level,
        "earned_in_level": earned_in_level,
        "remaining_exp": remaining_exp,
        "progress_pct": round(progress_pct, 1)
    }

def format_uptime(seconds: float) -> str:
    m, s = divmod(int(max(0, seconds)), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d > 0: return f"{d}d {h}h {m}m {s}s"
    elif h > 0: return f"{h}h {m}m {s}s"
    elif m > 0: return f"{m}m {s}s"
    return f"{s}s"

# ==================== BULK FILE PARSER ====================
UID_KEYS = {
    'uid', 'user', 'username', 'user_id', 'userid', 'id', 'account', 'account_id',
    'freefire_id', 'ffid', 'player_id', 'playerid', 'guest', 'guest_id',
    'guestuid', 'guest_uid', 'useruid', 'user_uid', 'accountid',
    'external_id', 'externalid', 'open_id', 'openid'
}

PWD_KEYS = {
    'password', 'pass', 'pwd', 'passwd', 'key', 'pass_word', 'passkey', 'secret',
    'guestpass', 'guest_pass', 'guestpassword', 'guest_password',
    'userpass', 'user_pass', 'accountpass', 'account_pass',
    'auth_password', 'authpassword'
}

def _try_add(accounts, seen, uid, pwd):
    try:
        uid_s = str(uid).strip()
        pwd_s = str(pwd).strip()
    except Exception: return
    if not uid_s or not pwd_s: return
    if len(uid_s) < 4 or len(pwd_s) < 4: return
    if uid_s in seen: return
    seen.add(uid_s)
    accounts.append({"uid": uid_s, "password": pwd_s})

def _parse_line(line, accounts, seen):
    line = line.strip()
    if not line: return
    if line.startswith('#') or line.startswith('//') or line.startswith(';'): return
    for sep in [':', '|', ',', '\t', ';', ' ', '=']:
        if sep in line:
            parts = line.split(sep)
            if len(parts) >= 2:
                uid_candidate = parts[0].strip().strip('"\'')
                pwd_candidate = sep.join(parts[1:]).strip().strip('"\'')
                if uid_candidate and pwd_candidate:
                    if uid_candidate.isdigit() or len(uid_candidate) >= 6:
                        _try_add(accounts, seen, uid_candidate, pwd_candidate)
                        return

def _walk_json(obj, accounts, seen, depth=0):
    if depth > 10: return
    if isinstance(obj, list):
        for item in obj: _walk_json(item, accounts, seen, depth + 1)
    elif isinstance(obj, dict):
        uid_val = None
        pwd_val = None
        for k, v in obj.items():
            kl = str(k).lower().strip().replace('-', '_').replace(' ', '_')
            kl_flat = kl.replace('_', '')
            if (kl in UID_KEYS or kl_flat in UID_KEYS) and not uid_val:
                if isinstance(v, (str, int)) and not isinstance(v, bool): uid_val = str(v)
            elif (kl in PWD_KEYS or kl_flat in PWD_KEYS) and not pwd_val:
                if isinstance(v, (str, int)) and not isinstance(v, bool): pwd_val = str(v)
        if uid_val and pwd_val:
            _try_add(accounts, seen, uid_val, pwd_val)
            return
        if len(obj) >= 1:
            simple_pairs = True
            pairs = []
            for k, v in obj.items():
                if isinstance(v, str): pairs.append((k, v))
                else:
                    simple_pairs = False
                    break
            if simple_pairs and pairs:
                for k, v in pairs:
                    k_s = str(k).strip()
                    if len(k_s) >= 4 and len(v) >= 4: _try_add(accounts, seen, k_s, v)
                if accounts: return
        for v in obj.values(): _walk_json(v, accounts, seen, depth + 1)
    elif isinstance(obj, str):
        s = obj.strip()
        if (s.startswith('{') or s.startswith('[')) and len(s) > 10:
            try:
                _walk_json(json.loads(s), accounts, seen, depth + 1)
                return
            except Exception: pass
        _parse_line(s, accounts, seen)

def parse_accounts_file(content: str) -> List[Dict]:
    accounts: List[Dict] = []
    seen: set = set()
    if not content: return accounts
    text = content.lstrip('\ufeff').strip()
    if not text: return accounts

    json_ok = False
    if text[0] in '[{':
        try:
            data = json.loads(text)
            _walk_json(data, accounts, seen)
            json_ok = True
        except Exception: json_ok = False

    if not json_ok or not accounts:
        for line in text.splitlines(): _parse_line(line, accounts, seen)

    return accounts

# ==================== BOT STATE ====================
class BotState:
    def __init__(self):
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 500
        self.total_matches = 0
        self.total_matches_started = 0
        self.total_gained_exp = 0
        self.start_time = time.time()
        self.account_workers: Dict[str, asyncio.Task] = {}
        self.account_token_map: Dict[str, str] = {}
        self.auth_to_game_id: Dict[str, str] = {}
        self.game_to_auth_id: Dict[str, str] = {}
        self.paused_accounts: set = set()
        self.refresh_callbacks: Dict[str, Any] = {}
        self.account_credentials: Dict[str, Dict[str, Any]] = {}
        self.active_writers: Dict[str, set] = {}
        self.account_logs: Dict[str, List[Dict[str, Any]]] = {}
        self.max_account_logs = 100
        self.ping_ms = 0.0

    def register_writer(self, uid, writer):
        uid_str = str(uid)
        if uid_str not in self.active_writers: self.active_writers[uid_str] = set()
        self.active_writers[uid_str].add(writer)

    def unregister_writer(self, uid, writer):
        uid_str = str(uid)
        if uid_str in self.active_writers:
            self.active_writers[uid_str].discard(writer)
            if not self.active_writers[uid_str]: self.active_writers.pop(uid_str, None)

    def close_writers_for_account(self, uid):
        uid_str = str(uid)
        candidates = {uid_str}
        if uid_str in self.auth_to_game_id: candidates.add(str(self.auth_to_game_id[uid_str]))
        if uid_str in self.game_to_auth_id: candidates.add(str(self.game_to_auth_id[uid_str]))
        for c in list(candidates):
            writers = list(self.active_writers.get(c, []))
            for w in writers:
                try:
                    if hasattr(w, "close"):
                        if hasattr(w, "is_closing"):
                            if not w.is_closing(): w.close()
                        else: w.close()
                except Exception: pass
            self.active_writers.pop(c, None)

    def _extract_uid_from_msg(self, message: str) -> Optional[str]:
        if not message: return None
        m = re.search(r'\bUID[:\s]+(\d{5,})', message)
        return m.group(1) if m else None

    def log(self, message, level="info", uid=None):
        if not uid: uid = self._extract_uid_from_msg(message)

        entry = {
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "uid": str(uid) if uid else None
        }
        self.logs.append(entry)
        if len(self.logs) > self.max_logs: self.logs.pop(0)

        if uid:
            uid_str = str(uid)
            if uid_str not in self.account_logs: self.account_logs[uid_str] = []
            self.account_logs[uid_str].append(entry)
            if len(self.account_logs[uid_str]) > self.max_account_logs: self.account_logs[uid_str].pop(0)

    def register_account(self, uid, nickname, region, level, exp, likes=0, token=None, auth_uid=None, owner="admin"):
        uid_str = str(uid)
        auth_uid_str = str(auth_uid) if auth_uid else self.game_to_auth_id.get(uid_str, "")
        if auth_uid_str:
            self.auth_to_game_id[auth_uid_str] = uid_str
            self.game_to_auth_id[uid_str] = auth_uid_str
            self.account_token_map[auth_uid_str] = uid_str
            self.account_token_map[uid_str] = auth_uid_str
        if token:
            self.account_token_map[uid_str] = token
            self.account_token_map[token[:16]] = uid_str
            if auth_uid_str: self.account_token_map[auth_uid_str] = token

        prog = calculate_level_progress(level or 1, exp)
        lvl_val = level or 1
        acc_mode = "BR" if lvl_val < 3 else "LONE_WOLF"
        acc_mode_label = "Battle Royale (Lvl < 3)" if lvl_val < 3 else "Lone Wolf (Lvl 3+)"

        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str, "auth_uid": auth_uid_str or "", "owner": owner,
                "nickname": nickname or f"Player_{uid_str[:6]}", "region": region or "IND",
                "level": lvl_val, "next_level": prog["next_level"], "mode": acc_mode, "mode_label": acc_mode_label,
                "initial_exp": exp, "current_exp": exp, "gained_exp": 0,
                "remaining_exp": prog["remaining_exp"], "target_exp": prog["target_exp"],
                "needed_for_level": prog["needed_for_level"], "earned_in_level": prog["earned_in_level"],
                "progress_pct": prog["progress_pct"], "likes": likes or 0,
                "status": "PAUSED" if self.is_paused(uid_str) else "ONLINE",
                "matches_played": 0, "active_matches": 0, "last_match_time": None, "token": token or "",
                "start_time": time.time(), "is_paused": self.is_paused(uid_str),
                "paused_at": time.time() if self.is_paused(uid_str) else None,
                "total_pause_duration": 0.0, "last_updated": time.time(),
                "match_total_players": 0, "match_alive_players": 0, "match_dead_players": 0,
                "match_mode": "", "match_started_at": None,
            }
        else:
            acc = self.accounts[uid_str]
            if auth_uid_str: acc["auth_uid"] = auth_uid_str
            if owner: acc["owner"] = owner
            if nickname: acc["nickname"] = nickname
            if region: acc["region"] = region
            if level: acc["level"] = level
            if token: acc["token"] = token
            acc["current_exp"] = exp
            acc["gained_exp"] = max(0, exp - acc["initial_exp"])
            acc["next_level"] = prog["next_level"]
            acc["remaining_exp"] = prog["remaining_exp"]
            acc["target_exp"] = prog["target_exp"]
            acc["needed_for_level"] = prog["needed_for_level"]
            acc["earned_in_level"] = prog["earned_in_level"]
            acc["progress_pct"] = prog["progress_pct"]
            acc["likes"] = likes
            if not acc.get("is_paused"): acc["status"] = "ONLINE"
            acc["last_updated"] = time.time()
        self.recalc_totals()

    def get_account_uptime(self, uid_str):
        acc = self.accounts.get(uid_str)
        if not acc:
            mapped = self.game_to_auth_id.get(uid_str) or self.auth_to_game_id.get(uid_str)
            if mapped and mapped in self.accounts: acc = self.accounts[mapped]
        if not acc: return 0
        start_t = acc.get("start_time", time.time())
        total_pause = acc.get("total_pause_duration", 0.0)
        if acc.get("is_paused") and acc.get("paused_at"):
            return max(0, int(acc["paused_at"] - start_t - total_pause))
        return max(0, int(time.time() - start_t - total_pause))

    def is_paused(self, uid):
        uid_str = str(uid)
        if uid_str in self.paused_accounts: return True
        game_id = self.auth_to_game_id.get(uid_str)
        if game_id and game_id in self.paused_accounts: return True
        auth_uid = self.game_to_auth_id.get(uid_str)
        if auth_uid and auth_uid in self.paused_accounts: return True
        return False

    def toggle_pause(self, uid):
        uid_str = str(uid)
        candidates = {uid_str}
        if uid_str in self.auth_to_game_id: candidates.add(self.auth_to_game_id[uid_str])
        if uid_str in self.game_to_auth_id: candidates.add(self.game_to_auth_id[uid_str])
        target_acc = None
        target_key = uid_str
        for c in candidates:
            if c in self.accounts:
                target_acc = self.accounts[c]
                target_key = c
                break
        is_now_paused = not self.is_paused(uid_str)
        if is_now_paused:
            for c in candidates:
                self.paused_accounts.add(c)
                self.close_writers_for_account(c)
            if target_acc:
                target_acc["is_paused"], target_acc["paused_at"], target_acc["status"] = True, time.time(), "PAUSED"
            self.log(f"⏸ UID {target_key} PAUSED", "warning", target_key)
            if "on_pause_toggle" in self.refresh_callbacks:
                try: asyncio.create_task(self.refresh_callbacks["on_pause_toggle"](target_key, True))
                except Exception: pass
        else:
            for c in candidates: self.paused_accounts.discard(c)
            if target_acc:
                target_acc["is_paused"] = False
                if target_acc.get("paused_at"):
                    target_acc["total_pause_duration"] += (time.time() - target_acc["paused_at"])
                    target_acc["paused_at"] = None
                target_acc["status"] = "ONLINE"
            self.log(f"▶ UID {target_key} RESUMED", "success", target_key)
            if "on_pause_toggle" in self.refresh_callbacks:
                try: asyncio.create_task(self.refresh_callbacks["on_pause_toggle"](target_key, False))
                except Exception: pass
        return is_now_paused

    def toggle_pause_all(self, owner=None):
        keys = list(self.accounts.keys())
        any_active = any(not self.is_paused(k) for k in keys)
        for k in keys:
            current_paused = self.is_paused(k)
            if any_active and not current_paused: self.toggle_pause(k)
            elif not any_active and current_paused: self.toggle_pause(k)
        return any_active

    def update_exp(self, uid, current_exp, level=None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            old_exp = acc["current_exp"]
            old_level = acc.get("level", 1)
            acc["current_exp"] = current_exp
            if level is not None and level > 0: acc["level"] = level
            acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])
            current_lvl = acc["level"]
            acc["mode"] = "BR" if current_lvl < 3 else "LONE_WOLF"
            acc["mode_label"] = "Battle Royale (Lvl < 3)" if current_lvl < 3 else "Lone Wolf (Lvl 3+)"
            prog = calculate_level_progress(acc["level"], current_exp)
            acc["next_level"], acc["remaining_exp"] = prog["next_level"], prog["remaining_exp"]
            acc["target_exp"], acc["needed_for_level"] = prog["target_exp"], prog["needed_for_level"]
            acc["earned_in_level"], acc["progress_pct"] = prog["earned_in_level"], prog["progress_pct"]
            acc["last_updated"] = time.time()
            if old_level < 3 and current_lvl >= 3:
                self.log(f"🎉 LEVEL UP! UID {uid_str} → Level {current_lvl}! BR→LW", "success", uid_str)
            diff = current_exp - old_exp
            if diff > 0:
                self.log(f"★ UID {uid_str} +{diff:,} EXP | Lvl {acc['level']} [{acc['mode']}] ({prog['progress_pct']}%)", "success", uid_str)
            self.recalc_totals()

    def get_account_level(self, uid):
        uid_str = str(uid)
        acc = self.accounts.get(uid_str)
        if not acc:
            mapped = self.game_to_auth_id.get(uid_str) or self.auth_to_game_id.get(uid_str)
            if mapped and mapped in self.accounts: acc = self.accounts[mapped]
        if acc: return int(acc.get("level", 1) or 1)
        return 1

    def get_account_mode(self, uid):
        lvl = self.get_account_level(uid)
        return "BR" if lvl < 3 else "LONE_WOLF"

    def update_status(self, uid, status, active_matches=None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if active_matches is not None: self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.time()

    def update_match_stats(self, uid, total=None, alive=None, dead=None, mode=None, started_at=None, clear=False):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            if clear:
                acc["match_total_players"] = acc["match_alive_players"] = acc["match_dead_players"] = 0
                acc["match_mode"], acc["match_started_at"] = "", None
            else:
                if total is not None: acc["match_total_players"] = total
                if alive is not None: acc["match_alive_players"] = alive
                if dead is not None: acc["match_dead_players"] = dead
                if mode is not None: acc["match_mode"] = mode
                if started_at is not None: acc["match_started_at"] = started_at
            acc["last_updated"] = time.time()

    def track_activity(self, uid, action, extra=None):
        uid_str = str(uid)
        if uid_str not in self.accounts: return
        acc = self.accounts[uid_str]
        now = time.time()
        acc["last_activity"], acc["last_action"] = now, action
        if action == "fire_lw": acc["last_fire_lw"] = now
        elif action == "fire_br": acc["last_fire_br"] = now
        elif action == "queue_confirm": acc["last_queue_confirm"] = now
        elif action == "match_found": acc["last_match_found"] = now
        elif action == "match_start": acc["last_match_start"] = now
        elif action in ("match_done", "match_failed"): acc["last_match_end"] = now
        elif action == "error": acc["last_error"] = str(extra or "")

    def increment_match_started(self):
        self.total_matches_started += 1

    def increment_match(self, uid):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            self.accounts[uid_str]["matches_played"] += 1
            self.accounts[uid_str]["last_match_time"] = time.strftime("%H:%M:%S")
            self.accounts[uid_str]["last_updated"] = time.time()

    def recalc_totals(self):
        self.total_gained_exp = sum(acc.get("gained_exp", 0) for acc in self.accounts.values())

bot_state = BotState()

FALLBACK_INDEX_HTML = """<!DOCTYPE html><html><head><title>🔴 XIRUS MODZ 🔵</title></head><body style="background:#0a0e0a;color:#00ff88;font-family:monospace;text-align:center;padding:50px;"><h1>XIRUS MODZ DASHBOARD</h1><p>Running Without UI Auth. Web interface connected.</p></body></html>"""

# ==================== MAIN API HANDLERS (No Auth) ====================
async def handle_index(request: web.Request) -> web.Response:
    content = FALLBACK_INDEX_HTML
    if os.path.exists(TEMPLATE_PATH):
        try:
            with open(TEMPLATE_PATH, "r", encoding="utf-8") as f: content = f.read()
        except Exception: pass
    return web.Response(text=content, content_type="text/html", charset="utf-8")

async def handle_get_stats(request: web.Request) -> web.Response:
    accounts_data = list(bot_state.accounts.values())
    accounts_data.sort(key=lambda x: x.get("gained_exp", 0), reverse=True)
    uptime_sec = max(1, int(time.time() - bot_state.start_time))
    my_total_gained = sum(acc.get("gained_exp", 0) for acc in accounts_data)
    exp_per_hour = int((my_total_gained / uptime_sec) * 3600) if uptime_sec > 0 else 0
    total_active_matches = sum(acc.get("active_matches", 0) for acc in accounts_data)

    for acc in accounts_data:
        uid_k = str(acc.get("uid", ""))
        acc["uptime_seconds"] = bot_state.get_account_uptime(uid_k)
        acc["is_paused"] = bot_state.is_paused(uid_k)
        acc.setdefault("match_total_players", 0)
        acc.setdefault("match_alive_players", 0)
        acc.setdefault("match_dead_players", 0)
        acc.setdefault("match_mode", "")
        acc.setdefault("match_started_at", None)

    return web.json_response({
        "total_accounts": len(accounts_data),
        "total_matches": sum(acc.get("matches_played", 0) for acc in accounts_data),
        "total_matches_started": bot_state.total_matches_started,
        "total_active_matches": total_active_matches,
        "total_gained_exp": my_total_gained,
        "exp_per_hour": exp_per_hour,
        "accounts": accounts_data,
        "logs": bot_state.logs[-200:],
        "uptime": uptime_sec
    })

async def handle_all_logs(request: web.Request) -> web.Response:
    return web.json_response({"logs": bot_state.logs[-250:]})

async def handle_account_logs(request: web.Request) -> web.Response:
    uid = request.match_info.get("uid", "").strip()
    if not uid: return web.json_response({"uid": "", "logs": []})
    logs = bot_state.account_logs.get(uid, [])
    if not logs:
        mapped = bot_state.game_to_auth_id.get(uid) or bot_state.auth_to_game_id.get(uid)
        if mapped: logs = bot_state.account_logs.get(mapped, [])
    return web.json_response({"uid": uid, "logs": logs[-100:]})

async def handle_account_settings(request: web.Request) -> web.Response:
    uid = request.match_info.get("uid", "").strip()
    if not uid: return web.json_response({"status": "error", "error": "UID required"})
    acc = bot_state.accounts.get(uid)
    if not acc: return web.json_response({"status": "error", "error": "Account not found"})
    auth_uid, password, owner = acc.get("auth_uid", ""), "", "admin"
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f: accs = json.load(f)
            for a in accs:
                if str(a.get("uid", "")) == auth_uid or str(a.get("uid", "")) == uid:
                    password = a.get("password", "")
                    break
        except Exception: pass
    return web.json_response({
        "status": "ok", "uid": uid, "auth_uid": auth_uid, "password": password, "owner": owner,
        "nickname": acc.get("nickname", ""), "region": acc.get("region", ""),
        "level": acc.get("level", 1), "created_at": acc.get("start_time", 0),
    })

async def handle_add_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        owner = "admin"
        existing = []
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f: existing = json.load(f)
            except Exception: existing = []
        if "uid" in data and "password" in data:
            uid, pwd = str(data["uid"]).strip(), str(data["password"]).strip()
            if not uid or not pwd: return web.json_response({"status": "error", "error": "UID/Password required"})
            if uid in bot_state.account_workers:
                try: bot_state.account_workers[uid].cancel()
                except Exception: pass
                bot_state.account_workers.pop(uid, None)
            existing = [a for a in existing if not str(a.get("uid", "")) == uid]
            existing.append({"uid": uid, "password": pwd, "owner": owner})
            identifier = uid
        elif "token" in data:
            token = str(data["token"]).strip()
            if not token: return web.json_response({"status": "error", "error": "Token required"})
            tok_key = token[:16]
            for k in list(bot_state.account_workers.keys()):
                if k == tok_key or k.startswith(tok_key[:10]) or tok_key.startswith(k[:10]):
                    try: bot_state.account_workers[k].cancel()
                    except Exception: pass
                    bot_state.account_workers.pop(k, None)
            existing = [a for a in existing if not a.get("token", "") == token]
            existing.append({"token": token, "owner": owner})
            identifier = f"Token_{token[:8]}..."
        else: return web.json_response({"status": "error", "error": "Invalid payload"})
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f: json.dump(existing, f, indent=2)
        bot_state.log(f"New account added: {identifier} by {owner}", "success")
        if "on_account_added" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"]({**data, "owner": owner}))
        return web.json_response({"status": "ok"})
    except Exception as e: return web.json_response({"status": "error", "error": str(e)})

async def handle_bulk_upload(request: web.Request) -> web.Response:
    try:
        owner = "admin"
        content_text = None
        ctype = request.content_type.lower() if request.content_type else ""
        if "multipart/form-data" in ctype:
            reader = await request.multipart()
            while True:
                part = await reader.next()
                if part is None: break
                if part.name in ("file", "accounts", "data"):
                    raw = await part.read()
                    try: content_text = raw.decode("utf-8", "ignore")
                    except Exception: content_text = raw.decode("latin-1", "ignore")
                    break
        else:
            raw = await request.read()
            try: content_text = raw.decode("utf-8", "ignore")
            except Exception: content_text = raw.decode("latin-1", "ignore")
        if not content_text: return web.json_response({"status": "error", "error": "Empty file"})
        parsed = parse_accounts_file(content_text)
        if not parsed: return web.json_response({"status": "error", "error": "No uid/password pairs found"})
        existing = []
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f: existing = json.load(f)
            except Exception: existing = []
        my_uids = {str(a.get("uid", "")).strip() for a in existing if a.get("uid")}
        added, skipped = [], 0
        for entry in parsed:
            uid = entry["uid"]
            if uid in my_uids:
                skipped += 1
                continue
            existing.append({**entry, "owner": owner})
            my_uids.add(uid)
            added.append(entry)
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f: json.dump(existing, f, indent=2)
        bot_state.log(f"📦 Bulk by {owner}: {len(added)} added, {skipped} dupes", "success")
        if added and "on_account_added" in bot_state.refresh_callbacks:
            for entry in added:
                asyncio.create_task(bot_state.refresh_callbacks["on_account_added"]({"uid": entry["uid"], "password": entry["password"], "owner": owner}))
        return web.json_response({
            "status": "ok", "added": len(added), "skipped": skipped, "total": len(existing),
            "preview": [{"uid": a["uid"], "password": a["password"][:4] + "***"} for a in added[:15]]
        })
    except Exception as e: return web.json_response({"status": "error", "error": str(e)})

async def handle_delete_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        req_uid, req_auth_uid = str(data.get("uid", "")).strip(), str(data.get("auth_uid", "")).strip()
        if not req_uid and not req_auth_uid: return web.json_response({"status": "error", "error": "UID required"})
        candidate_ids = set()
        if req_uid: candidate_ids.add(req_uid)
        if req_auth_uid: candidate_ids.add(req_auth_uid)
        for cid in list(candidate_ids):
            if cid in bot_state.game_to_auth_id: candidate_ids.add(str(bot_state.game_to_auth_id[cid]))
            if cid in bot_state.auth_to_game_id: candidate_ids.add(str(bot_state.auth_to_game_id[cid]))
        for cid in list(candidate_ids):
            acc_info = bot_state.accounts.get(cid, {})
            if acc_info:
                if acc_info.get("auth_uid"): candidate_ids.add(str(acc_info["auth_uid"]))
                if acc_info.get("uid"): candidate_ids.add(str(acc_info["uid"]))
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f: existing = json.load(f)
                new_existing = [acc for acc in existing if not (str(acc.get("uid", "")).strip() in candidate_ids)]
                with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f: json.dump(new_existing, f, indent=2)
            except Exception: pass
        for cid in candidate_ids:
            bot_state.accounts.pop(cid, None)
            bot_state.account_credentials.pop(cid, None)
            bot_state.auth_to_game_id.pop(cid, None)
            bot_state.game_to_auth_id.pop(cid, None)
            bot_state.account_token_map.pop(cid, None)
            bot_state.account_logs.pop(cid, None)
        cancelled = []
        for k, worker in list(bot_state.account_workers.items()):
            if str(k) in candidate_ids:
                try: worker.cancel()
                except Exception: pass
                cancelled.append(k)
        for k in cancelled: bot_state.account_workers.pop(k, None)
        if "on_account_deleted" in bot_state.refresh_callbacks:
            try: asyncio.create_task(bot_state.refresh_callbacks["on_account_deleted"](list(candidate_ids)))
            except Exception: pass
        bot_state.log(f"Account {req_uid or req_auth_uid} deleted by admin", "warning")
        bot_state.recalc_totals()
        return web.json_response({"status": "ok", "deleted": list(candidate_ids)})
    except Exception as e: return web.json_response({"status": "error", "error": str(e)})

async def handle_refresh_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if "on_refresh_account" in bot_state.refresh_callbacks: asyncio.create_task(bot_state.refresh_callbacks["on_refresh_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e: return web.json_response({"status": "error", "error": str(e)})

async def handle_restart_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if "on_restart_account" in bot_state.refresh_callbacks: asyncio.create_task(bot_state.refresh_callbacks["on_restart_account"](uid))
        elif "on_refresh_account" in bot_state.refresh_callbacks: asyncio.create_task(bot_state.refresh_callbacks["on_refresh_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e: return web.json_response({"status": "error", "error": str(e)})

async def handle_clear_logs(request: web.Request) -> web.Response:
    for uid in bot_state.accounts.keys(): bot_state.account_logs.pop(uid, None)
    return web.json_response({"status": "ok"})

async def handle_toggle_pause(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if not uid: return web.json_response({"status": "error", "error": "UID required"})
        is_paused = bot_state.toggle_pause(uid)
        return web.json_response({"status": "ok", "is_paused": is_paused})
    except Exception as e: return web.json_response({"status": "error", "error": str(e)})

async def handle_toggle_pause_all(request: web.Request) -> web.Response:
    try:
        paused_state = bot_state.toggle_pause_all()
        return web.json_response({"status": "ok", "all_paused": paused_state})
    except Exception as e: return web.json_response({"status": "error", "error": str(e)})

# ==================== TELEGRAM BOT INTEGRATION ====================
AUTHORIZED_TG_USERS = set()
TG_LIVE_MESSAGES = {}
LAST_TG_TEXTS = {}
TG_USER_VIEW = {}
TG_FSM_STATE = {}

def load_tg_users():
    global AUTHORIZED_TG_USERS
    AUTHORIZED_TG_USERS.add(str(ADMIN_ID))
    if os.path.exists(TG_USERS_FILE):
        try:
            with open(TG_USERS_FILE, "r") as f: AUTHORIZED_TG_USERS.update(json.load(f))
        except: pass

def save_tg_users():
    with open(TG_USERS_FILE, "w") as f: json.dump(list(AUTHORIZED_TG_USERS), f)

async def send_tg_message(session, url, chat_id, text, reply_markup=None, reply_to=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup: payload["reply_markup"] = reply_markup
    if reply_to: payload["reply_to_message_id"] = reply_to
    async with session.post(f"{url}/sendMessage", json=payload) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data.get("result", {}).get("message_id")
    return None

async def edit_tg_message(session, url, chat_id, msg_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "HTML"}
    if reply_markup: payload["reply_markup"] = reply_markup
    try:
        async with session.post(f"{url}/editMessageText", json=payload) as resp:
            return resp.status == 200
    except Exception: return False

async def answer_cb(session, url, callback_query_id, text=""):
    payload = {"callback_query_id": callback_query_id, "text": text}
    try:
        async with session.post(f"{url}/answerCallbackQuery", json=payload): pass
    except: pass

def get_live_clock():
    return f"🕒 <b>Live Sync:</b> <code>{time.strftime('%H:%M:%S')}</code>"

# --- TELEGRAM VIEWS ---
def get_main_menu_data():
    accs = list(bot_state.accounts.values())
    tot_matches = sum(a.get('matches_played', 0) for a in accs)
    tot_exp = sum(a.get('gained_exp', 0) for a in accs)
    uptime = format_uptime(time.time() - bot_state.start_time)
    
    text = (
        f"<b>🔴 XIRUS MODZ DASHBOARD 🔵</b>\n"
        f"{get_live_clock()}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Accounts:</b> <code>{len(accs)}</code>\n"
        f"⚔️ <b>Total Matches:</b> <code>{tot_matches}</code>\n"
        f"🏆 <b>Total EXP Gained:</b> <code>+{tot_exp:,}</code>\n"
        f"⏱ <b>System Uptime:</b> <code>{uptime}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Navigate using the buttons below:</i>"
    )
    keyboard = {"inline_keyboard": [
        [{"text": "📊 Live Stats & Accounts", "callback_data": "menu_list"}],
        [{"text": "👤 Add Account", "callback_data": "fsm_add_single"}, {"text": "📁 Bulk Upload", "callback_data": "fsm_add_bulk"}],
        [{"text": "⏸ Pause All", "callback_data": "cmd_pauseall"}, {"text": "▶️ Resume All", "callback_data": "cmd_resumeall"}],
        [{"text": "⚙️ System Health", "callback_data": "menu_health"}]
    ]}
    return text, keyboard

def get_accounts_list_data():
    accs = list(bot_state.accounts.values())
    text = (
        f"<b>🔴 XIRUS MODZ - LIVE LIST 🔵</b>\n"
        f"{get_live_clock()}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <i>Click an account to manage:</i>"
    )
    keyboard = []
    for a in accs:
        status = "⏸" if a.get("is_paused") else "▶️"
        btn_txt = f"{status} {a.get('nickname', 'User')} - ({a['uid']})"
        keyboard.append([{"text": btn_txt, "callback_data": f"viewacc_{a['uid']}"}])
        
    keyboard.append([{"text": "🔙 Main Menu", "callback_data": "menu_main"}])
    return text, {"inline_keyboard": keyboard}

def get_single_acc_data(uid):
    acc = bot_state.accounts.get(uid)
    if not acc: 
        return f"<b>🔴 XIRUS MODZ 🔵</b>\n❌ Account <code>{uid}</code> deleted.", {"inline_keyboard": [[{"text": "🔙 Back", "callback_data": "menu_list"}]]}
    
    status_icon = "⏸ PAUSED" if acc.get("is_paused") else "▶️ ONLINE"
    added_ago = format_uptime(time.time() - acc.get("start_time", time.time()))
    bar = acc.get("visual_bar", "[█████░░░░░]")
    
    text = (
        f"<b>🔴 ACCOUNT DETAILS 🔵</b>\n"
        f"{get_live_clock()}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Name:</b> <code>{acc.get('nickname', 'N/A')}</code>\n"
        f"🆔 <b>UID:</b> <code>{acc['uid']}</code>\n"
        f"⭐ <b>Level:</b> <code>{acc.get('level', 1)}</code>\n"
        f"📊 <b>Progress:</b> <code>{bar}</code> {acc.get('progress_pct',0)}%\n"
        f"✨ <b>EXP:</b> <code>{acc.get('initial_exp', 0)}</code> ➔ <code>{acc.get('current_exp', 0)}</code>\n"
        f"📈 <b>Gained:</b> <code>+{acc.get('gained_exp', 0)}</code>\n"
        f"⚔️ <b>Matches:</b> <code>{acc.get('matches_played', 0)}</code>\n"
        f"🚦 <b>Status:</b> <b>{status_icon}</b>\n"
        f"⏱ <b>Added:</b> <code>{added_ago} ago</code>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    
    toggle_txt = "▶️ Resume" if acc.get("is_paused") else "⏸ Stop"
    toggle_cb = f"resume_{uid}" if acc.get("is_paused") else f"pause_{uid}"
    
    keyboard = {"inline_keyboard": [
        [{"text": toggle_txt, "callback_data": toggle_cb}, {"text": "🗑 Delete", "callback_data": f"del_{uid}"}],
        [{"text": "🔙 Back to List", "callback_data": "menu_list"}, {"text": "🏠 Home", "callback_data": "menu_main"}]
    ]}
    return text, keyboard

def get_health_data():
    uptime = format_uptime(time.time() - bot_state.start_time)
    ping = f"{bot_state.ping_ms:.1f}ms" if bot_state.ping_ms > 0 else "Calculating..."
    text = (
        f"<b>🔴 XIRUS MODZ - SYSTEM HEALTH 🔵</b>\n"
        f"{get_live_clock()}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ <b>Uptime:</b> <code>{uptime}</code>\n"
        f"⚡ <b>API Ping:</b> <code>{ping}</code>\n"
        "🌐 <b>Web Server:</b> 🟢 <code>ONLINE</code>\n"
        "🤖 <b>Bot Engine:</b> 🟢 <code>ONLINE</code>\n"
        "💾 <b>Database:</b> 🟢 <code>SYNCED</code>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    keyboard = {"inline_keyboard": [[{"text": "🔙 Back", "callback_data": "menu_main"}]]}
    return text, keyboard

def resolve_view(chat_id):
    view = TG_USER_VIEW.get(chat_id, "menu")
    if view == "menu": return get_main_menu_data()
    elif view == "list": return get_accounts_list_data()
    elif view == "health": return get_health_data()
    elif view.startswith("acc_"): return get_single_acc_data(view.split("_")[1])
    return get_main_menu_data()

async def tg_live_updater(session, url):
    while True:
        start_t = time.monotonic()
        await asyncio.sleep(1.0)
        bot_state.ping_ms = (time.monotonic() - start_t) * 1000 
        
        if not TG_LIVE_MESSAGES: continue
        for chat_id, msg_id in list(TG_LIVE_MESSAGES.items()):
            if TG_FSM_STATE.get(chat_id, {}).get("step", "IDLE") != "IDLE": continue
            new_text, keyboard = resolve_view(chat_id)
            if LAST_TG_TEXTS.get(chat_id) == new_text: continue 
            try:
                await edit_tg_message(session, url, chat_id, msg_id, new_text, keyboard)
                LAST_TG_TEXTS[chat_id] = new_text
            except Exception: pass

async def process_callback(session, url, cb):
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    user_id = str(cb["from"]["id"])
    data = cb.get("data", "")
    
    if user_id not in AUTHORIZED_TG_USERS:
        await answer_cb(session, url, cb["id"], "❌ Unauthorized!")
        return

    await answer_cb(session, url, cb["id"])

    if data == "menu_main": TG_USER_VIEW[chat_id] = "menu"
    elif data == "menu_list": TG_USER_VIEW[chat_id] = "list"
    elif data == "menu_health": TG_USER_VIEW[chat_id] = "health"
    elif data.startswith("viewacc_"): TG_USER_VIEW[chat_id] = f"acc_{data.split('_')[1]}"
    
    elif data == "fsm_add_single":
        TG_FSM_STATE[chat_id] = {"step": "WAIT_UID", "uid": ""}
        text = "<b>🔴 XIRUS MODZ - SINGLE ACCOUNT 🔵</b>\n\n📝 <b>Please type the UID in chat:</b>\n<i>(Type /cancel to abort)</i>"
        await edit_tg_message(session, url, chat_id, msg_id, text, None)
        return

    elif data == "fsm_add_bulk":
        TG_FSM_STATE[chat_id] = {"step": "WAIT_FILE", "uid": ""}
        text = "<b>🔴 XIRUS MODZ - BULK UPLOAD 🔵</b>\n\n📁 <b>Please upload your .txt or .json file:</b>\n<i>(Type /cancel to abort)</i>"
        await edit_tg_message(session, url, chat_id, msg_id, text, None)
        return

    elif data == "fsm_cancel":
        TG_FSM_STATE[chat_id] = {"step": "IDLE"}
        TG_USER_VIEW[chat_id] = "menu"

    elif data.startswith("pause_"): bot_state.toggle_pause(data.split("_")[1])
    elif data.startswith("resume_"): bot_state.toggle_pause(data.split("_")[1])
    elif data.startswith("del_"):
        uid = data.split("_")[1]
        existing = []
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, "r") as f: existing = json.load(f)
        existing = [a for a in existing if str(a.get("uid", "")) != uid]
        with open(ACCOUNTS_FILE, "w") as f: json.dump(existing, f, indent=2)
        bot_state.accounts.pop(uid, None)
        TG_USER_VIEW[chat_id] = "list"
        
    elif data == "cmd_pauseall": bot_state.toggle_pause_all()
    elif data == "cmd_resumeall": bot_state.toggle_pause_all()

    new_text, keyboard = resolve_view(chat_id)
    LAST_TG_TEXTS[chat_id] = new_text
    await edit_tg_message(session, url, chat_id, msg_id, new_text, keyboard)

async def process_message(session, url, msg):
    chat_id = msg["chat"]["id"]
    user_id = str(msg["from"]["id"])
    text = msg.get("text", "").strip()

    if text.startswith("/add") and "reply_to_message" in msg:
        if user_id == str(ADMIN_ID):
            t_id = str(msg["reply_to_message"]["from"]["id"])
            AUTHORIZED_TG_USERS.add(t_id); save_tg_users()
            await send_tg_message(session, url, chat_id, f"✅ Admin Added: <code>{t_id}</code>")
        return
    if text.startswith("/remove") and "reply_to_message" in msg:
        if user_id == str(ADMIN_ID):
            t_id = str(msg["reply_to_message"]["from"]["id"])
            AUTHORIZED_TG_USERS.discard(t_id); save_tg_users()
            await send_tg_message(session, url, chat_id, f"❌ Admin Removed: <code>{t_id}</code>")
        return

    if user_id not in AUTHORIZED_TG_USERS: return

    state = TG_FSM_STATE.get(chat_id, {}).get("step", "IDLE")
    if text.lower() == "/cancel" and state != "IDLE":
        TG_FSM_STATE[chat_id] = {"step": "IDLE"}
        await send_tg_message(session, url, chat_id, "❌ Cancelled.")
        TG_USER_VIEW[chat_id] = "menu"
        msg_id = await send_tg_message(session, url, chat_id, *resolve_view(chat_id))
        if msg_id: TG_LIVE_MESSAGES[chat_id] = msg_id
        return

    if "document" in msg and state == "WAIT_FILE":
        file_id = msg["document"].get("file_id")
        if not file_id: return
        try:
            async with session.get(f"{url}/getFile?file_id={file_id}") as r:
                file_data = await r.json()
                file_path = file_data["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            async with session.get(download_url) as r: content = await r.text()
            parsed = parse_accounts_file(content)
            if not parsed:
                await send_tg_message(session, url, chat_id, "<b>🔴 XIRUS MODZ 🔵</b>\n❌ No valid UID/Password pairs found.")
                return
            existing = []
            if os.path.exists(ACCOUNTS_FILE):
                with open(ACCOUNTS_FILE, "r") as f: existing = json.load(f)
            added = 0
            existing_uids = {str(a.get("uid")) for a in existing}
            for p in parsed:
                if p["uid"] not in existing_uids:
                    existing.append(p)
                    added += 1
            with open(ACCOUNTS_FILE, "w") as f: json.dump(existing, f, indent=2)
            if added and "on_account_added" in bot_state.refresh_callbacks:
                for p in parsed:
                    if p["uid"] not in existing_uids:
                        asyncio.create_task(bot_state.refresh_callbacks["on_account_added"]({"uid": p["uid"], "password": p["password"], "owner": "admin"}))
            await send_tg_message(session, url, chat_id, f"<b>🔴 XIRUS MODZ 🔵</b>\n✅ <b>Bulk Upload Success!</b>\nAdded <code>{added}</code> accounts.")
        except Exception as e:
            await send_tg_message(session, url, chat_id, f"❌ Error processing file: {e}")
        
        TG_FSM_STATE[chat_id] = {"step": "IDLE"}
        TG_USER_VIEW[chat_id] = "menu"
        msg_id = await send_tg_message(session, url, chat_id, *resolve_view(chat_id))
        if msg_id: TG_LIVE_MESSAGES[chat_id] = msg_id
        return

    if state == "WAIT_UID":
        TG_FSM_STATE[chat_id] = {"step": "WAIT_PWD", "uid": text}
        if chat_id in TG_LIVE_MESSAGES:
            await edit_tg_message(session, url, chat_id, TG_LIVE_MESSAGES[chat_id], f"✅ UID Saved: <code>{text}</code>\n🔑 <b>Now type Password:</b>")
        else: await send_tg_message(session, url, chat_id, f"🔑 <b>Now type Password:</b>")
        return

    elif state == "WAIT_PWD":
        uid = TG_FSM_STATE[chat_id]["uid"]
        TG_FSM_STATE[chat_id] = {"step": "IDLE"}
        
        bot_state.register_account(uid, f"New_{uid[:4]}", "IND", 1, 0)
        existing = []
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, "r") as f: existing = json.load(f)
        existing.append({"uid": uid, "password": text, "owner": "admin"})
        with open(ACCOUNTS_FILE, "w") as f: json.dump(existing, f, indent=2)

        if "on_account_added" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"]({"uid": uid, "password": text, "owner": "admin"}))

        success_msg = f"<b>🔴 XIRUS MODZ 🔵</b>\n✅ Account <code>{uid}</code> Added!"
        if chat_id in TG_LIVE_MESSAGES:
            await edit_tg_message(session, url, chat_id, TG_LIVE_MESSAGES[chat_id], success_msg)
            await asyncio.sleep(1.5)
            TG_USER_VIEW[chat_id] = "menu"
            await edit_tg_message(session, url, chat_id, TG_LIVE_MESSAGES[chat_id], *resolve_view(chat_id))
        return

    if text.startswith(("/start", "/menu", "/stats")):
        if chat_id in TG_LIVE_MESSAGES: TG_LIVE_MESSAGES.pop(chat_id)
        TG_USER_VIEW[chat_id] = "menu"
        v_text, v_kb = resolve_view(chat_id)
        msg_id = await send_tg_message(session, url, chat_id, v_text, v_kb)
        if msg_id: TG_LIVE_MESSAGES[chat_id] = msg_id

async def tg_polling_loop():
    load_tg_users()
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    offset = 0
    print("[TG] 🔴 XIRUS MODZ Telegram Engine Active 🔵")
    async with aiohttp.ClientSession() as session:
        asyncio.create_task(tg_live_updater(session, url))
        while True:
            try:
                async with session.get(f"{url}/getUpdates?offset={offset}&timeout=30") as resp:
                    if resp.status == 200:
                        for up in (await resp.json()).get("result", []):
                            offset = up["update_id"] + 1
                            if "callback_query" in up: await process_callback(session, url, up["callback_query"])
                            elif "message" in up: await process_message(session, url, up["message"])
                    else: await asyncio.sleep(2)
            except Exception: await asyncio.sleep(3)

# ==================== 🚀 ENTRY POINT (REQUIRED BY MAIN.PY) 🚀 ====================
async def start_web_dashboard(host: str = "0.0.0.0", port: int = 5000):
    app = web.Application(client_max_size=50 * 1024 * 1024)
    
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/stats", handle_get_stats)
    app.router.add_get("/api/logs", handle_all_logs)
    app.router.add_get("/api/logs/{uid}", handle_account_logs)
    app.router.add_get("/api/account/settings/{uid}", handle_account_settings)
    app.router.add_post("/api/account/add", handle_add_account)
    app.router.add_post("/api/accounts/bulk_upload", handle_bulk_upload)
    app.router.add_post("/api/account/delete", handle_delete_account)
    app.router.add_post("/api/account/refresh", handle_refresh_account)
    app.router.add_post("/api/account/restart", handle_restart_account)
    app.router.add_post("/api/account/pause", handle_toggle_pause)
    app.router.add_post("/api/account/pause_all", handle_toggle_pause_all)
    app.router.add_post("/api/logs/clear", handle_clear_logs)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    print(f"\n[+] 🔴 XIRUS MODZ Server Running at http://{host}:{port}/ 🔵")
    asyncio.create_task(tg_polling_loop())

if __name__ == "__main__":
    try: asyncio.run(start_web_dashboard())
    except KeyboardInterrupt: print("\n[-] XIRUS MODZ Shutdown.")
