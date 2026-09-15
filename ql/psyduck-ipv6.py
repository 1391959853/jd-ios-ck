#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# psyduck-ipv6.py
# 版本：20260915_v1
# 功能：从 FRPS 获取 psyduck 穿透端口 → 探测各端口 IPv6 → 按前三段去重 → 写入代理配置
# 依赖：仅标准库（urllib）
#

import json
import logging
import logging.handlers
import os
import random
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

VERSION = "20260915_v1"


# ========== HTTP 封装（替代 requests） ==========
class HttpResponse:
    def __init__(self, status_code, data_bytes, headers):
        self.status_code = status_code
        self._data = data_bytes
        self.headers = headers
        try:
            self.text = data_bytes.decode('utf-8', errors='replace')
        except Exception:
            self.text = ''

    def json(self):
        return json.loads(self.text)


def http_get(url, headers=None, params=None, timeout=30, verify=True):
    if params:
        sep = '&' if '?' in url else '?'
        url = url + sep + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, method='GET')
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    handlers = []
    if not verify:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))

    opener = urllib.request.build_opener(*handlers)
    try:
        resp = opener.open(req, timeout=timeout)
        return HttpResponse(resp.status, resp.read(), dict(resp.headers))
    except urllib.error.HTTPError as e:
        return HttpResponse(e.code, e.read(), dict(e.headers))


# ========== Bark 通知配置 ==========
BARK_API = "https://api.day.app"

TOKEN_PORT_MAP = {
    "your_bark_token_1": [1234, 5678],
    "your_bark_token_2": [9000, 9001],
}

FAIL_COUNT_FILE = "/var/log/psyduck_frps_fail_count"
FAIL_THRESHOLD = 2

# ========== 远端青龙（同时是 FRPS 主机） ==========
REMOTE_QL_URL = os.environ.get("REMOTE_QL_URL", "").rstrip('/')
FRPS_API_PORT = int(os.environ.get("FRPS_API_PORT", "7500"))
FRPS_API_AUTH = os.environ.get("FRPS_API_AUTH", "")
FRPS_HTTP_NAME_PATTERN = os.environ.get("FRPS_HTTP_NAME_PATTERN", r"^psyduck\d{4}$")

LOG_FILE = "/var/log/psyduck-proxy-updater.log"


def setup_logging():
    logger = logging.getLogger("FrpsProxyUpdater")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(console)
    return logger


logger = setup_logging()


# ========== FRPS v2 节点解析 ==========
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
    return str(s).lower()


class Spinner:
    def __init__(self, message="正在获取", enabled=True):
        self.message = message
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.done = False
        self.thread = None
        self.enabled = enabled

    def _spin(self):
        i = 0
        while not self.done:
            sys.stdout.write(f"\r{self.message} {self.spinner_chars[i % len(self.spinner_chars)]}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

    def start(self):
        if not self.enabled:
            return
        self.done = False
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()

    def stop(self, success=True, message=""):
        if not self.enabled:
            return
        self.done = True
        if self.thread:
            self.thread.join()
        sys.stdout.write(f"\r{message} {'✅' if success else '❌'}\n")
        sys.stdout.flush()


class FrpsProxyUpdater:
    def __init__(self, verbose=False):
        if not REMOTE_QL_URL:
            logger.error("未配置 REMOTE_QL_URL，无法确定主机地址，退出")
            sys.exit(1)

        host = urlparse(REMOTE_QL_URL).hostname or ""
        if not host:
            logger.error("REMOTE_QL_URL 解析失败，退出")
            sys.exit(1)

        self.frps_url = f"http://{host}:{FRPS_API_PORT}"
        self.base_url = f"http://{host}"
        self.config_path = "qitoqito_psyduck/config/proxy.ini"
        self.verbose = verbose

    def log(self, message):
        if self.verbose:
            print(message)

    # ========== 失败计数管理 ==========
    def read_fail_count(self):
        try:
            with open(FAIL_COUNT_FILE, 'r') as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def write_fail_count(self, count):
        try:
            os.makedirs(os.path.dirname(FAIL_COUNT_FILE), exist_ok=True)
            with open(FAIL_COUNT_FILE, 'w') as f:
                f.write(str(count))
        except Exception as e:
            logger.warning(f"写入失败计数文件失败: {e}")

    def reset_fail_count(self):
        self.write_fail_count(0)
        logger.info("已重置 FRPS 失败计数")

    # ========== Bark 通知 ==========
    def send_bark_notification(self, token, message):
        try:
            url = f"{BARK_API}/{token}/{urllib.parse.quote(message, safe='')}"
            http_get(url, timeout=5)
            logger.info(f"Bark 通知已发送 (token: {token[:8]}...)")
            return True
        except Exception as e:
            logger.warning(f"发送 Bark 通知失败 (token: {token[:8]}...): {e}")
            return False

    def notify_affected_tokens(self, ports):
        if not ports:
            return
        for token, token_ports in TOKEN_PORT_MAP.items():
            affected = [p for p in token_ports if p in ports]
            if affected:
                port_str = ", ".join(map(str, affected))
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                message = f"时间：{current_time}，您部署的代理端口 {port_str} 未发现 IPv6，请检查一下您的设备电源与公网 IPv6 是否通畅。"
                self.send_bark_notification(token, message)

    # ========== 核心功能 ==========
    def get_frps_ports(self):
        try:
            api_url = f"{self.frps_url}/api/proxy/tcp"
            self.log(f"正在从 FRPS API 获取端口: {api_url}")
            resp = http_get(api_url, timeout=10)
            if resp.status_code != 200:
                logger.error(f"FRPS API 返回状态码: {resp.status_code}")
                return []
            data = resp.json()

            proxies_raw = data.get("proxies", [])
            pattern = re.compile(FRPS_HTTP_NAME_PATTERN)
            ports = []

            for node in proxies_raw:
                if _extract_status(node) != "online":
                    continue
                name = node.get("name", "")
                if not pattern.match(name):
                    continue
                remote_port = _extract_port(node)
                if remote_port:
                    ports.append(int(remote_port))

            self.log(f"从 FRPS API 获取到 {len(ports)} 个端口: {ports}")
            return ports
        except Exception as e:
            logger.error(f"获取 FRPS 端口时发生错误: {e}")
            return []

    def get_ipv6_from_port(self, port, max_retries=3):
        spinner = Spinner(f"端口 {port}", enabled=self.verbose)
        spinner.start()

        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}:{port}/ipv6"
                self.log(f"尝试 #{attempt+1} 从端口 {port} 获取IPv6地址")
                resp = http_get(url, timeout=5)

                if resp.status_code != 200:
                    self.log(f"端口 {port} 返回状态码 {resp.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    continue

                try:
                    data = resp.json()
                except json.JSONDecodeError as e:
                    self.log(f"解析端口 {port} 的JSON响应失败: {e}")
                    break

                if not data.get("success") or "addresses" not in data:
                    self.log(f"端口 {port} 返回的响应不成功或无addresses字段")
                    break

                addresses = data["addresses"]
                if not addresses:
                    self.log(f"端口 {port} 返回的addresses为空")
                    break

                public_ipv6 = self.filter_public_ipv6(addresses)
                if public_ipv6:
                    spinner.stop(True, f"端口 {port} 获取到公网IPv6: {public_ipv6}")
                    return public_ipv6
                else:
                    self.log(f"端口 {port} 没有找到公网IPv6地址")
                    break

            except Exception as e:
                self.log(f"从端口 {port} 获取IPv6失败 (尝试 #{attempt+1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)

        spinner.stop(False, f"端口 {port} 获取失败")
        return None

    def filter_public_ipv6(self, addresses):
        for ipv6 in addresses:
            if ipv6.startswith('fe80:'):
                continue
            if ipv6.startswith('fc') or ipv6.startswith('fd'):
                continue
            if ipv6.startswith('2001:db8:'):
                continue
            if ipv6.startswith('2002:'):
                continue
            if ipv6.startswith('2001:0:'):
                continue
            if ipv6.startswith('2001:10:'):
                continue
            if ipv6.startswith('3ffe:'):
                continue
            if ipv6.startswith('fec0:'):
                continue
            if self.is_valid_ipv6(ipv6):
                return ipv6
        return None

    def is_valid_ipv6(self, ip):
        ipv6_pattern = r'^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$'
        return re.match(ipv6_pattern, ip) is not None

    def filter_ports_by_ipv6_segment(self, port_ipv6_pairs):
        seen_segments = set()
        filtered_ports = []
        duplicate_ports = set()

        for port, ipv6 in port_ipv6_pairs.items():
            if not ipv6:
                continue
            segments = ipv6.split(':')
            if len(segments) >= 3:
                segment_key = f"{segments[0]}:{segments[1]}:{segments[2]}"
                if segment_key not in seen_segments:
                    seen_segments.add(segment_key)
                    filtered_ports.append(port)
                    self.log(f"保留端口 {port} (IPv6: {ipv6}, 前三段: {segment_key})")
                else:
                    duplicate_ports.add(port)
                    self.log(f"过滤掉重复前三段IPv6的端口: {port} (IPv6: {ipv6})")

        return filtered_ports, duplicate_ports

    def read_current_config(self):
        if not os.path.exists(self.config_path):
            self.log("配置文件不存在")
            return []

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            values = []
            in_jdrelay_section = False

            for line in lines:
                line = line.strip()
                if line == '[jdRelay]':
                    in_jdrelay_section = True
                    continue
                if line.startswith('[') and line.endswith(']') and line != '[jdRelay]':
                    in_jdrelay_section = False
                    continue
                if in_jdrelay_section and line and not line.startswith('#') and line.startswith('http://'):
                    values.append(line)

            self.log(f"成功读取现有配置: {values}")
            return values
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            return []

    def print_config_content(self, title="配置文件内容"):
        print(f"\n{title}:")
        print("-" * 50)
        if not os.path.exists(self.config_path):
            print("配置文件不存在")
            print("-" * 50)
            return
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if content:
                print(content)
            else:
                print("配置文件为空")
        except Exception as e:
            print(f"读取配置文件失败: {e}")
        print("-" * 50)

    def compare_with_existing_config(self, proxy_urls):
        existing_urls = self.read_current_config()
        existing_urls_sorted = sorted(existing_urls)
        new_urls_sorted = sorted(proxy_urls)
        self.log(f"现有配置URL: {existing_urls_sorted}")
        self.log(f"新配置URL: {new_urls_sorted}")
        return existing_urls_sorted == new_urls_sorted

    def write_proxy_config(self, proxy_urls):
        if self.compare_with_existing_config(proxy_urls):
            if not self.verbose:
                print("配置无变化，无需更新")
            else:
                print("配置无变化，跳过写入")
            return True

        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write("[jdRelay]\n")
                shuffled_urls = proxy_urls.copy()
                random.shuffle(shuffled_urls)
                for url in shuffled_urls:
                    f.write(f"{url}\n")
                    if self.verbose:
                        print(f"写入配置: {url}")

            if self.verbose:
                print(f"配置文件已写入: {self.config_path}")
                print(f"注意: 端口已随机排序，顺序为: {[url.split(':')[-1] for url in shuffled_urls]}")
            else:
                print(f"\n配置已更新，共 {len(shuffled_urls)} 条代理")
            return True

        except Exception as e:
            print(f"写入配置文件失败: {e}")
            return False

    def run(self):
        print(f"psyduck-ipv6  版本: {VERSION}")

        if self.verbose:
            print("")
            print(f"FRPS 面板地址: {self.frps_url}"
                  + (" (Basic 认证)" if FRPS_API_AUTH else " (无认证)"))
            print(f"主机来源: REMOTE_QL_URL ({urlparse(REMOTE_QL_URL).hostname})")
            print(f"ipv6 探测地址: {self.base_url}")
            print(f"节点匹配规则: {FRPS_HTTP_NAME_PATTERN}")
            print(f"HTTP 客户端: urllib（无 requests）")
            self.print_config_content("脚本开始前的配置文件内容")
            print("\n开始获取FRPS端口信息...")

        ports = self.get_frps_ports()

        if not ports:
            print("frps配置: ❌")
            logger.warning("FRPS API 未返回任何 psyduck 端口")

            fail_count = self.read_fail_count() + 1
            self.write_fail_count(fail_count)
            logger.info(f"FRPS 获取失败计数: {fail_count}/{FAIL_THRESHOLD}")

            if fail_count >= FAIL_THRESHOLD:
                logger.warning(f"连续 {FAIL_THRESHOLD} 次获取 FRPS 端口失败，触发通知")
                all_ports = []
                for token_ports in TOKEN_PORT_MAP.values():
                    all_ports.extend(token_ports)
                if all_ports:
                    self.notify_affected_tokens(all_ports)
                else:
                    logger.warning("未配置任何端口映射，跳过通知")
                self.reset_fail_count()
            else:
                logger.info(f"未达到通知阈值 ({FAIL_THRESHOLD})，跳过通知")

            print("未找到有效端口，脚本结束")
            return

        if self.read_fail_count() > 0:
            self.reset_fail_count()

        if not self.verbose:
            print("frps配置: ✅")

        if self.verbose:
            print(f"将尝试以下端口: {ports}")

        port_results = {}
        for port in ports:
            ipv6 = self.get_ipv6_from_port(port, max_retries=3)
            port_results[port] = ipv6
            time.sleep(1)

        port_ipv6_pairs = {p: v for p, v in port_results.items() if v}
        filtered_ports, duplicate_ports = self.filter_ports_by_ipv6_segment(port_ipv6_pairs)

        if not self.verbose:
            for i, port in enumerate(ports, 1):
                ipv6 = port_results.get(port)
                if ipv6:
                    seg = ":".join(ipv6.split(':')[:3])
                    if port in duplicate_ports:
                        print(f"[{i}/{len(ports)}] {port} | {seg}  ❌ 重复")
                    else:
                        print(f"[{i}/{len(ports)}] {port} | {seg}  ✅")
                else:
                    print(f"[{i}/{len(ports)}] {port} | 获取ip失败❌")

        if not filtered_ports:
            print("\n未获取到任何有效的 IPv6 地址")
            return

        proxy_urls = [f"{self.base_url}:{port}" for port in filtered_ports]

        if self.verbose:
            print(f"\n最终代理URL列表 (原始顺序): {proxy_urls}")

        write_result = self.write_proxy_config(proxy_urls)

        if self.verbose:
            if write_result:
                self.print_config_content("脚本运行后的配置文件内容")
            else:
                self.print_config_content("配置文件内容（未更改）")
            print("脚本执行完成")


def main():
    VERBOSE = False
    updater = FrpsProxyUpdater(verbose=VERBOSE)
    updater.run()


if __name__ == "__main__":
    main()