from requests import get, post, put
import requests
from re import findall
from os.path import exists
import json
import os
import sys, re
import random, time
import base64
import hashlib
import urllib.parse
import uuid
import urllib3

# 禁用 HTTPS 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 注意：若使用 SOCKS5 代理，需要安装 requests[socks] 或 PySocks
# pip install requests[socks]

from urllib.parse import unquote

"""
new Env('wskey本地转换');
57 21,9 * * * jd_wsck.py
by: lonesomexz
修改：通知改为 Bark，新增携趣白名单自动管理（支持清除所有后添加），代理改为 SOCKS5 并支持多代理轮换，
      增加内置调试开关 DEBUG_MODE，转换逻辑改为：对所有存在 JD_WSCK 的账号进行转换（无论原 cookie 是否禁用），
      若 wskey 过期则仅禁用 wskey，不影响原 cookie。

所需环境变量：
- BARK_KEY: Bark 推送的 key（必填，若使用 Bark 通知）
- BARK_SERVER: Bark 服务器地址，默认 https://api.day.app（可选）
- XIEQU_UID: 携趣账户 UID（必填，若使用白名单管理）
- XIEQU_UKEY: 携趣账户 UKEY（必填，若使用白名单管理）
- XIEQU_CLEAR_ALL: 是否在添加前清除所有白名单，设置为 true 则先清除全部再添加当前IP（可选，默认 false）
- SOCKS5_PROXY: SOCKS5 代理地址，支持多个（每行一个），格式如 socks5://127.0.0.1:1080（可选）
"""

# ========== 调试开关 ==========
# 修改此变量控制调试信息输出：True 显示详细过程，False 只显示关键结果
DEBUG_MODE = False

def debug_print(text):
    """仅在 DEBUG_MODE 为 True 时输出"""
    if DEBUG_MODE:
        print(text)
        sys.stdout.flush()

def printf(text):
    """始终输出（关键信息）"""
    print(text)
    sys.stdout.flush()


hadsend = True
UserAgent = ""

# ========== 全局代理列表 ==========
_proxy_list = []          # 存储所有代理地址字符串


def randomuserAgent():
    global struuid, addressid, iosVer, iosV, clientVersion, iPhone, area, ADID, lng, lat
    global UserAgent
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
    # 注意：原脚本中使用了未定义的 uuid，此处改用 struuid
    UserAgent = f'jdapp;iPhone;10.0.4;{iosVer};{struuid};network/wifi;ADID/{ADID};model/iPhone{iPhone},1;addressid/{addressid};appBuild/167707;jdSupportDarkMode/0;Mozilla/5.0 (iPhone; CPU iPhone OS {iosV} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/null;supportJDSHWK/1'


def load_send():
    global send
    global hadsend
    cur_path = os.path.abspath(os.path.dirname(__file__))
    sys.path.append(cur_path)
    if os.path.exists(cur_path + "/sendNotify.py"):
        try:
            from sendNotify import send
            hadsend = True
        except:
            printf("加载sendNotify.py的通知服务失败，请检查~")
            hadsend = False
    else:
        printf("加载通知服务失败,缺少sendNotify.py文件")
        hadsend = False


# ==================== Bark 通知函数 ====================
def bark_send(title, content, summary=""):
    """
    使用 Bark 发送通知
    环境变量：BARK_KEY（必填），BARK_SERVER（可选，默认 https://api.day.app）
    """
    key = os.environ.get("BARK_KEY")
    if not key:
        printf("未配置 BARK_KEY，无法发送 Bark 通知")
        return
    server = os.environ.get("BARK_SERVER", "https://api.day.app").rstrip('/')
    # 对标题和内容进行 URL 编码，避免特殊字符导致请求失败
    encoded_title = urllib.parse.quote(title, safe='')
    encoded_content = urllib.parse.quote(content, safe='')
    url = f"{server}/{key}/{encoded_title}/{encoded_content}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            printf("Bark 通知发送成功")
        else:
            printf(f"Bark 通知发送失败，状态码：{resp.status_code}")
    except Exception as e:
        printf(f"Bark 通知发送异常：{e}")


# ==================== 携趣白名单管理 ====================
def get_public_ip():
    """通过 4.ipw.cn 获取当前机器的公网 IPv4 地址（不使用代理）"""
    try:
        resp = requests.get("https://4.ipw.cn", timeout=10)
        if resp.status_code == 200:
            ip = resp.text.strip()
            if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                return ip
        else:
            debug_print(f"获取公网 IP 失败，状态码：{resp.status_code}")
    except Exception as e:
        debug_print(f"获取公网 IP 异常：{e}")
    return None


def get_xiequ_whitelist(uid, ukey):
    """获取携趣白名单列表（JSON 格式），返回 IP 列表"""
    url = f"http://op.xiequ.cn/IpWhiteList.aspx?uid={uid}&ukey={ukey}&act=getjson"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                return [item.get("IP") for item in data["data"] if item.get("IP")]
            else:
                debug_print(f"携趣白名单返回格式异常，返回数据：{data}")
        else:
            debug_print(f"获取携趣白名单失败，状态码：{resp.status_code}")
    except Exception as e:
        debug_print(f"获取携趣白名单异常：{e}")
    return []


def clear_xiequ_whitelist(uid, ukey):
    """删除携趣白名单中的所有记录"""
    url = f"http://op.xiequ.cn/IpWhiteList.aspx?uid={uid}&ukey={ukey}&act=del&ip=all"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            text = resp.text.strip()
            if "success" in text.lower():
                printf("已成功清除携趣白名单所有记录")
                return True
            else:
                printf(f"清除携趣白名单失败，返回：{text}")
                return False
        else:
            printf(f"清除携趣白名单请求失败，状态码：{resp.status_code}")
            return False
    except Exception as e:
        printf(f"清除携趣白名单异常：{e}")
        return False


def add_xiequ_ip(uid, ukey, ip, memo="auto_added_by_wskey_script"):
    """添加 IP 到携趣白名单，返回 (成功标志, 返回消息)"""
    url = f"http://op.xiequ.cn/IpWhiteList.aspx?uid={uid}&ukey={ukey}&act=add&ip={ip}&meno={memo}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            text = resp.text.strip()
            if "success" in text.lower():
                printf(f"成功添加 IP {ip} 到携趣白名单")
                return True, text
            elif "err:iprep" in text.lower():
                printf(f"IP {ip} 已在携趣白名单中，无需重复添加")
                return True, text
            else:
                printf(f"添加 IP {ip} 到携趣白名单失败，返回：{text}")
                return False, text
        else:
            printf(f"添加携趣白名单请求失败，状态码：{resp.status_code}")
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        printf(f"添加携趣白名单异常：{e}")
        return False, str(e)


def check_and_add_xiequ_ip():
    """检查当前公网 IP 并更新携趣白名单（仅保留当前 IP）"""
    uid = os.environ.get("XIEQU_UID")
    ukey = os.environ.get("XIEQU_UKEY")
    if not uid or not ukey:
        return

    printf("开始检查携趣白名单...")

    # 上次 IP 存储文件
    last_ip_file = "/tmp/last_public_ip.txt"

    # 获取当前公网 IP
    current_ip = get_public_ip()
    if not current_ip:
        printf("无法获取当前公网 IP，跳过携趣白名单检查")
        return

    # 读取上次记录的 IP
    last_ip = None
    if os.path.exists(last_ip_file):
        with open(last_ip_file, 'r') as f:
            last_ip = f.read().strip()

    if last_ip == current_ip:
        printf(f"当前 IP {current_ip} 与上次相同，无需更新白名单")
        # 可选：检查 IP 是否真的在白名单中，防止意外删除
        whitelist = get_xiequ_whitelist(uid, ukey)
        if current_ip in whitelist:
            return
        else:
            printf(f"警告：IP {current_ip} 不在白名单中，尝试添加...")
            add_xiequ_ip(uid, ukey, current_ip)
            # 无论添加成功与否，都记录当前 IP（防止重复添加）
            with open(last_ip_file, 'w') as f:
                f.write(current_ip)
            return
    else:
        printf(f"IP 发生变化：上次 {last_ip or '无记录'}，当前 {current_ip}，准备更新白名单")

    # IP 变化或无记录，先清除所有白名单
    printf("正在清除所有携趣白名单记录...")
    if clear_xiequ_whitelist(uid, ukey):
        # 清除成功后添加当前 IP
        success, message = add_xiequ_ip(uid, ukey, current_ip)
        if success:
            # 记录当前 IP 到文件
            with open(last_ip_file, 'w') as f:
                f.write(current_ip)
            printf(f"白名单更新完成，当前 IP {current_ip} 已添加")
        else:
            printf(f"添加 IP 失败，错误信息: {message}")
            # 即使添加失败，也记录 IP，避免下次重复尝试清除（如果接口返回错误，可能需要人工介入）
            with open(last_ip_file, 'w') as f:
                f.write(current_ip)
    else:
        printf("清除白名单失败，跳过添加")


load_send()


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


def base64Decode(string):
    return base64.b64decode(string.translate(
        str.maketrans("KLMNOPQRSTABCDEFGHIJUVWXYZabcdopqrstuvwxefghijklmnyz0123456789+/",
                      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"))).decode('utf-8')


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
    return '{"hdid":"JM9F1ywUPwflvMIpYPok0tt5k9kW4ArJEU3lfLhxBqw=","ts":%s,"ridx":-1,"cipher":{"area":"%s","d_model":"%s","wifiBssid":"dW5hbw93bq==","osVersion":"CJS=","d_brand":"WQvrb21f","screen":"CtS1DIenCNqm","uuid":"%s","aid":"%s","openudid":"%s"},"ciphertype":5,"version":"1.2.0","appname":"com.jingdong.app.mall"}' % (
        int(ts) - random.randint(100, 1000), area, d_model, bsjduuid, bsjduuid, bsjduuid), jduuid, ts


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


# ==================== 代理管理函数 ====================
def load_proxy_list():
    """从环境变量 SOCKS5_PROXY 读取代理列表（支持多行）"""
    global _proxy_list
    proxy_env = os.environ.get("SOCKS5_PROXY")
    if not proxy_env:
        _proxy_list = []
        return
    lines = proxy_env.strip().splitlines()
    _proxy_list = [line.strip() for line in lines if line.strip()]
    debug_print(f"加载到 {len(_proxy_list)} 个 SOCKS5 代理")


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
            debug_print(f"代理 {proxy_url} 访问 jd.com 返回状态码 {resp.status_code}，不可用")
            return False, None

        try:
            requests.head("https://api.m.jd.com", proxies=proxies, timeout=10, verify=False)
        except Exception as e:
            debug_print(f"代理 {proxy_url} 访问 api.m.jd.com 失败: {e}，不可用")
            return False, None

        debug_print(f"代理 {proxy_url} 可用")
        # 尝试获取出口 IP
        try:
            ip_resp = requests.get("https://4.ipw.cn", proxies=proxies, timeout=5, verify=False)
            if ip_resp.status_code == 200:
                exit_ip = ip_resp.text.strip()
                debug_print(f"通过代理 {proxy_url} 的出口 IP 为: {exit_ip}")
            else:
                debug_print(f"通过代理 {proxy_url} 获取出口 IP 失败，状态码: {ip_resp.status_code}")
        except Exception as e:
            debug_print(f"通过代理 {proxy_url} 获取出口 IP 时出现异常: {e}")
        return True, exit_ip
    except Exception as e:
        debug_print(f"代理 {proxy_url} 测试失败: {e}")
        return False, None


def get_next_available_proxy():
    """
    随机选择一个可用的 SOCKS5 代理
    返回 (代理地址, 代理字典, 出口IP)，若无可用则返回 (None, None, None)
    """
    global _proxy_list
    if not _proxy_list:
        debug_print("未配置代理，将使用直连")
        return None, None, None

    # 随机打乱代理列表
    shuffled = _proxy_list.copy()
    random.shuffle(shuffled)

    for proxy in shuffled:
        available, exit_ip = test_proxy(proxy)
        if available:
            if not proxy.startswith('socks5://'):
                proxy = 'socks5://' + proxy
            proxies_dict = {"http": proxy, "https": proxy}
            ip_info = f"，出口 IP: {exit_ip}" if exit_ip else ""
            printf(f"使用 SOCKS5 代理: {proxy}{ip_info}")  # 始终输出
            return proxy, proxies_dict, exit_ip
        else:
            debug_print(f"代理 {proxy} 不可用，尝试下一个")

    debug_print("警告：所有 SOCKS5 代理均不可用，将使用直连")
    return None, None, None


def getcookie_wskey(key):
    """
    转换 wskey 为 cookie
    内部会自动获取一个可用代理
    """
    proxy_str, proxies_dict, exit_ip = get_next_available_proxy()

    # 安全提取 pin，若失败则记录 key 前50字符（调试模式）
    try:
        pin_match = findall("pin=([^;]*);", key)
        if pin_match and pin_match[0]:
            pin = pin_match[0][0] if isinstance(pin_match[0], tuple) else pin_match[0]
        else:
            pin = "未知(pin提取失败)"
            debug_print(f"警告：无法从 key 中提取 pin，key 前50字符: {key[:50]}")
    except Exception as e:
        pin = "未知(pin提取异常)"
        debug_print(f"提取 pin 时发生异常: {e}，key: {key[:50]}")

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
                debug_print(f"正在为 {unquote(pin)} 请求 token，使用代理: {proxy_str}")
            else:
                debug_print(f"正在为 {unquote(pin)} 请求 token，使用直连")
            resp = post(url=url, headers=headers, data=body, verify=False, proxies=proxies_dict, timeout=30)
            token = resp.json()
            token = token['tokenKey']
        except Exception as error:
            debug_print(f"【警告】{unquote(pin)}在获取token时失败，错误详情：{error}，等待5秒后重试")
            time.sleep(5)
            if num == 4:
                debug_print(f"【错误】{unquote(pin)}在获取token时重试5次均失败，最后错误：{error}")
                return "Error"
            randomuserAgent()
            continue

        if token != "xxx":
            break
        else:
            debug_print(f"【警告】{unquote(pin)}在获取token时返回 'xxx'，等待5秒后重试")
            time.sleep(5)
            randomuserAgent()

    if token == "xxx":
        debug_print(f"【错误】{unquote(pin)}在获取token时最终失败，跳过")
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
                debug_print(f"正在为 {unquote(pin)} 获取 cookie，使用代理: {proxy_str}")
            else:
                debug_print(f"正在为 {unquote(pin)} 获取 cookie，使用直连")
            res = get(url=url, params=params, verify=False, allow_redirects=False,
                      proxies=proxies_dict, timeout=30).cookies.get_dict()
        except Exception as error:
            debug_print(f"【警告】{unquote(pin)}在获取cookie时失败，错误详情：{error}，等待5秒后重试")
            time.sleep(5)
            if num == 4:
                debug_print(f"【错误】{unquote(pin)}在获取cookie时重试5次均失败，最后错误：{error}")
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
        debug_print(f"【错误】{unquote(pin)}在解析cookie时异常：{error}，返回数据：{res}")
        return "Error"


def arcadia_getwskey():
    possible_paths = ['/arcadia/config/account.json', '/jd/config/account.json']

    for wskey_file in possible_paths:
        if os.path.isfile(wskey_file):
            with open(wskey_file, 'r') as f:
                data = json.load(f)

            json_data = []
            for item in data:
                if not item['pt_pin'] or not item['ws_key']:
                    continue
                pt_pin = item['pt_pin']
                ws_key = item['ws_key']
                remarks = item['remarks'][0] if item['remarks'] else ''
                json_item = f"pin={pt_pin};wskey={ws_key};"
                json_data.append((json_item, remarks))
            return json_data
    return []


def arcadia_subcookie(cookie, token):
    url = 'http://127.0.0.1:5678/openApi/updateCookie'
    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ', 'api-token': f'{token}'}
    data = {"cookie": cookie}
    res = post(url, data=json.dumps(data), headers=headers).json()
    return res


def subcookie(pt_pin, cookie, token):
    """
    更新 JD_COOKIE 环境变量
    pt_pin: 原始 pin（可能中文）
    cookie: 新获取的 cookie 字符串（pt_pin 为原始值）
    token: 青龙 token
    """
    # 对 pt_pin 进行 URL 编码，用于搜索和保存
    encoded_pin = urllib.parse.quote(pt_pin, safe='')
    if token != "":
        strptpin = pt_pin  # 用于显示
        url = 'http://127.0.0.1:5700/api/envs'
        headers = {'Authorization': f'Bearer {token}'}
        body = {
            'searchValue': encoded_pin,  # 使用编码后的 pin 搜索
            'Authorization': f'Bearer {token}'
        }
        datas = get(url, params=body, headers=headers).json()['data']
        old = False
        isline = True
        # 从 cookie 中提取 pt_key
        pt_key_match = re.search(r'pt_key=([^;]+)', cookie)
        if not pt_key_match:
            debug_print(f"无法从 cookie 中提取 pt_key: {cookie}")
            return
        pt_key = pt_key_match.group(1)
        new_cookie = f"pt_key={pt_key};pt_pin={encoded_pin};"

        for data in datas:
            if "pt_key" in data['value']:
                try:
                    body = {"name": "JD_COOKIE", "value": new_cookie, "_id": data['_id']}
                except:
                    body = {"name": "JD_COOKIE", "value": new_cookie, "id": data['id']}
                    isline = False
                old = True
                try:
                    reamrk = data['remarks']
                except:
                    reamrk = ""

                if reamrk != "" and reamrk is not None:
                    strptpin = strptpin + "(" + reamrk.split("@@")[0] + ")"
                break  # 找到第一个匹配的

        if old:
            put(url, json=body, headers=headers)
            url = 'http://127.0.0.1:5700/api/envs/enable'
            if isline:
                body = [body['_id']]
            else:
                body = [body['id']]
            put(url, json=body, headers=headers)
            printf(f"✅ 更新成功：{strptpin}")
        else:
            # 没找到对应环境变量，新增
            body = [{"value": new_cookie, "name": "JD_COOKIE"}]
            post(url, json=body, headers=headers)
            printf(f"✅ 新增成功：{strptpin}")


def get_latest_file(files):
    latest_file = None
    latest_mtime = 0
    for file in files:
        try:
            stats = os.stat(file)
            mtime = stats.st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = file
        except FileNotFoundError:
            continue
    return latest_file


def print_config_status():
    """打印环境变量和调试模式状态"""
    printf("\n========== 配置状态 ==========")
    bark_key = os.environ.get("BARK_KEY")
    printf(f"BARK_KEY: {'✅' if bark_key else '❌'}")
    
    xiequ_uid = os.environ.get("XIEQU_UID")
    xiequ_ukey = os.environ.get("XIEQU_UKEY")
    if xiequ_uid and xiequ_ukey:
        printf(f"携趣白名单: ✅ (UID: {xiequ_uid[:4]}..., UKEY: {xiequ_ukey[:4]}...)")
    else:
        printf(f"携趣白名单: ❌")
    
    # ---------- SOCKS5 代理可用性检测（详细列表） ----------
    proxy_env = os.environ.get("SOCKS5_PROXY")
    if proxy_env:
        lines = [line.strip() for line in proxy_env.strip().splitlines() if line.strip()]
        total = len(lines)
        available = 0
        printf(f"SOCKS5代理列表 ({total}个):")
        for idx, proxy in enumerate(lines, 1):
            avail, exit_ip = test_proxy(proxy)      # 调用已有检测函数
            if avail:
                mark = "✅"
                available += 1
                ip_info = f" (出口IP: {exit_ip})" if exit_ip else ""
            else:
                mark = "❌"
                ip_info = ""
            printf(f"  {idx}. {mark} {proxy}{ip_info}")
        printf(f"总计: {available}/{total}个可用")
    else:
        printf(f"SOCKS5代理: ❌")
    # ------------------------------------------------
    
    printf(f"调试模式: {'✅' if DEBUG_MODE else '❌'}")
    printf("==============================\n")


def main():
    printf("版本: 20230602 (修改：Bark通知 + 携趣白名单 + SOCKS5多代理轮换 + 内置调试开关 + 智能转换)")
    printf("说明: Bark通知需配置 BARK_KEY（必填）和 BARK_SERVER（可选）")
    printf("携趣白名单自动管理需配置 XIEQU_UID 和 XIEQU_UKEY")
    printf("SOCKS5代理需配置 SOCKS5_PROXY，支持多个（每行一个），格式如 socks5://127.0.0.1:1080（可选）")
    printf("调试模式：修改脚本开头 DEBUG_MODE = True 可显示详细过程")
    print_config_status()
    printf("====================================")

    load_proxy_list()
    check_and_add_xiequ_ip()

    config = ""
    envtype = ""
    use_bark = False

    token_file_list = ['/ql/data/db/keyv.sqlite', '/ql/data/config/auth.json', '/ql/config/auth.json']
    config = get_latest_file(token_file_list)
    envtype = "ql"

    if os.path.exists("/arcadia/config/auth.json"):
        config = "/arcadia/config/auth.json"
        envtype = "arcadia"

    if config == "":
        printf("无法判断使用环境，退出脚本!")
        return

    if os.environ.get("BARK_KEY"):
        printf('检测到已配置 BARK_KEY，将使用 Bark 发送通知')
        use_bark = True
    else:
        printf('未配置 BARK_KEY，将尝试使用 sendNotify.py 发送通知（若存在）')

    resurt = ""
    resurt1 = ""
    resurt2 = ""
    summary = ""

    if envtype == "ql":
        # 获取 token
        if 'keyv' in config:
            with open(config, "r", encoding="latin1") as file:
                auth = file.read()
                matches = re.search(r'"token":"([^"]*)"(?!.*"token":)', auth)
                token = matches.group(1)
        else:
            with open(config, "r") as file:
                auth = file.read()
                auth = json.loads(auth)
                token = auth["token"]

        headers = {'Authorization': f'Bearer {token}'}
        base_url = 'http://127.0.0.1:5700/api/envs'  # 修改为5700端口

        try:
            # 获取所有 JD_COOKIE
            params = {'searchValue': 'JD_COOKIE'}
            cookie_resp = get(base_url, params=params, headers=headers, timeout=10).json()
            cookie_list = cookie_resp.get('data', [])
        except requests.exceptions.ConnectionError as e:
            error_msg = f"连接青龙面板API失败 (127.0.0.1:5700)，请检查青龙面板是否运行。错误: {e}"
            printf(error_msg)
            if use_bark:
                bark_send("JD_WSCK转换失败", error_msg)
            return
        except Exception as e:
            error_msg = f"获取JD_COOKIE列表时发生未知错误: {e}"
            printf(error_msg)
            if use_bark:
                bark_send("JD_WSCK转换失败", error_msg)
            return

        try:
            # 获取所有 JD_WSCK
            params = {'searchValue': 'JD_WSCK'}
            wsck_resp = get(base_url, params=params, headers=headers, timeout=10).json()
            wsck_list = wsck_resp.get('data', [])
        except requests.exceptions.ConnectionError as e:
            error_msg = f"连接青龙面板API失败 (127.0.0.1:5700)，请检查青龙面板是否运行。错误: {e}"
            printf(error_msg)
            if use_bark:
                bark_send("JD_WSCK转换失败", error_msg)
            return
        except Exception as e:
            error_msg = f"获取JD_WSCK列表时发生未知错误: {e}"
            printf(error_msg)
            if use_bark:
                bark_send("JD_WSCK转换失败", error_msg)
            return

        # 构建 cookie 字典，以解码后的 pin 为键
        cookie_dict = {}
        for item in cookie_list:
            value = item.get('value', '')
            pin_match = re.findall(r'pt_pin=([^;]+)', value)
            if pin_match:
                raw_pin = pin_match[0]
                decoded_pin = unquote(raw_pin)  # 解码用于匹配
                cookie_dict[decoded_pin] = item
            else:
                debug_print(f"JD_COOKIE 中未找到 pt_pin: {value[:50]}")

        # 构建 wsck 字典，以解码后的 pin 为键
        wsck_dict = {}
        for item in wsck_list:
            value = item.get('value', '')
            pin_match = re.findall(r'pin=([^;]+)', value)
            if pin_match:
                raw_pin = pin_match[0]
                decoded_pin = unquote(raw_pin)
                wsck_dict[decoded_pin] = item
            else:
                debug_print(f"JD_WSCK 中未找到 pin: {value[:50]}")

        # 遍历所有 JD_COOKIE（不再检查是否禁用）
        for decoded_pin, cookie_item in cookie_dict.items():
            # 【修改点】移除了只处理禁用cookie的条件，现在所有cookie都会被尝试刷新
            printf(f"\n===== 处理账号: {decoded_pin} =====")
            debug_print(f"处理账号: {decoded_pin}")
            # 查找对应的 wsck
            wsck_item = wsck_dict.get(decoded_pin)
            if not wsck_item:
                debug_print(f"未找到 {decoded_pin} 对应的 JD_WSCK，跳过")
                # 获取备注用于显示
                remark = cookie_item.get('remarks', '')
                if remark:
                    display_pin = f"{decoded_pin}({remark.split('@@')[0]})"
                else:
                    display_pin = decoded_pin
                resurt2 += f"未找到 {display_pin} 的 wskey，无法转换\n"
                printf("----------")
                continue

            # 转换 wskey
            randomuserAgent()
            key = wsck_item['value']
            cookie = getcookie_wskey(key)

            if "app_open" in cookie:
                # 转换成功，更新 cookie
                # cookie 中的 pt_pin 是原始值，subcookie 会处理编码
                orgpin = cookie.split(";")[1].split("=")[1]  # 原始 pin
                # 获取备注
                remark = cookie_item.get('remarks', '')
                if remark:
                    display_pin = f"{decoded_pin}({remark.split('@@')[0]})"
                else:
                    display_pin = decoded_pin
                subcookie(orgpin, cookie, token)
                resurt1 += f"✅ 转换成功：{display_pin}\n"
            else:
                # 转换失败
                remark = cookie_item.get('remarks', '')
                if remark:
                    display_pin = f"{decoded_pin}({remark.split('@@')[0]})"
                else:
                    display_pin = decoded_pin
                if "fake_" in cookie:
                    message = f"❌ {display_pin} wskey过期并已禁用"
                    printf(message)
                    # 禁用对应的 wsck
                    if wsck_item:
                        disable_url = base_url + '/disable'
                        try:
                            body = [wsck_item['_id']]
                        except:
                            body = [wsck_item['id']]
                        put(disable_url, json=body, headers=headers)
                    resurt2 += f"{message}\n"
                else:
                    resurt2 += f"❌ 转换失败:{display_pin}\n"
            printf("----------")

    elif envtype == "arcadia":
        # Arcadia 模式保持不变（原有逻辑）
        with open(config, "r", encoding="utf-8") as f1:
            data = json.load(f1)
            token = data.get('openApiToken', '')
        wslist = arcadia_getwskey()
        for ws, remark in wslist:
            printf(f"\n===== 处理账号: {remark} =====")
            randomuserAgent()
            pin = re.findall(r'(pin=([^; ]+)(?=;?))', ws)[0][1]
            printf(f"当前转换的pin:\n{pin}")
            cookie = getcookie_wskey(ws)

            if "app_open" in cookie:
                res = arcadia_subcookie(cookie, token)
                msg = f"✅ 转换成功：{remark}@{pin}"
                if res["code"] == 1:
                    msg += f"，面板同步成功！"
                else:
                    msg += f"，面板同步失败，token错误或者请求失败。"
                printf(msg)
                resurt1 += msg + "\n"
            else:
                if "fake_" in cookie:
                    msg = f"❌ {remark}@{pin} wskey过期并已禁用"
                else:
                    msg = f"❌ {remark}@{pin} 转换失败！"
                printf(msg)
                resurt2 += msg + "\n"
            printf("----------")

    # 处理通知
    if resurt2 != "":
        resurt = "👇👇👇👇👇转换异常👇👇👇👇👇\n" + resurt2 + "\n"
        summary = "部分CK转换异常"

        if resurt1 != "":
            resurt = resurt + "👇👇👇👇👇转换成功👇👇👇👇👇\n" + resurt1
            if summary == "":
                summary = "全部转换成功"

        if use_bark:
            bark_send("JD_WSCK转换结果", resurt, summary)
        else:
            if hadsend:
                send("JD_WSCK转换结果", resurt)
            else:
                printf("没有启用通知!")
    else:
        if resurt1 != "":
            resurt = resurt + "👇👇👇👇👇转换成功👇👇👇👇👇\n" + resurt1

        if use_bark:
            bark_send("JD_WSCK转换结果", resurt, summary)
        else:
            if hadsend:
                send("JD_WSCK转换结果", resurt)
            else:
                printf("没有启用通知!")

    printf("\n\n===============转换结果==============\n")
    printf(resurt)


if __name__ == '__main__':
    main()