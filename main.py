# ==================== STANDARD IMPORTS ====================
import sys
import asyncio
import httpx
import random
import json
import socket
import struct
import time
import os
import uuid
import itertools
import base64
import re
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    from google.protobuf import runtime_version  # noqa: F401
except ImportError:
    import types as _types
    import sys as _sys
    try:
        import google.protobuf as _gp
        _fake = _types.ModuleType("google.protobuf.runtime_version")

        class _FakeVer:
            def __init__(self, *a, **k):
                self._parts = a if a else (0, 0, 0)
            def __str__(self):
                return ".".join(str(p) for p in self._parts)
        def _noop_validate(*a, **k):
            return None
        _fake.Version = _FakeVer
        _fake.ValidateProtobufRuntimeVersion = _noop_validate
        _sys.modules["google.protobuf.runtime_version"] = _fake
        try:
            _gp.runtime_version = _fake
        except Exception:
            pass
    except Exception:
        pass

from google_play_scraper import app as play_scraper
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from protobuf_decoder.protobuf_decoder import Parser
from message_ids import MESSAGE_ID_TO_NAME
import thunderFF_pb2
import StartMatch_pb2
import requests
import urllib3

try:
    import blackboxprotobuf
except ImportError:
    try:
        import bbpb as blackboxprotobuf
    except ImportError:
        blackboxprotobuf = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from dashboard_server import bot_state, start_web_dashboard

try:
    from bot import start_telegram_bot, stop_telegram_bot
    HAS_TG = True
except Exception:
    HAS_TG = False
    async def start_telegram_bot():
        return None
    async def stop_telegram_bot():
        return None


# ==================== CONFIG ====================
WEB_HOST = "0.0.0.0"
WEB_PORT = int(os.environ.get("PORT", 20338))
ACCOUNTS_FILE = "accounts.json"
STOPPED_FILE = "stopped_accounts.json"
TOKEN_CACHE_FILE = "token_cache.json"
DEVICES_FILE = "devices.json"
TOKEN_CACHE_TTL = 1200

DEFAULT_OWNER = "admin"

# ==================== FIRE TIMINGS ====================
# LW: original
# BR: 3 sec fire + 0.5 sec new_match_delay for fast parallel
LW_FIRE_INTERVAL = 3.0              # LW fire every 3s (original)
BR_FIRE_INTERVAL = 5.0              # BR fire every 3s (FAST)

LW_MAX_MATCH_DURATION = 1000.0         # 10 min (original)
BR_MAX_MATCH_DURATION = 2000.0        # 25 min

MATCH_IDLE_TIMEOUT = 1000.0           # LW idle timeout (original)
BR_IDLE_TIMEOUT = 1500.0            # BR idle timeout — NO exit

NEW_MATCH_DELAY = 0.5               # ✅ 0.5 sec (was 2.5) for fast cycles

ANTI_AFK_ENABLED = True
ANTI_AFK_MIN_INTERVAL = 2.5
ANTI_AFK_MAX_INTERVAL = 4.5
ANTI_AFK_FIRE_CHANCE = 0.5

FALLBACK_UID = ""
FALLBACK_PASSWORD = ""
PROXIES = []
MAX_LOGIN_ATTEMPTS = 3


# ==================== CRC7 ====================
CRC7_TABLE = bytes([
    0, 9, 18, 27, 36, 45, 54, 63, 72, 65, 90, 83, 108, 101, 126, 119,
    25, 16, 11, 2, 61, 52, 47, 38, 81, 88, 67, 74, 117, 124, 103, 110,
    50, 59, 32, 41, 22, 31, 4, 13, 122, 115, 104, 97, 94, 87, 76, 69,
    43, 34, 57, 48, 15, 6, 29, 20, 99, 106, 113, 120, 71, 78, 85, 92,
    100, 109, 118, 127, 64, 73, 82, 91, 44, 37, 62, 55, 8, 1, 26, 19,
    125, 116, 111, 102, 89, 80, 75, 66, 53, 60, 39, 46, 17, 24, 3, 10,
    86, 95, 68, 77, 114, 123, 96, 105, 30, 23, 12, 5, 58, 51, 40, 33,
    79, 70, 93, 84, 107, 98, 121, 112, 7, 14, 21, 28, 35, 42, 49, 56,
    65, 72, 83, 90, 101, 108, 119, 126, 9, 0, 27, 18, 45, 36, 63, 54,
    88, 81, 74, 67, 124, 117, 110, 103, 16, 25, 2, 11, 52, 61, 38, 47,
    115, 122, 97, 104, 87, 94, 69, 76, 59, 50, 41, 32, 31, 22, 13, 4,
    106, 99, 120, 113, 78, 71, 92, 85, 34, 43, 48, 57, 6, 15, 20, 29,
    37, 44, 55, 62, 1, 8, 19, 26, 109, 100, 127, 118, 73, 64, 91, 82,
    60, 53, 46, 39, 24, 17, 10, 3, 116, 125, 102, 111, 80, 89, 66, 75,
    23, 30, 5, 12, 51, 58, 33, 40, 95, 86, 77, 68, 123, 114, 105, 96,
    14, 7, 28, 21, 42, 35, 56, 49, 70, 79, 84, 93, 98, 107, 112, 121,
])


# ==================== ACCOUNT LEVEL FOLDER ====================
ACCOUNT_LVL_DIR = "Account lvl"


def _lvl_folder_for_region(region):
    return os.path.join(ACCOUNT_LVL_DIR, (region or "IND").upper().lower())


def _lvl_file_path(region, level):
    return os.path.join(_lvl_folder_for_region(region), f"{int(level)}lvl_account.json")


def _read_json_list(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_json_list(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print_error(f"[LVL] write failed {path}: {e}")


def _find_original_account_entry(account_data):
    try:
        accounts = load_accounts()
        auth_uid = str(account_data.get("auth_uid", "") or "")
        for acc in accounts:
            if auth_uid and str(acc.get("uid")) == auth_uid:
                return acc
    except Exception:
        pass
    return None


def _remove_from_all_lvl_files(region, game_uid, auth_uid, except_level=None):
    folder = _lvl_folder_for_region(region)
    if not os.path.isdir(folder):
        return None
    removed_from = None
    for fname in list(os.listdir(folder)):
        if not fname.endswith("lvl_account.json"):
            continue
        try:
            lvl = int(fname.replace("lvl_account.json", ""))
        except Exception:
            continue
        if except_level is not None and lvl == except_level:
            continue
        fpath = os.path.join(folder, fname)
        data = _read_json_list(fpath)
        new_data = [
            a for a in data
            if not (str(a.get("game_uid", "")) == game_uid or (auth_uid and str(a.get("uid", "")) == auth_uid))
        ]
        if len(new_data) != len(data):
            removed_from = lvl
            if new_data:
                _write_json_list(fpath, new_data)
            else:
                try:
                    os.remove(fpath)
                except Exception:
                    pass
            break
    return removed_from


def _remove_account_from_all_level_folders(uid_str, game_uid=None):
    base = ACCOUNT_LVL_DIR
    if not os.path.isdir(base):
        return 0
    uid_str = str(uid_str)
    game_uid = str(game_uid) if game_uid else None
    removed = 0
    for region in list(os.listdir(base)):
        folder = os.path.join(base, region)
        if not os.path.isdir(folder):
            continue
        for fname in list(os.listdir(folder)):
            if not fname.endswith("lvl_account.json"):
                continue
            fpath = os.path.join(folder, fname)
            data = _read_json_list(fpath)
            new_data = []
            for a in data:
                au = str(a.get("uid", ""))
                ag = str(a.get("game_uid", ""))
                if au == uid_str or ag == uid_str:
                    continue
                if game_uid and (ag == game_uid or au == game_uid):
                    continue
                new_data.append(a)
            if len(new_data) != len(data):
                removed += (len(data) - len(new_data))
                if new_data:
                    _write_json_list(fpath, new_data)
                else:
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
    if removed:
        try:
            print_warning(f"[LVL] Removed {removed} entries for {uid_str} from level folders", uid=uid_str)
        except Exception:
            pass
    return removed


def sync_account_level_folder(account_data):
    try:
        game_uid = str(account_data.get("account_id", "") or "")
        auth_uid = str(account_data.get("auth_uid", "") or "")
        if not game_uid and not auth_uid:
            return
        nickname = account_data.get("nickname", "") or ""
        level = int(account_data.get("level", 1) or 1)
        if level < 1:
            level = 1
        elif level > 100:
            level = 100
        region = (account_data.get("region") or "IND").upper()

        prev_level = _remove_from_all_lvl_files(region, game_uid, auth_uid, except_level=level)
        path = _lvl_file_path(region, level)
        data = _read_json_list(path)

        existing_idx = -1
        for i, a in enumerate(data):
            if str(a.get("game_uid", "")) == game_uid or (auth_uid and str(a.get("uid", "")) == auth_uid):
                existing_idx = i
                break

        if existing_idx >= 0:
            ex = data[existing_idx]
            if (int(ex.get("level", 0)) == level and
                ex.get("nickname") == nickname and
                str(ex.get("game_uid", "")) == game_uid and
                ex.get("region", "").upper() == region):
                return

        orig = _find_original_account_entry(account_data)
        pwd = None
        if orig:
            pwd = orig.get("password")
        if not pwd and account_data.get("auth_password"):
            pwd = account_data["auth_password"]
        if not pwd and auth_uid:
            try:
                for acc in load_accounts():
                    if str(acc.get("uid")) == auth_uid:
                        pwd = acc.get("password")
                        break
            except Exception:
                pass

        entry = {
            "uid": auth_uid or (orig.get("uid", "") if orig else ""),
            "password": pwd or "",
            "game_uid": game_uid,
            "nickname": nickname,
            "level": level,
            "region": region,
        }
        if account_data.get("owner"):
            entry["owner"] = account_data["owner"]
        elif orig and orig.get("owner"):
            entry["owner"] = orig["owner"]

        if existing_idx >= 0:
            data[existing_idx] = entry
        else:
            data.append(entry)

        _write_json_list(path, data)
    except Exception as e:
        print_error(f"sync_account_level_folder error: {e}")


# ==================== AUTO-ASSIGN OWNERS ====================
def _auto_assign_owners():
    try:
        if not os.path.exists(ACCOUNTS_FILE):
            return 0
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            accounts = json.load(f)
        if not isinstance(accounts, list):
            return 0
        fixed = 0
        for acc in accounts:
            if not acc.get("owner"):
                acc["owner"] = DEFAULT_OWNER
                fixed += 1
        if fixed > 0:
            try:
                backup_path = ACCOUNTS_FILE + ".backup"
                with open(backup_path, "w", encoding="utf-8") as f:
                    json.dump(accounts, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump(accounts, f, indent=2, ensure_ascii=False)
            print(f"[OWNER] Auto-assigned '{DEFAULT_OWNER}' to {fixed} accounts")
        return fixed
    except Exception as e:
        print(f"[OWNER] failed: {e}")
        return 0


# ==================== STOP / DELETE ====================
_stop_flags: Dict[str, bool] = {}
_deleted_accounts: set = set()


def mark_account_stopped(uid):
    _stop_flags[str(uid)] = True


def mark_account_deleted(uid):
    _deleted_accounts.add(str(uid))
    _stop_flags[str(uid)] = True


def is_account_stopped(uid):
    return _stop_flags.get(str(uid), False)


def is_account_deleted(uid):
    return str(uid) in _deleted_accounts


def _remove_from_accounts_json(uid_str: str) -> bool:
    try:
        if not os.path.exists(ACCOUNTS_FILE):
            return False
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            accs = json.load(f)
        if not isinstance(accs, list):
            return False
        new_accs = [a for a in accs if str(a.get("uid", "")) != uid_str]
        if len(new_accs) == len(accs):
            return False
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(new_accs, f, indent=2)
        return True
    except Exception:
        return False


# ==================== FF LOGIN ====================
@dataclass
class nMkLpQ:
    mD: str
    oS: str
    gP: str
    iP: str
    dV: str
    uA: str


class qZxWvY:
    aB1 = "https://loginbp.ppmainecoonghj.com/MajorLogin"
    aB2 = "https://client.ind.freefiremobile.com/GetLoginData"
    kY1 = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
    kV1 = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
    rV1 = "OB55"
    gV1 = "2.133.9"

    uAp1 = [
        "GarenaMSDK/4.0.46(25028RN03A ;Android 10;en;SG;app 2.133.9 2019118527;)",
        "GarenaMSDK/4.0.46(25028RN03A ;Android 10;en;IN;app 2.133.9 2019118527;)",
        "GarenaMSDK/4.0.44(25028RN03A ;Android 15;ar;EG;app 1.132.1 2019121229;)",
        "GarenaMSDK/4.0.43(25028RN03A ;Android 14;en;IN;app 1.131.1 2019121229;)",
    ]

    iPp1 = [
        "49.36.180.10","49.36.180.22","49.36.181.15","49.36.181.30",
        "103.87.24.10","103.87.24.25","103.87.25.14","103.87.25.30",
        "115.99.10.20","115.99.10.35","115.99.11.40","115.99.11.55",
        "49.36.83.10","49.36.83.22","49.36.84.15","49.36.84.30",
    ]

    dPv1 = [
        ("Asus ASUS_AI2501_B","Android OS 12 / API-31 (SP1A.210812.016.C2)","Adreno (TM) 640"),
        ("Redmi Note 12 Pro","Android OS 13 / API-33 (TP1A.220624.014)","Adreno (TM) 618"),
        ("Samsung SM-M135F","Android OS 13 / API-33 (TP1A.220624.014)","Mali-G68"),
        ("Realme RMX3630","Android OS 12 / API-31 (SP1A.210812.016)","Adreno (TM) 610"),
        ("Vivo V2149","Android OS 13 / API-33 (TP1A.220624.014)","Adreno (TM) 642L"),
        ("OnePlus CPH2411","Android OS 13 / API-33 (TP1A.220624.014)","Adreno (TM) 730"),
        ("Poco M4 Pro 5G","Android OS 12 / API-31 (SP1A.210812.016)","Mali-G57 MC2"),
        ("iQOO I2012","Android OS 13 / API-33 (TP1A.220624.014)","Adreno (TM) 650"),
    ]

    def __init__(self, pRx=None, rOt=20):
        self.pRx = pRx or []
        self.rOt = rOt
        self.cNt = 0
        self.sEs = self._bS()

    def _bS(self):
        sEs = requests.Session()
        aDp = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0)
        sEs.mount("https://", aDp)
        sEs.mount("http://", aDp)
        if self.pRx:
            pXy = random.choice(self.pRx)
            if not pXy.startswith("http"):
                pXy = f"http://{pXy}"
            sEs.proxies = {"http": pXy, "https": pXy}
        return sEs

    def _rS(self):
        self.cNt += 1
        if self.cNt >= self.rOt:
            self.cNt = 0
            self.sEs = self._bS()

    @classmethod
    def mKId(cls):
        mD, oS, gP = random.choice(cls.dPv1)
        return nMkLpQ(
            mD=mD, oS=oS, gP=gP,
            iP=random.choice(cls.iPp1),
            dV=f"Google|{uuid.uuid4()}",
            uA=random.choice(cls.uAp1),
        )

    @staticmethod
    def _eV(n):
        if n < 0:
            return b""
        bUf = bytearray()
        while True:
            bYt = n & 0x7F
            n >>= 7
            if n:
                bYt |= 0x80
            bUf.append(bYt)
            if not n:
                break
        return bytes(bUf)

    @classmethod
    def _eF(cls, fN, fV):
        if isinstance(fV, int):
            return cls._eV((fN << 3) | 0) + cls._eV(fV)
        if isinstance(fV, (str, bytes)):
            rW = fV.encode() if isinstance(fV, str) else fV
            return cls._eV((fN << 3) | 2) + cls._eV(len(rW)) + rW
        return b""

    @classmethod
    def _sM(cls, fD):
        return b"".join(cls._eF(k, v) for k, v in fD.items())

    @classmethod
    def _eP(cls, rW):
        return AES.new(cls.kY1, AES.MODE_CBC, cls.kV1).encrypt(pad(rW, AES.block_size))

    _jR = re.compile(rb"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")

    @classmethod
    def _jX(cls, bDy):
        if not bDy:
            return None
        if blackboxprotobuf is None:
            mTc = cls._jR.search(bDy)
            return mTc.group(0).decode("utf-8", "ignore") if mTc else None
        for oFf in (0, 64, 4, 8, 16):
            try:
                dEc, _ = blackboxprotobuf.decode_message(bDy[oFf:] if oFf < len(bDy) else bDy)
                if not isinstance(dEc, dict):
                    continue
                for kEy in ('8', 8, b'8', 'jwt', b'jwt', 'token', b'token'):
                    if kEy not in dEc:
                        continue
                    vAl = dEc[kEy]
                    if isinstance(vAl, bytes) and vAl.startswith(b"eyJ"):
                        return vAl.decode("utf-8", "ignore")
                    if isinstance(vAl, str) and vAl.startswith("eyJ"):
                        return vAl
            except Exception:
                continue
        mTc = cls._jR.search(bDy)
        return mTc.group(0).decode("utf-8", "ignore") if mTc else None

    def mAjL(self, tKn, oId, iDv, lNg="en"):
        tSt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        fLd = {
            3: tSt, 4: "free fire", 5: 1,
            7: "2.133.9", 8: iDv.oS, 9: "Handheld",
            10: "Vi India", 11: "WIFI",
            12: 1600, 13: 720, 14: "320",
            15: "ARM64 FP ASIMD AES | 2301 | 8", 16: 2799,
            17: iDv.gP, 18: "OpenGL ES 3.2 build 1.11@5425693",
            19: iDv.dV, 20: iDv.iP,
            21: lNg, 22: oId, 23: "4", 24: "Handheld",
            25: iDv.mD, 26: "IND", 29: tKn, 30: 1,
            41: "Vi India", 42: "WIFI",
            57: "1ac4b80ecf0478a44203bf8fac6120f5",
            60: 19799, 61: 2536, 62: 5056, 64: 2768,
            65: 19999, 66: 2536, 67: 19799,
            73: 1,
            74: "/data/app/com.dts.freefireth-FFifmAAfKh0HbXBegWOzaxw==/lib/arm64",
            76: 2,
            77: "4c322aeb56444feaa151d1ea91a8f7f2|/data/app/com.dts.freefireth-FFifmAAfKh0HbXBegWOzaxw==/base.apk",
            78: 2, 79: 2, 81: "64", 83: "2019118527",
            86: "OpenGLES3", 87: 3071, 88: 4,
            92: 67920, 93: "android_max",
            94: "KqsHT+UrR1HKqb6+1db+Ofei+NtZr2+hbiBo3yKDL8w+8E3S5qF2IgEEe1fFQFyHRzl4iyHjHp+QsfeLbjJ6+DidTiKxm0ak2uYYa6QR4nAUdlZR",
            95: 111107,
            96: '{"cur_rate":null,"support_etc2":true}',
            97: 1, 98: 1, 99: "4", 100: "4", 102: "",
            104: 83812, 105: 1,
            106: "https://dl-bs.ggpolarbear.com/live/ABHotUpdates/|https://core-bs.ggpolarbear.com/live/ABHotUpdates/|a4332cb1c1a84e51dd77441e4856ed5a",
            107: "1.9393e7b8e53e8aeb",
        }
        pLd = self._eP(self._sM(fLd))
        hDr = {
            "User-Agent": iDv.uA,
            "Accept-Encoding": "deflate, gzip",
            "X-GA-SV": "1789535859",
            "Authorization": f"Bearer {tKn}",
            "X-GA": "v1 1",
            "ReleaseVersion": self.rV1,
            "Content-Type": "application/octet-stream",
            "X-Unity-Version": "2018.4.12f1",
            "Host": "loginbp.ppmainecoonghj.com",
        }
        try:
            rSp = self.sEs.post(self.aB1, headers=hDr, data=pLd, verify=False, timeout=8)
        except requests.RequestException:
            return None
        finally:
            self._rS()

        if rSp.status_code != 200 or len(rSp.content) < 20:
            return None
        jWt = self._jX(rSp.content)
        aId = self._aX(jWt, rSp.content)

        aes_ak = None
        iv_i = None
        server_time = None
        server_url = None
        try:
            res_proto = thunderFF_pb2.MajorLoginRes()
            try:
                res_proto.ParseFromString(rSp.content)
            except Exception:
                pass
            if not res_proto.token and len(rSp.content) > 64:
                try:
                    res_proto = thunderFF_pb2.MajorLoginRes()
                    res_proto.ParseFromString(rSp.content[64:])
                except Exception:
                    pass
            if not res_proto.token:
                for offset in range(min(128, len(rSp.content))):
                    try:
                        candidate = thunderFF_pb2.MajorLoginRes()
                        candidate.ParseFromString(rSp.content[offset:])
                        if candidate.token:
                            res_proto = candidate
                            break
                    except Exception:
                        pass
            if res_proto.aes_ak:
                aes_ak = res_proto.aes_ak
            if res_proto.iv_i:
                iv_i = res_proto.iv_i
            if res_proto.server_time:
                server_time = res_proto.server_time
            if res_proto.url:
                server_url = res_proto.url
        except Exception:
            pass

        if not aes_ak or not iv_i:
            if blackboxprotobuf is not None:
                try:
                    for oFf in (0, 4, 8, 16, 64):
                        if oFf >= len(rSp.content):
                            continue
                        dEc, _ = blackboxprotobuf.decode_message(rSp.content[oFf:])
                        if not isinstance(dEc, dict):
                            continue
                        sixteen = [(k, v) for k, v in dEc.items() if isinstance(v, bytes) and len(v) == 16]
                        if len(sixteen) >= 2:
                            if not aes_ak:
                                aes_ak = sixteen[0][1]
                            if not iv_i:
                                iv_i = sixteen[1][1]
                            break
                except Exception:
                    pass

        return {
            "account_id": str(aId) if aId else None,
            "jwt": jWt or "",
            "aes_ak": aes_ak,
            "iv_i": iv_i,
            "server_time": server_time,
            "server_url": server_url,
        } if aId else None

    @classmethod
    def _aX(cls, jWt, bDy):
        if jWt and jWt.count(".") == 2:
            try:
                sEg = jWt.split(".")[1]
                sEg += "=" * (4 - len(sEg) % 4)
                dEc = json.loads(base64.urlsafe_b64decode(sEg))
                vAl = dEc.get("account_id") or dEc.get("external_id") or dEc.get("uid")
                if vAl:
                    return str(vAl)
            except Exception:
                pass
        if blackboxprotobuf is None:
            return None
        for oFf in (0, 4, 8, 16, 64):
            try:
                dEc, _ = blackboxprotobuf.decode_message(bDy[oFf:] if oFf < len(bDy) else bDy)
                if not isinstance(dEc, dict):
                    continue
                for kEy in ('3', 3, b'3', 'account_id', b'account_id'):
                    if kEy in dEc:
                        vAl = dEc[kEy]
                        return vAl.decode("utf-8", "ignore") if isinstance(vAl, bytes) else str(vAl)
            except Exception:
                continue
        return None

    def gEtL(self, tKn, oId, iDv, lNg="en"):
        if not tKn or not oId:
            return {"ok": False, "c": 0xE01, "m": "arg"}
        tSt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        fLd = {
            3: tSt, 4: "free fire", 5: 1,
            7: self.gV1, 8: iDv.oS, 9: "Handheld",
            10: "Vi India", 11: "WIFI",
            12: 1600, 13: 720, 14: "320",
            15: "ARM64 FP ASIMD AES | 2301 | 8", 16: 2799,
            17: iDv.gP, 18: "OpenGL ES 3.2 build 1.1@5425693",
            19: iDv.dV, 20: iDv.iP,
            21: lNg, 22: oId, 23: "4", 24: "Handheld",
            25: iDv.mD, 26: "IND", 29: tKn, 30: 1,
            41: "Vi India", 42: "WIFI",
            57: "1ac4b80ecf0478a44203bf8fac6120f5",
            60: 19799, 61: 2536, 62: 5056, 64: 2768,
            65: 19999, 66: 2536, 67: 19799, 70: 4, 73: 1,
            74: "/data/app/com.dts.freefireth-FFifmAAfKh0HbXBegWOzaxw==/lib/arm64",
            76: 2,
            77: "4c322aeb56444feaa151d1ea91a8f7f2|/data/app/com.dts.freefireth-FFifmAAfKh0HbXBegWOzaxw==/base.apk",
            78: 2, 79: 2, 81: "64", 83: "2019118527",
            86: "OpenGLES3", 87: 3071, 88: 4,
            90: "Mumbai", 91: "DL", 92: 67920,
            93: "android_max", 95: 111107,
            96: '{"cur_rate":null,"support_etc2":true}',
            97: 1, 99: "4", 100: "4", 102: "",
            104: 83812, 105: 1,
            106: "https://dl-bs.ggpolarbear.com/live/ABHotUpdates/|https://core-bs.ggpolarbear.com/live/ABHotUpdates/|a4332cb1c1a84e51dd77441e4856ed5a",
            107: "1.9393e7b8e53e8aeb",
        }
        pLd = self._eP(self._sM(fLd))
        hDr = {
            "Host": "client.ind.freefiremobile.com",
            "User-Agent": "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            "Accept": "*/*",
            "Accept-Encoding": "deflate, gzip",
            "Authorization": f"Bearer {tKn}",
            "X-GA": "v1 1",
            "ReleaseVersion": self.rV1,
            "Content-Type": "application/octet-stream",
            "X-Unity-Version": "2022.3.47f1",
        }
        try:
            rSp = self.sEs.post(self.aB2, headers=hDr, data=pLd, verify=False, timeout=8)
        except Exception:
            return {"ok": False, "c": 0xE02, "m": "net"}
        finally:
            self._rS()

        if rSp.status_code == 200:
            result = {"ok": True, "c": 0x00, "m": "OK"}
            if blackboxprotobuf is None:
                return result
            try:
                dEc, _ = blackboxprotobuf.decode_message(rSp.content)
                if isinstance(dEc, dict):
                    result["raw"] = dEc
                    sixteen = [(k, v) for k, v in dEc.items() if isinstance(v, bytes) and len(v) == 16]
                    if len(sixteen) >= 2:
                        result["aes_ak"] = sixteen[0][1]
                        result["iv_i"] = sixteen[1][1]

                    def _s(k, d=""):
                        v = dEc.get(str(k), dEc.get(k, d))
                        if isinstance(v, bytes):
                            try:
                                return v.decode("utf-8", "ignore")
                            except Exception:
                                return ""
                        return str(v) if v else d

                    def _i(k, d=0):
                        try:
                            return int(dEc.get(str(k), dEc.get(k, d)))
                        except Exception:
                            return d

                    result["nickname"] = _s(4, "")
                    result["level"] = _i(6, 1)
                    result["exp"] = _i(7, 0)
                    result["likes"] = _i(8, 0)
                    result["region"] = _s(3, "IND")
                    result["functional_addrs"] = _s(14, "")
                    result["informational_addrs"] = _s(32, "")
                    result["server_time"] = _i(21, 0)
            except Exception as e:
                result["decode_error"] = str(e)
            return result
        if rSp.status_code in (401, 403):
            return {"ok": False, "c": 0xE03, "m": "tok"}
        return {"ok": False, "c": 0xE00 + rSp.status_code, "m": "http"}


ff_login_client = qZxWvY(pRx=PROXIES)


# ==================== DEVICE SYNC ====================
def _generate_new_device():
    dev = qZxWvY.mKId()
    return {
        "unique_device_id": dev.dV,
        "brand": dev.mD.split()[0] if dev.mD else "Android",
        "model": dev.mD,
        "gpu_renderer": dev.gP,
        "system_software": dev.oS,
        "screen_width": 1600,
        "screen_height": 720,
        "screen_dpi": "320",
        "memory": 2799,
        "processor_details": "ARM64 FP ASIMD AES | 2301 | 8",
        "client_ip": dev.iP,
    }


def sync_devices_with_accounts():
    accounts = load_accounts()
    devices = {}
    if os.path.exists(DEVICES_FILE):
        try:
            with open(DEVICES_FILE, "r", encoding="utf-8") as f:
                devices = json.load(f)
                if not isinstance(devices, dict):
                    devices = {}
        except Exception:
            devices = {}
    synced = {}
    for acc in accounts:
        acc_key = None
        if "uid" in acc and acc["uid"]:
            acc_key = str(acc["uid"]).strip()
        elif "token" in acc and acc["token"]:
            acc_key = str(acc["token"]).strip()[:16]
        if not acc_key:
            continue
        dev_profile = devices.get(acc_key) or _generate_new_device()
        synced[acc_key] = dev_profile
    try:
        with open(DEVICES_FILE, "w", encoding="utf-8") as f:
            json.dump(synced, f, indent=4)
    except Exception:
        pass
    return synced


# ==================== DNS ====================
CLOUDFLARE_PRIMARY_DNS = "1.1.1.1"
CLOUDFLARE_SECONDARY_DNS = "1.0.0.1"
_DNS_CACHE = {}
_DNS_CACHE_TTL = 300.0


async def resolve_host_cloudflare(hostname):
    if not hostname:
        return hostname
    parts = hostname.split('.')
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return hostname
    now = time.time()
    if hostname in _DNS_CACHE:
        ip, exp = _DNS_CACHE[hostname]
        if now < exp:
            return ip

    def _query(server_ip):
        s = None
        try:
            tx_id = random.randint(1000, 65535)
            header = struct.pack(">HHHHHH", tx_id, 0x0100, 1, 0, 0, 0)
            qname = b"".join(bytes([len(p)]) + p.encode('ascii') for p in hostname.split('.')) + b"\x00"
            qp = header + qname + struct.pack(">HH", 1, 1)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1.2)
            s.sendto(qp, (server_ip, 53))
            resp, _ = s.recvfrom(1024)
            if len(resp) >= 12:
                ancount = struct.unpack(">H", resp[6:8])[0]
                if ancount > 0:
                    offset = 12 + len(qname) + 4
                    for _ in range(ancount):
                        if offset >= len(resp):
                            break
                        if (resp[offset] & 0xC0) == 0xC0:
                            offset += 2
                        else:
                            while offset < len(resp) and resp[offset] != 0:
                                offset += 1 + resp[offset]
                            offset += 1
                        if offset + 10 > len(resp):
                            break
                        rtype, _, _, rdlen = struct.unpack(">HHIH", resp[offset:offset+10])
                        offset += 10
                        if rtype == 1 and rdlen == 4 and offset + 4 <= len(resp):
                            return socket.inet_ntoa(resp[offset:offset+4])
                        offset += rdlen
        except Exception:
            pass
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        return None

    loop = asyncio.get_running_loop()
    ip = await loop.run_in_executor(None, _query, CLOUDFLARE_PRIMARY_DNS)
    if not ip:
        ip = await loop.run_in_executor(None, _query, CLOUDFLARE_SECONDARY_DNS)
    if not ip:
        try:
            info = await loop.getaddrinfo(hostname, None, family=socket.AF_INET)
            if info:
                ip = info[0][4][0]
        except Exception:
            ip = hostname
    if ip:
        _DNS_CACHE[hostname] = (ip, now + _DNS_CACHE_TTL)
    return ip or hostname


def optimize_tcp_socket(sock):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
    except Exception:
        pass


async def safe_close_writer(writer):
    if not writer:
        return
    try:
        if not writer.is_closing():
            writer.close()
        await asyncio.wait_for(writer.wait_closed(), timeout=1.5)
    except Exception:
        pass


def optimize_udp_socket(sock):
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
        if hasattr(socket, 'SIO_UDP_CONNRESET') and os.name == 'nt':
            try:
                sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except Exception:
                pass
    except Exception:
        pass


# ==================== NETWORK ====================
client = httpx.AsyncClient(
    verify=False, timeout=15.0,
    limits=httpx.Limits(max_connections=1000, max_keepalive_connections=500)
)
_LOGIN_SEMAPHORE = asyncio.Semaphore(10000)

AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'

_DELTA = 0x9E3779B9
_ROUNDS = 16
_FIELD_SIZES = {0: 1, 1: 2, 2: 2, 3: 1, 4: 2}
_FIELD_NAMES = {0: "sendOption", 1: "cmd", 2: "orderId", 3: "flags", 4: "length"}


# ==================== PRINT ====================
def print_success(text, uid=None):
    try:
        print(f"[+] {text}")
    except Exception:
        pass
    try:
        bot_state.log(text, "success", uid)
    except Exception:
        pass


def print_error(text, uid=None):
    try:
        print(f"[-] {text}")
    except Exception:
        pass
    try:
        bot_state.log(text, "error", uid)
    except Exception:
        pass


def print_warning(text, uid=None):
    try:
        print(f"[!] {text}")
    except Exception:
        pass
    try:
        bot_state.log(text, "warning", uid)
    except Exception:
        pass


def print_info(text, uid=None):
    try:
        bot_state.log(text, "info", uid)
    except Exception:
        pass


# ==================== MATCH COUNTER ====================
_match_counters = {}
_match_counter_lock = asyncio.Lock()


async def _inc_match(uid):
    async with _match_counter_lock:
        _match_counters[uid] = _match_counters.get(uid, 0) + 1
        return _match_counters[uid]


async def _dec_match(uid):
    async with _match_counter_lock:
        if uid in _match_counters and _match_counters[uid] > 0:
            _match_counters[uid] -= 1
        return _match_counters.get(uid, 0)


async def _get_match_count(uid):
    async with _match_counter_lock:
        return _match_counters.get(uid, 0)


# ==================== TOKEN CACHE ====================
_token_cache_memo = {}
_token_cache_memo_time = 0.0
_TOKEN_CACHE_MEMO_TTL = 5.0


def _json_serializer(obj):
    if isinstance(obj, (bytes, bytearray)):
        return {"__bytes_hex__": bytes(obj).hex()}
    raise TypeError(f"Type {type(obj)} not serializable")


def _json_deserializer(obj):
    if isinstance(obj, dict):
        if "__bytes_hex__" in obj and len(obj) == 1:
            try:
                return bytes.fromhex(obj["__bytes_hex__"])
            except Exception:
                return b""
        return {k: _json_deserializer(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_deserializer(x) for x in obj]
    return obj


def _load_token_cache():
    global _token_cache_memo, _token_cache_memo_time
    now = time.time()
    if _token_cache_memo and (now - _token_cache_memo_time) < _TOKEN_CACHE_MEMO_TTL:
        return _token_cache_memo
    if not os.path.exists(TOKEN_CACHE_FILE):
        return {}
    try:
        with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return {}
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Cache root must be dict")
        parsed = _json_deserializer(data)
        _token_cache_memo = parsed
        _token_cache_memo_time = now
        return parsed
    except Exception as e:
        print_error(f"Token cache corrupt: {e}")
        try:
            os.remove(TOKEN_CACHE_FILE)
        except Exception:
            pass
        return {}


def _save_token_cache(cache):
    global _token_cache_memo, _token_cache_memo_time
    try:
        tmp_file = TOKEN_CACHE_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, default=_json_serializer)
        os.replace(tmp_file, TOKEN_CACHE_FILE)
        _token_cache_memo = cache
        _token_cache_memo_time = time.time()
    except Exception as e:
        print_error(f"Token cache save error: {e}")


def cache_get(uid):
    cache = _load_token_cache()
    entry = cache.get(str(uid))
    if not entry:
        return None
    if time.time() - entry.get("cached_at", 0) > TOKEN_CACHE_TTL:
        cache_invalidate(uid)
        return None
    if str(entry.get("account_id", "")).isdigit():
        entry["account_id"] = int(entry["account_id"])
    return entry


def cache_set(uid, account_data):
    cache = _load_token_cache()
    entry = dict(account_data)
    entry["cached_at"] = time.time()
    cache[str(uid)] = entry
    _save_token_cache(cache)


def cache_invalidate(uid):
    cache = _load_token_cache()
    if str(uid) in cache:
        del cache[str(uid)]
        _save_token_cache(cache)


# ==================== ENCRYPTION ====================
async def aes_encrypt(payload, key, iv):
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(payload, AES.block_size))


_VERSION_CONFIG_CACHE = None
_VERSION_CONFIG_CACHE_TIME = 0.0
_VERSION_CONFIG_TTL = 1800.0


async def get_playstore_version():
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, lambda: play_scraper('com.dts.freefireth', lang='hi', country='id')
        )
        return result.get("version")
    except Exception:
        return "2.133.9"


async def version_config():
    global _VERSION_CONFIG_CACHE, _VERSION_CONFIG_CACHE_TIME
    now = time.time()
    if _VERSION_CONFIG_CACHE and (now - _VERSION_CONFIG_CACHE_TIME) < _VERSION_CONFIG_TTL:
        return _VERSION_CONFIG_CACHE
    try:
        app_version = await get_playstore_version() or "2.133.9"
        api_url = (
            "https://version.ggwhitehawk.com/live/ver.php"
            f"?version={app_version}"
            "&lang=hi&device=android&channel=android"
            "&appstore=googleplay&region=IND"
            "&whitelist_version=1.3.0&whitelist_sp_version=1.0.0"
        )
        response = await client.get(api_url, timeout=8.0)
        response.raise_for_status()
        data = response.json()
        server_url = data.get("server_url")
        remote_version = data.get("remote_version")
        latest_release_version = data.get("latest_release_version")
        if server_url and remote_version and latest_release_version:
            _VERSION_CONFIG_CACHE = (latest_release_version, remote_version, server_url)
            _VERSION_CONFIG_CACHE_TIME = now
            return _VERSION_CONFIG_CACHE
    except Exception:
        if _VERSION_CONFIG_CACHE:
            return _VERSION_CONFIG_CACHE
    return None


async def get_access_token(uid, password):
    url = "https://100067.connect.garena.com/oauth/guest/token/grant"
    hdrs = {
        "Host": "100067.connect.garena.com",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; SM-G998B Build/SP1A.210812.016)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip, deflate, br", "Connection": "close"
    }
    data = {
        "uid": uid, "password": password, "response_type": "token", "client_type": "2",
        "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
        "client_id": "100067"
    }
    for attempt in range(5):
        try:
            response = await client.post(url, headers=hdrs, data=data)
            if response.status_code == 200:
                response_data = response.json()
                open_id = response_data.get("open_id")
                access_token = response_data.get("access_token")
                platform = response_data.get("platform", 4)
                if open_id and access_token:
                    return open_id, access_token, platform
            if response.status_code == 429:
                await asyncio.sleep(1)
                continue
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return None


async def parse_results(parsed_results):
    result_dict = {}
    for result in parsed_results:
        field_data = {"wire_type": result.wire_type}
        if result.wire_type == "varint":
            field_data["data"] = result.data
        elif result.wire_type == "string":
            field_data["data"] = result.data
        elif result.wire_type == "bytes":
            field_data["data"] = result.data
        elif result.wire_type == "length_delimited":
            if hasattr(result.data, "results"):
                field_data["data"] = await parse_results(result.data.results)
            elif isinstance(result.data, list):
                field_data["data"] = await parse_results(result.data)
            else:
                field_data["data"] = str(result.data)
        result_dict[str(result.field)] = field_data
    return result_dict


async def decode_protobuf(data):
    parsed_results = Parser().parse(data)
    parsed_results_dict = await parse_results(parsed_results)
    return json.dumps(parsed_results_dict)


async def build_tcp_startup_packet(account_id, token, server_time, key, iv, region="IND", typ='OnLine'):
    uid_hex = f"{int(account_id):016x}"
    timestamp_hex = f"{int(server_time):08x}"
    encode_token = token.encode()
    encrypted_packet = (await aes_encrypt(encode_token, key, iv)).hex()
    encrypted_packet_length = f"{len(encrypted_packet) // 2:08x}"
    reg = str(region).upper() if region else "IND"
    if typ == 'OnLine':
        prefix = '7214' if reg == 'IND' else ('7219' if reg == 'BD' else '7215')
        return f"{prefix}{uid_hex}{timestamp_hex}00000000{encrypted_packet_length}{encrypted_packet}"
    else:
        prefix = '8114' if reg == 'IND' else ('8119' if reg == 'BD' else '8115')
        return f"{prefix}{uid_hex}{timestamp_hex}{encrypted_packet_length}{encrypted_packet}"


async def send_keep_alive(region="IND"):
    try:
        reg = str(region).upper() if region else "IND"
        ka_hex = "0214" if reg == "IND" else ("0219" if reg == "BD" else "0215")
        return bytes.fromhex(ka_hex)
    except Exception:
        return bytes.fromhex("0214")


# ==================== BR / LW PACKETS ====================
async def build_br_packet_bytes(region, client_version, key, iv):
    packet = bytes.fromhex("080112800a0a010110013a110a044944433110aa011a064555524f50453a100a044944433210311a064555524f504540014a0801090a0b1219202758016291090a8001303838463832424630324139363736373032303130313030303030303030303030303136303030313030313530303032323246393745454530463030303030303436373632353134303030303030303030303030303030303030303030303030303030303030303030303030303066663030303030303030636163666131366410241afb02735d5e571400024a775d45414d1a041b1c001f11010449715f4243481a001e1d071c1703004b1a4066785c524570735c51486775421b5c5a4c07504042685a63610816054e19025e75196001477c015165406370195f5547404e4550640103020f1304064863754268676c755f65576e40467e5f0a417a4701026d675d6e73670b1108495a4c6a0b78470b740065645e525a057258425f584a447d4e6759440c11044e7c596d7f4b625f7d04055a47505c4e1d6b5b4107447d7201057d7f0f14084e430457674f7e517d72015172415d027473577c4d615f79535256780911030f4d5e027a797f614165067806505d53777750475e75064257076500460817014e741e7e5078487e7a7c465e7669767153497064605a7376677773550d160148037e18675966787f4c42607a645f577e7b441b460776026b18685d0b110205490060020f70676175654674706671797f41067346677c4e06585e780f15074c57047b40517075415f6364027259674b5b0166407f7340600407770a22047a5d5c52300b3a0a167305067162727516134208312e3133302e3232480350015ae90403626253513635686e556f4e36416456324b796f566c636f477776484f624e56526c4d727073504b4f43654177616848494176795556497273743752737149734a7a786b3247525268377a2f637664626d504f6a73552f79626d38547a4c69586d2f474351696d494b53486833447955726f39515152756c34545350626d6d624b7949565937545671577059455372323646572f59624578507338514f706d317372785455736c30796a434144444d4f34616a654b615753366361496c554b4963797a494e396d52516f715277687939797257476d337a644345337a6a61436f492f5a585233656f65365a42647a64677654636b6b665733356e4d4c6a6a565072564b6433523172756174394e50514150724a5546627859696c4c5a3859707336654d5447666b6649793574666a526c314d4648706b51774c6373374439656378566c41636f374e664f6d2b30654756466c4434744478706771385533595973587645384842502f70666c767a737138316a32524f4d7857437556445442492f684735625462773166456e4249725162762b636144775147696f74554e316d4c4b77734379456f4766706746614251457645672b736a764c4c78704743334c304a5344532f74526169504354553344374e6249306547516651622f5a466f4c36455630775a324d6f583932414c572f5049752f56634663584e70596b356f7966326151416a536971486a2f363276354843644f525551303578754e6171795251625653704654303137655237675255636b4966366c6f447476342b514e4a4670766d74757077707774396a5a5974437a4b56743657726d6e36785837706658456251555434684f3758a201050803108703a201050804108103a20105080510c001a20105081d10cc01a2010408161078a20105080e10af01a201020815")
    proto = thunderFF_pb2.StartMatch()
    proto.ParseFromString(packet)
    if hasattr(proto.main, 'region_list') and len(proto.main.region_list) > 0:
        proto.main.region_list[0].region = region
        if len(proto.main.region_list) > 1:
            proto.main.region_list[1].region = region
    if hasattr(proto.main, 'client_version'):
        proto.main.client_version.remote_version = client_version
    packet = proto.SerializeToString()
    encrypted_packet = (await aes_encrypt(packet, key, iv)).hex()
    packet_length = len(encrypted_packet) // 2
    hex_length = hex(packet_length)[2:]
    hex_length = hex_length if len(hex_length) > 1 else "0" + hex_length
    reg = str(region).upper() if region else "IND"
    reg_prefix = "031400" if reg == "IND" else ("031900" if reg == "BD" else "031500")
    final_packet = reg_prefix + "0" * (6 - len(hex_length)) + hex_length + encrypted_packet
    return bytes.fromhex(final_packet)


async def build_lw_packet_bytes(region, client_version, key, iv):
    packet = bytes.fromhex("080112800a0a010b102b3a110a044944433110aa011a064555524f50453a100a044944433210311a064555524f504540014a0801090a0b1219202758016291090a8001303838463832424630324139363736373032303130313030303030303030303030303136303030313030313530303032323246393745454530463030303030303436373632353134303030303030303030303030303030303030303030303030303030303030303030303030303066663030303030303030636163666131366410241afb02735d5e571400024a775d45414d1a041b1c001f11010449715f4243481a001e1d071c1703004b1a4066785c524570735c51486775421b5c5a4c07504042685a63610816054e19025e75196001477c015165406370195f5547404e4550640103020f1304064863754268676c755f65576e40467e5f0a417a4701026d675d6e73670b1108495a4c6a0b78470b740065645e525a057258425f584a447d4e6759440c11044e7c596d7f4b625f7d04055a47505c4e1d6b5b4107447d7201057d7f0f14084e430457674f7e517d72015172415d027473577c4d615f79535256780911030f4d5e027a797f614165067806505d53777750475e75064257076500460817014e741e7e5078487e7a7c465e7669767153497064605a7376677773550d160148037e18675966787f4c42607a645f577e7b441b460776026b18685d0b110205490060020f70676175654674706671797f41067346677c4e06585e780f15074c57047b40517075415f6364027259674b5b0166407f7340600407770a22047a5d5c52300b3a0a167305067162727516134208312e3133302e3232480350015ae90403626253513635686e556f4e36416456324b796f566c636f477776484f624e56526c4d727073504b4f43654177616848494176795556497273743752737149734a7a786b3247525268377a2f637664626d504f6a73552f79626d38547a4c69586d2f474351696d494b53486833447955726f39515152756c34545350626d6d624b7949565937545671577059455372323646572f59624578507338514f706d317372785455736c30796a434144444d4f34616a654b615753366361496c554b4963797a494e396d52516f715277687939797257476d337a644345337a6a61436f492f5a585233656f65365a42647a64677654636b6b665733356e4d4c6a6a565072564b6433523172756174394e50514150724a5546627859696c4c5a3859707336654d5447666b6649793574666a526c314d4648706b51774c6373374439656378566c41636f374e664f6d2b30654756466c4434744478706771385533595973587645384842502f70666c767a737138316a32524f4d7857437556445442492f684735625462773166456e4249725162762b636144775147696f74554e316d4c4b77734379456f4766706746614251457645672b736a764c4c78704743334c304a5344532f74526169504354553344374e6249306547516651622f5a466f4c36455630775a324d6f583932414c572f5049752f56634663584e70596b356f7966326151416a536971486a2f363276354843644f525551303578754e6171795251625653704654303137655237675255636b4966366c6f447476342b514e4a4670766d74757077707774396a5a5974437a4b56743657726d6e36785837706658456251555434684f3758a201050803108703a201050804108103a20105080510c001a20105081d10cc01a2010408161078a20105080e10af01a201020815")
    proto = thunderFF_pb2.StartMatch()
    proto.ParseFromString(packet)
    if hasattr(proto.main, 'region_list') and len(proto.main.region_list) > 0:
        proto.main.region_list[0].region = region
        if len(proto.main.region_list) > 1:
            proto.main.region_list[1].region = region
    if hasattr(proto.main, 'client_version'):
        proto.main.client_version.remote_version = client_version
    packet = proto.SerializeToString()
    encrypted_packet = (await aes_encrypt(packet, key, iv)).hex()
    packet_length = len(encrypted_packet) // 2
    hex_length = hex(packet_length)[2:]
    hex_length = hex_length if len(hex_length) > 1 else "0" + hex_length
    reg = str(region).upper() if region else "IND"
    reg_prefix = "031400" if reg == "IND" else ("031900" if reg == "BD" else "031500")
    final_packet = reg_prefix + "0" * (6 - len(hex_length)) + hex_length + encrypted_packet
    return bytes.fromhex(final_packet)


# ==================== SHARED BUILDERS ====================
async def has_ssan_zig(n):
    z = (n << 1) & 0xFFFFFFFFFFFFFFFF
    out = bytearray()
    while z >= 0x80:
        out.append((z & 0x7F) | 0x80)
        z >>= 7
    out.append(z)
    return bytes(out)


async def uleb_encode(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            break
    return bytes(out)


async def tea_enc(v0, v1, k0, k1, k2, k3):
    s = 0
    for _ in range(_ROUNDS):
        s = (s + _DELTA) & 0xFFFFFFFF
        v0 = (v0 + (((((v1 << 4) & 0xFFFFFFFF) + k0) & 0xFFFFFFFF ^ ((v1 + s) & 0xFFFFFFFF) ^ (((v1 >> 5) + k1) & 0xFFFFFFFF)))) & 0xFFFFFFFF
        v1 = (v1 + (((((v0 << 4) & 0xFFFFFFFF) + k2) & 0xFFFFFFFF ^ ((v0 + s) & 0xFFFFFFFF) ^ (((v0 >> 5) + k3) & 0xFFFFFFFF)))) & 0xFFFFFFFF
    return v0, v1


async def tea_dec(v0, v1, k0, k1, k2, k3):
    s = (_DELTA * _ROUNDS) & 0xFFFFFFFF
    for _ in range(_ROUNDS):
        v1 = (v1 - (((((v0 << 4) & 0xFFFFFFFF) + k2) & 0xFFFFFFFF ^ ((v0 + s) & 0xFFFFFFFF) ^ (((v0 >> 5) + k3) & 0xFFFFFFFF)))) & 0xFFFFFFFF
        v0 = (v0 - (((((v1 << 4) & 0xFFFFFFFF) + k0) & 0xFFFFFFFF ^ ((v1 + s) & 0xFFFFFFFF) ^ (((v1 >> 5) + k1) & 0xFFFFFFFF)))) & 0xFFFFFFFF
        s = (s - _DELTA) & 0xFFFFFFFF
    return v0, v1


async def tea_cbc_encrypt(padded, key_bytes):
    k0, k1, k2, k3 = (struct.unpack_from("<I", key_bytes, o)[0] for o in (0, 4, 8, 12))
    out = bytearray(len(padded))
    prev_cipher = bytearray(8)
    prev_intermediate = bytearray(8)
    for i in range(0, len(padded), 8):
        xored = bytearray(8)
        for j in range(8):
            xored[j] = padded[i + j] ^ prev_cipher[j]
        e0, e1 = await tea_enc(struct.unpack_from("<I", xored, 0)[0], struct.unpack_from("<I", xored, 4)[0], k0, k1, k2, k3)
        enc = bytearray(8)
        struct.pack_into("<I", enc, 0, e0)
        struct.pack_into("<I", enc, 4, e1)
        for j in range(8):
            out[i + j] = enc[j] ^ prev_intermediate[j]
        prev_cipher[:] = out[i:i + 8]
        prev_intermediate[:] = xored
    return bytes(out)


async def build_padded(content):
    pad_len = (8 - (len(content) + 10) % 8) % 8
    return bytes([pad_len, 0, 0]) + b"\x00" * pad_len + content + b"\x00" * 7


async def encode_header(layout, send_option, cmd, order_id, flags, length, k, v80):
    out = bytearray()
    for code in layout:
        value = {0: send_option, 1: cmd, 2: order_id, 3: flags, 4: length}[code]
        if _FIELD_SIZES[code] == 1:
            out.append((value & 0xFF) ^ k)
        else:
            v = ((value & 0xFFFF) ^ v80) & 0xFFFF
            out.append(v & 0xFF)
            out.append((v >> 8) & 0xFF)
    return bytes(out)


async def crc7_buff(crc, buf):
    c = crc & 0x7F
    for b in buf:
        c = CRC7_TABLE[((2 * (c & 0xFF)) ^ (b & 0xFF)) & 0xFF] & 0x7F
    return c & 0x7F


async def sv_frame(msg_key, layout, send_option, cmd, order_id, flags, content, key, encrypted=True):
    k = key[0]
    v80 = ((k << 8) | k) & 0xFFFF
    body = await tea_cbc_encrypt(await build_padded(content), key) if encrypted else content
    hdr = bytearray([msg_key, 0]) + await encode_header(layout, send_option, cmd, order_id, flags, len(body), k, v80)
    packet = bytearray(hdr + body)
    packet[1] = await crc7_buff(0, bytes(packet[2:])) & 0x7F
    return bytes(packet)


async def build_match_startup_packets(token, udp_key, match_code, account_id, block_val,
                                      server_ip="", region="IND", client_version="2.133.9",
                                      client_version_code="2019118527", access_token="",
                                      mode="LONE_WOLF"):
    token = token.strip()
    udp_key = bytes.fromhex(udp_key)
    match_code = [int(ch) for ch in str(match_code).strip()]
    thunder_jwt = token[:660] if len(token) > 660 else token
    sharma_jwt = token[660:] if len(token) > 660 else ""
    encoded_thunder_jwt = thunder_jwt.encode() if isinstance(thunder_jwt, str) else thunder_jwt
    encoded_sharma_jwt = sharma_jwt.encode() if isinstance(sharma_jwt, str) else sharma_jwt
    garena420 = await has_ssan_zig(len(encoded_thunder_jwt)) + encoded_thunder_jwt
    reg = str(region).upper() if region else "IND"

    if mode == "BR":
        csoversea_block = bytes.fromhex(
            "ca0163736f7665727365612e7374726f6e67686f6c642e66726565666972656d6f62696c652e636f6d"
            "3b302e302e302e303b33342e3132362e37362e34353b33342e38372e3137372e31343b33342e38372e"
            "3137302e3233303b33352e3138352e3138332e35370000000000000100000000000000000000000001"
            "00000000000100010000000100b09df8c5fad88bdf110200"
        )
        m_val1 = 1
        m_val2 = 1
    else:
        csoversea_block = bytes.fromhex(
            "ca0163736f7665727365612e7374726f6e67686f6c642e66726565666972656d6f62696c652e636f6d"
            "3b302e302e302e303b33342e3132362e37362e34353b33342e38372e3137372e31343b33342e38372e"
            "3137302e3233303b33352e3138352e3138332e35370000000000000100000000000000000000000001"
            "00000800000100000000000100a8a2d7bebd8d8bdf110200"
        )
        m_val1 = 43
        m_val2 = 11

    mid = bytes.fromhex('0000000001000102030101') + await has_ssan_zig(len(reg)) + reg.encode()
    mid += bytes.fromhex('0001030003000004')
    mid += await has_ssan_zig(len(client_version)) + client_version.encode()
    mid += await has_ssan_zig(len(client_version_code)) + client_version_code.encode()
    mid += csoversea_block
    clean_ip = server_ip.split(':')[0] if server_ip else "0.0.0.0"
    mid += await has_ssan_zig(len(clean_ip)) + clean_ip.encode()
    clean_acc_tok = access_token.strip() if access_token else ""
    if clean_acc_tok:
        mid += await has_ssan_zig(len(clean_acc_tok)) + clean_acc_tok.encode()
    mid += await has_ssan_zig(len(encoded_sharma_jwt)) + encoded_sharma_jwt
    tg_garena420 = (
        await uleb_encode(int(account_id)) +
        await uleb_encode(int(block_val)) +
        await uleb_encode(1) + await uleb_encode(m_val1) +
        await uleb_encode(int(block_val)) + await uleb_encode(m_val2) + mid
    )
    process = await sv_frame(0x5E, match_code, 2, 447, 0, 1, garena420, udp_key)
    loading = await sv_frame(0x5A, match_code, 2, 448, 1, 1, tg_garena420, udp_key)
    return process.hex(), loading.hex()


async def produce_xor_key(secret_key):
    k = secret_key[0] if secret_key and len(secret_key) > 0 else 10
    return k, ((k << 8) | k) & 0xFFFF


async def parse_layout(layout):
    if isinstance(layout, str):
        return [int(ch) for ch in layout.strip()]
    return list(layout)


async def tea_cbc_decrypt(body, key_bytes):
    k0, k1, k2, k3 = (struct.unpack_from("<I", key_bytes, o)[0] for o in (0, 4, 8, 12))
    out = bytearray(len(body))
    prev_intermediate = bytearray(8)
    prev_cipher = bytearray(8)
    xored = bytearray(8)
    dec = bytearray(8)
    for i in range(0, len(body), 8):
        for j in range(8):
            xored[j] = body[i + j] ^ prev_intermediate[j]
        d0, d1 = await tea_dec(struct.unpack_from("<I", xored, 0)[0], struct.unpack_from("<I", xored, 4)[0], k0, k1, k2, k3)
        struct.pack_into("<I", dec, 0, d0)
        struct.pack_into("<I", dec, 4, d1)
        for j in range(8):
            out[i + j] = dec[j] ^ prev_cipher[j]
        prev_cipher[:] = body[i:i + 8]
        prev_intermediate[:] = dec
    return bytes(out)


async def build_hello_packet(text, key, layout):
    data = text.encode("utf-8")
    if len(data) > 25:
        raise ValueError(f"Text too long ({len(data)} bytes)")
    content = b"\x10\x00\x00\x00" + data + b"\x00" * (29 - 4 - len(data))
    k, v80 = await produce_xor_key(key)
    layout = await parse_layout(layout)
    padded = await build_padded(content)
    enc_body = await tea_cbc_encrypt(padded, key)
    header_bytes = await encode_header(layout, 1, 1, 0, 1, len(enc_body), k, v80)
    packet = bytearray([0x63, 0x00]) + header_bytes + enc_body
    packet[1] = await crc7_buff(0, packet[2:]) & 0x7F
    return bytes(packet).hex()


async def classify(frame):
    cmd = frame["cmd"]
    msg_name = MESSAGE_ID_TO_NAME.get(cmd, f"UNKNOWN_{cmd}")
    if msg_name == "UDP_HELLO": return "HELLO"
    if msg_name == "UDP_ACK": return "ACK"
    if msg_name == "UDP_PING": return "PING"
    if msg_name == "RUDP_JOIN_MATCH": return "JOIN_MATCH"
    if msg_name.startswith("RUDP_"): return msg_name
    if msg_name.startswith("UDP_"): return msg_name
    return "DATA"


async def build_packet(msg_key, layout, send_option, cmd, order_id, flags, content, key, encrypted=True):
    k = key[0]
    v80 = ((k << 8) | k) & 0xFFFF
    body = await tea_cbc_encrypt(await build_padded(content), key) if encrypted else content
    hdr = bytearray([msg_key, 0])
    for code in layout:
        value = {0: send_option, 1: cmd, 2: order_id, 3: flags, 4: len(body)}[code]
        if _FIELD_SIZES[code] == 1:
            hdr.append((value & 0xFF) ^ k)
        else:
            v = ((value & 0xFFFF) ^ v80) & 0xFFFF
            hdr.append(v & 0xFF)
            hdr.append((v >> 8) & 0xFF)
    packet = bytearray(hdr + body)
    packet[1] = await crc7_buff(0, bytes(packet[2:])) & 0x7F
    return bytes(packet)


async def layouts_from_mask(mask):
    ru = [int(c) for c in str(mask).strip()]
    nr = [c for c in ru if c != 2]
    return ru, nr


async def reply_for(frame, key, mask, ack_key=0x68, ping_key=0x6D, hello_key=0x5B, ack_style="short"):
    ru, nr = await layouts_from_mask(mask)
    typ = await classify(frame)
    if typ == "HELLO":
        if ack_style == "echo":
            content = frame["content"] if frame["content"] else b"\x10\x00\x00\x00"
            return typ, await build_packet(hello_key, nr, 1, 1, None, 1, content, key)
        return typ, await build_packet(ack_key, nr, 0, 2, None, 1, b"\x01\x00", key)
    if typ == "ACK":
        content = frame["content"] if frame["content"] else b"\x01\x00"
        return typ, await build_packet(ack_key, nr, 0, 2, None, 1, content, key)
    if typ == "PING":
        c = frame["content"]
        counter = c[:4] if len(c) >= 4 else c
        return typ, await build_packet(ping_key, nr, 0, 3, None, 0, counter + b"\x00\x00\x00", key, encrypted=False)
    if typ == "JOIN_MATCH":
        return typ, await build_packet(ack_key, nr, 0, 2, None, 1, b"\x02\x00", key)
    return typ, None


async def keepalive_ping(sock, ip, port, key_bytes, mask, stop_event):
    nr = (await layouts_from_mask(mask))[1]
    ping_keys = [0x66, 0x6D, 0x69, 0x6C, 0x6B, 0x6E, 0x6F, 0x70]
    loop = asyncio.get_event_loop()
    i = 0
    while not stop_event.is_set():
        pk = ping_keys[i % len(ping_keys)]
        counter = int(time.time() * 1000) & 0xFFFFFFFF
        pkt = await build_packet(pk, nr, 0, 3, None, 0, struct.pack("<I", counter) + b"\x00\x00\x00", key_bytes, encrypted=False)
        try:
            await loop.sock_sendto(sock, pkt, (ip, port))
        except Exception:
            pass
        i += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            pass


async def try_header(buf, layout, k, v80):
    off = 2
    out = {}
    for code in layout:
        size = _FIELD_SIZES[code]
        if off + size > len(buf):
            return None
        out[_FIELD_NAMES[code]] = (buf[off] ^ k) if size == 1 else ((buf[off] | (buf[off + 1] << 8)) ^ v80) & 0xFFFF
        off += size
    out["headerLen"] = off
    return out


async def oicq_unpad(padded):
    if not padded or len(padded) < 8:
        return None
    if not all(padded[-1 - i] == 0 for i in range(7)):
        return None
    pad_len = padded[0] & 0x07
    s = 3 + pad_len
    e = len(padded) - 7
    return padded[s:e] if s < e else b""


async def decode_packet(packet, key, mask=None):
    data = bytes(packet) if isinstance(packet, bytes) else bytes.fromhex(packet)
    if len(data) < 8:
        return None
    k = key[0]
    v80 = ((k << 8) | k) & 0xFFFF
    crc_ok = (data[1] & 0x7F) == await crc7_buff(0, data[2:])
    candidates = []
    if mask:
        ru, nr = await layouts_from_mask(mask)
        layouts = [("RUDP", ru), ("nonRUDP", nr)]
    else:
        layouts = [("RUDP", list(p)) for p in itertools.permutations([0, 1, 2, 3, 4])]
        layouts += [("nonRUDP", list(p)) for p in itertools.permutations([0, 1, 3, 4])]
    for kind, layout in layouts:
        f = await try_header(data, layout, k, v80)
        if not f:
            continue
        if f["flags"] > 7 or f["sendOption"] > 7:
            continue
        if f["length"] != len(data) - f["headerLen"]:
            continue
        body = data[f["headerLen"]:f["headerLen"] + f["length"]]
        content = None
        padded = None
        if f["flags"] & 1:
            if len(body) < 8 or len(body) % 8 != 0:
                continue
            padded = await tea_cbc_decrypt(body, key)
            content = await oicq_unpad(padded)
            if content is None:
                continue
        else:
            content = body
        score = (1 if crc_ok else 0) + (1 if content is not None else 0)
        candidates.append({
            "kind": kind, "layout": layout, "headerLen": f["headerLen"],
            "msgKey": data[0], "cmd": f["cmd"], "flags": f["flags"],
            "sendOption": f["sendOption"], "orderId": f.get("orderId"),
            "length": f["length"], "content": content, "crcOk": crc_ok,
            "padded": padded, "score": score, "total": len(data),
        })
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c["kind"] == "RUDP" or c["kind"] == "nonRUDP", c["score"]), reverse=True)
    return candidates[0]


# ==================== ANTI-AFK ====================
async def send_anti_afk_movement(sock, server_addr, udp_key_bytes, match_code, account_id):
    try:
        nr = (await layouts_from_mask(match_code))[1]
        rx = random.randint(-100, 100)
        ry = random.randint(-50, 50)
        rz = random.randint(-100, 100)
        ts = int(time.time() * 1000) & 0xFFFFFFFF
        try:
            pid = int(account_id)
        except Exception:
            pid = 0
        body = struct.pack("<IIiiiH", pid & 0xFFFFFFFF, ts, rx, ry, rz, 1)
        pkt = await build_packet(0x6B, nr, 0, 2001, None, 0, body, udp_key_bytes, encrypted=False)
        loop = asyncio.get_event_loop()
        await loop.sock_sendto(sock, pkt, server_addr)
        return True
    except Exception:
        return False


async def send_anti_afk_fire(sock, server_addr, udp_key_bytes, match_code, account_id):
    try:
        nr = (await layouts_from_mask(match_code))[1]
        try:
            pid = int(account_id)
        except Exception:
            pid = 0
        ts = int(time.time() * 1000) & 0xFFFFFFFF
        wid = random.choice([101, 102, 103, 201, 202])
        fire_body = struct.pack("<IIHB", pid & 0xFFFFFFFF, ts, wid, 1)
        fire_pkt = await build_packet(0x68, nr, 0, 104, None, 0, fire_body, udp_key_bytes, encrypted=False)
        loop = asyncio.get_event_loop()
        await loop.sock_sendto(sock, fire_pkt, server_addr)
        await asyncio.sleep(random.uniform(0.15, 0.30))
        stop_body = struct.pack("<IIHB", pid & 0xFFFFFFFF, ts + 200, wid, 0)
        stop_pkt = await build_packet(0x68, nr, 0, 105, None, 0, stop_body, udp_key_bytes, encrypted=False)
        await loop.sock_sendto(sock, stop_pkt, server_addr)
        return True
    except Exception:
        return False


async def anti_afk_worker(sock, resolved_ip, port, udp_key_bytes, match_code, account_id, stop_event, match_index):
    loop = asyncio.get_event_loop()
    server_addr = (resolved_ip, port)
    try:
        await asyncio.sleep(2.5)
        while not stop_event.is_set():
            try:
                roll = random.random()
                if roll < ANTI_AFK_FIRE_CHANCE:
                    await send_anti_afk_fire(sock, server_addr, udp_key_bytes, match_code, account_id)
                    if random.random() < 0.4:
                        await send_anti_afk_movement(sock, server_addr, udp_key_bytes, match_code, account_id)
                else:
                    await send_anti_afk_movement(sock, server_addr, udp_key_bytes, match_code, account_id)
                wt = random.uniform(ANTI_AFK_MIN_INTERVAL, ANTI_AFK_MAX_INTERVAL)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=wt)
                    break
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass


# ==================== FIRE WORKER (INDEPENDENT TIME-BASED) ====================
async def fire_worker(shared, uid_str, get_mode_fn):
    """
    Independent fire task — fires LW/BR at EXACT wall-clock intervals.
    Runs at 50ms tick (20 checks/sec). Ignores packet-read loop speed.
    """
    last_lw_fire = 0.0
    last_br_fire = 0.0

    while True:
        try:
            await asyncio.sleep(0.05)  # 50ms tick

            w = shared.get('writer')
            if not w or w.is_closing():
                continue

            now = time.time()
            mode, lvl = get_mode_fn()

            if mode == "LONE_WOLF":
                lw = shared.get('lw_packet')
                if lw and (now - last_lw_fire) >= LW_FIRE_INTERVAL:
                    try:
                        w.write(lw)
                        await w.drain()
                        last_lw_fire = now
                        try:
                            bot_state.track_activity(uid_str, "fire_lw")
                        except Exception:
                            pass
                        print_info(f"LW FIRE | UID {uid_str} Lvl {lvl} | interval {LW_FIRE_INTERVAL}s", uid=uid_str)
                    except Exception as e:
                        print_warning(f"LW FIRE {uid_str}: {e}", uid=uid_str)
                        last_lw_fire = now
            else:
                br = shared.get('br_packet')
                if br and (now - last_br_fire) >= BR_FIRE_INTERVAL:
                    try:
                        w.write(br)
                        await w.drain()
                        last_br_fire = now
                        try:
                            bot_state.track_activity(uid_str, "fire_br")
                        except Exception:
                            pass
                        print_info(f"BR FIRE | UID {uid_str} Lvl {lvl} | interval {BR_FIRE_INTERVAL}s", uid=uid_str)
                    except Exception as e:
                        print_warning(f"BR FIRE {uid_str}: {e}", uid=uid_str)
                        last_br_fire = now
        except asyncio.CancelledError:
            break
        except Exception as e:
            print_warning(f"fire_worker {uid_str}: {e}", uid=uid_str)
            await asyncio.sleep(0.5)


# ==================== play_game — MODE-DEPENDENT ====================
async def play_game(server_ip_port, thunder, sharma, udp_key, match_code,
                    account_id, player_region, client_version, key, iv,
                    match_index: int, mode: str = "LONE_WOLF", owner=None):
    match_start_time = time.time()
    if mode == "BR":
        max_duration = BR_MAX_MATCH_DURATION
        idle_timeout = BR_IDLE_TIMEOUT
    else:
        max_duration = LW_MAX_MATCH_DURATION
        idle_timeout = MATCH_IDLE_TIMEOUT

    ping_task = None
    anti_afk_task = None
    sock = None
    ping_stop = asyncio.Event()
    uid_str = str(account_id)
    completed_cleanly = False
    total_players = 50 if mode == "BR" else 2
    dead_count = 0
    alive_count = total_players
    match_start_ts = time.time()

    try:
        ip, port = server_ip_port.split(":")
        port = int(port)
        resolved_ip = await resolve_host_cloudflare(ip)
        loop = asyncio.get_event_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(('0.0.0.0', 0))
        except Exception:
            pass
        optimize_udp_socket(sock)
        sock.setblocking(False)
        udp_key_bytes = bytes.fromhex(udp_key)

        hello_packet = await build_hello_packet(f"{account_id}_2585", udp_key_bytes, match_code)
        await loop.sock_sendto(sock, bytes.fromhex(hello_packet), (resolved_ip, port))

        ack_state = "waiting_for_hello_reply"
        thunder_sent = False
        join_match_received = False
        local_closed = False
        send_lock = asyncio.Lock()
        ping_task = asyncio.create_task(keepalive_ping(sock, resolved_ip, port, udp_key_bytes, match_code, ping_stop))

        try:
            bot_state.update_match_stats(uid_str, total=total_players, alive=alive_count, dead=0, mode=mode, started_at=match_start_ts)
            bot_state.track_activity(uid_str, "match_start")
            bot_state.update_status(uid_str, f"IN_MATCH ({mode})", 1)
            print_success(f"Match #{match_index} [{mode}] UDP started | {total_players} players", uid=uid_str)
        except Exception:
            pass

        if ANTI_AFK_ENABLED:
            anti_afk_task = asyncio.create_task(anti_afk_worker(
                sock, resolved_ip, port, udp_key_bytes, match_code,
                account_id, ping_stop, match_index
            ))

        last_activity = time.time()
        MAX_IDLE_BEFORE_HELLO_RESEND = 7.0

        async def send_thunder_sharma_inline():
            nonlocal ack_state, thunder_sent
            if thunder_sent:
                return
            async with send_lock:
                if thunder_sent:
                    return
                try:
                    await loop.sock_sendto(sock, bytes.fromhex(thunder), (resolved_ip, port))
                    thunder_sent = True
                    await asyncio.sleep(0.3)
                    prepare_ack = await build_packet(0x68, (await layouts_from_mask(match_code))[1], 0, 2, None, 1, b"\x01\x00", udp_key_bytes)
                    await loop.sock_sendto(sock, prepare_ack, (resolved_ip, port))
                    await asyncio.sleep(0.4)
                    await loop.sock_sendto(sock, bytes.fromhex(sharma), (resolved_ip, port))
                    ack_state = "thunder_sharma_sent"
                except Exception:
                    pass

        while not local_closed:
            if time.time() - match_start_time > max_duration:
                print_warning(f"[MATCH #{match_index}] Max duration ({max_duration}s)", uid=uid_str)
                break
            try:
                response, server_addr = await asyncio.wait_for(loop.sock_recvfrom(sock, 65535), timeout=1.5)
                if response:
                    last_activity = time.time()
                    frame = await decode_packet(response, udp_key_bytes, match_code)
                    if frame:
                        ptype = await classify(frame)

                        if frame['cmd'] == 107:
                            dead_count += 1
                            alive_count = max(0, total_players - dead_count)
                            try:
                                bot_state.update_match_stats(uid_str, alive=alive_count, dead=dead_count)
                            except Exception:
                                pass
                            continue
                        if frame['cmd'] == 103:
                            print_success(f"[MATCH #{match_index}] MATCH_END", uid=uid_str)
                            completed_cleanly = True
                            local_closed = True
                            continue
                        if frame['cmd'] == 102:
                            dead_count += 1
                            alive_count = max(0, total_players - dead_count)
                            try:
                                bot_state.update_match_stats(uid_str, alive=alive_count, dead=dead_count)
                            except Exception:
                                pass
                            continue
                        if frame['cmd'] == 101:
                            try:
                                ack_pkt = await build_packet(0x68, (await layouts_from_mask(match_code))[1], 0, 2, None, 1, b"\x01\x00", udp_key_bytes)
                                await loop.sock_sendto(sock, ack_pkt, server_addr)
                            except Exception:
                                pass
                            continue
                        if ptype in ["ACK", "PING", "HELLO", "JOIN_MATCH"]:
                            if ptype == "HELLO" and ack_state == "waiting_for_hello_reply":
                                typ, reply = await reply_for(frame, udp_key_bytes, match_code, ack_style="short")
                                if reply:
                                    await loop.sock_sendto(sock, reply, server_addr)
                                ack_state = "ack_sent_waiting"
                            elif ptype == "ACK":
                                if ack_state == "waiting_for_hello_reply":
                                    typ, reply = await reply_for(frame, udp_key_bytes, match_code)
                                    if reply:
                                        await loop.sock_sendto(sock, reply, server_addr)
                                    ack_state = "ready_to_send_thunder"
                                elif ack_state == "ack_sent_waiting":
                                    ack_state = "ready_to_send_thunder"
                                else:
                                    typ, reply = await reply_for(frame, udp_key_bytes, match_code)
                                    if reply:
                                        await loop.sock_sendto(sock, reply, server_addr)
                            elif ptype == "PING":
                                typ, reply = await reply_for(frame, udp_key_bytes, match_code)
                                if reply:
                                    await loop.sock_sendto(sock, reply, server_addr)
                            elif ptype == "JOIN_MATCH" and not join_match_received:
                                typ, reply = await reply_for(frame, udp_key_bytes, match_code)
                                if reply:
                                    await loop.sock_sendto(sock, reply, server_addr)
                                    join_match_received = True
            except asyncio.TimeoutError:
                if ack_state == "ready_to_send_thunder" and not thunder_sent:
                    await send_thunder_sharma_inline()
                elif ack_state == "waiting_for_hello_reply":
                    if (time.time() - last_activity) > MAX_IDLE_BEFORE_HELLO_RESEND:
                        try:
                            pkt = await build_hello_packet(f"{account_id}_2585", udp_key_bytes, match_code)
                            await loop.sock_sendto(sock, bytes.fromhex(pkt), (resolved_ip, port))
                        except Exception:
                            pass
                        last_activity = time.time()
                    if (time.time() - match_start_time) > 25.0:
                        print_warning(f"[MATCH #{match_index}] Handshake timeout", uid=uid_str)
                        break
                elif ack_state == "thunder_sharma_sent":
                    if mode != "BR":
                        # LW: exit on idle timeout (original)
                        if (time.time() - last_activity) > idle_timeout:
                            print_info(f"[MATCH #{match_index}] Idle timeout", uid=uid_str)
                            completed_cleanly = True
                            break
                continue
            except BlockingIOError:
                await asyncio.sleep(0.05)
            except OSError:
                await asyncio.sleep(0.5)
                continue
            except Exception:
                await asyncio.sleep(0.5)
                continue
            if ack_state == "ready_to_send_thunder" and not thunder_sent:
                await send_thunder_sharma_inline()

        return f"match #{match_index} finished"
    except Exception as e:
        return f"match #{match_index} error: {e}"
    finally:
        try:
            duration = int(time.time() - match_start_ts)
            if completed_cleanly:
                print_success(f"Match #{match_index} [{mode}] DONE | Total {total_players} | Dead {dead_count} | Alive {alive_count} | {duration // 60}m {duration % 60}s", uid=uid_str)
                bot_state.track_activity(uid_str, "match_done")
            else:
                print_warning(f"Match #{match_index} [{mode}] ENDED | {duration // 60}m {duration % 60}s", uid=uid_str)
            bot_state.update_match_stats(uid_str, clear=True)
        except Exception:
            pass
        if anti_afk_task:
            anti_afk_task.cancel()
            try:
                await anti_afk_task
            except (asyncio.CancelledError, Exception):
                pass
        if completed_cleanly:
            try:
                bot_state.increment_match(uid_str)
                async def _post_match_exp_check(uid):
                    try:
                        await asyncio.sleep(3.0)
                        await refresh_account_profile(uid)
                    except Exception:
                        pass
                asyncio.create_task(_post_match_exp_check(uid_str))
            except Exception:
                pass
        ping_stop.set()
        if ping_task:
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass
        if sock:
            try:
                sock.close()
            except Exception:
                pass
        remaining = await _dec_match(uid_str)
        try:
            bot_state.update_status(uid_str, f"IN_MATCH ({mode})" if remaining > 0 else "ONLINE", remaining)
        except Exception:
            pass


# ==================== functional_match ====================
async def functional_match(addrs, starter_packet, account_region, client_version,
                            key, iv, account_id="", account_data=None, max_reconnects=10):
    reconnects = 0
    ip, port = addrs.split(":")
    play_matches = []
    no_response_count = 0
    match_modes = {}
    uid_str = str(account_id)
    current_token = starter_packet
    current_key = key
    current_iv = iv
    current_account_data = account_data
    br_packet_bytes = None
    lw_packet_bytes = None
    _status_cache = {"s": None, "n": -1}
    _br_match_start_time = 0.0

    # ✅ Independent fire task — shared state
    shared = {'writer': None, 'br_packet': None, 'lw_packet': None}
    fire_task = None

    def get_current_mode():
        cur_lvl = bot_state.get_account_level(uid_str)
        if current_account_data and "level" in current_account_data:
            cur_lvl = max(cur_lvl, int(current_account_data.get("level", 1) or 1))
        cur_mode = "BR" if cur_lvl < 3 else "LONE_WOLF"
        return cur_mode, cur_lvl

    try:
        while True:
            if is_account_deleted(uid_str) or is_account_stopped(uid_str):
                for m in play_matches:
                    if not m.done():
                        m.cancel()
                return
            while bot_state.is_paused(uid_str):
                try:
                    bot_state.update_status(uid_str, "PAUSED", 0)
                except Exception:
                    pass
                await asyncio.sleep(1.0)
            writer = None
            try:
                if current_account_data:
                    fresh = None
                    if current_account_data.get('auth_type') == 'guest' and current_account_data.get('auth_uid'):
                        fresh = cache_get(str(current_account_data['auth_uid']))
                    if fresh:
                        current_account_data = fresh
                        current_key = fresh.get('aes_ak', key)
                        current_iv = fresh.get('iv_i', iv)
                        if current_account_data.get('token') and current_account_data.get('server_time'):
                            current_token = await build_tcp_startup_packet(
                                current_account_data['account_id'], current_account_data['token'],
                                current_account_data['server_time'], current_key, current_iv,
                                region=current_account_data.get('region', account_region), typ='OnLine'
                            )
                resolved_ip = await resolve_host_cloudflare(ip)
                reader, writer = await asyncio.open_connection(resolved_ip, int(port))
                bot_state.register_writer(uid_str, writer)
                raw_sock = writer.get_extra_info('socket')
                if raw_sock:
                    optimize_tcp_socket(raw_sock)
                writer.write(bytes.fromhex(current_token))
                await writer.drain()
                try:
                    init_ka = await send_keep_alive(account_region)
                    if init_ka and writer and not writer.is_closing():
                        writer.write(init_ka)
                        await asyncio.wait_for(writer.drain(), timeout=3)
                except Exception:
                    pass

                async def func_gateway_keepalive():
                    ka_bytes = await send_keep_alive(account_region)
                    while True:
                        await asyncio.sleep(5)
                        try:
                            if writer and not writer.is_closing():
                                writer.write(ka_bytes)
                                await writer.drain()
                        except Exception:
                            break

                gateway_ping_task = asyncio.create_task(func_gateway_keepalive())
                print_success(f"TCP Gateway Connected | UID: {uid_str}", uid=uid_str)
                reconnects = 0
                no_response_count = 0

                try:
                    br_packet_bytes = await build_br_packet_bytes(account_region, client_version, current_key, current_iv)
                    lw_packet_bytes = await build_lw_packet_bytes(account_region, client_version, current_key, current_iv)
                    print_info(f"Packets ready | BR: {len(br_packet_bytes) if br_packet_bytes else 0}B | LW: {len(lw_packet_bytes) if lw_packet_bytes else 0}B", uid=uid_str)
                except Exception as _e:
                    print_warning(f"Packet precompute failed: {_e}", uid=uid_str)
                    br_packet_bytes = None
                    lw_packet_bytes = None

                # ✅ Update shared state — writer + packets
                shared['writer'] = writer
                shared['br_packet'] = br_packet_bytes
                shared['lw_packet'] = lw_packet_bytes

                # ✅ Start fire_worker ONCE per writer session
                if fire_task is None or fire_task.done():
                    fire_task = asyncio.create_task(fire_worker(shared, uid_str, get_current_mode))

                while True:
                    play_matches[:] = [m for m in play_matches if not m.done()]
                    if is_account_stopped(uid_str) or is_account_deleted(uid_str):
                        return
                    if bot_state.is_paused(uid_str):
                        try:
                            bot_state.update_status(uid_str, "PAUSED", 0)
                        except Exception:
                            pass
                        shared['writer'] = None  # ✅ stop firing while paused
                        bot_state.unregister_writer(uid_str, writer)
                        if 'gateway_ping_task' in locals() and gateway_ping_task:
                            gateway_ping_task.cancel()
                        await safe_close_writer(writer)
                        writer = None
                        while bot_state.is_paused(uid_str):
                            await asyncio.sleep(1.0)
                        break

                    active_count = await _get_match_count(uid_str)
                    has_active_match = any(not m.done() for m in play_matches)
                    cur_mode, cur_lvl = get_current_mode()
                    current_status = f"IN_MATCH ({cur_mode})" if (active_count > 0 or has_active_match) else f"ONLINE ({cur_mode})"
                    if _status_cache["s"] != current_status or _status_cache["n"] != active_count:
                        _status_cache["s"] = current_status
                        _status_cache["n"] = active_count
                        try:
                            bot_state.update_status(uid_str, current_status, active_count)
                        except Exception:
                            pass

                    for _t in list(match_modes.keys()):
                        if _t.done():
                            del match_modes[_t]
                    play_matches[:] = [m for m in play_matches if not m.done()]

                    # Level 3+ → kill BR, go LW (original)
                    if cur_mode == "LONE_WOLF":
                        running_br = [m for m, md in match_modes.items() if md == "BR" and not m.done()]
                        if running_br:
                            print_success(f"UID {uid_str} Lvl {cur_lvl} -> LW NOW (killing BR)", uid=uid_str)
                            for _m in running_br:
                                _m.cancel()
                            await asyncio.gather(*running_br, return_exceptions=True)
                            for _m in running_br:
                                match_modes.pop(_m, None)
                            play_matches[:] = [m for m in play_matches if m not in running_br]
                            _br_match_start_time = 0.0

                    # ✅ Fire logic now in fire_worker (independent task)
                    # No fire code here — just read packets

                    try:
                        data = await asyncio.wait_for(reader.read(8192), timeout=1.0)
                    except asyncio.TimeoutError:
                        no_response_count += 1
                        if no_response_count > 60:
                            no_response_count = 0
                        continue
                    if not data:
                        raise ConnectionError("Connection closed by server")
                    hex_data = data.hex()
                    packet_length = len(data)
                    no_response_count = 0

                    if hex_data.startswith("0300") and 10 < packet_length < 30:
                        cur_mode, _ = get_current_mode()
                        print_info(f"Queue Confirmed ({cur_mode}) | UID: {uid_str} | {packet_length}B", uid=uid_str)
                        try:
                            bot_state.update_status(uid_str, f"SEARCHING ({cur_mode})", 0)
                        except Exception:
                            pass
                        continue

                    if hex_data.startswith("0300") and packet_length >= 300:
                        cur_mode, cur_lvl = get_current_mode()
                        print_success(f"Match Found [{cur_mode}] | UID: {uid_str}", uid=uid_str)
                        try:
                            bot_state.track_activity(uid_str, "match_found")
                        except Exception:
                            pass

                        try:
                            res = json.loads(await decode_protobuf(hex_data[10:]))
                            token = udp_key = match_code = server_ip_port = match_account_id = block_val = None
                            if '42' in res and 'data' in res['42']:
                                match_code = res['42']['data']
                            if '5' in res and 'data' in res['5']:
                                res_field5 = res['5']['data']
                                server_ip_port = res_field5.get('2', {}).get('data')
                                udp_key = res_field5.get('3', {}).get('data')
                                token = res_field5.get('4', {}).get('data')
                                if '42' in res_field5:
                                    match_code = res_field5['42']['data']
                            if '1' in res and 'data' in res['1']:
                                match_account_id = res['1']['data']
                            if '5' in res and 'data' in res['5']:
                                block_val = res['5']['data'].get('1', {}).get('data')
                            effective_acc_id = match_account_id or account_id or "BD_BOT"

                            if token and udp_key and match_code and server_ip_port:
                                if is_account_stopped(uid_str) or is_account_deleted(uid_str):
                                    return
                                acc_tok = ""
                                if current_account_data:
                                    acc_tok = current_account_data.get('access_token', '') or ""
                                thunder, sharma = await build_match_startup_packets(
                                    token, udp_key, match_code, effective_acc_id, block_val or 0,
                                    server_ip=server_ip_port, region=account_region,
                                    client_version=client_version, access_token=acc_tok, mode=cur_mode
                                )

                                match_index = await _inc_match(uid_str)
                                print_info(f"Match #{match_index} [{cur_mode}] -> {server_ip_port}", uid=uid_str)
                                try:
                                    bot_state.increment_match_started()
                                except Exception:
                                    pass

                                owner = current_account_data.get('owner') if current_account_data else None
                                new_match = asyncio.create_task(play_game(
                                    server_ip_port, thunder, sharma, udp_key, match_code,
                                    effective_acc_id, "IND", client_version,
                                    current_key, current_iv, match_index=match_index,
                                    mode=cur_mode, owner=owner
                                ))
                                play_matches.append(new_match)
                                match_modes[new_match] = cur_mode

                                _br_match_start_time = time.time()
                                # ✅ Stop firing — writer closing
                                shared['writer'] = None
                                await safe_close_writer(writer)
                                await asyncio.sleep(NEW_MATCH_DELAY)
                                reconnects = 0
                                break
                            else:
                                print_info(f"[FUNCTIONAL] Config packet ({packet_length}B)", uid=uid_str)
                                continue
                        except Exception as e:
                            print_warning(f"[FUNCTIONAL] Match packet notice: {e}", uid=uid_str)
                            continue
                    if 30 <= packet_length <= 40:
                        continue
            except asyncio.CancelledError:
                if 'gateway_ping_task' in locals() and gateway_ping_task:
                    gateway_ping_task.cancel()
                if writer:
                    bot_state.unregister_writer(uid_str, writer)
                raise
            except Exception as e:
                if 'gateway_ping_task' in locals() and gateway_ping_task:
                    gateway_ping_task.cancel()
                if writer:
                    bot_state.unregister_writer(uid_str, writer)
                play_matches[:] = [m for m in play_matches if not m.done()]
                shared['writer'] = None
                await safe_close_writer(writer)
                reconnects += 1
                if reconnects > max_reconnects:
                    print_warning(f"UID {uid_str} max reconnects -> refresh", uid=uid_str)
                    if current_account_data:
                        try:
                            if current_account_data.get('auth_uid'):
                                cache_invalidate(str(current_account_data['auth_uid']))
                        except Exception:
                            pass
                    reconnects = 0
                    break
                await asyncio.sleep(min(reconnects * 0.5, 2.0))
            finally:
                if 'gateway_ping_task' in locals() and gateway_ping_task:
                    gateway_ping_task.cancel()
                if writer:
                    bot_state.unregister_writer(uid_str, writer)
                    await safe_close_writer(writer)
    except asyncio.CancelledError:
        raise
    finally:
        # ✅ Cancel fire_worker cleanly
        if fire_task and not fire_task.done():
            fire_task.cancel()
            try:
                await fire_task
            except (asyncio.CancelledError, Exception):
                pass
        for m in play_matches:
            if not m.done():
                m.cancel()


async def informational(addrs, starter_packet, key, iv, region="IND", account_id="", max_reconnects=3):
    uid_str = str(account_id)
    reconnects = 0
    ip, port = addrs.split(":")
    while True:
        while uid_str and bot_state.is_paused(uid_str):
            await asyncio.sleep(1.0)
        writer = None
        ping_task = None
        try:
            resolved_ip = await resolve_host_cloudflare(ip)
            reader, writer = await asyncio.open_connection(resolved_ip, int(port))
            if uid_str:
                bot_state.register_writer(uid_str, writer)
            raw_sock = writer.get_extra_info('socket')
            if raw_sock:
                optimize_tcp_socket(raw_sock)
            writer.write(bytes.fromhex(starter_packet))
            await writer.drain()
            reconnects = 0
            try:
                init_ka = await send_keep_alive(region)
                if init_ka and writer and not writer.is_closing():
                    writer.write(init_ka)
                    await asyncio.wait_for(writer.drain(), timeout=3)
            except Exception:
                pass

            async def info_keepalive():
                ka_bytes = await send_keep_alive(region)
                while True:
                    await asyncio.sleep(5)
                    try:
                        if writer and not writer.is_closing():
                            writer.write(ka_bytes)
                            await writer.drain()
                    except Exception:
                        break

            ping_task = asyncio.create_task(info_keepalive())
            while True:
                if uid_str and bot_state.is_paused(uid_str):
                    if ping_task:
                        ping_task.cancel()
                    if uid_str:
                        bot_state.unregister_writer(uid_str, writer)
                    await safe_close_writer(writer)
                    writer = None
                    while bot_state.is_paused(uid_str):
                        await asyncio.sleep(1.0)
                    break
                try:
                    data = await asyncio.wait_for(reader.read(8192), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if not data:
                    raise ConnectionError("Connection closed")
        except asyncio.CancelledError:
            if ping_task:
                ping_task.cancel()
            if uid_str:
                bot_state.unregister_writer(uid_str, writer)
            await safe_close_writer(writer)
            raise
        except Exception:
            if ping_task:
                ping_task.cancel()
            if uid_str:
                bot_state.unregister_writer(uid_str, writer)
            await safe_close_writer(writer)
            reconnects += 1
            if reconnects > max_reconnects:
                await asyncio.sleep(3)
                reconnects = 0
            else:
                await asyncio.sleep(1)


# ==================== ACCOUNT PROCESSORS ====================
def _register_credentials(account_data):
    try:
        acc_id = str(account_data['account_id'])
        bot_state.account_credentials[acc_id] = account_data
        if account_data.get('auth_uid'):
            bot_state.account_credentials[str(account_data['auth_uid'])] = account_data
    except Exception:
        pass


async def refresh_account_profile(account_data_or_uid):
    try:
        if isinstance(account_data_or_uid, str):
            uid = str(account_data_or_uid)
            account_data = bot_state.account_credentials.get(uid)
        else:
            account_data = account_data_or_uid
            uid = str(account_data.get('account_id'))
        if not account_data:
            return
        jwt = account_data.get('token')
        open_id = account_data.get('open_id')
        if not (jwt and open_id):
            return
        loop = asyncio.get_running_loop()
        dev = qZxWvY.mKId()
        res = await loop.run_in_executor(None, lambda: ff_login_client.gEtL(jwt, open_id, dev, "en"))
        if res and res.get("ok"):
            level = int(res.get("level", 1) or 1)
            exp = int(res.get("exp", 0) or 0)
            likes = int(res.get("likes", 0) or 0)
            nickname = res.get("nickname") or ""
            acc_id = str(account_data['account_id'])
            if exp > 0:
                old_exp = bot_state.accounts.get(acc_id, {}).get("current_exp", 0)
                bot_state.update_exp(acc_id, exp, level)
                if old_exp and exp > old_exp:
                    diff = exp - old_exp
                    print_success(f"+{diff:,} EXP | UID {acc_id} | Lvl {level}", uid=acc_id)
            try:
                account_data['level'] = level
                sync_account_level_folder(account_data)
            except Exception:
                pass
            if likes > 0 and acc_id in bot_state.accounts:
                bot_state.accounts[acc_id]["likes"] = likes
            if nickname and acc_id in bot_state.accounts:
                bot_state.accounts[acc_id]["nickname"] = nickname
    except Exception:
        pass


async def process_account_uid_pass(uid, password, owner=None):
    cached = cache_get(uid)
    if cached and cached.get('aes_ak') and cached.get('iv_i'):
        acc_id = str(cached['account_id'])
        nick = cached.get('nickname', f"Player_{acc_id}")
        lvl = cached.get('level', 1)
        exp_val = cached.get('exp', 0)
        if owner and not cached.get('owner'):
            cached['owner'] = owner
            cache_set(uid, cached)
        print_success(f"Online (cache): {nick} Lvl {lvl} | EXP: {exp_val:,}", uid=acc_id)
        bot_state.register_account(
            uid=acc_id, nickname=nick, region=cached.get('region', 'IND'),
            level=lvl, exp=exp_val, likes=cached.get('likes', 0),
            auth_uid=str(uid), owner=owner or cached.get('owner')
        )
        _register_credentials(cached)
        try:
            sync_account_level_folder(cached)
        except Exception:
            pass
        return cached

    print_info(f"Authenticating UID: {uid}...", uid=uid)
    try:
        async with _LOGIN_SEMAPHORE:
            verconfig_res = await version_config()
            release_version = "OB55"
            client_version = "2.133.9"
            if verconfig_res:
                release_version, client_version, _ = verconfig_res
            tokengrant_response = await get_access_token(uid, password)
            if tokengrant_response is None:
                return None
            open_id, access_token, platform = tokengrant_response
            loop = asyncio.get_running_loop()
            dev = qZxWvY.mKId()
            major = await loop.run_in_executor(None, lambda: ff_login_client.mAjL(access_token, open_id, dev, "en"))
            if not major or not major.get("jwt"):
                print_error(f"MajorLogin failed for {uid}", uid=uid)
                return None
            jwt_token = major["jwt"]
            acc_id = major["account_id"]
            aes_ak = major.get("aes_ak")
            iv_i = major.get("iv_i")
            server_time = major.get("server_time")
            getlogin_result = await loop.run_in_executor(None, lambda: ff_login_client.gEtL(jwt_token, open_id, dev, "en"))
            if not getlogin_result or not getlogin_result.get("ok"):
                print_error(f"GetLoginData failed for {uid}", uid=uid)
                return None
            if not aes_ak and getlogin_result.get("aes_ak"):
                aes_ak = getlogin_result["aes_ak"]
            if not iv_i and getlogin_result.get("iv_i"):
                iv_i = getlogin_result["iv_i"]
            level = int(getlogin_result.get("level", 1) or 1)
            exp = int(getlogin_result.get("exp", 0) or 0)
            likes = int(getlogin_result.get("likes", 0) or 0)
            nickname = getlogin_result.get("nickname") or f"Player_{acc_id}"
            region = getlogin_result.get("region", "IND")

        bot_state.register_account(
            uid=acc_id, nickname=nickname, region=region,
            level=level, exp=exp, likes=likes,
            auth_uid=str(uid), owner=owner
        )
        print_success(f"Login Success: {nickname} Lvl {level} | EXP: {exp:,}", uid=acc_id)
        account_data = {
            'account_id': acc_id, 'nickname': nickname, 'region': region,
            'level': level, 'exp': exp, 'likes': likes, 'open_id': open_id,
            'access_token': access_token, 'platform': str(platform), 'token': jwt_token,
            'server_time': server_time or getlogin_result.get('server_time') or int(time.time()),
            'aes_ak': aes_ak, 'iv_i': iv_i,
            'functional_addrs': getlogin_result.get('functional_addrs', ''),
            'informational_addrs': getlogin_result.get('informational_addrs', ''),
            'release_version': release_version, 'client_version': client_version,
            'server_url': major.get('server_url') or 'https://client.ind.freefiremobile.com',
            'login_payload_data': b'',
            'auth_type': 'guest', 'auth_uid': uid, 'auth_password': password,
            'owner': owner
        }
        _register_credentials(account_data)
        cache_set(uid, account_data)
        try:
            sync_account_level_folder(account_data)
        except Exception:
            pass
        return account_data
    except Exception as e:
        print_error(f"process_account error: {e}", uid=uid)
        return None


async def run_account_worker(account_data, label):
    acc_id = str(account_data['account_id'])
    informational_task = None
    exp_task = None
    try:
        reg = account_data.get('region', 'IND')
        if not account_data.get('server_time'):
            account_data['server_time'] = int(time.time())
        if not account_data.get('aes_ak') or not account_data.get('iv_i'):
            print_warning(f"[{label}] Missing aes_ak/iv_i", uid=acc_id)
            return
        if not account_data.get('functional_addrs'):
            print_warning(f"[{label}] Missing functional_addrs", uid=acc_id)
            return
        tcp_packet_online = await build_tcp_startup_packet(account_data['account_id'], account_data['token'], account_data['server_time'], account_data['aes_ak'], account_data['iv_i'], region=reg, typ='OnLine')
        tcp_packet_chat = await build_tcp_startup_packet(account_data['account_id'], account_data['token'], account_data['server_time'], account_data['aes_ak'], account_data['iv_i'], region=reg, typ='ChaT')
        if account_data.get('informational_addrs'):
            informational_task = asyncio.create_task(informational(account_data['informational_addrs'], tcp_packet_chat, account_data['aes_ak'], account_data['iv_i'], region=reg, account_id=acc_id))

        async def exp_refresher():
            while True:
                await asyncio.sleep(30)
                fresh = bot_state.account_credentials.get(acc_id)
                if fresh:
                    await refresh_account_profile(fresh)

        exp_task = asyncio.create_task(exp_refresher())
        functional_task = asyncio.create_task(functional_match(
            account_data['functional_addrs'], tcp_packet_online,
            account_data['region'], account_data['client_version'],
            account_data['aes_ak'], account_data['iv_i'],
            account_id=acc_id, account_data=account_data
        ))
        await functional_task
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print_error(f"worker error {label}: {e}", uid=acc_id)
    finally:
        for t in (informational_task, exp_task):
            if t and not t.done():
                t.cancel()
        for t in (informational_task, exp_task):
            if t:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass


async def account_loop_guest(uid, password, owner=None):
    uid_str = str(uid)
    bot_state.account_workers[uid_str] = asyncio.current_task()
    acc_id = None
    attempt = 0
    while True:
        try:
            if is_account_deleted(uid_str) or is_account_stopped(uid_str):
                break
            try:
                if os.path.exists(ACCOUNTS_FILE):
                    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                        accs = json.load(f)
                    if not any(str(a.get("uid")) == uid_str for a in accs):
                        mark_account_deleted(uid_str)
                        break
            except Exception:
                pass

            attempt += 1
            if attempt > MAX_LOGIN_ATTEMPTS:
                print_error(f"{uid_str} failed {MAX_LOGIN_ATTEMPTS}x - removing from accounts.json + level folders", uid=uid_str)
                _remove_from_accounts_json(uid_str)
                try:
                    _remove_account_from_all_level_folders(uid_str, game_uid=acc_id)
                except Exception as _e:
                    print_error(f"[LVL cleanup] {_e}", uid=uid_str)
                try:
                    cache_invalidate(uid_str)
                except Exception:
                    pass
                mark_account_stopped(uid_str)
                mark_account_deleted(uid_str)
                try:
                    bot_state.update_status(uid_str, "REMOVED")
                    bot_state.accounts.pop(uid_str, None)
                    bot_state.account_credentials.pop(uid_str, None)
                except Exception:
                    pass
                try:
                    cb = bot_state.refresh_callbacks.get("on_account_deleted")
                    if cb:
                        asyncio.create_task(cb([uid_str]))
                except Exception:
                    pass
                break

            try:
                bot_state.update_status(uid_str, "CONNECTING")
            except Exception:
                pass

            account_data = await process_account_uid_pass(uid_str, password, owner=owner)
            if is_account_stopped(uid_str) or is_account_deleted(uid_str):
                break
            if not account_data:
                print_error(f"Login failed ({attempt}/{MAX_LOGIN_ATTEMPTS}) {uid_str}", uid=uid_str)
                try:
                    bot_state.update_status(uid_str, "ERROR")
                except Exception:
                    pass
                await asyncio.sleep(3)
                continue

            attempt = 0
            acc_id = str(account_data['account_id'])
            bot_state.account_workers[acc_id] = asyncio.current_task()
            bot_state.account_workers[uid_str] = asyncio.current_task()
            bot_state.auth_to_game_id[uid_str] = acc_id
            bot_state.game_to_auth_id[acc_id] = uid_str

            await run_account_worker(account_data, uid_str)
            print_warning(f"Session finished for {uid_str}. Reconnect in 5s...", uid=uid_str)
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            print_warning(f"Worker {uid_str} stopped.", uid=uid_str)
            try:
                bot_state.update_status(uid_str, "OFFLINE")
                if acc_id:
                    bot_state.update_status(acc_id, "OFFLINE")
            except Exception:
                pass
            break
        except Exception as e:
            print_error(f"Error {uid_str}: {e}", uid=uid_str)
            if attempt >= MAX_LOGIN_ATTEMPTS:
                continue
            await asyncio.sleep(3)


def load_accounts():
    accounts = []
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    accounts = data
        except Exception as e:
            print_error(f"Could not load {ACCOUNTS_FILE}: {e}")
    if not accounts and FALLBACK_UID and FALLBACK_PASSWORD:
        accounts.append({"uid": FALLBACK_UID, "password": FALLBACK_PASSWORD})
    return accounts


# ==================== MAIN ====================
async def main():
    print("=" * 62)
    print("       HACKRR BOT - Auto Level Up System")
    print(f"       Dashboard: http://0.0.0.0:{WEB_PORT}")
    print(f"       BR: {BR_FIRE_INTERVAL}s fire | LW: {LW_FIRE_INTERVAL}s fire")
    print("=" * 62)

    _auto_assign_owners()

    try:
        await start_web_dashboard(host=WEB_HOST, port=WEB_PORT)
        print(f"[+] Dashboard started on port {WEB_PORT}")
    except Exception as e:
        print(f"[-] Dashboard error: {e}")

    try:
        if HAS_TG:
            await start_telegram_bot()
    except Exception as e:
        print(f"[-] Telegram bot failed: {e}")

    async def on_account_added_handler(data):
        sync_devices_with_accounts()
        if "uid" in data and "password" in data:
            u = str(data["uid"]).strip()
            p = str(data["password"]).strip()
            owner = data.get("owner")
            task = asyncio.create_task(account_loop_guest(u, p, owner=owner))
            bot_state.account_workers[u] = task

    async def on_refresh_account_handler(uid):
        await refresh_account_profile(uid)

    async def on_restart_account_handler(uid):
        uid_str = str(uid)
        resolved_uids = {uid_str}
        if uid_str in bot_state.game_to_auth_id:
            resolved_uids.add(str(bot_state.game_to_auth_id[uid_str]))
        if uid_str in bot_state.auth_to_game_id:
            resolved_uids.add(str(bot_state.auth_to_game_id[uid_str]))
        for u in resolved_uids:
            if u in bot_state.account_workers:
                try:
                    bot_state.account_workers[u].cancel()
                except Exception:
                    pass
                bot_state.account_workers.pop(u, None)
        accounts = load_accounts()
        for acc in accounts:
            acc_u = str(acc.get("uid", ""))
            if acc_u in resolved_uids and acc.get("password"):
                owner = acc.get("owner")
                t = asyncio.create_task(account_loop_guest(acc_u, acc["password"], owner=owner))
                bot_state.account_workers[acc_u] = t
                break

    async def on_account_deleted_handler(deleted_ids):
        for d_id in deleted_ids:
            cache_invalidate(str(d_id))
            try:
                _remove_account_from_all_level_folders(str(d_id))
            except Exception:
                pass
        sync_devices_with_accounts()

    async def on_pause_toggle_handler(uid, is_paused):
        if is_paused:
            bot_state.close_writers_for_account(str(uid))

    bot_state.refresh_callbacks["on_account_added"] = on_account_added_handler
    bot_state.refresh_callbacks["on_account_deleted"] = on_account_deleted_handler
    bot_state.refresh_callbacks["on_refresh_account"] = on_refresh_account_handler
    bot_state.refresh_callbacks["on_restart_account"] = on_restart_account_handler
    bot_state.refresh_callbacks["on_pause_toggle"] = on_pause_toggle_handler

    sync_devices_with_accounts()
    accounts = load_accounts()
    if not accounts:
        print_warning(f"[!] No accounts in {ACCOUNTS_FILE}")
    else:
        print_success(f"Loaded {len(accounts)} accounts")

    for acc in accounts:
        if "uid" in acc and "password" in acc and acc["uid"]:
            u = str(acc["uid"])
            owner = acc.get("owner")
            t = asyncio.create_task(account_loop_guest(u, acc["password"], owner=owner))
            bot_state.account_workers[u] = t

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[STOP] Shutting down...")
        try:
            await stop_telegram_bot()
        except Exception:
            pass
        for t in list(bot_state.account_workers.values()):
            t.cancel()
        await asyncio.gather(*bot_state.account_workers.values(), return_exceptions=True)
        print("[+] All sessions closed.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")