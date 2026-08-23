#!/usr/bin/env python3
"""
Docker 镜像加速器速度测试（使用 proxychains4 强制代理）
硬编码 SOCKS5 账号密码，通过 proxychains4 执行所有需要代理的命令。
"""

import subprocess
import time
import os
import json
import sys
import tempfile

# ========== 设置时区为北京时间 ==========
os.environ['TZ'] = 'Asia/Shanghai'
time.tzset()
# =========================================

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

# ========== 🔧 硬编码 SOCKS5 代理账号密码 ==========
SOCKS5_HOST = "1.sggg3326.top"
SOCKS5_PORT = "6005"
SOCKS5_USER = "socksuser"   # 请替换为真实值
SOCKS5_PASS = "sockspass123"     # 请替换为真实值
# =================================================

def install_proxychains():
    """确保 proxychains4 已安装"""
    try:
        subprocess.run(["proxychains4", "-h"], capture_output=True, check=True)
    except:
        print("⚠️ proxychains4 未安装，正在安装...")
        subprocess.run(["sudo", "apt-get", "update"], check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y", "proxychains4"], check=True)

def create_proxychains_conf():
    """
    生成 proxychains 配置文件，返回文件路径
    格式依据官方文档：socks5 主机 端口 用户名 密码
    """
    conf_content = f"""strict_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000

[ProxyList]
socks5 {SOCKS5_HOST} {SOCKS5_PORT} {SOCKS5_USER} {SOCKS5_PASS}
"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf') as f:
        f.write(conf_content)
        return f.name

def run_with_proxy(cmd, conf_path, timeout=None):
    """通过 proxychains4 执行命令，返回 (返回码, stdout, stderr)"""
    full_cmd = ["proxychains4", "-f", conf_path] + cmd
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"

def check_proxy(conf_path):
    """预检代理是否可用（通过 httpbin.org/ip）"""
    print("🔍 预检 SOCKS5 代理...")
    cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "https://httpbin.org/ip"]
    ret, out, err = run_with_proxy(cmd, conf_path, timeout=10)
    if ret == 0 and out == "200":
        print("✅ 代理预检成功")
        return True
    else:
        print(f"❌ 代理预检失败 (返回码: {ret}, 输出: {out}, 错误: {err})")
        return False

def get_proxy_ip(conf_path):
    """通过代理获取出口 IP（使用 myip.ipip.net）"""
    cmd = ["curl", "-s", "http://myip.ipip.net"]
    ret, out, err = run_with_proxy(cmd, conf_path, timeout=10)
    if ret == 0 and out:
        return out.strip()
    else:
        print(f"⚠️ 获取出口 IP 失败: {err}")
        return None

def get_ip_country(ip, conf_path):
    """查询 IP 归属地（通过 ip-api.com）"""
    cmd = ["curl", "-s", f"http://ip-api.com/json/{ip}?fields=country"]
    ret, out, err = run_with_proxy(cmd, conf_path, timeout=10)
    if ret == 0 and out:
        try:
            data = json.loads(out)
            return data.get('country', 'unknown')
        except:
            pass
    return None

def clear_docker_cache():
    """清理 Docker 缓存（无需代理）"""
    print("🧹 清理 Docker 缓存...")
    subprocess.run(["docker", "system", "prune", "-a", "-f"], check=False)
    subprocess.run(["docker", "volume", "prune", "-f"], check=False)
    subprocess.run(["docker", "builder", "prune", "-a", "-f"], check=False)

def pull_image(mirror, conf_path):
    """通过代理拉取镜像"""
    registry = mirror.replace("https://", "").replace("http://", "")
    if "/" in TEST_IMAGE:
        full_image = f"{registry}/{TEST_IMAGE}"
    else:
        full_image = f"{registry}/library/{TEST_IMAGE}"
    
    cmd = ["docker", "pull", full_image]
    print(f"📥 拉取: {full_image}")
    start = time.time()
    ret, out, err = run_with_proxy(cmd, conf_path, timeout=TIMEOUT)
    elapsed = time.time() - start
    
    if ret == 0:
        return mirror, elapsed, True, "成功"
    else:
        err_msg = err[:200] if err else "未知错误"
        return mirror, elapsed, False, f"拉取失败: {err_msg}"

def get_beijing_time():
    return time.strftime('%Y-%m-%d %H:%M:%S')

def main():
    print("=" * 70)
    print("🐳 Docker 镜像加速器速度测试 (proxychains4 + SOCKS5)")
    print(f"测试镜像: {TEST_IMAGE}")
    print(f"镜像站数量: {len(MIRRORS)}")
    print(f"代理出口: {SOCKS5_HOST}:{SOCKS5_PORT}")
    print(f"当前时间（北京时间）: {get_beijing_time()}")
    print("=" * 70)

    # 安装 proxychains4
    install_proxychains()

    # 创建临时配置文件
    conf_path = create_proxychains_conf()
    print(f"📄 使用 proxychains 配置文件: {conf_path}")

    # 预检代理
    if not check_proxy(conf_path):
        print("❌ 代理不可用，终止测试")
        sys.exit(1)

    # 获取出口 IP 并检查归属地
    ip = get_proxy_ip(conf_path)
    if ip:
        print(f"🌐 代理出口 IP: {ip}")
        country = get_ip_country(ip, conf_path)
        if country:
            print(f"🌍 归属地: {country}")
            if country.lower() != 'china':
                print("❌ 出口 IP 非中国大陆，终止测试")
                sys.exit(1)
            else:
                print("✅ 出口 IP 为中国大陆，继续测试")
        else:
            print("⚠️ 无法查询归属地，但代理预检通过，继续测试")
    else:
        print("⚠️ 无法获取出口 IP，但代理预检通过，继续测试")

    # 清理 Docker 缓存
    clear_docker_cache()

    results = []
    for idx, mirror in enumerate(MIRRORS, 1):
        print("\n" + "=" * 70)
        print(f"🔄 [{idx}/{len(MIRRORS)}] 测试镜像站: {mirror}")
        print(f"⏰ 开始时间: {get_beijing_time()}")
        print("=" * 70)
        
        url, elapsed, success, msg = pull_image(mirror, conf_path)
        results.append((url, elapsed, success, msg))
        status_icon = "✅" if success else "❌"
        print(f"{status_icon} 完成: {url:<45} - 耗时 {elapsed:.2f}s - {msg}")
        
        # 每个镜像测试后清理缓存（避免缓存影响下一个）
        if idx < len(MIRRORS):
            clear_docker_cache()

    # 排序
    results.sort(key=lambda x: (not x[2], x[1] if x[2] else float('inf')))

    # 生成结果文件
    with open("docker_mirror_results.txt", "w", encoding="utf-8") as f:
        f.write("Docker 镜像加速器测速结果（proxychains4 + SOCKS5）\n")
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

    # 删除临时配置文件
    try:
        os.unlink(conf_path)
    except:
        pass

if __name__ == "__main__":
    exit(main())