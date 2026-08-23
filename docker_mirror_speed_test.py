#!/usr/bin/env python3
"""
Docker 镜像加速器速度测试（强制清理缓存，实时打印日志，北京时间，IP归属检测）
如果代理出口 IP 非中国大陆，则立即退出，并明确区分失败原因。
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
SOCKS5_USER = os.getenv("SOCKS5_USER", "你的用户名")   # 请替换
SOCKS5_PASS = os.getenv("SOCKS5_PASS", "你的密码")     # 请替换
# ======================================================

def find_free_port():
    """找一个空闲端口"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def start_socat(port):
    """启动 socat，将本地 HTTP 代理转发到 SOCKS5（使用正确的认证选项）"""
    # 正确的选项名：socksuser 和 sockspass（不是 socks5user）
    if SOCKS5_USER and SOCKS5_PASS:
        socks5_url = f"SOCKS5:{SOCKS5_HOST}:{SOCKS5_PORT},socksuser={SOCKS5_USER},sockspass={SOCKS5_PASS}"
    else:
        socks5_url = f"SOCKS5:{SOCKS5_HOST}:{SOCKS5_PORT}"
    cmd = [
        "socat",
        f"TCP4-LISTEN:{port},fork,reuseaddr",
        socks5_url
    ]
    # 不将 stderr 重定向，以便检测启动失败
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(2)
    # 检查进程是否还活着
    if proc.poll() is not None:
        _, err = proc.communicate()
        print(f"❌ socat 启动失败: {err.decode().strip()}")
        sys.exit(1)
    return proc

def clear_docker_cache():
    """强制清理所有 Docker 缓存"""
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
    """
    通过 HTTP 代理查询出口 IP 并检查是否为中国大陆，详细区分失败原因
    """
    proxy_url = f"http://127.0.0.1:{port}"
    proxies = {"http": proxy_url, "https": proxy_url}

    # 1. 先尝试通过国内网站 myip.ipip.net 获取出口 IP（纯文本，简单可靠）
    try:
        cmd = ["curl", "-x", proxy_url, "-s", "http://myip.ipip.net"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            ip = result.stdout.strip()
            print(f"🌐 代理出口 IP: {ip}")
            # 2. 查询该 IP 的归属地
            try:
                resp = requests.get(
                    f"http://ip-api.com/json/{ip}?fields=country",
                    proxies=proxies,
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    country = data.get('country', 'unknown')
                    print(f"🌍 归属地: {country}")
                    if country.lower() == 'china':
                        print("✅ 代理出口 IP 为中国大陆，继续测试。")
                        return
                    else:
                        print(f"❌ 代理出口 IP 归属地为 {country}，非中国大陆，终止测试。")
                        sys.exit(1)
                else:
                    print("⚠️ 查询归属地接口返回状态码异常，无法确定归属地，终止测试。")
                    sys.exit(1)
            except Exception as e:
                print(f"⚠️ 查询归属地失败: {e}，无法确定代理 IP 归属地，终止测试。")
                sys.exit(1)
        else:
            print("⚠️ 通过 myip.ipip.net 获取 IP 失败（代理可能无法访问该网站），尝试其他接口...")
    except Exception as e:
        print(f"⚠️ curl 执行异常: {e}，尝试其他接口...")

    # 备选方案：使用其他接口（如 ip-api.com 直接返回国家）
    apis = [
        ("https://ip.useragentinfo.com/json", "ip", "country"),
        ("http://ip-api.com/json/", "query", "country"),
    ]
    for api_url, ip_key, country_key in apis:
        try:
            response = requests.get(api_url, proxies=proxies, timeout=10)
            if response.status_code == 200:
                data = response.json()
                ip = data.get(ip_key, 'unknown')
                country = data.get(country_key, 'unknown')
                print(f"🌐 代理出口 IP: {ip}, 国家: {country}")
                if country.lower() != 'china':
                    print(f"❌ 代理出口 IP 归属地为 {country}，非中国大陆，终止测试。")
                    sys.exit(1)
                else:
                    print("✅ 代理出口 IP 为中国大陆，继续测试。")
                    return
            else:
                print(f"⚠️ 接口 {api_url} 返回状态码 {response.status_code}，尝试下一个...")
        except Exception as e:
            print(f"⚠️ 接口 {api_url} 请求失败: {e}，尝试下一个...")

    # 所有方法均失败
    print("❌ 所有 IP 查询方式均失败，代理可能无法访问外网或配置错误，终止测试。")
    sys.exit(1)

def pull_image(mirror: str, proxy_port: int) -> tuple:
    """通过 HTTP 代理拉取镜像，实时打印 Docker 输出"""
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

    # 排序
    results.sort(key=lambda x: (not x[2], x[1] if x[2] else float('inf')))

    # 生成结果文件
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

    # 提取最快的三个
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