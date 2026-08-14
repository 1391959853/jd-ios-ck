#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
京东 Cookie API 服务器（完全采用参考脚本转换逻辑，FRPS 动态获取 SOCKS5 代理，修复 pin 拼接 + 青龙 API 更新 + 同步格式 + 返回扩展信息 + 自动启用变量）
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
from urllib.parse import unquote, urlparse

import requests
import urllib3
from flask import Flask, request, jsonify

# ==================== 配置 ====================
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 9090
DEBUG_MODE = False

QL_BASE_URL = "http://192.168.2.100:5700"
QL_CLIENT_ID = "3e650-DrGtwj"
QL_CLIENT_SECRET = "r5lhk0qhQ_sPuvbRWAoU8JXW"

# FRPS API 地址（用于动态获取 SOCKS5 代理）
FRPS_API_URL = "http://192.168.10.10:7500/api/proxy/tcp"
# =============================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
BEIJING_TZ = timezone(timedelta(hours=8))


# ==================== 青龙 API（按官方文档修正） ====================
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
                logger.info("青龙登录成功")
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
        if result and isinstance(result, list) and len(result) > 0:
            return result[0].get("id")
        return None

    def update_env(self, env_id, name, value, remarks=""):
        data = {"id": env_id, "name": name, "value": value, "remarks": remarks}
        result = self._request("PUT", "/open/envs", json=data)
        return result

    def enable_env(self, env_id):
        """启用环境变量"""
        if not env_id:
            return None
        data = [env_id]
        result = self._request("PUT", "/open/envs/enable", json=data)
        return result


# ==================== 签名相关函数（与参考脚本完全一致） ====================
UserAgent = ""

def randomuserAgent():
    global UserAgent, struuid, addressid, iosVer, iosV, clientVersion, iPhone, area, ADID, lng, lat
    struuid = ''.join(random.sample(
        ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v',
         'w', 'x', 'y', 'z', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'z'], 40))
    addressid = ''.join(random.sample('1234567898647', 10))
    iosVer = ''.join(random.sample(["15.1.1", "14.5.1", "14.4", "14.3", "14.2", "14.1", "14.0.1"], 1))
    iosV = iosVer.replace('.', '_')
    clientVersion = ''.join(random.sample(["10.3.0", "10.2.7", "10.2.4"], 1))
    iPhone = ''.join(random.sample(["8", "9", "10", "11", "12", "13"], 1))
    area = ''.join(random.sample('0123456789', 2)) + '_' + ''.join(random.sample('0123456789', 4)) + '_' + ''.join(
        random.sample('0123456789', 5)) + '_' + ''.join(random.sample('0123456789', 5))
    ADID = ''.join(random.sample('0987654321ABCDEF', 8)) + '-' + ''.join(
        random.sample('0987654321ABCDEF', 4)) + '-' + ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + ''.join(
        random.sample('0987654321ABCDEF', 4)) + '-' + ''.join(random.sample('0987654321ABCDEF', 12))
    lng = '119.31991256596' + str(random.randint(100, 999))
    lat = '26.1187118976' + str(random.randint(100, 999))
    UserAgent = f'jdapp;iPhone;10.0.4;{iosVer};{struuid};network/wifi;ADID/{ADID};model/iPhone{iPhone},1;addressid/{addressid};appBuild/167707;jdSupportDarkMode/0;Mozilla/5.0 (iPhone; CPU iPhone OS {iosV} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/null;supportJDSHWK/1'

def randomstr(num):
    return ''.join(str(uuid.uuid4()).split('-'))

def randomstr1(num):
    randomstr = ""
    for i in range(num):
        randomstr = randomstr + random.choice("abcdefghijklmnopqrstuvwxyz0123456789")
    return randomstr

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
        random.randint(1, 10000), random.randint(1, 10000), random.randint(1, 10000), random.randint(1, 10000)))
    d_model = random.choice(['Mi11Ultra', 'Mi11', 'Mi10'])
    d_model = base64Encode(d_model)
    ep = '{"hdid":"JM9F1ywUPwflvMIpYPok0tt5k9kW4ArJEU3lfLhxBqw=","ts":%s,"ridx":-1,"cipher":{"area":"%s","d_model":"%s","wifiBssid":"dW5hbw93bq==","osVersion":"CJS=","d_brand":"WQvrb21f","screen":"CtS1DIenCNqm","uuid":"%s","aid":"%s","openudid":"%s"},"ciphertype":5,"version":"1.2.0","appname":"com.jingdong.app.mall"}' % (
        int(ts) - random.randint(100, 1000), area, d_model, bsjduuid, bsjduuid, bsjduuid)
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
    convertUrl = 'body=%s&clientVersion=%s&client=%s&sdkVersion=31&lang=zh_CN&harmonyOs=0&networkType=wifi&oaid=%s&ef=1&ep=%s&st=%s&sign=%s&sv=%s' % (
        body, clientVersion, client, suid, urllib.parse.quote(ep), st, sign, sv)
    return convertUrl


# ==================== FRPS 代理获取 ====================
def fetch_proxies_from_frps():
    """
    从 FRPS API 获取在线 SOCKS5 代理列表
    """
    try:
        resp = requests.get(FRPS_API_URL, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"FRPS API 状态码异常: {resp.status_code}")
            return []
        data = resp.json()
        proxies_raw = data.get("proxies", [])
        frps_host = urlparse(FRPS_API_URL).hostname or "192.168.10.10"
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
        return active
    except Exception as e:
        logger.error(f"FRPS API 请求失败: {e}")
        return []


def test_proxy(proxy_url):
    """
    测试代理是否可用，并尝试获取出口 IP
    返回 (True, 出口IP) 或 (True, None) 或 (False, None)
    """
    if not proxy_url:
        return False, None
    if not proxy_url.startswith('socks5://'):
        proxy_url = 'socks5://' + proxy_url
    proxies = {"http": proxy_url, "https": proxy_url}
    exit_ip = None
    try:
        resp = requests.get("https://jd.com", proxies=proxies, timeout=10, verify=False)
        if resp.status_code != 200:
            logger.debug(f"代理 {proxy_url} 访问 jd.com 返回状态码 {resp.status_code}，不可用")
            return False, None

        try:
            requests.head("https://api.m.jd.com", proxies=proxies, timeout=10, verify=False)
        except Exception as e:
            logger.debug(f"代理 {proxy_url} 访问 api.m.jd.com 失败: {e}，不可用")
            return False, None

        logger.debug(f"代理 {proxy_url} 可用")
        # 尝试获取出口 IP（网站可能不可用，异常可忽略）
        try:
            ip_resp = requests.get("https://4.ipw.cn", proxies=proxies, timeout=5, verify=False)
            if ip_resp.status_code == 200:
                exit_ip = ip_resp.text.strip()
                logger.debug(f"通过代理 {proxy_url} 的出口 IP 为: {exit_ip}")
            else:
                logger.debug(f"通过代理 {proxy_url} 获取出口 IP 失败，状态码: {ip_resp.status_code}")
        except Exception as e:
            logger.debug(f"通过代理 {proxy_url} 获取出口 IP 时出现异常（可忽略）: {e}")
        return True, exit_ip
    except Exception as e:
        logger.debug(f"代理 {proxy_url} 测试失败: {e}")
        return False, None


def get_next_available_proxy():
    """
    从 FRPS 获取代理列表，随机选择一个可用代理
    返回 (代理地址, 代理字典, 出口IP)，若无可用则返回 (None, None, None)
    """
    proxies = fetch_proxies_from_frps()
    if not proxies:
        logger.debug("FRPS 未获取到可用代理，将使用直连")
        return None, None, None

    random.shuffle(proxies)
    for proxy in proxies:
        available, exit_ip = test_proxy(proxy)
        if available:
            if not proxy.startswith('socks5://'):
                proxy = 'socks5://' + proxy
            proxies_dict = {"http": proxy, "https": proxy}
            ip_info = f"，出口 IP: {exit_ip}" if exit_ip else ""
            logger.info(f"使用 SOCKS5 代理: {proxy}{ip_info}")
            return proxy, proxies_dict, exit_ip
        else:
            logger.debug(f"代理 {proxy} 不可用，尝试下一个")

    logger.debug("警告：所有 FRPS 代理均不可用，将使用直连")
    return None, None, None


# ==================== 转换主函数（完全复制自参考脚本，仅将 print 替换为 logger） ====================
def getcookie_wskey(key):
    """
    转换 wskey 为 cookie
    内部会自动获取一个可用代理
    """
    proxy_str, proxies_dict, exit_ip = get_next_available_proxy()

    # 安全提取 pin，若失败则记录 key 前50字符（调试模式）
    try:
        pin_match = re.findall("pin=([^;]*);", key)
        if pin_match and pin_match[0]:
            pin = pin_match[0][0] if isinstance(pin_match[0], tuple) else pin_match[0]
        else:
            pin = "未知(pin提取失败)"
            logger.debug(f"警告：无法从 key 中提取 pin，key 前50字符: {key[:50]}")
    except Exception as e:
        pin = "未知(pin提取异常)"
        logger.debug(f"提取 pin 时发生异常: {e}，key: {key[:50]}")

    body = "body=%7B%22to%22%3A%22https%3A//plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html%22%7D"

    for num in range(0, 5):
        sign = get_sign("genToken", {"url": "https://plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html"},
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
            if proxy_str:
                logger.debug(f"正在为 {unquote(pin)} 请求 token，使用代理: {proxy_str}")
            else:
                logger.debug(f"正在为 {unquote(pin)} 请求 token，使用直连")
            resp = requests.post(url=url, headers=headers, data=body, verify=False,
                                 proxies=proxies_dict, timeout=30)
            token = resp.json()
            token = token['tokenKey']
        except Exception as error:
            logger.debug(f"【警告】{unquote(pin)}在获取token时失败，错误详情：{error}，等待5秒后重试")
            time.sleep(5)
            if num == 4:
                logger.debug(f"【错误】{unquote(pin)}在获取token时重试5次均失败，最后错误：{error}")
                return "Error"
            randomuserAgent()
            continue

        if token != "xxx":
            break
        else:
            logger.debug(f"【警告】{unquote(pin)}在获取token时返回 'xxx'，等待5秒后重试")
            time.sleep(5)
            randomuserAgent()

    if token == "xxx":
        logger.debug(f"【错误】{unquote(pin)}在获取token时最终失败，跳过")
        return "Error"

    for num in range(0, 5):
        url = 'https://un.m.jd.com/cgi-bin/app/appjmp'
        params = {
            'tokenKey': token,
            'to': 'https://plogin.m.jd.com/cgi-bin/m/thirdapp_auth_page',
            'client_type': 'android',
            'appid': 879,
            'appup_type': 1,
        }
        try:
            if proxy_str:
                logger.debug(f"正在为 {unquote(pin)} 获取 cookie，使用代理: {proxy_str}")
            else:
                logger.debug(f"正在为 {unquote(pin)} 获取 cookie，使用直连")
            res = requests.get(url=url, params=params, verify=False, allow_redirects=False,
                               proxies=proxies_dict, timeout=30).cookies.get_dict()
        except Exception as error:
            logger.debug(f"【警告】{unquote(pin)}在获取cookie时失败，错误详情：{error}，等待5秒后重试")
            time.sleep(5)
            if num == 4:
                logger.debug(f"【错误】{unquote(pin)}在获取cookie时重试5次均失败，最后错误：{error}")
                return "Error"
            randomuserAgent()
            continue

    try:
        if "app_open" in res['pt_key']:
            cookie = f"pt_key={res['pt_key']};pt_pin={res['pt_pin']};"
            return cookie
        else:
            return ("Error:" + str(res))
    except Exception as error:
        logger.debug(f"【错误】{unquote(pin)}在解析cookie时异常：{error}，返回数据：{res}")
        return "Error"


# ==================== IP 归属地查询 ====================
def get_ip_region(ip):
    """
    通过 ip-api.com 查询 IP 归属地（省市），失败返回空字符串
    """
    if not ip:
        return ""
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?lang=zh-CN", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                region = data.get("regionName", "")
                city = data.get("city", "")
                return f"{region} {city}".strip()
    except Exception as e:
        logger.warning(f"查询 IP 归属地失败: {e}")
    return ""


# ==================== Flask 接口 ====================
app = Flask(__name__)
qinglong_api = QingLongAPI(QL_BASE_URL, QL_CLIENT_ID, QL_CLIENT_SECRET)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "qinglong_connected": qinglong_api.token is not None}), 200

@app.route('/jd/raw_ck', methods=['POST'])
def receive_cookie():
    try:
        if not request.is_json:
            return "校验失败，京东账号: ", 400
        data = request.get_json()
        if isinstance(data, list):
            data = data[0]
        pt_key = data.get('pt_key', '')
        pt_pin_raw = data.get('pt_pin', '')   # 客户端可能已经 URL 编码，不在此处解码
        wskey = data.get('wskey', '')
        # 获取客户端 IP
        client_ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or \
                    request.headers.get('X-Real-IP', '') or \
                    request.remote_addr

        if not pt_key or not pt_pin_raw or not wskey:
            return "校验失败，京东账号: " + pt_pin_raw, 400

        # 直接使用原始 pt_pin（可能含 URL 编码）拼接 key
        full_key = f"pin={pt_pin_raw};wskey={wskey};"

        randomuserAgent()
        result = getcookie_wskey(full_key)

        # 获取当前时间
        current_time = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

        # 查询 IP 归属地
        ip_region = get_ip_region(client_ip)

        if result and result.startswith("pt_key="):
            parts = result.split(';')
            pt_key_converted = parts[0].split('=')[1]
            pt_pin_converted = parts[1].split('=')[1]   # 可能是原始编码值

            # 校验账号是否一致：直接比较原始提交的 pt_pin 与转换返回的 pt_pin（忽略大小写）
            if pt_pin_raw.lower() == pt_pin_converted.lower():
                # 同步青龙
                pt_pin_decoded = unquote(pt_pin_raw)
                remarks = f"{pt_pin_decoded};更新于 {current_time}"

                jd_cookie_value = f"pt_key={pt_key_converted};pt_pin={pt_pin_raw};"
                wskey_value = f"pin={pt_pin_raw};wskey={wskey};"

                # JD_COOKIE 同步
                existing = qinglong_api.search_env_by_pin(pt_pin_raw)
                if existing:
                    res = qinglong_api.update_env(existing['id'], "JD_COOKIE", jd_cookie_value, remarks)
                    if res is None:
                        return "校验失败，京东账号: " + pt_pin_raw, 500
                    qinglong_api.enable_env(existing['id'])   # 启用 JD_COOKIE
                else:
                    new_id = qinglong_api.add_env("JD_COOKIE", jd_cookie_value, remarks)
                    if new_id is None:
                        return "校验失败，京东账号: " + pt_pin_raw, 500
                    qinglong_api.enable_env(new_id)           # 启用新 JD_COOKIE

                # JD_WSCK 同步
                existing_wskey = qinglong_api.search_env_by_pin(pt_pin_raw, name_prefix="JD_WSCK")
                if existing_wskey:
                    res_wskey = qinglong_api.update_env(existing_wskey['id'], "JD_WSCK", wskey_value, remarks)
                    if res_wskey is None:
                        return "校验失败，京东账号: " + pt_pin_raw, 500
                    qinglong_api.enable_env(existing_wskey['id'])  # 启用 JD_WSCK
                else:
                    new_wskey_id = qinglong_api.add_env("JD_WSCK", wskey_value, remarks)
                    if new_wskey_id is None:
                        return "校验失败，京东账号: " + pt_pin_raw, 500
                    qinglong_api.enable_env(new_wskey_id)          # 启用新 JD_WSCK

                # 成功响应（纯文本换行）
                success_text = (
                    f"ok\n"
                    f"账号：{pt_pin_decoded}\n"
                    f"地区：{ip_region}\n"
                    f"时间：{current_time}\n"
                    f"IP：{client_ip}"
                )
                return success_text
            else:
                # 校验失败，返回特定文本
                return "校验失败，京东账号: " + pt_pin_raw, 400
        else:
            # 转换失败也统一返回“校验失败”
            return "校验失败，京东账号: " + pt_pin_raw, 400
    except Exception as e:
        logger.error(f"异常: {e}", exc_info=True)
        return "校验失败，京东账号: ", 500

if __name__ == '__main__':
    logger.info(f"服务启动 - 青龙：{QL_BASE_URL}, 端口：{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=DEBUG_MODE)
