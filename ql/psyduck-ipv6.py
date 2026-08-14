#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import re
import os
import time
import json
import sys
import threading
import random

class Spinner:
    """旋转进度条类"""
    def __init__(self, message="正在获取"):
        self.message = message
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.done = False
        self.thread = None
    
    def _spin(self):
        i = 0
        while not self.done:
            sys.stdout.write(f"\r{self.message} {self.spinner_chars[i % len(self.spinner_chars)]}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1
    
    def start(self):
        self.done = False
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self, success=True, message=""):
        self.done = True
        if self.thread:
            self.thread.join()
        if success:
            sys.stdout.write(f"\r{message} ✅\n")
        else:
            sys.stdout.write(f"\r{message} ❌\n")
        sys.stdout.flush()

class FrpsProxyUpdater:
    def __init__(self, verbose=False):
        self.frps_url = "http://192.168.10.10:7500"
        self.base_url = "http://192.168.10.10"   # 正确的 FRPS 服务器地址
        self.config_path = "qitoqito_psyduck/config/proxy.ini"
        self.verbose = verbose
        
    def log(self, message):
        if self.verbose:
            print(message)
    
    def get_frps_ports(self):
        """
        从 FRPS API 自动获取 psyduck 穿透端口列表
        匹配规则：节点名称以 psyduck 开头，后接 4 位数字（如 psyduck1234），且状态为 online
        """
        try:
            api_url = f"{self.frps_url}/api/proxy/tcp"
            self.log(f"正在从 FRPS API 获取端口: {api_url}")
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            proxies_raw = data.get("proxies", [])
            pattern = re.compile(r"^psyduck\d{4}$")
            ports = []
            
            for node in proxies_raw:
                if node.get("status") != "online":
                    continue
                name = node.get("name", "")
                if not pattern.match(name):
                    continue
                conf = node.get("conf", {})
                remote_port = conf.get("remotePort")
                if remote_port:
                    ports.append(int(remote_port))
            
            self.log(f"从 FRPS API 获取到 {len(ports)} 个端口: {ports}")
            return ports
        except requests.exceptions.RequestException as e:
            print(f"获取 FRPS 端口列表失败: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"解析 FRPS API 响应失败: {e}")
            return []
        except Exception as e:
            print(f"获取 FRPS 端口时发生未知错误: {e}")
            return []
    
    def get_ipv6_from_port(self, port, max_retries=3):
        """通过指定端口获取IPv6地址，支持重试"""
        spinner = Spinner(f"端口 {port}")
        spinner.start()
        
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}:{port}/ipv6"
                self.log(f"尝试 #{attempt+1} 从端口 {port} 获取IPv6地址")
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("success") and "addresses" in data:
                    addresses = data["addresses"]
                    if addresses:
                        public_ipv6 = self.filter_public_ipv6(addresses)
                        if public_ipv6:
                            spinner.stop(True, f"端口 {port} 获取到公网IPv6: {public_ipv6}")
                            return public_ipv6
                        else:
                            self.log(f"端口 {port} 没有找到公网IPv6地址")
                    else:
                        self.log(f"端口 {port} 返回的addresses为空")
                else:
                    self.log(f"端口 {port} 返回的响应不成功或无addresses字段")
                    return None
                
            except requests.exceptions.RequestException as e:
                self.log(f"从端口 {port} 获取IPv6失败 (尝试 #{attempt+1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
            except json.JSONDecodeError as e:
                self.log(f"解析端口 {port} 的JSON响应失败: {e}")
                return None
            except Exception as e:
                self.log(f"从端口 {port} 获取IPv6时发生未知错误: {e}")
                return None
        
        spinner.stop(False, f"端口 {port} 无法获取到IP")
        return None
    
    def filter_public_ipv6(self, addresses):
        """过滤出公网IPv6地址"""
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
                    print(f"过滤掉重复前三段IPv6的端口: {port} (IPv6: {ipv6})")
        
        print(f"过滤后剩余端口数量: {len(filtered_ports)}")
        return filtered_ports
    
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
            print(f"读取配置文件失败: {e}")
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
        
        if existing_urls_sorted == new_urls_sorted:
            print("配置无变化，无需更新")
            return True
        else:
            print("配置有变化，需要更新")
            return False
    
    def write_proxy_config(self, proxy_urls):
        if self.compare_with_existing_config(proxy_urls):
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
                    print(f"写入配置: {url}")
            
            print(f"配置文件已写入: {self.config_path}")
            print(f"注意: 端口已随机排序，顺序为: {[url.split(':')[-1] for url in shuffled_urls]}")
            return True
            
        except Exception as e:
            print(f"写入配置文件失败: {e}")
            return False
    
    def run(self):
        self.print_config_content("脚本开始前的配置文件内容")
        
        print("\n开始获取FRPS端口信息...")
        
        ports = self.get_frps_ports()
        if not ports:
            print("未找到有效端口，脚本结束")
            return
        
        print(f"将尝试以下端口: {ports}")
        
        port_ipv6_pairs = {}
        
        for port in ports:
            ipv6 = self.get_ipv6_from_port(port, max_retries=3)
            if ipv6:
                port_ipv6_pairs[port] = ipv6
            time.sleep(1)
        
        if not port_ipv6_pairs:
            print("未获取到任何有效的IPv6地址")
            return
        
        filtered_ports = self.filter_ports_by_ipv6_segment(port_ipv6_pairs)
        
        # 关键修改：使用 self.base_url 作为 IP，而不是硬编码 192.168.2.254
        proxy_urls = [f"{self.base_url}:{port}" for port in filtered_ports]
        
        print(f"\n最终代理URL列表 (原始顺序): {proxy_urls}")
        
        write_result = self.write_proxy_config(proxy_urls)
        
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
