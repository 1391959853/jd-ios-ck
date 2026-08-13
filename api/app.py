#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
京东 Cookie API 服务器（使用 FRPS 代理，只尝试2个代理后回退直连）
"""

import base64
import hashlib
import json
import logging
import os
import random
import re
import time
import urllib.parse
import uuid
from datetime import datetime, timezone, timedelta
from typing import List
from urllib.parse import unquote, urlparse

import requests
import urllib3
from flask import Flask, request, jsonify

# ==================== 硬编码配置 ====================
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 9090
DEBUG_MODE = False

QL_BASE_URL = "http://192.168.188.183:5800"
QL_CLIENT_ID = "PYT3_ru72T8L"
QL_CLIENT_SECRET = "qLRGGwO2o-AsV0otN3fVHgJk"

# FRPS API 配置（无认证）
FRPS_API_URL = os.environ.get("FRPS_API_URL", "http://1.sggg3326.top:7500/api/proxy/tcp")
FRPS_API_AUTH = os.environ.get("FRPS_API_AUTH", "")
# ===================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))


# ==================== FRPS 代理获取 ====================
def fetch_proxies_from_frps() -> List[str]:
    """从 FRPS API 获取 SOCKS5 代理列表（只返回在线且名称匹配的）"""
    headers = {}
    if FRPS_API_AUTH:
        encoded = base64.b64encode(FRPS_API_AUTH.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    try:
        logger.info("正在从 FRPS API 获取代理节点...")
        resp = requests.get(FRPS_API_URL, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"FRPS API 返回状态码 {resp.status_code}")
            return []
        data = resp.json()
        proxies_raw = data.get("proxies", [])
        frps_host = urlparse(FRPS_API_URL).hostname or "1.sggg3326.top"
        pattern = re.compile(r"^psyduck\d{4}-socks5$")
        active = []
        for node in proxies_raw:
            if node.get("status") != "online":
                continue
            name = node.get("name", "")
            if not pattern.match(name):
                continue
            conf = node.get("conf", {})
            remote_port = conf.get("remotePort")
            if not remote_port:
                continue
            proxy_url = f"socks5://{frps_host}:{remote_port}"
            active.append(proxy_url)
        logger.info(f"获取到 {len(active)} 个在线 SOCKS5 代理")
        return active
    except Exception as e:
        logger.error(f"FRPS API 请求异常: {e}")
        return []

def get_proxy_list() -> List[str]:
    """获取代理列表（优先自定义，否则从 FRPS 获取）"""
    custom = os.environ.get("CUSTOM_SOCKS5_PROXY", "")
    if custom:
        return [p.strip() for p in custom.split(',') if p.strip()]
    if not hasattr(get_proxy_list, "cached_list"):
        get_proxy_list.cached_list = fetch_proxies_from_frps()
    return get_proxy_list.cached_list


# ==================== 青龙 API ====================
class QingLongAPI:
    def __init__(self, base_url, client_id, client_secret):
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self._login()

    def _login(self):
        url = f"{self.base_url}/open/auth/token?client_id={self.client_id}&client_secret={self.client_secret}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 200:
                self.token = result["data"]["token"]
                logger.info("青龙登录成功 (GET 方式)")
            else:
                raise Exception(f"登录失败: {result.get('message')}")
        except Exception as e:
            logger.error(f"青龙登录异常: {e}")
            raise

    def _request(self, method, endpoint, **kwargs):
        if not self.token:
            self._login()
        url = f"{self.base_url}{endpoint}"
        headers = {"Authorization": f"Bearer {self.token}"}
        if "headers" in kwargs:
            kwargs["headers"].update(headers)
        else:
            kwargs["headers"] = headers
        try:
            resp = requests.request(method, url, **kwargs)
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 200:
                return result.get("data")
            else:
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
        result = self._request("POST", "/open/envs", json=data)
        return result

    def update_env(self, env_id, name, value, remarks=""):
        data = {"name": name, "value": value, "remarks": remarks}
        result = self._request("PUT", f"/open/envs/{env_id}", json=data)
        return result


# ==================== 京东签名与转换逻辑（原仓库） ====================
def randomstr(num: int) -> str:
    return ''.join(str(uuid.uuid4()).split('-'))

def randomstr1(num: int) -> str:
    return ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=num))

def base64Encode(string: str) -> str:
    return base64.b64encode(string.encode("utf-8")).decode('utf-8').translate(
        str.maketrans("KLMNOPQRSTABCDEFGHIJUVWXYZabcdopqrstuvwxefghijklmnyz0123456789+/",
                      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"))

def base64Decode(string: str) -> str:
    return base64.b64decode(string.translate(
        str.maketrans("KLMNOPQRSTABCDEFGHIJUVWXYZabcdopqrstuvwxefghijklmnyz0123456789+/",
                      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"))).decode('utf-8')

def randomeid() -> str:
    return 'eidAaf8081218as20a2GM%s7FnfQYOecyDYLcd0rfzm3Fy2ePY4UJJOeV0Ub840kG8C7lmIqt3DTlc11fB/s4qsAP8gtPTSoxu' % randomstr1(20)

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

def get_ep(jduuid: str = ''):
    if not jduuid:
        jduuid = randomstr(16)
    ts = str(int(time.time() * 1000))
    bsjduuid = base64Encode(jduuid)
    area_encoded = base64Encode('%s_%s_%s_%s' % (random.randint(1,10000), random.randint(1,10000), random.randint(1,10000), random.randint(1,10000)))
    d_model = base64Encode(random.choice(['Mi11Ultra', 'Mi11', 'Mi10']))
    ep_str = '{"hdid":"JM9F1ywUPwflvMIpYPok0tt5k9kW4ArJEU3lfLhxBqw=","ts":%s,"ridx":-1,"cipher":{"area":"%s","d_model":"%s","wifiBssid":"dW5hbw93bq==","osVersion":"CJS=","d_brand":"WQvrb21f","screen":"CtS1DIenCNqm","uuid":"%s","aid":"%s","openudid":"%s"},"ciphertype":5,"version":"1.2.0","appname":"com.jingdong.app.mall"}' % (int(ts)-random.randint(100,1000), area_encoded, d_model, bsjduuid, bsjduuid, bsjduuid)
    return ep_str, jduuid, ts

def get_sign(functionId: str, body: dict, client: str = "android", clientVersion: str = '11.2.8', jduuid: str = ''):
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
    convertUrl = f'body={body_str}&clientVersion={clientVersion}&client={client}&sdkVersion=31&lang=zh_CN&harmonyOs=0&networkType=wifi&oaid={suid}&ef=1&ep={urllib.parse.quote(ep)}&st={st}&sign={sign}&sv={sv}'
    return convertUrl

UserAgent = ""
def randomuserAgent():
    global UserAgent, struuid, addressid, iosVer, iosV, clientVersion, iPhone, area, ADID, lng, lat
    struuid = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=40))
    addressid = ''.join(random.sample('1234567898647', 10))
    iosVer = random.choice(["15.1.1", "14.5.1", "14.4", "14.3", "14.2", "14.1", "14.0.1"])
    iosV = iosVer.replace('.', '_')
    clientVersion = random.choice(["10.3.0", "10.2.7", "10.2.4"])
    iPhone = random.choice(["8", "9", "10", "11", "12", "13"])
    area = ''.join(random.sample('0123456789', 2)) + '_' + ''.join(random.sample('0123456789', 4)) + '_' + ''.join(random.sample('0123456789', 5)) + '_' + ''.join(random.sample('0123456789', 5))
    ADID = ''.join(random.sample('0987654321ABCDEF', 8)) + '-' + ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + ''.join(random.sample('0987654321ABCDEF', 12))
    lng = '119.31991256596' + str(random.randint(100, 999))
    lat = '26.1187118976' + str(random.randint(100, 999))
    UserAgent = f'jdapp;iPhone;10.0.4;{iosVer};{struuid};network/wifi;ADID/{ADID};model/iPhone{iPhone},1;addressid/{addressid};appBuild/167707;jdSupportDarkMode/0;Mozilla/5.0 (iPhone; CPU iPhone OS {iosV} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/null;supportJDSHWK/1'


# ==================== 核心转换函数（只尝试2个代理后回退直连） ====================
def getcookie_wskey(key: str) -> str:
    """
    尝试使用随机选择的2个代理（每个仅尝试一次），若都失败则回退到直连（尝试一次）
    返回 pt_key=xxx;pt_pin=xxx; 或 "Error"
    """
    pin_match = re.findall(r"pin=([^;]*);", key)
    pin = pin_match[0] if pin_match else "未知"
    body = "body=%7B%22to%22%3A%22https%3A//plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html%22%7D"
    token = None
    res = {}

    # 获取代理列表并随机取最多2个
    proxy_list = get_proxy_list()
    if proxy_list:
        shuffled = proxy_list.copy()
        random.shuffle(shuffled)
        selected_proxies = shuffled[:2]  # 最多2个
    else:
        selected_proxies = []

    # 尝试顺序：先代理（最多2个），再直连
    attempts = selected_proxies + [None]  # None 表示直连
    logger.info(f"将尝试 {len(selected_proxies)} 个代理，然后回退直连")

    # ----- 第一步：获取 token -----
    for proxy in attempts:
        proxies_dict = None
        if proxy:
            proxies_dict = {"http": proxy, "https": proxy}
            logger.info(f"尝试使用代理获取 token: {proxy}")
        else:
            logger.info("尝试直连获取 token")

        # 每个代理/直连只尝试一次（无重试）
        randomuserAgent()
        sign = get_sign("genToken", {"url":"https://plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html"}, "android", "11.2.8")
        if not sign:
            logger.warning("签名生成失败，跳过此尝试")
            continue
        url = f"http://api.m.jd.com/client.action?functionId=genToken&{sign}"
        headers = {
            "cookie": key,
            'user-agent': UserAgent,
            'accept-language': 'zh-Hans-CN;q=1, en-CN;q=0.9',
            'content-type': 'application/x-www-form-urlencoded;'
        }
        try:
            resp = requests.post(url=url, headers=headers, data=body, verify=False, proxies=proxies_dict, timeout=30)
            token = resp.json().get('tokenKey')
            if token and token != "xxx":
                logger.info(f"成功获取 token (代理 {proxy or '直连'})")
                break
            else:
                logger.warning(f"获取 token 失败（返回无效），代理 {proxy or '直连'}")
        except Exception as e:
            logger.warning(f"获取 token 失败 (代理 {proxy or '直连'}): {e}")
            continue
    else:
        # 所有尝试（包括直连）都失败
        logger.error("所有代理及直连均无法获取 token")
        return "Error"

    # 如果 token 获取成功，继续第二步（获取 cookie）
    # 同样采用先代理（同样列表）后直连的策略，但不重新生成列表，使用之前成功的代理顺序即可
    # 但为了尝试代理获取 cookie，可以复用 attempts 列表（已包含直连）
    for proxy in attempts:
        proxies_dict = None
        if proxy:
            proxies_dict = {"http": proxy, "https": proxy}
            logger.info(f"尝试使用代理获取 cookie: {proxy}")
        else:
            logger.info("尝试直连获取 cookie")

        # 每个代理/直连只尝试一次
        url = 'https://un.m.jd.com/cgi-bin/app/appjmp'
        params = {
            'tokenKey': token,
            'to': 'https://plogin.m.jd.com/cgi-bin/m/thirdapp_auth_page',
            'client_type': 'android',
            'appid': 879,
            'appup_type': 1,
        }
        try:
            resp = requests.get(url=url, params=params, verify=False, allow_redirects=False, proxies=proxies_dict, timeout=30)
            res = resp.cookies.get_dict()
            if 'pt_key' in res:
                logger.info(f"成功获取 cookie (代理 {proxy or '直连'})")
                break
            else:
                logger.warning(f"获取 cookie 失败（响应无 pt_key），代理 {proxy or '直连'}")
        except Exception as e:
            logger.warning(f"获取 cookie 失败 (代理 {proxy or '直连'}): {e}")
            continue
    else:
        logger.error("所有代理及直连均无法获取 cookie")
        return "Error"

    # 解析结果
    try:
        if "app_open" in res.get('pt_key', ''):
            return f"pt_key={res['pt_key']};pt_pin={res['pt_pin']};"
        else:
            return "Error:" + str(res)
    except Exception as e:
        logger.error(f"解析 cookie 异常: {e}")
        return "Error"


# ==================== 适配接口 ====================
def convert_wskey(wskey: str) -> dict:
    randomuserAgent()
    result_str = getcookie_wskey(wskey)
    if result_str and result_str.startswith("pt_key="):
        parts = result_str.split(';')
        pt_key = parts[0].split('=')[1]
        pt_pin = parts[1].split('=')[1]
        return {"pt_key": pt_key, "pt_pin": urllib.parse.unquote(pt_pin)}
    else:
        logger.error(f"转换失败，返回: {result_str}")
        return None


# ==================== Flask 应用 ====================
app = Flask(__name__)
qinglong_api = QingLongAPI(QL_BASE_URL, QL_CLIENT_ID, QL_CLIENT_SECRET)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "qinglong_connected": qinglong_api.token is not None
    }), 200


@app.route('/jd/raw_ck', methods=['POST'])
def receive_cookie():
    try:
        if not request.is_json:
            return jsonify({"code": 400, "message": "Content-Type must be application/json"}), 400

        data = request.get_json()
        if isinstance(data, list):
            data = data[0]

        pt_key = data.get('pt_key', '')
        pt_pin = data.get('pt_pin', '')
        wskey = data.get('wskey', '')

        if not pt_key or not pt_pin:
            return jsonify({"code": 400, "message": "缺少 pt_key 或 pt_pin"}), 400
        if not wskey:
            return jsonify({"code": 400, "message": "缺少 wskey"}), 400

        pt_pin_decoded = unquote(pt_pin)

        converted = convert_wskey(wskey)
        match = False
        if converted:
            pt_pin_converted = converted.get("pt_pin")
            if pt_pin_decoded.lower() == pt_pin_converted.lower():
                match = True
                logger.info(f"wskey 匹配成功：{pt_pin_decoded}")
            else:
                logger.warning(f"wskey 不匹配！提交：{pt_pin_decoded}, 转换：{pt_pin_converted}")
        else:
            logger.warning(f"wskey 转换失败：{pt_pin_decoded}")

        if not match:
            return jsonify({
                "code": 400,
                "message": "wskey 不匹配",
                "pt_pin": pt_pin_decoded,
                "match": False,
                "conversion": {
                    "success": bool(converted),
                    "matched": False
                },
                "synced": False
            })

        # 同步青龙
        jd_cookie_value = f"pt_key={pt_key};pt_pin={pt_pin_decoded};"
        wskey_value = f"wskey={wskey};pt_pin={converted['pt_pin']};"
        beijing_now = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')
        remarks = f"{pt_pin_decoded} 更新于 {beijing_now}"

        existing = qinglong_api.search_env_by_pin(pt_pin_decoded)
        if existing:
            qinglong_api.update_env(existing['id'], "JD_COOKIE", jd_cookie_value, remarks)
            action = "updated"
        else:
            qinglong_api.add_env("JD_COOKIE", jd_cookie_value, remarks)
            action = "added"

        existing_wskey = qinglong_api.search_env_by_pin(converted["pt_pin"], name_prefix="JD_WSCK")
        if existing_wskey:
            qinglong_api.update_env(existing_wskey['id'], "JD_WSCK", wskey_value, remarks)
        else:
            qinglong_api.add_env("JD_WSCK", wskey_value, remarks)

        return jsonify({
            "code": 200,
            "message": "ok",
            "action": action,
            "pt_pin": pt_pin_decoded,
            "match": True,
            "synced_vars": ["JD_COOKIE", "JD_WSCK"],
            "conversion": {"success": True, "matched": True},
            "synced": True
        })

    except Exception as e:
        logger.error(f"异常：{e}")
        return jsonify({"code": 500, "message": str(e)}), 500


if __name__ == '__main__':
    logger.info(f"服务启动 - 青龙：{QL_BASE_URL}, 端口：{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=DEBUG_MODE)
