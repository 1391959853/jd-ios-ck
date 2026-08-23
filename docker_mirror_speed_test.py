#!/usr/bin/env python3
"""
Docker 镜像加速器速度测试（通过 socat 将 SOCKS5 转为 HTTP 代理，供 Docker 使用）
"""

import subprocess
import time
import os
import json
import socket

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

TEST_IMAGE = "ubuntu:22.04"
TIMEOUT = 300  # 每个镜像拉取超时（秒）

# ========== 🔧 请在这里修改为您的真实代理账密 ==========
SOCKS5_HOST = os.getenv("SOCKS5_HOST", "1.sggg3326.top")
SOCKS5_PORT = os.getenv("SOCKS5_PORT", "6005")
SOCKS5_USER = os.getenv("SOCKS5_USER", "socksuser")   # 请替换
SOCKS5_PASS = os.getenv("SOCKS5_PASS", "sockspass123")     # 请替换
# ======================================================

def find_free_port():
    """找一个空闲端口"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def start_socat(port):
    """启动 socat，将本地 HTTP 代理转发到 SOCKS5"""
    socks5_url = f"SOCKS5:{SOCKS5_HOST}:{SOCKS5_PORT}"
    if SOCKS5_USER and SOCKS5_PASS:
        socks5_url = f"SOCKS5:{SOCKS5_HOST}:{SOCKS5_PORT},socks5user={SOCKS5_USER},socks5pass={SOCKS5_PASS}"
    cmd = [
        "socat",
        f"TCP4-LISTEN:{port},fork,reuseaddr",
        socks5_url
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)  # 等待 socat 就绪
    return proc

def pull_image(mirror: str, proxy_port: int) -> tuple:
    """通过 HTTP 代理拉取镜像"""
    registry = mirror.replace("https://", "").replace("http://", "")
    full_image = f"{registry}/library/{TEST_IMAGE}"
    env = os.environ.copy()
    env["HTTP_PROXY"] = f"http://127.0.0.1:{proxy_port}"
    env["HTTPS_PROXY"] = f"http://127.0.0.1:{proxy_port}"
    env["NO_PROXY"] = "localhost,127.0.0.1"
    cmd = ["docker", "pull", full_image]
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            env=env,
            check=False
        )
        elapsed = time.time() - start
        if proc.returncode == 0:
            return mirror, elapsed, True, "成功"
        else:
            err = proc.stderr.strip()[:100]
            return mirror, elapsed, False, f"拉取失败: {err}"
    except subprocess.TimeoutExpired:
        return mirror, TIMEOUT, False, "超时"
    except Exception as e:
        return mirror, 0, False, f"异常: {str(e)[:50]}"

def main():
    print("=" * 70)
    print("🐳 Docker 镜像加速器速度测试（socat 代理转换）")
    print(f"测试镜像: {TEST_IMAGE}")
    print(f"镜像站数量: {len(MIRRORS)}")
    print(f"代理出口: {SOCKS5_HOST}:{SOCKS5_PORT}")
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

    results = []
    try:
        for idx, mirror in enumerate(MIRRORS, 1):
            print(f"\n🔄 [{idx}/{len(MIRRORS)}] 测试: {mirror}")
            url, elapsed, success, msg = pull_image(mirror, port)
            results.append((url, elapsed, success, msg))
            status_icon = "✅" if success else "❌"
            print(f"{status_icon} 完成: {url:<45} - {elapsed:.2f}s - {msg}")
    finally:
        socat_proc.terminate()
        socat_proc.wait()

    # 排序：成功的按耗时升序，失败的放最后
    results.sort(key=lambda x: (not x[2], x[1] if x[2] else float('inf')))

    # 生成结果文件
    with open("docker_mirror_results.txt", "w", encoding="utf-8") as f:
        f.write("Docker 镜像加速器测速结果\n")
        f.write(f"测试镜像: {TEST_IMAGE}\n")
        f.write(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
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

    # 提取最快的三个
    fast_three = []
    for url, elapsed, success, _ in results:
        if success:
            fast_three.append(url)
            if len(fast_three) == 3:
                break

    if fast_three:
        daemon_config = {"registry-mirrors": fast_three}
        with open("docker-daemon.json", "w", encoding="utf-8") as f:
            json.dump(daemon_config, f, indent=2)
        print(f"📦 已生成 docker-daemon.json，包含最快的 {len(fast_three)} 个镜像：")
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
