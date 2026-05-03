"""TradeMind Update Manager — 版本检查、更新、回退"""
import os, sys, json, subprocess, tempfile, shutil, urllib.request, zipfile, io
from datetime import datetime
from pathlib import Path

REPO = "fanjumin/TradeMind"
REMOTE = f"https://api.github.com/repos/{REPO}"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_local_version():
    """读取本地版本号"""
    vfile = os.path.join(PROJECT_DIR, "VERSION")
    if os.path.exists(vfile):
        return open(vfile).read().strip()
    return "0.0.0"

def check_update():
    """检查 GitHub 远程是否有新版本"""
    try:
        req = urllib.request.Request(f"{REMOTE}/releases/latest")
        req.add_header("Accept", "application/vnd.github.v3+json")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        latest = data.get("tag_name", "").lstrip("v")
        local = get_local_version()
        has_update = False
        if latest and local:
            lv = [int(x) for x in local.split(".")]
            rv = [int(x) for x in latest.split(".")]
            # Pad to same length
            while len(lv) < len(rv): lv.append(0)
            while len(rv) < len(lv): rv.append(0)
            has_update = rv > lv
        return {
            "has_update": has_update,
            "current": local,
            "latest": latest,
            "changelog": data.get("body", "")[:500] if has_update else "",
            "html_url": data.get("html_url", f"https://github.com/{REPO}/releases"),
        }
    except Exception as e:
        return {"has_update": False, "current": get_local_version(), "latest": "?", "error": str(e)}

def download_source():
    """从 GitHub 下载最新源码 zip"""
    try:
        url = f"https://github.com/{REPO}/archive/refs/heads/master.zip"
        resp = urllib.request.urlopen(url, timeout=30)
        return resp.read()
    except Exception as e:
        return {"error": str(e)}

def apply_update():
    """执行 git pull 更新"""
    try:
        # Stash local changes first
        subprocess.run(["git", "stash"], cwd=PROJECT_DIR, capture_output=True, timeout=10)
        # Pull
        r = subprocess.run(["git", "pull", "origin", "master"], cwd=PROJECT_DIR, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return {"ok": True, "output": r.stdout[:500]}
        return {"ok": False, "error": r.stderr[:500]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def rollback(version=""):
    """回退到指定版本"""
    try:
        if not version:
            # Get previous tag
            r = subprocess.run(["git", "describe", "--tags", "--abbrev=0", "HEAD~1"],
                             cwd=PROJECT_DIR, capture_output=True, text=True, timeout=10)
            version = r.stdout.strip()
        subprocess.run(["git", "stash"], cwd=PROJECT_DIR, capture_output=True, timeout=10)
        r = subprocess.run(["git", "checkout", f"v{version}" if not version.startswith("v") else version],
                         cwd=PROJECT_DIR, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return {"ok": True, "version": version}
        return {"ok": False, "error": r.stderr[:500]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def list_versions():
    """列出所有 git tag 版本"""
    try:
        r = subprocess.run(["git", "tag", "--sort=-version:refname"], cwd=PROJECT_DIR, capture_output=True, text=True, timeout=10)
        tags = [t.strip().lstrip("v") for t in r.stdout.strip().split("\n") if t.strip()]
        return tags
    except:
        return []
