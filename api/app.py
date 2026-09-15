#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import hashlib
import json
import logging
import os
import random
import re
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote, urlparse

try:
    import socks
except ImportError:
    raise SystemExit("缺少 PySocks: pip install PySocks")

from flask import Flask, request, Response

# ==================== 配置 ====================
LOCAL_HOST = "127.0.0.1"

# 青龙
QL_PORT = 5700
QL_BASE_URL = f"http://{LOCAL_HOST}:{QL_PORT}"
QL_CLIENT_ID = "EuLT2_tKHm-M"
QL_CLIENT_SECRET = "gOLvnmMFvkvrNkV5hh_7S5mB"
KEEP_WSKEY_ONLY = True

# FRPS
FRPS_PORT = 7500
FRPS_API_PATH = "/api/proxy/tcp"
FRPS_API_URL = f"http://{LOCAL_HOST}:{FRPS_PORT}{FRPS_API_PATH}"
FRPS_HOST = LOCAL_HOST
FRPS_NAME_PATTERN = re.compile(r"^psyduck\d{4}-socks5$")
FRPS_TEST_URL = "https://jd.com"

# SOCKS5 认证
SOCKS5_USERNAME = "xiaoz"
SOCKS5_PASSWORD = "a1391959853"

# 超时与重试
REQUEST_TIMEOUT = 8
TEST_TIMEOUT = 3
RETRY_TIMES = 2
RETRY_SLEEP = 1

# 校验成功记录文件
CACHE_FILE = "/app/data/success_cache.json"

# 服务
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 9090
DEBUG_MODE = False
# ==============================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
BEIJING_TZ = timezone(timedelta(hours=8))

_SOCK_LOCK = threading.Lock()
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE
_ua_local = threading.local()
_CACHE_LOCK = threading.Lock()


def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"读取缓存文件失败: {e}")
        return {}


def _save_cache(data):
    try:
        d = os.path.dirname(CACHE_FILE)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CACHE_FILE)
    except Exception as e:
        logger.warning(f"写入缓存文件失败: {e}")


def cache_lookup(pt_pin, pin_hash):
    if not pt_pin or not pin_hash:
        return False
    with _CACHE_LOCK:
        data = _load_cache()
        stored = data.get(pt_pin)
        if not isinstance(stored, str) or not stored:
            return False
        return stored == pin_hash


def cache_store(pt_pin, pin_hash):
    if not pt_pin or not pin_hash:
        return
    with _CACHE_LOCK:
        data = _load_cache()
        if data.get(pt_pin) == pin_hash:
            return
        data[pt_pin] = pin_hash
        _save_cache(data)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return fp
    http_error_301 = http_error_303 = http_error_307 = http_error_302


def _urlopen_via_socks5(req, proxy_host, proxy_port, timeout=None, follow_redirect=True):
    if timeout is None:
        timeout = REQUEST_TIMEOUT
    with _SOCK_LOCK:
        original_socket = socket.socket
        socks.set_default_proxy(
            socks.SOCKS5,
            proxy_host,
            int(proxy_port),
            username=SOCKS5_USERNAME or None,
            password=SOCKS5_PASSWORD or None,
        )
        socket.socket = socks.socksocket
        try:
            handlers = [urllib.request.HTTPSHandler(context=_SSL_CTX)]
            if not follow_redirect:
                handlers.append(_NoRedirectHandler())
            opener = urllib.request.build_opener(*handlers)
            return opener.open(req, timeout=timeout)
        finally:
            socket.socket = original_socket


class QingLongAPI:
    def __init__(self, base_url, client_id, client_secret):
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self._login()

    def _login(self):
        query = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        })
        url = f"{self.base_url}/open/auth/token?{query}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") == 200:
                self.token = result["data"]["token"]
                logger.info("青龙登录成功")
            else:
                raise Exception(f"登录失败: {result.get('message')}")
        except Exception as e:
            logger.error(f"青龙登录异常: {e}")
            raise

    def _request(self, method, endpoint, params=None, json_body=None):
        if not self.token:
            self._login()
        url = f"{self.base_url}{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Authorization": f"Bearer {self.token}"}
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") == 200:
                return result.get("data")
            logger.error(f"青龙接口错误: {result}")
            return None
        except Exception as e:
            logger.error(f"请求青龙失败: {e}")
            return None

    def search_env_by_pin(self, pt_pin, name_prefix="JD_COOKIE"):
        data = self._request("GET", "/open/envs", params={"searchValue": pt_pin})
        if not data:
            return None
        for env in data:
            if env.get("name", "").startswith(name_prefix) and pt_pin.lower() in env.get("value", "").lower():
                return env
        return None

    def add_env(self, name, value, remarks=""):
        data = [{"name": name, "value": value, "remarks": remarks}]
        result = self._request("POST", "/open/envs", json_body=data)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0].get("id")
        return None

    def update_env(self, env_id, name, value, remarks=""):
        data = {"id": env_id, "name": name, "value": value, "remarks": remarks}
        return self._request("PUT", "/open/envs", json_body=data)

    def enable_env(self, env_id):
        if not env_id:
            return None
        return self._request("PUT", "/open/envs/enable", json_body=[env_id])


def randomuserAgent():
    struuid = ''.join(random.sample(
        ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v',
         'w', 'x', 'y', 'z', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'z'], 40))
    addressid = ''.join(random.sample('1234567898647', 10))
    iosVer = ''.join(random.sample(["15.1.1", "14.5.1", "14.4", "14.3", "14.2", "14.1", "14.0.1"], 1))
    iosV = iosVer.replace('.', '_')
    iPhone = ''.join(random.sample(["8", "9", "10", "11", "12", "13"], 1))
    ADID = (''.join(random.sample('0987654321ABCDEF', 8)) + '-' +
            ''.join(random.sample('0987654321ABCDEF', 4)) + '-' +
            ''.join(random.sample('0987654321ABCDEF', 4)) + '-' +
            ''.join(random.sample('0987654321ABCDEF', 4)) + '-' +
            ''.join(random.sample('0987654321ABCDEF', 12)))
    ua = (f'jdapp;iPhone;10.0.4;{iosVer};{struuid};network/wifi;ADID/{ADID};'
          f'model/iPhone{iPhone},1;addressid/{addressid};appBuild/167707;'
          f'jdSupportDarkMode/0;Mozilla/5.0 (iPhone; CPU iPhone OS {iosV} like Mac OS X) '
          f'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/null;supportJDSHWK/1')
    _ua_local.useragent = ua
    return ua


def randomstr(num):
    return ''.join(str(uuid.uuid4()).split('-'))


def randomstr1(num):
    return ''.join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(num))


def sign_core(inarg):
    key = b'80306f4370b39fd5630ad0529f77adb6'
    mask = [0x37, 0x92, 0x44, 0x68, 0xA5, 0x3D, 0xCC, 0x7F, 0xBB, 0xF, 0xD9, 0x88, 0xEE, 0x9A, 0xE9, 0x5A]
    array = [0 for _ in range(len(inarg))]
    for i in range(len(inarg)):
        r0 = int(inarg[i])
        r2 = mask[i & 0xf]
        r4 = int(key[i & 7])
        r0 = r2 ^ r0
        r0 = r0 ^ r4
        r0 = r0 + r2
        r2 = r2 ^ r0
        r1 = int(key[i & 7])
        r2 = r2 ^ r1
        array[i] = r2 & 0xff
    return bytes(array)


def base64Encode(string):
    return base64.b64encode(string.encode("utf-8")).decode('utf-8').translate(
        str.maketrans("KLMNOPQRSTABCDEFGHIJUVWXYZabcdopqrstuvwxefghijklmnyz0123456789+/",
                      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"))


def randomeid():
    return 'eidAaf8081218as20a2GM%s7FnfQYOecyDYLcd0rfzm3Fy2ePY4UJJOeV0Ub840kG8C7lmIqt3DTlc11fB/s4qsAP8gtPTSoxu' % randomstr1(20)


def get_ep(jduuid: str = ''):
    if not jduuid:
        jduuid = randomstr(16)
    ts = str(int(time.time() * 1000))
    bsjduuid = base64Encode(jduuid)
    area = base64Encode('%s_%s_%s_%s' % (
        random.randint(1, 10000), random.randint(1, 10000),
        random.randint(1, 10000), random.randint(1, 10000)))
    d_model = base64Encode(random.choice(['Mi11Ultra', 'Mi11', 'Mi10']))
    ep = ('{"hdid":"JM9F1ywUPwflvMIpYPok0tt5k9kW4ArJEU3lfLhxBqw=","ts":%s,"ridx":-1,'
          '"cipher":{"area":"%s","d_model":"%s","wifiBssid":"dW5hbw93bq==","osVersion":"CJS=",'
          '"d_brand":"WQvrb21f","screen":"CtS1DIenCNqm","uuid":"%s","aid":"%s","openudid":"%s"},'
          '"ciphertype":5,"version":"1.2.0","appname":"com.jingdong.app.mall"}'
          % (int(ts) - random.randint(100, 1000), area, d_model, bsjduuid, bsjduuid, bsjduuid))
    return ep, jduuid, ts


def get_sign(functionId, body, client: str = "android", clientVersion: str = '11.2.8', jduuid: str = '') -> str:
    if isinstance(body, dict):
        d = body
        body = json.dumps(body)
    else:
        d = json.loads(body)
    if "eid" in d:
        eid = d["eid"]
    else:
        eid = randomeid()
    ep, suid, st = get_ep(jduuid)
    sv = random.choice(["102", "111", "120"])
    all_arg = "functionId=%s&body=%s&uuid=%s&client=%s&clientVersion=%s&st=%s&sv=%s" % (
        functionId, body, suid, client, clientVersion, st, sv)
    back_bytes = sign_core(str.encode(all_arg))
    sign = hashlib.md5(base64.b64encode(back_bytes)).hexdigest()
    convertUrl = ('body=%s&clientVersion=%s&client=%s&sdkVersion=31&lang=zh_CN&harmonyOs=0'
                  '&networkType=wifi&oaid=%s&ef=1&ep=%s&st=%s&sign=%s&sv=%s'
                  % (urllib.parse.quote(body, safe=''), clientVersion, client, suid,
                     urllib.parse.quote(ep), st, sign, sv))
    return convertUrl


def fetch_proxies_from_frps():
    try:
        req = urllib.request.Request(FRPS_API_URL, method="GET")
        with urllib.request.urlopen(req, timeout=TEST_TIMEOUT) as resp:
            if resp.status != 200:
                logger.warning(f"FRPS API 状态码异常: {resp.status}")
                return []
            data = json.loads(resp.read().decode("utf-8"))
        active = []
        for node in data.get("proxies", []):
            try:
                if node.get("status") != "online":
                    continue
                if not FRPS_NAME_PATTERN.match(node.get("name") or ""):
                    continue
                conf = node.get("conf") or {}
                remote_port = conf.get("remotePort")
                if not remote_port:
                    continue
                active.append(f"socks5://{FRPS_HOST}:{remote_port}")
            except Exception as e:
                logger.debug(f"跳过异常节点: {e}")
                continue
        return active
    except Exception as e:
        logger.error(f"FRPS API 请求失败: {e}")
        return []


def test_proxy(proxy_url):
    if not proxy_url.startswith('socks5://'):
        proxy_url = 'socks5://' + proxy_url
    parsed = urlparse(proxy_url)
    host, port = parsed.hostname, parsed.port
    if not host or not port:
        return False
    try:
        req = urllib.request.Request(FRPS_TEST_URL, method="GET")
        with _urlopen_via_socks5(req, host, port, timeout=TEST_TIMEOUT) as resp:
            if resp.status != 200:
                return False
            resp.read()
        return True
    except Exception as e:
        logger.debug(f"代理 {proxy_url} 测试失败: {e}")
        return False


def get_next_available_proxy():
    proxies = fetch_proxies_from_frps()
    if not proxies:
        logger.warning("FRPS 未获取到可用代理（拒绝直连）")
        return None, None, None

    random.shuffle(proxies)
    for proxy in proxies:
        if test_proxy(proxy):
            parsed = urlparse(proxy)
            logger.info(f"使用 SOCKS5 代理: {proxy}")
            return proxy, parsed.hostname, parsed.port

    logger.warning("所有 FRPS 代理均不可用（拒绝直连）")
    return None, None, None


def getcookie_wskey(key):
    proxy_str, proxy_host, proxy_port = get_next_available_proxy()
    if not proxy_str:
        logger.error("无可用 SOCKS5 代理，转换终止（不允许直连）")
        return "Error"

    try:
        pin_match = re.findall(r"pin=([^;]*);", key)
        pin = pin_match[0] if pin_match and pin_match[0] else "未知"
    except Exception:
        pin = "未知"

    body = 'body=%7B%22to%22%3A%22https%3A//plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html%22%7D'

    token = None
    for num in range(RETRY_TIMES):
        ua = randomuserAgent()
        sign = get_sign(
            "genToken",
            {"url": "https://plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html"},
            "android", "11.2.8",
        )
        if not sign:
            continue
        url = f"http://api.m.jd.com/client.action?functionId=genToken&{sign}"
        headers = {
            "cookie": key,
            'user-agent': ua,
            'accept-language': 'zh-Hans-CN;q=1, en-CN;q=0.9',
            'content-type': 'application/x-www-form-urlencoded;',
        }
        try:
            req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
            with _urlopen_via_socks5(req, proxy_host, proxy_port, timeout=REQUEST_TIMEOUT) as resp:
                token_data = json.loads(resp.read().decode("utf-8"))
            token = token_data["tokenKey"]
        except Exception as error:
            logger.warning(f"{unquote(pin)} 获取 token 失败（第 {num+1}/{RETRY_TIMES} 次）: {error}")
            time.sleep(RETRY_SLEEP)
            if num == RETRY_TIMES - 1:
                return "Error"
            continue

        if token != "xxx":
            break
        logger.warning(f"{unquote(pin)} genToken 返回 'xxx'（第 {num+1}/{RETRY_TIMES} 次）")
        time.sleep(RETRY_SLEEP)

    if not token or token == "xxx":
        logger.warning(f"{unquote(pin)} 最终未取得有效 token")
        return "Error"

    res_cookies = {}
    for num in range(RETRY_TIMES):
        params = {
            'tokenKey': token,
            'to': 'https://plogin.m.jd.com/cgi-bin/m/thirdapp_auth_page',
            'client_type': 'android',
            'appid': 879,
            'appup_type': 1,
        }
        full_url = 'https://un.m.jd.com/cgi-bin/app/appjmp?' + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(full_url, method="GET")
            resp = _urlopen_via_socks5(req, proxy_host, proxy_port,
                                       timeout=REQUEST_TIMEOUT, follow_redirect=False)
            try:
                try:
                    raw_cookies = resp.headers.get_all('Set-Cookie') or []
                except AttributeError:
                    raw_cookies = [v for (k, v) in resp.getheaders() if k.lower() == 'set-cookie']
            finally:
                resp.close()

            cookies_dict = {}
            for sc in raw_cookies:
                nv = sc.split(';', 1)[0].strip()
                if '=' in nv:
                    k, v = nv.split('=', 1)
                    cookies_dict[k.strip()] = v.strip()
            res_cookies = cookies_dict
        except Exception as error:
            logger.warning(f"{unquote(pin)} 获取 cookie 失败（第 {num+1}/{RETRY_TIMES} 次）: {error}")
            time.sleep(RETRY_SLEEP)
            if num == RETRY_TIMES - 1:
                return "Error"
            continue
        break

    try:
        pt_key_v = res_cookies.get('pt_key', '')
        pt_pin_v = res_cookies.get('pt_pin', '')
        if "app_open" in pt_key_v and pt_key_v and pt_pin_v:
            return f"pt_key={pt_key_v};pt_pin={pt_pin_v};"
        logger.warning(f"{unquote(pin)} appjmp 结果不含 app_open")
        return "Error"
    except Exception as e:
        logger.warning(f"{unquote(pin)} 解析 cookie 异常: {e}")
        return "Error"


app = Flask(__name__)
qinglong_api = QingLongAPI(QL_BASE_URL, QL_CLIENT_ID, QL_CLIENT_SECRET)


@app.route('/health', methods=['GET'])
def health():
    return Response(
        json.dumps({"status": "ok", "qinglong_connected": qinglong_api.token is not None}),
        mimetype="application/json",
    )


@app.route('/jd/raw_ck', methods=['POST'])
def receive_cookie():
    pt_pin_decoded = ""
    try:
        data = request.get_json(silent=True)
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            return Response("校验失败，京东账号: ", mimetype="text/plain")

        pt_key = data.get('pt_key', '')
        pt_pin_raw = data.get('pt_pin', '')
        wskey = data.get('wskey', '')
        pin_hash = data.get('pin_hash', '')

        client_ip = (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
                     or request.headers.get('X-Real-IP', '')
                     or request.remote_addr or '')

        try:
            pt_pin_decoded = unquote(pt_pin_raw) if pt_pin_raw else ""
        except Exception:
            pt_pin_decoded = pt_pin_raw

        # 四字段必填
        if not pt_key or not pt_pin_raw or not wskey or not pin_hash:
            return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")

        if not KEEP_WSKEY_ONLY:
            return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")

        current_time = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

        # 命中历史记录 → 跳过 JD 转换，用客户端 pt_key/wskey 写青龙
        if cache_lookup(pt_pin_decoded, pin_hash):
            logger.info(f"命中历史记录，跳过 JD 转换: {pt_pin_decoded}")

            remarks = f"{pt_pin_decoded};更新于 {current_time}"
            jd_cookie_value = f"pt_key={pt_key};pt_pin={pt_pin_raw};"
            wskey_value = f"pin={pt_pin_raw};wskey={wskey};"

            existing = qinglong_api.search_env_by_pin(pt_pin_raw)
            if existing:
                if qinglong_api.update_env(existing['id'], "JD_COOKIE", jd_cookie_value, remarks) is None:
                    return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")
                qinglong_api.enable_env(existing['id'])
            else:
                new_id = qinglong_api.add_env("JD_COOKIE", jd_cookie_value, remarks)
                if new_id is None:
                    return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")
                qinglong_api.enable_env(new_id)

            existing_wskey = qinglong_api.search_env_by_pin(pt_pin_raw, name_prefix="JD_WSCK")
            if existing_wskey:
                if qinglong_api.update_env(existing_wskey['id'], "JD_WSCK", wskey_value, remarks) is None:
                    return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")
                qinglong_api.enable_env(existing_wskey['id'])
            else:
                new_wskey_id = qinglong_api.add_env("JD_WSCK", wskey_value, remarks)
                if new_wskey_id is None:
                    return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")
                qinglong_api.enable_env(new_wskey_id)

            success_text = (
                "ok\n"
                + "账号：" + pt_pin_decoded + "\n"
                + "时间：" + current_time + "\n"
                + "IP：" + client_ip
            )
            return Response(success_text, mimetype="text/plain")

        # 未命中 → 完整校验
        logger.info(f"未命中，进入完整校验: {pt_pin_decoded}")
        full_key = f"pin={pt_pin_raw};wskey={wskey};"
        randomuserAgent()
        result = getcookie_wskey(full_key)

        if not (result and result.startswith("pt_key=")):
            return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")

        parts = result.split(';')
        try:
            pt_key_converted = parts[0].split('=', 1)[1]
            pt_pin_converted = parts[1].split('=', 1)[1]
        except Exception:
            return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")

        try:
            pin_conv_decoded = unquote(pt_pin_converted)
        except Exception:
            pin_conv_decoded = pt_pin_converted

        if pt_pin_decoded.lower() != pin_conv_decoded.lower():
            logger.warning(f"pt_pin 不一致: 提交={pt_pin_decoded} 返回={pin_conv_decoded}")
            return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")

        remarks = f"{pt_pin_decoded};更新于 {current_time}"
        jd_cookie_value = f"pt_key={pt_key_converted};pt_pin={pt_pin_raw};"
        wskey_value = f"pin={pt_pin_raw};wskey={wskey};"

        existing = qinglong_api.search_env_by_pin(pt_pin_raw)
        if existing:
            if qinglong_api.update_env(existing['id'], "JD_COOKIE", jd_cookie_value, remarks) is None:
                return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")
            qinglong_api.enable_env(existing['id'])
        else:
            new_id = qinglong_api.add_env("JD_COOKIE", jd_cookie_value, remarks)
            if new_id is None:
                return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")
            qinglong_api.enable_env(new_id)

        existing_wskey = qinglong_api.search_env_by_pin(pt_pin_raw, name_prefix="JD_WSCK")
        if existing_wskey:
            if qinglong_api.update_env(existing_wskey['id'], "JD_WSCK", wskey_value, remarks) is None:
                return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")
            qinglong_api.enable_env(existing_wskey['id'])
        else:
            new_wskey_id = qinglong_api.add_env("JD_WSCK", wskey_value, remarks)
            if new_wskey_id is None:
                return Response("校验失败，京东账号: " + pt_pin_decoded, mimetype="text/plain")
            qinglong_api.enable_env(new_wskey_id)

        cache_store(pt_pin_decoded, pin_hash)

        success_text = (
            "ok\n"
            + "账号：" + pt_pin_decoded + "\n"
            + "时间：" + current_time + "\n"
            + "IP：" + client_ip
        )
        return Response(success_text, mimetype="text/plain")

    except Exception as e:
        logger.error(f"异常: {e}", exc_info=True)
        return Response("校验失败，京东账号: " + (pt_pin_decoded or ""), mimetype="text/plain")


if __name__ == '__main__':
    logger.info(f"服务启动 - 青龙：{QL_BASE_URL}, 端口：{SERVER_PORT}, DEBUG={DEBUG_MODE}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, threaded=True)