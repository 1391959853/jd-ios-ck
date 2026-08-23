#!/usr/bin/env python3
"""
Docker 镜像加速器速度测试（顺序执行，强制 SOCKS5 代理）
使用 proxychains4 使 docker pull 走 SOCKS5 出口
"""

import subprocess
import time
import os
import json

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

# ========== 🔧 请在这里替换为您的真实代理账密 ==========
SOCKS5_HOST = os.getenv("SOCKS5_HOST", "1.sggg3326.top")
SOCKS5_PORT = os.getenv("SOCKS5_PORT", "6005")
SOCKS5_USER = "socksuser"   # <--- 替换为真实用户名
SOCKS5_PASS = "sockspass123"     # <--- 替换为真实密码
# ==================================================

def setup_proxychains():
    """生成 proxychains4 配置文件"""
    config = f"""
strict_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000

[ProxyList]
socks5://{SOCKS5_USER}:{SOCKS5_PASS}@{SOCKS5_HOST}:{SOCKS5_PORT}
"""
    with open("/tmp/proxychains.conf", "w") as f:
        f.write(config)

def pull_from_mirror(mirror: str) -> tuple:
    registry = mirror.replace("https://", "").replace("http://", "")
    full_image = f"{registry}/library/{TEST_IMAGE}"
    cmd = ["proxychains4", "-f", "/tmp/proxychains.conf", "docker", "pull", full_image]
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False)
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
    print("🐳 Docker 镜像加速器速度测试（顺序执行，SOCKS5 强制代理）")
    print(f"测试镜像: {TEST_IMAGE}")
    print(f"镜像站数量: {len(MIRRORS)}")
    print(f"代理出口: {SOCKS5_HOST}:{SOCKS5_PORT}")
    print("=" * 70)

    setup_proxychains()
    results = []

    for idx, mirror in enumerate(MIRRORS, 1):
        print(f"\n🔄 [{idx}/{len(MIRRORS)}] 测试: {mirror}")
        url, elapsed, success, msg = pull_from_mirror(mirror)
        results.append((url, elapsed, success, msg))
        status_icon = "✅" if success else "❌"
        print(f"{status_icon} 完成: {url:<45} - {elapsed:.2f}s - {msg}")

    # 按成功+耗时排序
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

    # 提取最快的三个镜像
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

    # 输出最优镜像
    for url, elapsed, success, _ in results:
        if success:
            print(f"\n🏆 最快的镜像站: {url} (耗时 {elapsed:.2f}s)")
            break
    else:
        print("\n⚠️  没有找到可用的镜像站")

if __name__ == "__main__":
    exit(main())
