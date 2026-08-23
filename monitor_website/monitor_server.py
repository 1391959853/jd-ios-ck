#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务健康监控面板
监控 FRPS TCP 代理组、青龙面板、API 服务端
"""

import socket
import time
import json
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify
import requests

# ==================== 配置 ====================

# FRPS API
FRPS_HOST = "1.sggg3326.top"
FRPS_PORT = 7500
FRPS_API = f"http://{FRPS_HOST}:{FRPS_PORT}/api/proxy/tcp"

# 监控目标服务（不暴露完整 URL）
TARGET_SERVICES = {
    'qinglong': {
        'name': '青龙面板',
        'host': FRPS_HOST,
        'port': 12121,
        'path': '/',
        'timeout': 5
    },
    'api': {
        'name': 'API 服务端',
        'host': FRPS_HOST,
        'port': 9090,
        'path': '/health',
        'timeout': 5
    }
}

# 检测频率
CHECK_INTERVAL = 30  # 秒
SERVER_PORT = 5000   # 监控面板端口

# =============================================

app = Flask(__name__)

# 全局数据
monitor_data = {
    'proxy_groups': {},      # 代理组状态
    'target_services': {},   # 目标服务状态
    'last_update': None,
    'overall_status': 'unknown'
}


def check_tcp_port(host, port, timeout=3):
    """检查 TCP 端口"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def check_http(url, timeout=5):
    """检查 HTTP 服务"""
    try:
        start = time.time()
        resp = requests.get(url, timeout=timeout)
        response_time = (time.time() - start) * 1000
        return {
            'success': resp.status_code == 200,
            'status_code': resp.status_code,
            'response_time': round(response_time, 2)
        }
    except Exception as e:
        return {
            'success': False,
            'status_code': None,
            'response_time': None,
            'error': str(e)
        }


def fetch_frps_proxies():
    """从 FRPS 获取代理列表"""
    try:
        resp = requests.get(FRPS_API, timeout=10)
        if resp.status_code == 200:
            return resp.json().get('proxies', [])
    except Exception:
        pass
    return []


def parse_proxy_groups(proxies):
    """解析代理组"""
    groups = {}
    
    for p in proxies:
        name = p.get('name', '')
        status = p.get('status', '')
        remote_port = p.get('conf', {}).get('remotePort', '')
        
        # 分类
        if '-socks5' in name:
            # SOCKS5 代理 - psyduck1010-socks5
            match_id = name.replace('-socks5', '')
            group_id = match_id.replace('psyduck', '')
            group_key = group_id
            
            if group_key not in groups:
                groups[group_key] = {'id': group_key, 'main': None, 'socks5': None, 'ssh': None}
            
            groups[group_key]['socks5'] = {
                'name': name,
                'port': remote_port,
                'status': 'online' if status == 'online' else 'offline'
            }
        
        elif '-ssh' in name and name.startswith('psyduck-ssh'):
            # SSH 隧道 - psyduck-ssh-1010
            group_id = name.replace('psyduck-ssh-', '')
            group_key = group_id
            
            if group_key not in groups:
                groups[group_key] = {'id': group_key, 'main': None, 'socks5': None, 'ssh': None}
            
            groups[group_key]['ssh'] = {
                'name': name,
                'port': remote_port,
                'status': 'online' if status == 'online' else 'offline'
            }
        
        elif name.startswith('psyduck') and not '-ssh' in name and not '-socks5' in name:
            # 主容器 - psyduck1010
            group_id = name.replace('psyduck', '')
            group_key = group_id
            
            if group_key not in groups:
                groups[group_key] = {'id': group_key, 'main': None, 'socks5': None, 'ssh': None}
            
            groups[group_key]['main'] = {
                'name': name,
                'port': remote_port,
                'status': 'online' if status == 'online' else 'offline'
            }
    
    return groups


def check_group_health(group):
    """检查组整体健康状态"""
    statuses = []
    
    if group.get('main'):
        statuses.append(group['main']['status'] == 'online')
    if group.get('socks5'):
        statuses.append(group['socks5']['status'] == 'online')
    if group.get('ssh'):
        statuses.append(group['ssh']['status'] == 'online')
    
    if not statuses:
        return 'unknown'
    elif all(statuses):
        return 'all_online'
    elif any(statuses):
        return 'partial'
    else:
        return 'all_offline'


def update_monitor_status():
    """更新监控状态"""
    global monitor_data
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. 获取 FRPS 代理列表
    proxies = fetch_frps_proxies()
    groups = parse_proxy_groups(proxies)
    
    # 2. 更新代理组状态
    monitor_data['proxy_groups'] = {}
    for group_id, group in groups.items():
        health = check_group_health(group)
        monitor_data['proxy_groups'][group_id] = {
            **group,
            'health': health
        }
    
    # 3. 检测目标服务
    for key, config in TARGET_SERVICES.items():
        url = f"http://{config['host']}:{config['port']}{config['path']}"
        result = check_http(url, config['timeout'])
        monitor_data['target_services'][key] = {
            'name': config['name'],
            'host': config['host'],
            'port': config['port'],
            'status': 'online' if result['success'] else 'offline',
            'status_code': result['status_code'],
            'response_time': result['response_time'],
            'error': result.get('error'),
            'last_check': timestamp
        }
    
    # 4. 计算整体状态
    group_health_list = [g['health'] for g in monitor_data['proxy_groups'].values()]
    target_status_list = [s['status'] for s in monitor_data['target_services'].values()]
    
    all_online = (
        all(h == 'all_online' for h in group_health_list) and
        all(s == 'online' for s in target_status_list)
    )
    
    any_online = (
        any(h in ['all_online', 'partial'] for h in group_health_list) or
        any(s == 'online' for s in target_status_list)
    )
    
    if all_online:
        monitor_data['overall_status'] = 'all_online'
    elif any_online:
        monitor_data['overall_status'] = 'partial'
    else:
        monitor_data['overall_status'] = 'all_offline'
    
    monitor_data['last_update'] = timestamp
    
    # 日志
    online_groups = sum(1 for g in monitor_data['proxy_groups'].values() if g['health'] == 'all_online')
    total_groups = len(monitor_data['proxy_groups'])
    online_targets = sum(1 for s in monitor_data['target_services'].values() if s['status'] == 'online')
    total_targets = len(monitor_data['target_services'])
    
    print(f"\n[{timestamp}] 更新完成")
    print(f"  代理组：{online_groups}/{total_groups} 正常")
    print(f"  目标服务：{online_targets}/{total_targets} 在线")


def periodic_check():
    """定期检查"""
    while True:
        update_monitor_status()
        time.sleep(CHECK_INTERVAL)


@app.route('/')
def index():
    """监控面板首页"""
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    """获取状态"""
    return jsonify(monitor_data)


@app.route('/api/check', methods=['POST'])
def manual_check():
    """手动检查"""
    update_monitor_status()
    return jsonify({'message': '检查完成'})


if __name__ == '__main__':
    print("="*60)
    print("🖥️  服务健康监控面板")
    print("="*60)
    print(f"\n监控目标:")
    print(f"  • FRPS: {FRPS_HOST}:{FRPS_PORT}")
    for key, cfg in TARGET_SERVICES.items():
        print(f"  • {cfg['name']}: {cfg['host']}:{cfg['port']}{cfg['path']}")
    print(f"\n代理组数量：动态检测")
    print(f"检查间隔：{CHECK_INTERVAL} 秒")
    print(f"服务端口：{SERVER_PORT}")
    print("="*60)
    
    # 启动监控线程
    monitor_thread = threading.Thread(target=periodic_check, daemon=True)
    monitor_thread.start()
    
    time.sleep(1)
    
    print(f"\n访问地址：http://127.0.0.1:{SERVER_PORT}\n")
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, threaded=True)
