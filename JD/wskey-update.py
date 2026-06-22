# -*- coding: utf-8 -*-
"""
京东 WSKY 本地转换脚本（仅青龙面板）
版本：2026028_xiaoz（FRPS动态代理·精简版）
功能：
1. 仅适配青龙最新版，通过本地配置文件读取静态 Token
2. 代理：仅从 FRPS API 拉取 psyduckNNNN-socks5 节点，测试出口 IP + 省市，每次运行拉取一次
3. 携趣白名单自动管理
4. Bark 分组通知（仅失败/过期推送）
5. 过期账号同时禁用 JD_WSCK 与 JD_COOKIE，全星号 pin 自动清理
6. 京东签名、转换逻辑保持不变
7. 已移除 Arcadia、sendNotify 及旧版兼容代码
"""

import base64
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.parse
import uuid
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== 调试开关 ==========
DEBUG_MODE = os.environ.get("DEBUG_MODE", "False").lower() == "true"
FRPS_API_URL = os.environ.get("FRPS_API_URL", "http://frps的ip:7500/api/proxy/tcp")
FRPS_API_AUTH = os.environ.get("FRPS_API_AUTH", "frps-web-ui设置的账号:密码")  
BARK_GROUP_MAP = {
    "bark-token填写在这里": [
        "京东账号1", "账号2", "账号3",
        "……" ],"bark-token2": ["京东账号1", "京东账号2"]
}
def debug_print(text: str):
    if DEBUG_MODE:
        print(text)
        sys.stdout.flush()

def printf(text: str):
    print(text)
    sys.stdout.flush()

# ========== FRPS 代理获取 ==========
def fetch_proxies_from_frps() -> List[str]:
    """从 frps API 获取在线 psyduckNNNN-socks5 节点"""
    headers = {}
    if FRPS_API_AUTH:
        encoded = base64.b64encode(FRPS_API_AUTH.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"

    try:
        printf("正在从 FRPS API 获取可用代理节点...")
        resp = requests.get(FRPS_API_URL, headers=headers, timeout=10)
        if resp.status_code != 200:
            printf(f"FRPS API 返回非 200 状态码: {resp.status_code}")
            return []

        data = resp.json()
        proxies_raw = data.get("proxies", [])
        frps_host = urlparse(FRPS_API_URL).hostname or "192.168.2.17"

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

        printf(f"从 FRPS API 获取到 {len(active)} 个可用 SOCKS5 节点")
        return active

    except Exception as e:
        printf(f"FRPS API 请求异常: {e}")
        return []
def get_ip_through_proxy(proxies: dict) -> Optional[str]:
    """通过代理获取出口 IP（多服务商热备，清洗地区文字）"""
    api_list = [
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://icanhazip.com",
        "https://ident.me",
    ]
    for api_url in api_list:
        try:
            resp = requests.get(api_url, proxies=proxies, timeout=10, verify=False)
            if resp.status_code == 200:
                ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", resp.text)
                if ip_match:
                    return ip_match.group(0)
        except Exception:
            continue
    return None

def get_ip_location(ip: str) -> str:
    """查询 IP 地理位置（国家/省/市），失败返回空字符串"""
    try:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                country = data.get("country", "")
                region = data.get("regionName", "")
                city = data.get("city", "")
                return f"{country} {region} {city}".strip()
    except Exception:
        pass
    return ""

def test_proxy(proxy_url: str) -> Tuple[bool, Optional[str]]:
    """测试代理可用性：获取到公网 IP 即认为可用，并输出地理位置"""
    if not proxy_url:
        return False, None
    if not proxy_url.startswith("socks5://"):
        proxy_url = "socks5://" + proxy_url
    proxies = {"http": proxy_url, "https": proxy_url}

    ip = get_ip_through_proxy(proxies)
    if ip is None:
        return False, None

    location = get_ip_location(ip)
    if location:
        debug_print(f"代理出口 IP: {ip}，位置: {location}")
    else:
        debug_print(f"代理出口 IP: {ip}，位置获取失败")

    return True, ip

def get_next_available_proxy() -> Tuple[Optional[str], Optional[dict], Optional[str]]:
    """从动态代理列表中随机选取可用代理（每次运行仅拉取一次）"""
    if not hasattr(get_next_available_proxy, "proxy_list") or not get_next_available_proxy.proxy_list:
        get_next_available_proxy.proxy_list = fetch_proxies_from_frps()

    if not get_next_available_proxy.proxy_list:
        printf("没有可用代理，使用直连")
        return None, None, None

    shuffled = get_next_available_proxy.proxy_list.copy()
    random.shuffle(shuffled)
    for proxy in shuffled:
        available, exit_ip = test_proxy(proxy)
        if available:
            proxies_dict = {"http": proxy, "https": proxy}
            printf(f"使用 SOCKS5 代理: {proxy}" + (f"，出口 IP: {exit_ip}" if exit_ip else ""))
            return proxy, proxies_dict, exit_ip

    printf("警告：所有代理均不可用，使用直连")
    return None, None, None
def get_public_ip() -> Optional[str]:
    api_list = [
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://icanhazip.com",
        "https://ident.me",
    ]
    for api_url in api_list:
        try:
            resp = requests.get(api_url, timeout=10)
            if resp.status_code == 200:
                ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", resp.text)
                if ip_match:
                    printf(f"成功获取公网 IP: {ip_match.group(0)} (来自 {api_url})")
                    return ip_match.group(0)
        except Exception as e:
            printf(f"从 {api_url} 获取 IP 异常: {e}")
    return None

# ========== 携趣白名单 ==========
def get_xiequ_whitelist(uid: str, ukey: str) -> List[str]:
    url = f"http://op.xiequ.cn/IpWhiteList.aspx?uid={uid}&ukey={ukey}&act=getjson"
    try:
        resp = requests.get(url, timeout=10)
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
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200 and "success" in resp.text.lower():
            printf("已成功清除携趣白名单所有记录")
            return True
        else:
            printf(f"清除携趣白名单失败，返回：{resp.text}")
    except Exception as e:
        printf(f"清除携趣白名单异常：{e}")
    return False

def add_xiequ_ip(uid: str, ukey: str, ip: str, memo: str = "auto_added_by_wskey_script") -> bool:
    url = f"http://op.xiequ.cn/IpWhiteList.aspx?uid={uid}&ukey={ukey}&act=add&ip={ip}&meno={memo}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            text = resp.text.strip()
            if "success" in text.lower():
                printf(f"成功添加 IP {ip} 到携趣白名单")
                return True
            elif "err:iprep" in text.lower():
                printf(f"IP {ip} 已在携趣白名单中，无需重复添加")
                return True
            else:
                printf(f"添加 IP {ip} 失败：{text}")
    except Exception as e:
        printf(f"添加携趣白名单异常：{e}")
    return False

def check_and_add_xiequ_ip():
    uid = os.environ.get("XIEQU_UID")
    ukey = os.environ.get("XIEQU_UKEY")
    if not uid or not ukey:
        return
    printf("开始检查携趣白名单...")
    last_ip_file = "/tmp/last_public_ip.txt"
    current_ip = get_public_ip()
    if not current_ip:
        printf("无法获取当前公网 IP，跳过携趣白名单检查")
        return
    last_ip = None
    if os.path.exists(last_ip_file):
        with open(last_ip_file, 'r') as f:
            last_ip = f.read().strip()
    if last_ip == current_ip:
        whitelist = get_xiequ_whitelist(uid, ukey)
        if current_ip in whitelist:
            printf(f"当前 IP {current_ip} 与上次相同，无需更新白名单")
            return
        else:
            printf(f"IP {current_ip} 不在白名单中，尝试添加...")
            add_xiequ_ip(uid, ukey, current_ip)
            with open(last_ip_file, 'w') as f:
                f.write(current_ip)
            return
    printf(f"IP 变化：上次 {last_ip or '无记录'}，当前 {current_ip}，更新白名单")
    if clear_xiequ_whitelist(uid, ukey):
        add_xiequ_ip(uid, ukey, current_ip)
        with open(last_ip_file, 'w') as f:
            f.write(current_ip)
def bark_send(token: str, title: str, content: str):
    server = os.environ.get("BARK_SERVER", "https://api.day.app").rstrip('/')
    encoded_title = urllib.parse.quote(title, safe='')
    encoded_content = urllib.parse.quote(content, safe='')
    url = f"{server}/{token}/{encoded_title}/{encoded_content}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            printf(f"Bark 通知发送成功 (token: {token[:6]}...)")
        else:
            printf(f"Bark 通知发送失败，状态码：{resp.status_code}")
    except Exception as e:
        printf(f"Bark 通知发送异常：{e}")
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

def base64Decode(string: str) -> str:
    return base64.b64decode(string.translate(
        str.maketrans("KLMNOPQRSTABCDEFGHIJUVWXYZabcdopqrstuvwxefghijklmnyz0123456789+/",
                      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"))).decode('utf-8')

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
    area = ''.join(random.sample('0123456789', 2)) + '_' + ''.join(random.sample('0123456789', 4)) + '_' + ''.join(random.sample('0123456789', 5)) + '_' + ''.join(random.sample('0123456789', 5))
    ADID = ''.join(random.sample('0987654321ABCDEF', 8)) + '-' + ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + ''.join(random.sample('0987654321ABCDEF', 4)) + '-' + ''.join(random.sample('0987654321ABCDEF', 12))
    lng = '119.31991256596' + str(random.randint(100, 999))
    lat = '26.1187118976' + str(random.randint(100, 999))
    UserAgent = f'jdapp;iPhone;10.0.4;{iosVer};{struuid};network/wifi;ADID/{ADID};model/iPhone{iPhone},1;addressid/{addressid};appBuild/167707;jdSupportDarkMode/0;Mozilla/5.0 (iPhone; CPU iPhone OS {iosV} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/null;supportJDSHWK/1'

def get_ep(jduuid: str = ''):
    if not jduuid:
        jduuid = randomstr(16)
    ts = str(int(time.time() * 1000))
    bsjduuid = base64Encode(jduuid)
    area_encoded = base64Encode('%s_%s_%s_%s' % (random.randint(1,10000), random.randint(1,10000), random.randint(1,10000), random.randint(1,10000)))
    d_model = base64Encode(random.choice(['Mi11Ultra', 'Mi11', 'Mi10']))
    return '{"hdid":"JM9F1ywUPwflvMIpYPok0tt5k9kW4ArJEU3lfLhxBqw=","ts":%s,"ridx":-1,"cipher":{"area":"%s","d_model":"%s","wifiBssid":"dW5hbw93bq==","osVersion":"CJS=","d_brand":"WQvrb21f","screen":"CtS1DIenCNqm","uuid":"%s","aid":"%s","openudid":"%s"},"ciphertype":5,"version":"1.2.0","appname":"com.jingdong.app.mall"}' % (int(ts)-random.randint(100,1000), area_encoded, d_model, bsjduuid, bsjduuid, bsjduuid), jduuid, ts

def get_sign(functionId: str, body: dict, client: str = "android", clientVersion: str = '11.2.8', jduuid: str = ''):
    if isinstance(body, dict):
        body_str = json.dumps(body)
        d = body
    else:
        body_str = body
        d = json.loads(body_str)
    eid = d.get("eid", randomeid())
    ep, suid, st = get_ep(jduuid)
    sv = random.choice(["102","111","120"])
    all_arg = f"functionId={functionId}&body={body_str}&uuid={suid}&client={client}&clientVersion={clientVersion}&st={st}&sv={sv}"
    back_bytes = sign_core(str.encode(all_arg))
    sign = hashlib.md5(base64.b64encode(back_bytes)).hexdigest()
    convertUrl = f'body={body_str}&clientVersion={clientVersion}&client={client}&sdkVersion=31&lang=zh_CN&harmonyOs=0&networkType=wifi&oaid={suid}&ef=1&ep={urllib.parse.quote(ep)}&st={st}&sign={sign}&sv={sv}'
    return convertUrl

def getcookie_wskey(key: str) -> str:
    """通过 wskey 获取京东 cookie"""
    proxy_str, proxies_dict, exit_ip = get_next_available_proxy()
    try:
        pin_match = re.findall("pin=([^;]*);", key)
        pin = pin_match[0][0] if isinstance(pin_match[0], tuple) else pin_match[0] if pin_match else "未知"
    except:
        pin = "未知"
    body = "body=%7B%22to%22%3A%22https%3A//plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html%22%7D"
    token = None
    res = {}
    for num in range(5):
        sign = get_sign("genToken", {"url":"https://plogin.m.jd.com/jd-mlogin/static/html/appjmp_blank.html"}, "android", "11.2.8")
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
            if proxies_dict:
                debug_print(f"为 {unquote(pin)} 请求 token，代理: {proxy_str}")
            resp = requests.post(url=url, headers=headers, data=body, verify=False, proxies=proxies_dict, timeout=30)
            token = resp.json().get('tokenKey')
        except Exception as e:
            debug_print(f"警告：{unquote(pin)} 获取 token 失败：{e}，重试 {num+1}/5")
            time.sleep(5)
            randomuserAgent()
            continue
        if token and token != "xxx":
            break
        else:
            debug_print(f"警告：{unquote(pin)} 返回 token 无效，重试")
            time.sleep(5)
            randomuserAgent()
    if not token or token == "xxx":
        debug_print(f"错误：{unquote(pin)} 获取 token 最终失败")
        return "Error"
    # 第二步：获取 cookie
    for num in range(5):
        url = 'https://un.m.jd.com/cgi-bin/app/appjmp'
        params = {
            'tokenKey': token,
            'to': 'https://plogin.m.jd.com/cgi-bin/m/thirdapp_auth_page',
            'client_type': 'android',
            'appid': 879,
            'appup_type': 1,
        }
        try:
            if proxies_dict:
                debug_print(f"为 {unquote(pin)} 获取 cookie，代理: {proxy_str}")
            resp = requests.get(url=url, params=params, verify=False, allow_redirects=False, proxies=proxies_dict, timeout=30)
            res = resp.cookies.get_dict()
        except Exception as e:
            debug_print(f"警告：{unquote(pin)} 获取 cookie 失败：{e}，重试")
            time.sleep(5)
            randomuserAgent()
            continue
        if 'pt_key' in res:
            break
    try:
        if "app_open" in res.get('pt_key', ''):
            return f"pt_key={res['pt_key']};pt_pin={res['pt_pin']};"
        else:
            return "Error:" + str(res)
    except Exception as e:
        debug_print(f"错误：{unquote(pin)} 解析 cookie 异常：{e}")
        return "Error"
def subcookie(pt_pin: str, cookie: str, token: str):
    encoded_pin = urllib.parse.quote(pt_pin, safe='')
    if token == "":
        return
    url = 'http://127.0.0.1:5700/api/envs'
    headers = {'Authorization': f'Bearer {token}'}
    body = {'searchValue': encoded_pin, 'Authorization': f'Bearer {token}'}
    datas = requests.get(url, params=body, headers=headers).json().get('data', [])
    old = False
    isline = True
    pt_key_match = re.search(r'pt_key=([^;]+)', cookie)
    if not pt_key_match:
        return
    pt_key = pt_key_match.group(1)
    new_cookie = f"pt_key={pt_key};pt_pin={encoded_pin};"
    for data in datas:
        if "pt_key" in data['value']:
            if '_id' in data:
                body = {"name": "JD_COOKIE", "value": new_cookie, "_id": data['_id']}
            else:
                body = {"name": "JD_COOKIE", "value": new_cookie, "id": data['id']}
                isline = False
            old = True
            break
    if old:
        requests.put(url, json=body, headers=headers)
        enable_url = 'http://127.0.0.1:5700/api/envs/enable'
        ids = [body['_id']] if isline else [body['id']]
        requests.put(enable_url, json=ids, headers=headers)
        printf(f"✅ 更新成功：{pt_pin}")
    else:
        body = [{"value": new_cookie, "name": "JD_COOKIE"}]
        requests.post(url, json=body, headers=headers)
        printf(f"✅ 新增成功：{pt_pin}")

def get_latest_file(files):
    latest_file = None
    latest_mtime = 0
    for file in files:
        try:
            mtime = os.stat(file).st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = file
        except:
            continue
    return latest_file

def print_config_status():
    printf("\n========== 配置状态 ==========")
    if BARK_GROUP_MAP:
        printf(f"Bark 分组通知：已配置 {len(BARK_GROUP_MAP)} 个 token")
        for token, pins in BARK_GROUP_MAP.items():
            printf(f"  Token {token[:8]}... 绑定 {len(pins)} 个账号")
    else:
        printf("Bark 分组通知：未配置，将不会推送通知")
    xiequ_uid = os.environ.get("XIEQU_UID")
    xiequ_ukey = os.environ.get("XIEQU_UKEY")
    printf(f"携趣白名单: {'✅' if xiequ_uid and xiequ_ukey else '❌'}")
    printf(f"FRPS API: {FRPS_API_URL}")
    printf(f"调试模式: {'✅' if DEBUG_MODE else '❌'}")
    printf("==============================\n")
def main():
    printf("版本: 2026028_xiaoz (仅青龙·FRPS动态代理·精简版)")
    get_next_available_proxy.proxy_list = fetch_proxies_from_frps()

    check_and_add_xiequ_ip()
    print_config_status()
    token_file_list = ['/ql/data/db/keyv.sqlite', '/ql/data/config/auth.json']
    config = get_latest_file(token_file_list)
    if not config:
        printf("无法找到青龙 Token 配置文件，退出")
        return

    if 'keyv' in config:
        with open(config, "r", encoding="latin1") as file:
            auth = file.read()
            matches = re.search(r'"token":"([^"]*)"(?!.*"token":)', auth)
            token = matches.group(1) if matches else ""
    else:
        with open(config, "r") as file:
            auth = json.loads(file.read())
            token = auth.get("token", "")

    if not token:
        printf("获取青龙 token 失败")
        return

    headers = {'Authorization': f'Bearer {token}'}
    base_url = 'http://127.0.0.1:5700/api/envs'
    try:
        cookie_resp = requests.get(base_url, params={'searchValue': 'JD_COOKIE'}, headers=headers, timeout=10).json()
        cookie_list = cookie_resp.get('data', [])
    except Exception as e:
        printf(f"获取 JD_COOKIE 列表失败: {e}")
        return
    try:
        wsck_resp = requests.get(base_url, params={'searchValue': 'JD_WSCK'}, headers=headers, timeout=10).json()
        wsck_list = wsck_resp.get('data', [])
    except Exception as e:
        printf(f"获取 JD_WSCK 列表失败: {e}")
        return
    cookie_dict = {}
    for item in cookie_list:
        value = item.get('value', '')
        pin_match = re.findall(r'pt_pin=([^;]+)', value)
        if pin_match:
            decoded_pin = unquote(pin_match[0])
            cookie_dict[decoded_pin] = item
    cookie
    invalid_pins = []
    wsck_ids_to_delete = set()
    for item in wsck_list:
        value = item.get('value', '')
        pin_match = re.findall(r'pin=([^;]+)', value)
        if pin_match and re.fullmatch(r'\*+', pin_match[0]):
            wsck_id = item.get('_id') or item.get('id')
            try:
                requests.delete(base_url, json=[wsck_id], headers=headers)
                printf(f"已删除无效 wskey (pin=****): {value[:50]}...")
            except Exception as e:
                printf(f"删除无效 wskey 失败: {e}")
            invalid_pins.append(unquote(pin_match[0]))
            wsck_ids_to_delete.add(wsck_id)

    for invalid_pin in invalid_pins:
        cookie_item = cookie_dict.get(invalid_pin)
        if cookie_item:
            cookie_id = cookie_item.get('_id') or cookie_item.get('id')
            try:
                requests.delete(base_url, json=[cookie_id], headers=headers)
                printf(f"已同步删除无效 cookie: pt_pin={invalid_pin}")
            except Exception as e:
                printf(f"删除无效 cookie 失败: {e}")

    wsck_dict = {}
    for item in wsck_list:
        item_id = item.get('_id') or item.get('id')
        if item_id in wsck_ids_to_delete:
            continue
        value = item.get('value', '')
        pin_match = re.findall(r'pin=([^;]+)', value)
        if pin_match:
            decoded_pin = unquote(pin_match[0])
            wsck_dict[decoded_pin] = item

    # 遍历 cookie 进行转换
    group_fail = {token: [] for token in BARK_GROUP_MAP}
    for decoded_pin, cookie_item in cookie_dict.items():
        if decoded_pin in invalid_pins:
            continue

        printf(f"\n===== 处理账号: {decoded_pin} =====")
        wsck_item = wsck_dict.get(decoded_pin)
        if not wsck_item:
            debug_print(f"未找到对应的 wskey，跳过 {decoded_pin}")
            printf("----------")
            continue

        randomuserAgent()
        key = wsck_item['value']
        cookie = getcookie_wskey(key)

        remark = cookie_item.get('remarks', '')
        display_pin = f"{decoded_pin}({remark.split('@@')[0]})" if remark else decoded_pin

        if "app_open" in cookie:
            orgpin = cookie.split(";")[1].split("=")[1]
            subcookie(orgpin, cookie, token)
            debug_print(f"✅ {display_pin} 转换成功，不推送通知")
        else:
            # 失败处理
            if "fake_" in cookie:
                disable_ids = []
                if wsck_item:
                    disable_ids.append(wsck_item.get('_id') or wsck_item.get('id'))
                if cookie_item:
                    disable_ids.append(cookie_item.get('_id') or cookie_item.get('id'))
                if disable_ids:
                    try:
                        requests.put(base_url + '/disable', json=disable_ids, headers=headers)
                        printf(f"已禁用 {display_pin} 的 wskey 和 cookie")
                    except Exception as e:
                        printf(f"禁用变量失败: {e}")
                msg = f"❌ {display_pin} wskey过期并已禁用"
            else:
                msg = f"❌ 转换失败: {display_pin}"

            assigned = False
            for token_group, pins in BARK_GROUP_MAP.items():
                if decoded_pin in pins:
                    group_fail[token_group].append(msg)
                    assigned = True
                    break
            if not assigned:
                debug_print(f"{display_pin} 未绑定 Bark 分组，不推送失败通知")
        printf("----------")

    # 发送分组 Bark 通知
    for token_group in BARK_GROUP_MAP:
        if group_fail[token_group]:
            content = "👇转换异常，麻溜的更新👇\n" + "\n".join(group_fail[token_group])
            bark_send(token_group, "JD_WSCK转换异常提醒", content)

    printf("\n\n===============转换结束==============\n")

if __name__ == '__main__':
    main()