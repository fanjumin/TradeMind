"""TradeMind Backup Module — 本地备份 + 企业微信推送"""
import os, sys, json, time, hashlib, threading, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
DEFAULT_DB = str(HOME / ".hermes" / "skills" / "stock-analysis-skill" / "experience.db")
DATA_DIR = HOME / ".trademind-sync"
BACKUP_DIR = DATA_DIR / "backups"
CONFIG_DIR = DATA_DIR / "config"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_BACKUP_DIR = str(BACKUP_DIR)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PUSH_CONFIG_PATH = CONFIG_DIR / "push.json"
TRADEMIND_WEB = "http://localhost:8081"
WECOM_API = TRADEMIND_WEB + "/api/alert/send"

def fmt_sz(s):
    if not s: return "0B"
    if s < 1024: return f"{s}B"
    if s < 1024**2: return f"{s/1024:.1f}KB"
    return f"{s/1024**2:.1f}MB"

def load_push_config():
    if PUSH_CONFIG_PATH.exists():
        try: return json.loads(PUSH_CONFIG_PATH.read_text())
        except: pass
    return {"enabled": False, "wecom_user": "FanJuMin", "last_push": None, "last_error": None}

def save_push_config(cfg):
    PUSH_CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))

def push_notification(name, size=0, source="auto"):
    cfg = load_push_config()
    if not cfg.get("enabled"):
        return {"ok": False, "reason": "disabled"}
    sz_fmt = fmt_sz(size)
    now = datetime.now().strftime("%H:%M:%S")
    src = "自动备份" if source == "auto" else "手动备份"
    content = f"\u2705 TradeMind \u7ecf\u9a8c\u5e93{src}\\n\\n\U0001f4c1 {name}\\n\U0001f4e6 {sz_fmt}\\n\U0001f550 {now}\\n\\n\U0001f517 http://localhost:8081/backup"
    try:
        payload = json.dumps({"message": content, "type": "text"}).encode()
        req = urllib.request.Request(WECOM_API, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        cfg["last_push"] = datetime.now().isoformat()
        cfg["last_error"] = None
        save_push_config(cfg)
        return {"ok": True}
    except Exception as e:
        cfg["last_error"] = str(e)
        save_push_config(cfg)
        return {"ok": False, "error": str(e)}

class BackupManager:
    def list(self):
        r = []
        for f in sorted(BACKUP_DIR.iterdir(), key=os.path.getmtime, reverse=True):
            if not f.is_file() or not f.name.endswith(".db"): continue
            dt = datetime.fromtimestamp(os.path.getmtime(f))
            r.append({"name":f.name,"size":f.stat().st_size,"size_fmt":fmt_sz(f.stat().st_size),
                       "date":dt.strftime("%Y-%m-%d %H:%M"),"days_ago":(datetime.now()-dt).days})
        return r
    def save(self, data, fn=None):
        fn = fn or f"experience-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        (BACKUP_DIR / fn).write_bytes(data)
        return {"name":fn,"size":len(data)}
    def load(self, name):
        p = BACKUP_DIR / name
        if not p.exists(): raise FileNotFoundError(name)
        return p.read_bytes()
    def restore(self, name, dest):
        data = self.load(name)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)
        return {"from":name,"to":dest,"size":len(data)}
    def delete(self, name):
        p = BACKUP_DIR / name
        if p.exists(): p.unlink(); return True
        return False

class Watchdog:
    def __init__(self, db_path):
        self.db_path = db_path
        self._last_mtime = 0
        self._running = False
        self._thread = None
        self.backup = BackupManager()
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    def stop(self): self._running = False
    def set_db(self, path): self.db_path = path
    def _run(self):
        if os.path.exists(self.db_path): self._last_mtime = os.path.getmtime(self.db_path)
        while self._running:
            try:
                if os.path.exists(self.db_path):
                    mtime = os.path.getmtime(self.db_path)
                    if mtime != self._last_mtime:
                        self._last_mtime = mtime
                        data = Path(self.db_path).read_bytes()
                        r = self.backup.save(data)
                        push_notification(r["name"], r["size"], source="auto")
            except: pass
            time.sleep(10)
