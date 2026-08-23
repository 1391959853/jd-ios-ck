#!/usr/bin/env python3
"""
Docker 镜像加速器速度测试（强制清理缓存，实时打印日志，北京时间，IP归属检测）
如果代理出口 IP 非中国大陆，则立即退出。
"""

import subprocess
import time
import os
import json
import socket
import sys
import requests

# ========== 设置时区为北京时间 ==========
os.environ['TZ'] = 'Asia/Shanghai'
time.tzset()
# ======================================

# ---------- 镜像站列表 ----------
MIRRORS = [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.1ms.run",
    "https://docker.1panel.live",
    "https://docker.sparkcr.cn",
    "https://hub.rat.dev",
    "https://docker.xuanyuan.run",
    "https://docker.xuanyuan.dev",
    "https://dockerproxy.net",
    "https://docker-registry.nmqu.com",
    "https://docker.hlmirror.com",
    "https://hub1.nat.tf",
    "https://hub4.nat.tf",
    "https://docker.m.daocloud.io",
    "https://docker.367231.xyz",
    "https://hub.1panel.dev",
    "https://dockerproxy.cool",
    "https://docker.fnnas.com",
]

TEST_IMAGE = "hdbjlizhe/autman:latest"
TIMEOUT = 600  # 每个镜像拉取超时（秒）

# ========== 🔧 请在这里修改为您的真实代理账密 ==========
SOCKS5_HOST = os.getenv("SOCKS5_HOST", "1.sggg3326.top")
SOCKS5_PORT = os.getenv("SOCKS5_PORT", "6005")
SOCKS5_USER = os.getenv("SOCKS5_USER", "socksuser")   # 请替换
SOCKS5_PASS = os.getenv("SOCKS5_PASS", "sockspass123")     # 请替换
# ======================================================

def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def start_socat(port):
    socks5_url = f"SOCKS5:{SOCKS5_HOST}:{SOCKS5_PORT}"
    if SOCKS5_USER and SOCKS5_PASS:
        socks5_url = f"SOCKS5:{SOCKS5_HOST}:{SOCKS5_PORT},socks5user={SOCKS5_USER},socks5pass={SOCKS5_PASS}"
    cmd = [
        "socat",
        f"TCP4-LISTEN:{port},fork,reuseaddr",
        socks5_url
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    return proc

def clear_docker_cache():
    print("🧹 正在清理 Docker 缓存...")
    try:
        subprocess.run(["docker", "stop", "$(docker ps -aq)"], shell=True, check=False)
        subprocess.run(["docker", "system", "prune", "-a", "-f"], check=True)
        subprocess.run(["docker", "volume", "prune", "-f"], check=True)
        subprocess.run(["docker", "builder", "prune", "-a", "-f"], check=True)
        print("✅ Docker 缓存已清空")
    except Exception as e:
        print(f"⚠️ 清理缓存时出错: {e}")

def test_proxy_ip(port):
    """通过 HTTP 代理查询出口 IP 并检查是否为中国大陆"""
    proxy_url = f"http://127.0.0.1:{port}"
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        # 使用 ip-api.com 获取 IP 和归属地（免费，无需key）
        response = requests.get("http://ip-api.com/json/", proxies=proxies, timeout=10)
        if response.status_code == 200:
            data = response.json()
            ip = data.get('query', 'unknown')
            country = data.get('country', 'unknown')
            print(f"🌐 代理出口 IP: {ip}, 国家: {country}")
            if country.lower() != 'china':
                print("❌ 代理出口 IP 不是中国大陆，无法访问限制国内 IP 的镜像站，终止测试。")
                sys.exit(1)
            else:
                print("✅ 代理出口 IP 为中国大陆，继续测试。")
        else:
            print(f"⚠️ 获取出口 IP 失败，状态码: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"⚠️ 无法通过代理获取出口 IP: {e}")
        sys.exit(1)

def pull_image(mirror: str, proxy_port: int) -> tuple:
    registry = mirror.replace("https://", "").replace("http://", "")
    if "/" in TEST_IMAGE:
        full_image = f"{registry}/{TEST_IMAGE}"
    else:
        full_image = f"{registry}/library/{TEST_IMAGE}"
    
    env = os.environ.copy()
    env["HTTP_PROXY"] = f"http://127.0.0.1:{proxy_port}"
    env["HTTPS_PROXY"] = f"http://127.0.0.1:{proxy_port}"
    env["NO_PROXY"] = "localhost,127.0.0.1"
    cmd = ["docker", "pull", full_image]
    
    print(f"📥 执行: {' '.join(cmd)}")
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            stdout=None,
            stderr=subprocess.PIPE,
            text=True,
            timeout=TIMEOUT,
            env=env,
            check=False
        )
        elapsed = time.time() - start
        if proc.returncode == 0:
            return mirror, elapsed, True, "成功"
        else:
            err = proc.stderr.strip()[:200] if proc.stderr else "未知错误"
            return mirror, elapsed, False, f"拉取失败: {err}"
    except subprocess.TimeoutExpired:
        print("⏰ 拉取超时")
        return mirror, TIMEOUT, False, "超时"
    except Exception as e:
        return mirror, 0, False, f"异常: {str(e)[:50]}"

def get_beijing_time():
    return time.strftime('%Y-%m-%d %H:%M:%S')

def main():
    print("=" * 70)
    print("🐳 Docker 镜像加速器速度测试（强制清理缓存 + 实时日志）")
    print(f"测试镜像: {TEST_IMAGE}")
    print(f"镜像站数量: {len(MIRRORS)}")
    print(f"代理出口: {SOCKS5_HOST}:{SOCKS5_PORT}")
    print(f"当前时间（北京时间）: {get_beijing_time()}")
    print("=" * 70)

    # 确保 socat 已安装
    try:
        subprocess.run(["socat", "-V"], capture_output=True, check=True)
    except:
        print("⚠️ socat 未安装，正在安装...")
        subprocess.run(["sudo", "apt-get", "update"], check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y", "socat"], check=True)

    # 启动 socat
    port = find_free_port()
    socat_proc = start_socat(port)
    print(f"✅ socat 已启动，监听 127.0.0.1:{port}")

    # ========== 关键检测：检查代理出口 IP 是否为中国大陆 ==========
    test_proxy_ip(port)

    # 首次清理缓存
    clear_docker_cache()

    results = []
    try:
        for idx, mirror in enumerate(MIRRORS, 1):
            print("\n" + "=" * 70)
            print(f"🔄 [{idx}/{len(MIRRORS)}] 测试镜像站: {mirror}")
            print(f"⏰ 开始时间: {get_beijing_time()}")
            print("=" * 70)
            
            url, elapsed, success, msg = pull_image(mirror, port)
            results.append((url, elapsed, success, msg))
            status_icon = "✅" if success else "❌"
            print(f"{status_icon} 完成: {url:<45} - 耗时 {elapsed:.2f}s - {msg}")
            
            if idx < len(MIRRORS):
                clear_docker_cache()
    finally:
        socat_proc.terminate()
        socat_proc.wait()

    results.sort(key=lambda x: (not x[2], x[1] if x[2] else float('inf')))

    with open("docker_mirror_results.txt", "w", encoding="utf-8") as f:
        f.write("Docker 镜像加速器测速结果（强制清理缓存）\n")
        f.write(f"测试镜像: {TEST_IMAGE}\n")
        f.write(f"测试时间（北京时间）: {get_beijing_time()}\n")
        f.write("=" * 70 + "\n")
        f.write("排名 | 镜像站 | 耗时 | 状态\n")
        f.write("-" * 70 + "\n")
        rank = 1
        success_count = 0
        for url, elapsed, success, msg in results:
            if success:
                success_count += 1
                f.write(f"{rank:>4} | {url} | {elapsed:.2f}s | 成功\n")
                rank += 1
            else:
                f.write(f"{'':>4} | {url} | 失败 | {msg}\n")
        f.write("=" * 70 + "\n")
        f.write(f"成功: {success_count} / 总数: {len(MIRRORS)}\n")

    print("\n" + "-" * 70)
    print(f"✅ 测试完成！成功 {success_count} 个，失败 {len(MIRRORS)-success_count} 个")
    print(f"📄 结果已保存至 docker_mirror_results.txt")
    print(f"⏰ 完成时间（北京时间）: {get_beijing_time()}")

    fast_three = []
    for url, elapsed, success, _ in results:
        if success:
            fast_three.append(url)
            if len(fast_three) == 3:
                break

    if fast_three:
        daemon_config = {"registry-mirrors": fast_three}
        with open("daemon.json", "w", encoding="utf-8") as f:
            json.dump(daemon_config, f, indent=2)
        print(f"📦 已生成 daemon.json，包含最快的 {len(fast_three)} 个镜像：")
        for i, url in enumerate(fast_three, 1):
            print(f"   {i}. {url}")
    else:
        print("⚠️ 没有可用镜像，不生成配置文件")

    for url, elapsed, success, _ in results:
        if success:
            print(f"\n🏆 最快的镜像站: {url} (耗时 {elapsed:.2f}s)")
            break
    else:
        print("\n⚠️  没有找到可用的镜像站")

if __name__ == "__main__":
    exit(main())