# -*- coding: utf-8 -*-
"""
京东 WSKY 本地转换脚本（仅青龙面板）
版本：20260915_v9
功能：urllib + 远端同步 + FRPS v2 + 失败对比 + OpenAPI + 拒绝直连
DEBUG 模式：打印所有请求与响应
"""

# ========== 自动安装依赖 ==========
import subprocess
import sys
import importlib

REQUIRED_DEPS = {"pysocks": "socks"}


def _ensure_dependencies():
    missing = []
    for pip_name, import_name in REQUIRED_DEPS.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        return

    print(f"检测到缺失依赖: {', '.join(missing)}，开始自动安装...")
    sys.stdout.flush()

    pip_cmds = [
        [sys.executable, "-m", "pip", "install", "--no-cache-dir"],
        ["pip3", "install", "--no-cache-dir"],
        ["pip", "install", "--no-cache-dir"],
    ]

    for pip_name in missing:
        ok = False
        for base in pip_cmds:
            try:
                cmd = base + [pip_name]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if r.returncode == 0:
                    print(f"✅ 依赖 {pip_name} 安装成功")
                    sys.stdout.flush()
                    ok = True
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                continue
        if not ok:
            try:
                cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir",
                       "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", pip_name]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if r.returncode == 0:
                    print(f"✅ 依赖 {pip_name} 通过镜像源安装成功")
                    sys.stdout.flush()
                else:
                    print(f"❌ 依赖 {pip_name} 安装失败，请手动执行: pip3 install {pip_name}")
                    sys.stdout.flush()
            except Exception as e:
                print(f"❌ 镜像源安装 {pip_name} 异常: {e}")
                sys.stdout.flush()


_ensure_dependencies()

# ========== 正式导入 ==========
import base64
import hashlib
import json
import os
import random
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from http.cookiejar import CookieJar
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


# ========== 日志 ==========
DEBUG_MODE = os.environ.get("DEBUG_MODE", "False").lower() == "true"


def debug_print(text: str):
    if DEBUG_MODE:
        print(text)
    sys.stdout.flush()


def printf(text: str = ""):
    print(text)
    sys.stdout.flush()


# ========== HTTP 封装 ==========
class HttpResponse:
    def __init__(self, status_code, data_bytes, headers, cookies):
        self.status_code = status_code
        self._data = data_bytes
        self.headers = headers
        self._cookies = cookies
        try:
            self.text = data_bytes.decode('utf-8', errors='replace')
        except Exception:
            self.text = ''

    def json(self):
        return json.loads(self.text)

    def cookies_get_dict(self):
        return self._cookies


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_SOCKS_LOCK = threading.Lock()


def http_request(method, url, headers=None, params=None, data=None, json_data=None,
                 proxies=None, timeout=30, allow_redirects=True, verify=True):
    if params:
        sep = '&' if '?' in url else '?'
        url = url + sep + urllib.parse.urlencode(params)

    h = dict(headers) if headers else {}

    body_bytes = None
    if json_data is not None:
        body_bytes = json.dumps(json_data).encode('utf-8')
        h.setdefault('Content-Type', 'application/json')
    elif data is not None:
        if isinstance(data, str):
            body_bytes = data.encode('utf-8')
        elif isinstance(data, bytes):
            body_bytes = data
        else:
            body_bytes = urllib.parse.urlencode(data).encode('utf-8')
        h.setdefault('Content-Type', 'application/x-www-form-urlencoded')

    # ===== DEBUG: 请求 =====
    if DEBUG_MODE:
        proxy_info = f"  proxy={proxies.get('http','')}" if proxies else ""
        print(f"  → {method.upper()} {url[:200]}{proxy_info}")
        sys.stdout.flush()

    req = urllib.request.Request(url, data=body_bytes, method=method.upper())
    for k, v in h.items():
        req.add_header(k, v)

    cj = CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(cj)]

    if not verify:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))

    if not allow_redirects:
        handlers.append(_NoRedirect())

    proxy_url = None
    if proxies:
        proxy_url = proxies.get('http') or proxies.get('https')

    use_socks = bool(proxy_url and proxy_url.startswith('socks5://'))

    if not use_socks:
        if proxy_url:
            handlers.append(urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url}))
        else:
            handlers.append(urllib.request.ProxyHandler({}))

    opener = urllib.request.build_opener(*handlers)

    def _do_open():
        try:
            r = opener.open(req, timeout=timeout)
            return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    try:
        if use_socks:
            import socks
            parsed = urllib.parse.urlparse(proxy_url)
            with _SOCKS_LOCK:
                original_socket = socket.socket
                socks.set_default_proxy(
                    socks.SOCKS5,
                    parsed.hostname,
                    parsed.port,
                    username=parsed.username or None,
                    password=parsed.password or None,
                )
                socket.socket = socks.socksocket
                try:
                    status_code, data_bytes, resp_headers = _do_open()
                finally:
                    socket.socket = original_socket
        else:
            status_code, data_bytes, resp_headers = _do_open()
    except Exception as e:
        if DEBUG_MODE:
            print(f"  ← 异常: {e}")
            sys.stdout.flush()
        raise

    if DEBUG_MODE:
        preview = data_bytes[:300].decode('utf-8', errors='replace') if data_bytes else ""
        print(f"  ← {status_code}  {preview}")
        sys.stdout.flush()

    cookies = {c.name: c.value for c in cj}
    return HttpResponse(status_code, data_bytes, resp_headers, cookies)


def http_get(url, **kwargs):
    return http_request('GET', url, **kwargs)


def http_post(url, **kwargs):
    return http_request('POST', url, **kwargs)


def http_put(url, **kwargs):
    return http_request('PUT', url, **kwargs)


def http_delete(url, **kwargs):
    return http_request('DELETE', url, **kwargs)


class NoProxyAvailable(Exception):
    pass


# ========== 全局常量 ==========
MAX_ATTEMPTS = 2
RETRY_SLEEP = 3
REQUEST_TIMEOUT = 10
PROXY_TEST_TIMEOUT = 5

# ========== 远端青龙 ==========
REMOTE_QL_URL = os.environ.get("REMOTE_QL_URL", "").strip().rstrip('/')
REMOTE_QL_CLIENT_ID = os.environ.get("REMOTE_QL_CLIENT_ID", "").strip()
REMOTE_QL_CLIENT_SECRET = os.environ.get("REMOTE_QL_CLIENT_SECRET", "").strip()
_REMOTE_QL_TOKEN_CACHE = {"token": "", "expire_at": 0}

# ========== FRPS ==========
FRPS_API_PORT = int(os.environ.get("FRPS_API_PORT", "7500"))
FRPS_API_AUTH = os.environ.get("FRPS_API_AUTH", "").strip()
FRPS_SOCKS5_NAME_PATTERN = os.environ.get("FRPS_SOCKS5_NAME_PATTERN", r"^psyduck\d{4}-socks5$")
_REMOTE_SOCKS5_CACHE = {"list": [], "ts": 0}

REMOTE_SOCKS5_USER = os.environ.get("REMOTE_SOCKS5_USER", "xiaoz").strip()
REMOTE_SOCKS5_PASS = os.environ.get("REMOTE_SOCKS5_PASS", "a1391959853").strip()

# ========== Bark ==========
BARK_GROUP_MAP = {
    "qbV7HgD5P8S3i5CpQ2hmbD": [
        "h965238774", "jd_643f51dc7ddbd", "pz9042", "jd_7ce8f957eb6b7",
        "wdrgAYOQxEZPqR", "jd_6c60bf61dce54", "wdLBZyHKdgsewZ",
        "jd_vWLjBHuFeyMR", "jd_xRLJJQWFFyHn", "jd_XPlvnEmzHHFw"
    ],
    "YPewrTxp7GtBR6RFLHegLH": ["jd_488ac02303d5f"],
    "BPdbBNjmRQZH683PNzEWCY": ["jd_454e08fd6299d"],
    "WEWrmpBXqd6BdBap3ixqcd": [
        "jd_RfRHNqmekmJg", "jhgj12", "jd_itoZPRQaPKin", "wdiFjvufhXwXkt", "minitby"
    ],
    "HPnHKPr4TLbpR7bGPngbiJ": ["jd_56c714570f1b3"]
}


def _center_wrap(text: str, width: int = 40) -> str:
    """居中 + ▓▓ 包裹（无 ANSI）"""
    wrapped = f"▓▓ {text} ▓▓"

    def _w(s):
        return sum(2 if ord(c) > 127 else 1 for c in s)

    text_w = _w(wrapped)
    if text_w >= width:
        return wrapped
    left = (width - text_w) // 2
    return " " * left + wrapped


# ========== FRPS 节点解析 ==========
def _extract_port(node):
    try:
        spec = node.get("spec") or {}
        tcp = spec.get("tcp") or {}
        v = tcp.get("remotePort")
        if v:
            return int(v)
    except (ValueError, TypeError, AttributeError):
        pass
    for container in (node.get("conf") or {}, node):
        if not isinstance(container, dict):
            continue
        for key in ("remotePort", "remote_port", "remoteport", "port"):
            v = container.get(key)
            if v:
                try:
                    return int(v)
                except (ValueError, TypeError):
                    pass
    return None


def _extract_status(node):
    s = node.get("status", "")
    if isinstance(s, dict):
        s = s.get("phase") or s.get("status") or s.get("state") or ""
    s = str(s).lower()
    if s in ("online", "running", "active", "started"):
        return "online"
    return s


_PIN_RE = re.compile(r'(?:^|;)\s*(?:pt_)?pin=([^;]+)')


def _extract_pin(env_name: str, value: str) -> Optional[str]:
    try:
        m = _PIN_RE.search(value or "")
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


# ========== 远端青龙 Token ==========
def get_remote_ql_token(force_refresh: bool = False) -> str:
    if not REMOTE_QL_URL or not REMOTE_QL_CLIENT_ID or not REMOTE_QL_CLIENT_SECRET:
        return ""

    now = time.time()
    if (not force_refresh) and _REMOTE_QL_TOKEN_CACHE["token"] \
            and now < _REMOTE_QL_TOKEN_CACHE["expire_at"]:
        return _REMOTE_QL_TOKEN_CACHE["token"]

    token = ""
    expiration = 0
    ok = False

    for ep_url in [f"{REMOTE_QL_URL}/open/auth/token", f"{REMOTE_QL_URL}/open/auth/token2"]:
        try:
            params = {"client_id": REMOTE_QL_CLIENT_ID, "client_secret": REMOTE_QL_CLIENT_SECRET}
            resp = http_get(ep_url, params=params, timeout=10, verify=False)

            if resp.status_code == 200:
                data = resp.json() or {}
                body = data.get("data") if isinstance(data, dict) else None
                if isinstance(body, dict):
                    token = body.get("token", "") or ""
                    try:
                        expiration = int(body.get("expiration", 0) or 0)
                    except (TypeError, ValueError):
                        expiration = 0
                if not token and isinstance(data, dict):
                    token = data.get("token", "") or ""
                if token:
                    ok = True
                    break
        except Exception as e:
            debug_print(f"  ⚠️ {ep_url} 异常: {e}")

    if not ok:
        try:
            url = f"{REMOTE_QL_URL}/api/user/token"
            payload = {"client_id": REMOTE_QL_CLIENT_ID, "client_secret": REMOTE_QL_CLIENT_SECRET}
            resp = http_post(url, json_data=payload,
                             headers={"Content-Type": "application/json"},
                             timeout=10, verify=False)
            if resp.status_code == 200:
                data = resp.json() or {}
                body = data.get("data") if isinstance(data, dict) else None
                if isinstance(body, dict):
                    token = body.get("token", "") or ""
                    try:
                        expiration = int(body.get("expiration", 0) or 0)
                    except (TypeError, ValueError):
                        expiration = 0
                if not token and isinstance(data, dict):
                    token = data.get("token", "") or ""
        except Exception as e:
            debug_print(f"  ⚠️ Fallback 异常: {e}")

    if not token:
        return ""

    cache_until = (expiration - 600) if expiration > now else (now + 6600)
    _REMOTE_QL_TOKEN_CACHE["token"] = token
    _REMOTE_QL_TOKEN_CACHE["expire_at"] = cache_until
    return token


def fetch_remote_envs(env_name: str, remote_token: str, _retry: bool = True) -> List[dict]:
    try:
        url = f"{REMOTE_QL_URL}/open/envs"
        headers = {"Authorization": f"Bearer {remote_token}"}
        resp = http_get(url, headers=headers, timeout=15, verify=False)

        if resp.status_code in (401, 403) and _retry:
            new_token = get_remote_ql_token(force_refresh=True)
            if new_token:
                return fetch_remote_envs(env_name, new_token, _retry=False)
            return []

        if resp.status_code != 200:
            return []
        data = resp.json()
        if data.get("code") != 200:
            return []

        all_envs = data.get("data", []) or []
        return [it for it in all_envs if (it.get("name") or "").strip() == env_name]
    except Exception:
        return []


# ========== 远端 → 本机 静默同步 ==========
def sync_remote_envs_to_local_silent(local_token: str) -> Dict[str, Dict[str, dict]]:
    remote_cache: Dict[str, Dict[str, dict]] = {"JD_COOKIE": {}, "JD_WSCK": {}}
    if not REMOTE_QL_URL or not REMOTE_QL_CLIENT_ID or not REMOTE_QL_CLIENT_SECRET:
        return remote_cache

    remote_token = get_remote_ql_token()
    if not remote_token:
        return remote_cache

    local_headers = {"Authorization": f"Bearer {local_token}"}
    local_base_url = 'http://127.0.0.1:5700/api/envs'

    for env_name in ("JD_COOKIE", "JD_WSCK"):
        remote_list = fetch_remote_envs(env_name, remote_token)
        remote_by_pin: Dict[str, dict] = {}
        for it in remote_list:
            p = _extract_pin(env_name, it.get("value", ""))
            if p:
                remote_by_pin[urllib.parse.unquote(p)] = it
        remote_cache[env_name] = remote_by_pin

        try:
            local_resp = http_get(local_base_url, params={"searchValue": env_name},
                                  headers=local_headers, timeout=10)
            local_list = local_resp.json().get("data", [])
        except Exception:
            continue

        local_pins = set()
        for it in local_list:
            p = _extract_pin(env_name, it.get("value", ""))
            if p:
                local_pins.add(urllib.parse.unquote(p))

        add_list = []
        for pin, it in remote_by_pin.items():
            if pin in local_pins:
                continue
            new_env = {"name": env_name, "value": it.get("value", "")}
            if it.get("remarks"):
                new_env["remarks"] = it.get("remarks")
            add_list.append(new_env)

        if add_list:
            try:
                http_post(local_base_url, json_data=add_list, headers=local_headers, timeout=15)
            except Exception:
                pass

    return remote_cache


# ========== FRPS 代理获取 ==========
def _frps_request(path: str) -> List[dict]:
    if not REMOTE_QL_URL:
        return []
    host = urlparse(REMOTE_QL_URL).hostname or ""
    if not host:
        return []

    base = f"http://{host}:{FRPS_API_PORT}"
    headers = {}
    if FRPS_API_AUTH:
        encoded = base64.b64encode(FRPS_API_AUTH.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    url = f"{base}{path}"
    try:
        resp = http_get(url, headers=headers, timeout=10, verify=False)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if isinstance(data.get("data"), dict) and isinstance(data["data"].get("items"), list):
                return data["data"]["items"]
            if isinstance(data.get("proxies"), list):
                return data["proxies"]
            if isinstance(data.get("data"), list):
                return data["data"]
    except Exception:
        pass
    return []


def fetch_proxies_from_frps() -> List[str]:
    now = time.time()
    if _REMOTE_SOCKS5_CACHE["list"] and now - _REMOTE_SOCKS5_CACHE["ts"] < 300:
        return list(_REMOTE_SOCKS5_CACHE["list"])

    host = ""
    if REMOTE_QL_URL:
        host = urlparse(REMOTE_QL_URL).hostname or ""
    if not host:
        return []

    proxies_raw: List[dict] = []
    for ep in ["/api/v2/proxies?page=1&pageSize=200", "/api/v2/proxies", "/api/proxies", "/api/proxy/tcp"]:
        proxies_raw = _frps_request(ep)
        if proxies_raw:
            debug_print(f"  FRPS 端点: {ep}，共 {len(proxies_raw)} 个代理")
            break

    if not proxies_raw:
        return []

    auth = ""
    if REMOTE_SOCKS5_USER and REMOTE_SOCKS5_PASS:
        u = urllib.parse.quote(REMOTE_SOCKS5_USER, safe='')
        p = urllib.parse.quote(REMOTE_SOCKS5_PASS, safe='')
        auth = f"{u}:{p}@"

    pattern = re.compile(FRPS_SOCKS5_NAME_PATTERN)
    result: List[str] = []
    for node in proxies_raw:
        name = node.get("name", "") or ""
        if not pattern.match(name):
            continue
        if _extract_status(node) != "online":
            continue
        remote_port = _extract_port(node)
        if not remote_port:
            continue
        result.append(f"socks5://{auth}{host}:{remote_port}")

    debug_print(f"  ✅ FRPS 返回 {len(result)} 个 SOCKS5 节点")
    _REMOTE_SOCKS5_CACHE["list"] = result
    _REMOTE_SOCKS5_CACHE["ts"] = now
    return list(result)


# ========== 代理测试 ==========
def test_proxy(proxy_url: str) -> bool:
    if not proxy_url:
        return False
    url = proxy_url
    if url.startswith("socks5://"):
        url = url[len("socks5://"):]
    if '@' in url:
        url = url.split('@', 1)[1]
    if ':' not in url:
        return False
    host, port_str = url.rsplit(':', 1)
    try:
        port = int(port_str)
    except ValueError:
        return False
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        return True
    except Exception:
        return False


def get_exit_ip(proxies_dict: dict) -> Optional[str]:
    try:
        resp = http_get("https://checkip.amazonaws.com",
                        proxies=proxies_dict, timeout=3, verify=False)
        if resp.status_code == 200:
            m = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", resp.text)
            if m:
                return m.group(0)
    except Exception:
        pass
    return None


def select_proxy_with_ip() -> Tuple[Optional[str], Optional[dict], Optional[str]]:
    candidates = fetch_proxies_from_frps()
    if not candidates:
        return None, None, None

    random.shuffle(candidates)
    tested = 0
    for p in candidates:
        tested += 1
        if test_proxy(p):
            proxies_dict = {"http": p, "https": p}
            exit_ip = get_exit_ip(proxies_dict)
            debug_print(f"  [代理] ✅ {p.split('@')[-1]}（{tested}/{len(candidates)}） 出口: {exit_ip}")
            return p, proxies_dict, exit_ip
        debug_print(f"  [代理] ✗ {p.split('@')[-1]}（{tested}/{len(candidates)}）")

    debug_print(f"  [代理] 全部 {tested} 个不可用")
    return None, None, None


# ========== 公网 IP ==========
def get_public_ip() -> Optional[str]:
    for api_url in ["https://checkip.amazonaws.com", "https://icanhazip.com", "https://ident.me"]:
        try:
            resp = http_get(api_url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                m = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", resp.text)
                if m:
                    return m.group(0)
        except Exception:
            continue
    return None


# ========== 携趣白名单 ==========
def get_xiequ_whitelist(uid: str, ukey: str) -> List[str]:
    url = f"http://op.xiequ.cn/IpWhiteList.aspx?uid={uid}&ukey={ukey}&act=getjson"
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                return [item.get("IP") for item in data["data"] if item.get("IP")]
    except Exception:
        pass
    return []


def clear_xiequ_whitelist(uid: str, ukey: str) -> bool:
    url = f"http://op.xiequ.cn/IpWhiteList.aspx?uid={uid}&ukey={ukey}&act=del&ip=all"
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
        return resp.status_code == 200 and "success" in resp.text.lower()
    except Exception:
        return False


def add_xiequ_ip(uid: str, ukey: str, ip: str, memo: str = "auto") -> bool:
    url = f"http://op.xiequ.cn/IpWhiteList.aspx?uid={uid}&ukey={ukey}&act=add&ip={ip}&meno={memo}"
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            t = resp.text.strip().lower()
            return "success" in t or "err:iprep" in t
    except Exception:
        pass
    return False


def check_and_add_xiequ_ip():
    uid = os.environ.get("XIEQU_UID")
    ukey = os.environ.get("XIEQU_UKEY")
    if not uid or not ukey:
        return
    last_ip_file = "/tmp/last_public_ip.txt"
    current_ip = get_public_ip()
    if not current_ip:
        return
    last_ip = None
    if os.path.exists(last_ip_file):
        with open(last_ip_file, 'r') as f:
            last_ip = f.read().strip()
    if last_ip == current_ip:
        whitelist = get_xiequ_whitelist(uid, ukey)
        if current_ip not in whitelist:
            add_xiequ_ip(uid, ukey, current_ip)
            with open(last_ip_file, 'w') as f:
                f.write(current_ip)
        return
    if clear_xiequ_whitelist(uid, ukey):
        add_xiequ_ip(uid, ukey, current_ip)
        with open(last_ip_file, 'w') as f:
            f.write(current_ip)


# ========== Bark ==========
def bark_send(token: str, title: str, content: str) -> bool:
    server = os.environ.get("BARK_SERVER", "https://api.day.app").rstrip('/')
    url = f"{server}/{token}/{urllib.parse.quote(title, safe='')}/{urllib.parse.quote(content, safe='')}"
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
        return resp.status_code == 200
    except Exception:
        return False


# ========== 京东签名 ==========
def randomstr(num: int) -> str:
    return ''.join(str(uuid.uuid4()).split('-'))


def randomstr1(num: int) -> str:
    return ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=num))


def sign_core(inarg: bytes) -> bytes:
    key = b'80306f4370b39fd5630ad0529f77adb6'
    mask = [0x37, 0x92, 0x44, 0x68, 0xA5, 0x3D, 0xCC, 0x7F, 0xBB, 0xF, 0xD9, 0x88, 0xEE, 0x9A, 0xE9, 0x5A]
    array = [0] * len(inarg)
    for i in range(len(inarg)):
        r0 = inarg[i]
        r2 = mask[i & 0xf]
        r4 = key[i & 7]
        r0 = r2 ^ r0
        r0 = r0 ^ r4
        r0 = r0 + r2
        r2 = r2 ^ r0
        r1 = key[i & 7]
        r2 = r2 ^ r1
        array[i] = r2 & 0xff
    return bytes(array)


def base64Encode(string: str) -> str:
    return base64.b64encode(string.encode("utf-8")).decode('utf-8').translate(
        str.maketrans("KLMNOPQRSTABCDEFGHIJUVWXYZabcdopqrstuvwxefghijklmnyz0123456789+/",
                      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"))


def randomeid() -> str:
    return 'eidAaf8081218as20a2GM%s7FnfQYOecyDYLcd0rfzm3Fy2ePY4UJJOeV0Ub840kG8C7lmIqt3DTlc11fB/s4qsAP8gtPTSoxu' % randomstr1(20)


def randomuserAgent():
    global struuid, addressid, iosVer, iosV, clientVersion, iPhone, area, ADID, lng, lat, UserAgent
    struuid = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=40))
    addressid = ''.join(random.sample('1234567898647', 10))
    iosVer = random.choice(["15.1.1", "14.5.1", "14.4", "14.3", "14.2", "14.1", "14.0.1"])
    iosV = iosVer.replace('.', '_')
    clientVersion = random.choice(["10.3.0", "10.2.7", "10.2.4"])
    iPhone = random.choice(["8", "9", "10", "11", "12", "13"])
    area = ''.join(random.sample('0123456789', 2)) + '_' + \
           ''.join(random.sample('0123456789', 4)) + '_' + \
           ''.join(random.sample('0123456789', 5)) + '_' + \
           ''.join(random.sample('0123456789', 5))
    ADID = ''.join(random.sample('0987654321ABCDEF', 8)) + '-' + \
           ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + \
           ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + \
           ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + \
           ''.join(random.sample('0987654321ABCDEF', 12))
    lng = '119.31991256596' + str(random.randint(100, 999))
    lat = '26.1187118976' + str(random.randint(100, 999))
    UserAgent = f'jdapp;iPhone;10.0.4;{iosVer};{struuid};network/wifi;ADID/{ADID};model/iPhone{iPhone},1;addressid/{addressid};appBuild/167707;jdSupportDarkMode/0;Mozilla/5.0 (iPhone; CPU iPhone OS {iosV} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/null;supportJDSHWK/1'


def get_ep(jduuid: str = ''):
    if not jduuid:
        jduuid = randomstr(16)
    ts = str(int(time.time() * 1000))
    bsjduuid = base64Encode(jduuid)
    area_encoded = base64Encode('%s_%s_%s_%s' % (
        random.randint(1, 10000), random.randint(1, 10000),
        random.randint(1, 10000), random.randint(1, 10000)))
    d_model = base64Encode(random.choice(['Mi11Ultra', 'Mi11', 'Mi10']))
    return '{"hdid":"JM9F1ywUPwflvMIpYPok0tt5k9kW4ArJEU3lfLhxBqw=","ts":%s,"ridx":-1,"cipher":{"area":"%s","d_model":"%s","wifiBssid":"dW5hbw93bq==","osVersion":"CJS=","d_brand":"WQvrb21f","screen":"CtS1DIenCNqm","uuid":"%s","aid":"%s","openudid":"%s"},"ciphertype":5,"version":"1.2.0","appname":"com.jingdong.app.mall"}' % \
           (int(ts) - random.randint(100, 1000), area_encoded, d_model, bsjduuid, bsjduuid, bsjduuid), jduuid, ts


def get_sign(functionId: str, body: dict, client: str = "android",
             clientVersion: str = '11.2.8', jduuid: str = ''):
    if isinstance(body, dict):
        body_str = json.dumps(body)
        d = body
    else:
        body_str = body
        d = json.loads(body_str)
    eid = d.get("eid", randomeid())
    ep, suid, st = get_ep(jduuid)
    sv = random.choice(["102", "111", "120"])
    all_arg = f"functionId={functionId}&body={body_str}&uuid={suid}&client={client}&clientVersion={clientVersion}&st={st}&sv={sv}"
    back_bytes = sign_core(str.encode(all_arg))
    sign = hashlib.md5(base64.b64encode(back_bytes)).hexdigest()
    return (
        f'body={urllib.parse.quote(body_str, safe="")}'
        f'&clientVersion={clientVersion}'
        f'&client={client}'
        f'&sdkVersion=31'
        f'&lang=zh_CN'
        f'&harmonyOs=0'
        f'&networkType=wifi'
        f'&oaid={suid}'
        f'&ef=1'
        f'&ep={urllib.parse.quote(ep, safe="")}'
        f'&st={st}'
        f'&sign={sign}'
        f'&sv={sv}'
    )


def getcookie_wskey(key: str, proxy_str: str, proxies_dict: dict) -> str:
    """用指定代理完成转换。成功返回 'pt_key=...;pt_pin=...;'，失败返回 'Error'。"""
    try:
        pin_match = re.findall("pin=([^;]*);", key)
        pin = pin_match[0] if pin_match else "未知"
    except Exception:
        pin = "未知"

    body = "body=%7B%22to%22%3A%22https%3A//plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html%22%7D"
    token = None

    for num in range(MAX_ATTEMPTS):
        sign = get_sign("genToken",
                        {"url": "https://plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html"},
                        "android", "11.2.8")
        if not sign:
            continue
        url = f"http://api.m.jd.com/client.action?functionId=genToken&{sign}"
        headers = {
            "cookie": key,
            'user-agent': UserAgent,
            'accept-language': 'zh-Hans-CN;q=1, en-CN;q=0.9',
            'content-type': 'application/x-www-form-urlencoded;'
        }
        try:
            debug_print(f"  [genToken] 第 {num+1}/{MAX_ATTEMPTS} 次")
            resp = http_post(url=url, headers=headers, data=body, verify=False,
                             proxies=proxies_dict, timeout=REQUEST_TIMEOUT)
            token = resp.json().get('tokenKey')
        except Exception as e:
            debug_print(f"  [genToken] ⚠️ {e}")
            time.sleep(RETRY_SLEEP)
            randomuserAgent()
            continue
        if token and token != "xxx":
            break
        time.sleep(RETRY_SLEEP)
        randomuserAgent()

    if not token or token == "xxx":
        return "Error"

    res = {}
    for num in range(MAX_ATTEMPTS):
        url = 'https://un.m.jd.com/cgi-bin/app/appjmp'
        params = {
            'tokenKey': token,
            'to': 'https://plogin.m.jd.com/cgi-bin/m/thirdapp_auth_page',
            'client_type': 'android',
            'appid': 879,
            'appup_type': 1,
        }
        try:
            debug_print(f"  [appjmp] 第 {num+1}/{MAX_ATTEMPTS} 次")
            resp = http_get(url=url, params=params, verify=False, allow_redirects=False,
                            proxies=proxies_dict, timeout=REQUEST_TIMEOUT)
            res = resp.cookies_get_dict()
        except Exception as e:
            debug_print(f"  [appjmp] ⚠️ {e}")
            time.sleep(RETRY_SLEEP)
            randomuserAgent()
            continue
        if 'pt_key' in res:
            break

    pk = res.get('pt_key', '')
    pp = res.get('pt_pin', '')
    if "app_open" in pk and pk and pp:
        return f"pt_key={pk};pt_pin={pp};"
    return "Error"


# ========== 青龙操作 ==========
def subcookie(pt_pin: str, cookie: str, token: str, remarks: str = ""):
    url = 'http://127.0.0.1:5700/api/envs'
    headers = {'Authorization': f'Bearer {token}'}
    params = {'searchValue': pt_pin}
    datas = http_get(url, params=params, headers=headers).json().get('data', [])
    old = False
    pt_key_match = re.search(r'pt_key=([^;]+)', cookie)
    if not pt_key_match:
        return
    pt_key = pt_key_match.group(1)
    encoded_pin = urllib.parse.quote(pt_pin, safe='')
    new_cookie = f"pt_key={pt_key};pt_pin={encoded_pin};"
    for data in datas:
        if "pt_key" in data['value']:
            if '_id' in data:
                body = {"name": "JD_COOKIE", "value": new_cookie, "_id": data['_id']}
            else:
                body = {"name": "JD_COOKIE", "value": new_cookie, "id": data['id']}
            if remarks:
                body["remarks"] = remarks
            old = True
            break
    if old:
        http_put(url, json_data=body, headers=headers)
        enable_url = 'http://127.0.0.1:5700/api/envs/enable'
        ids = [body.get('_id') or body.get('id')]
        http_put(enable_url, json_data=ids, headers=headers)
    else:
        new_env = {"value": new_cookie, "name": "JD_COOKIE"}
        if remarks:
            new_env["remarks"] = remarks
        http_post(url, json_data=[new_env], headers=headers)


def get_latest_file(files):
    latest_file = None
    latest_mtime = 0
    for file in files:
        try:
            mtime = os.stat(file).st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = file
        except Exception:
            continue
    return latest_file


# ========== 备注 ==========
_TIME_PATTERN = re.compile(r'转换时间:(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
_STRIP_TIME_PATTERN = re.compile(r'\s*-?\s*转换时间:.*$')


def extract_time_from_remarks(remarks: str) -> Optional[datetime]:
    if not remarks:
        return None
    m = _TIME_PATTERN.search(remarks)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    return None


def build_remarks(pin: str, remote_remarks: str, now_str: str) -> str:
    base = (remote_remarks or "").strip()
    base = _STRIP_TIME_PATTERN.sub('', base).strip()
    if base:
        return f"{base} - 转换时间:{now_str}"
    return f"转换时间:{now_str}"


# ========== 配置检查 ==========
def check_config_and_print():
    xiequ_uid = os.environ.get("XIEQU_UID")
    xiequ_ukey = os.environ.get("XIEQU_UKEY")
    if xiequ_uid and xiequ_ukey:
        printf("携趣白名单: ✅")
    else:
        printf("携趣白名单: ❌  缺少以下环境变量")
        printf("  export XIEQU_UID=10086")
        printf("  export XIEQU_UKEY=a1b2c3d4e5f6")

    if BARK_GROUP_MAP:
        printf("Bark: ✅")
    else:
        printf("Bark: ❌  请配置脚本内 BARK_GROUP_MAP")
        printf("  {")
        printf('    "BarkToken1": ["京东账号1", "京东账号2"],')
        printf('    "BarkToken2": ["京东账号3"]')
        printf("  }")

    remote_ok = False
    if REMOTE_QL_URL and REMOTE_QL_CLIENT_ID and REMOTE_QL_CLIENT_SECRET:
        remote_ok = bool(get_remote_ql_token())
    if remote_ok:
        printf("服务端: ✅")
    else:
        if not (REMOTE_QL_URL and REMOTE_QL_CLIENT_ID and REMOTE_QL_CLIENT_SECRET):
            printf("服务端: ❌  缺少以下环境变量")
            printf("  export REMOTE_QL_URL=http://1.2.3.4:5700")
            printf("  export REMOTE_QL_CLIENT_ID=abc123")
            printf("  export REMOTE_QL_CLIENT_SECRET=def456")
        else:
            printf("服务端: ❌  远端青龙 OpenAPI 换取失败，请检查 URL / ID / SECRET")

    frps_ok = False
    if REMOTE_QL_URL:
        try:
            host = urlparse(REMOTE_QL_URL).hostname or ""
            s = socket.create_connection((host, FRPS_API_PORT), timeout=3)
            s.close()
            frps_ok = True
        except Exception:
            frps_ok = False
    if frps_ok:
        printf("FRPS: ✅")
    else:
        printf("FRPS: ❌  无法连接 FRPS，请检查")
        printf("  export REMOTE_QL_URL=http://1.2.3.4:5700")
        printf("  export FRPS_API_PORT=7500")

    printf(f"超时: {REQUEST_TIMEOUT}s/{PROXY_TEST_TIMEOUT}s")
    printf(f"重试: {MAX_ATTEMPTS}")
    printf(f"调试: {'on' if DEBUG_MODE else 'off'}")


# ========== 主流程 ==========
def main():
    t_start = time.time()
    printf(f"版本: 20260915_v9  DEBUG={'on' if DEBUG_MODE else 'off'}")
    printf("")

    check_config_and_print()
    check_and_add_xiequ_ip()

    token_file_list = ['/ql/data/db/keyv.sqlite', '/ql/data/config/auth.json']
    config = get_latest_file(token_file_list)
    if not config:
        printf("❌ 无法找到本机青龙 Token 配置，退出")
        return

    try:
        if 'keyv' in config:
            with open(config, "r", encoding="latin1") as file:
                auth = file.read()
            matches = re.search(r'"token":"([^"]*)"(?!.*"token":)', auth)
            token = matches.group(1) if matches else ""
        else:
            with open(config, "r") as file:
                auth = json.loads(file.read())
            token = auth.get("token", "")
    except Exception:
        token = ""

    if not token:
        printf("❌ 本机青龙 Token 读取失败，退出")
        return

    remote_cache = sync_remote_envs_to_local_silent(token)
    remote_cookie_map = remote_cache.get("JD_COOKIE", {})
    remote_wsck_map = remote_cache.get("JD_WSCK", {})

    headers = {'Authorization': f'Bearer {token}'}
    base_url = 'http://127.0.0.1:5700/api/envs'

    try:
        cookie_list = http_get(base_url, params={'searchValue': 'JD_COOKIE'},
                               headers=headers, timeout=10).json().get('data', [])
    except Exception as e:
        printf(f"❌ 拉取 JD_COOKIE 失败: {e}")
        return

    try:
        wsck_list = http_get(base_url, params={'searchValue': 'JD_WSCK'},
                             headers=headers, timeout=10).json().get('data', [])
    except Exception as e:
        printf(f"❌ 拉取 JD_WSCK 失败: {e}")
        return

    cookie_dict = {}
    for item in cookie_list:
        value = item.get('value', '')
        pin_match = re.findall(r'pt_pin=([^;]+)', value)
        if pin_match:
            decoded_pin = urllib.parse.unquote(pin_match[0])
            cookie_dict[decoded_pin] = item

    printf(f"Cookie: {len(cookie_list)}    Wskey: {len(wsck_list)}")
    printf("")

    wsck_ids_to_delete = set()
    for item in wsck_list:
        value = item.get('value', '')
        p = _extract_pin("JD_WSCK", value)
        if p and re.fullmatch(r'\*+', p):
            wsck_id = item.get('_id') or item.get('id')
            try:
                http_delete(base_url, json_data=[wsck_id], headers=headers)
            except Exception:
                pass
            wsck_ids_to_delete.add(wsck_id)

    printf("━━━━━━━━━━━━ 进入转换流程 ━━━━━━━━━━━━")
    printf("")

    group_fail = {token_key: [] for token_key in BARK_GROUP_MAP}
    current_time = datetime.now()
    skipped_no_proxy = 0
    skipped_by_time = 0
    fail_count = 0
    ok_count = 0
    total = len([x for x in wsck_list if (x.get('_id') or x.get('id')) not in wsck_ids_to_delete
                 and _extract_pin("JD_WSCK", x.get('value', ''))])

    for item in wsck_list:
        item_id = item.get('_id') or item.get('id')
        if item_id in wsck_ids_to_delete:
            continue
        value = item.get('value', '')
        p = _extract_pin("JD_WSCK", value)
        if not p:
            continue
        decoded_pin = urllib.parse.unquote(p)

        printf(_center_wrap(decoded_pin, 40))

        cookie_item = cookie_dict.get(decoded_pin)
        original_remarks = cookie_item.get('remarks', '') if cookie_item else ''
        remote_cookie_item = remote_cookie_map.get(decoded_pin)
        remote_cookie_remarks = (remote_cookie_item or {}).get('remarks', '') if remote_cookie_item else ''
        ref_remarks = remote_cookie_remarks or original_remarks

        if cookie_item:
            last_time = extract_time_from_remarks(original_remarks)
            if last_time:
                time_diff = current_time - last_time
                if time_diff < timedelta(hours=4):
                    printf(f"  ⏭️ 未到转换时间（已过 {time_diff.total_seconds()/3600:.1f}h）")
                    printf("")
                    skipped_by_time += 1
                    continue

        proxy_str, proxies_dict, exit_ip = select_proxy_with_ip()
        if not proxy_str:
            printf("  ⏭️ 无可用代理")
            printf("")
            skipped_no_proxy += 1
            continue

        ip_display = exit_ip if exit_ip else "未知"
        printf(f"  转换中，代理 {proxy_str.split('@')[-1]}  出口 IP: {ip_display}")

        randomuserAgent()
        cookie = getcookie_wskey(value, proxy_str, proxies_dict)

        if "app_open" in cookie:
            now_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
            new_remarks = build_remarks(decoded_pin, ref_remarks, now_str)
            try:
                orgpin = cookie.split(";")[1].split("=")[1]
            except Exception:
                m2 = re.search(r'pt_pin=([^;]+)', cookie)
                orgpin = m2.group(1) if m2 else None
            if orgpin:
                subcookie(orgpin, cookie, token, new_remarks)
                printf("  ✅ 转换成功，已更新备注时间")
                ok_count += 1
            else:
                printf("  ⚠️ 转换成功但无法解析 pt_pin")
            printf("")
            continue

        converted_ok = False
        remote_wsck = remote_wsck_map.get(decoded_pin) if remote_wsck_map else None
        remote_value = remote_wsck.get("value", "") if remote_wsck else ""
        if remote_wsck and remote_value and remote_value != value:
            try:
                body = {
                    "name": "JD_WSCK",
                    "value": remote_value,
                    "_id": item.get('_id') or item.get('id'),
                }
                if remote_wsck.get("remarks"):
                    body["remarks"] = remote_wsck.get("remarks")
                http_put(base_url, json_data=body, headers=headers, timeout=15)
            except Exception:
                pass

            randomuserAgent()
            cookie2 = getcookie_wskey(remote_value, proxy_str, proxies_dict)
            if "app_open" in cookie2:
                try:
                    orgpin2 = cookie2.split(";")[1].split("=")[1]
                except Exception:
                    m2 = re.search(r'pt_pin=([^;]+)', cookie2)
                    orgpin2 = m2.group(1) if m2 else None
                if orgpin2:
                    now_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
                    remote_wsck_remarks = remote_wsck.get("remarks", "") if remote_wsck else ""
                    new_remarks = build_remarks(decoded_pin, ref_remarks or remote_wsck_remarks, now_str)
                    subcookie(orgpin2, cookie2, token, new_remarks)
                    printf("  ✅ 转换成功（远端重试）")
                    converted_ok = True
                    ok_count += 1

        if converted_ok:
            printf("")
            continue

        if cookie.startswith("Error"):
            disable_ids = []
            if item:
                disable_ids.append(item.get('_id') or item.get('id'))
            if cookie_item:
                disable_ids.append(cookie_item.get('_id') or cookie_item.get('id'))
            if disable_ids:
                try:
                    http_put(base_url + '/disable', json_data=disable_ids, headers=headers)
                except Exception:
                    pass
            printf("  ❌ 转换失败，wskey 已过期并禁用")
            msg = f"❌ {decoded_pin} wskey过期并已禁用"
        else:
            printf("  ❌ 转换失败，代理返回异常")
            msg = f"❌ 转换失败: {decoded_pin}"

        fail_count += 1
        for token_group, pins in BARK_GROUP_MAP.items():
            if decoded_pin in pins:
                group_fail[token_group].append(msg)
                break
        printf("")

    any_sent = False
    for token_group in BARK_GROUP_MAP:
        if group_fail[token_group]:
            content = "转换异常，麻溜的更新\n" + "\n".join(group_fail[token_group])
            ok = bark_send(token_group, "JD_WSCK转换异常提醒", content)
            printf(f"Bark 推送 {token_group[:8]}...  {'✅' if ok else '❌'}（{len(group_fail[token_group])} 条失败）")
            any_sent = True
    if any_sent:
        printf("")

    elapsed = time.time() - t_start
    printf(f"完成: 成功 {ok_count}  跳过 {skipped_by_time}  无代理 {skipped_no_proxy}  失败 {fail_count}  共 {total}  耗时 {elapsed:.0f}s")


if __name__ == '__main__':
    main()