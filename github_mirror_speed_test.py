#!/usr/bin/env python3
"""
GitHub 镜像下载速度测试 - SOCKS5 版本 (2026 最新地址)
用于模拟国内网络环境测试
"""

import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# ---------- SOCKS5 代理配置（从环境变量读取） ----------
SOCKS5_HOST = os.getenv("SOCKS5_HOST", "1.sggg3326.top")
SOCKS5_PORT = int(os.getenv("SOCKS5_PORT", "6005"))
SOCKS5_USER = os.getenv("SOCKS5_USER", "socksuser")
SOCKS5_PASS = os.getenv("SOCKS5_PASS", "sockspass123")

print(f"🔐 SOCKS5 代理：{SOCKS5_HOST}:{SOCKS5_PORT} (用户：{SOCKS5_USER})")

# 代理配置
PROXY = {
    "http": f"socks5h://{SOCKS5_USER}:{SOCKS5_PASS}@{SOCKS5_HOST}:{SOCKS5_PORT}",
    "https": f"socks5h://{SOCKS5_USER}:{SOCKS5_PASS}@{SOCKS5_HOST}:{SOCKS5_PORT}"
}

# ---------- 2026年最新 GitHub 镜像列表 ----------
# 根据搜索结果更新，包含 gh-proxy.com 多区域节点和其他可用镜像
PROXY_LIST = [
    # gh-proxy.com 多区域节点（2026 年可用）
    "https://gh-proxy.com/",          # 主站
    "https://gh.404cafe.fun/",        # 2026 新增
    "https://ghfast.top/",
    "https://ghproxy.cc/"
]  # 👈 这里需要闭合

# 测试文件 (~30MB，先测小文件)
TEST_FILE_URL = "https://github.com/microsoft/vscode/archive/refs/tags/1.85.0.tar.gz"
# 备选：https://github.com/git/git/archive/refs/tags/v2.43.0.tar.gz

def test_proxy_download(proxy_base_url, timeout=180):
    """通过 SOCKS5 代理测试镜像下载速度"""
    proxy_download_url = proxy_base_url + TEST_FILE_URL
    start_time = time.time()
    
    try:
        response = requests.get(
            proxy_download_url, 
            proxies=PROXY,
            timeout=timeout, 
            stream=True,
            verify=False  # 跳过 SSL 验证（部分镜像证书问题）
        )
        response.raise_for_status()
        
        total_size = 0
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                total_size += len(chunk)
        
        duration = time.time() - start_time
        
        if total_size > 0:
            size_mb = total_size / (1024 * 1024)
            speed_mbps = (total_size * 8) / (duration * 1000000) if duration > 0 else 0
            return proxy_base_url, duration, size_mb, speed_mbps, "成功"
        else:
            return proxy_base_url, duration, 0, 0, "内容为空"
            
    except requests.exceptions.Timeout:
        return proxy_base_url, timeout, 0, 0, f"超时"
    except requests.exceptions.ConnectionError as e:
        return proxy_base_url, float('inf'), 0, 0, f"连接失败"
    except requests.exceptions.RequestException as e:
        error_msg = str(e)[:30]
        return proxy_base_url, float('inf'), 0, 0, f"{error_msg}"
    except Exception as e:
        return proxy_base_url, float('inf'), 0, 0, f"异常"

def main():
    print("=" * 70)
    print("🚀 GitHub 镜像下载速度测试 (SOCKS5 模拟国内网络)")
    print(f"📦 代理：{SOCKS5_HOST}:{SOCKS5_PORT}")
    print("=" * 70)
    print(f"📦 测试文件：{TEST_FILE_URL}")
    print(f"⏱️  超时时间：180 秒")
    print(f"📡 代理节点数量：{len(PROXY_LIST)}")
    print("=" * 70)
    
    results = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_proxy = {executor.submit(test_proxy_download, proxy): proxy for proxy in PROXY_LIST}
        
        for future in as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            try:
                proxy_url, duration, size_mb, speed, status = future.result()
                results.append((proxy_url, duration, size_mb, speed, status))
                
                status_icon = "✅" if "成功" in status else "❌"
                print(f"{status_icon} 完成：{proxy_url:<45} - {status}")
                
            except Exception as exc:
                results.append((proxy, float('inf'), 0, 0, f"异常"))
    
    # 按速度排序
    results.sort(key=lambda x: x[1])
    
    # 输出结果
    print("\n" + "=" * 70)
    print("📊 测试结果（按耗时排序）")
    print("=" * 70)
    print(f"{'排名':<4} {'代理地址':<42} {'耗时':<10} {'大小':<8} {'速度':<10} {'状态'}")
    print("-" * 70)
    
    for i, (proxy_url, duration, size_mb, speed, status) in enumerate(results, 1):
        duration_str = f"{duration:.1f}s" if duration != float('inf') else "失败"
        size_str = f"{size_mb:.0f}MB" if size_mb > 0 else "-"
        speed_str = f"{speed:.1f}Mbps" if speed > 0 else "-"
        status_short = status[:15] if len(status) > 15 else status
        print(f"{i:<4} {proxy_url:<42} {duration_str:<10} {size_str:<8} {speed_str:<10} {status_short}")
    
    # 保存结果（固定文件名）
    result_file = "speed_test_results.txt"
    
    with open(result_file, "w", encoding="utf-8") as f:
        f.write("GitHub 镜像下载速度测试 (SOCKS5 代理)\n")
        f.write("=" * 60 + "\n")
        f.write(f"SOCKS5 代理：{SOCKS5_HOST}:{SOCKS5_PORT}\n")
        f.write(f"测试时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"测试文件：{TEST_FILE_URL}\n")
        f.write(f"超时时间：180 秒\n")
        f.write("=" * 60 + "\n\n")
        f.write("排名 | 地址 | 耗时 | 大小 | 速度 | 状态\n")
        f.write("-" * 60 + "\n")
        for i, (proxy_url, duration, size_mb, speed, status) in enumerate(results, 1):
            if duration != float('inf'):
                f.write(f"{i:4d} | {proxy_url} | {duration:.1f}s | {size_mb:.1f}MB | {speed:.1f}Mbps | {status}\n")
            else:
                f.write(f"{i:4d} | {proxy_url} | 失败 | - | - | {status}\n")
    
    # GitHub Actions 输出
    github_output = os.getenv('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            for proxy_url, duration, size_mb, speed, status in results[:3]:
                if duration != float('inf') and size_mb > 0:
                    f.write(f"working_proxy={proxy_url}\n")
                    f.write(f"best_speed={speed:.1f}\n")
                    break
    
    print(f"\n✅ 测试完成，结果已保存至 {result_file}")
    
    # 返回最佳代理
    for proxy_url, duration, size_mb, speed, status in results:
        if duration != float('inf') and size_mb > 10:
            print(f"\n🏆 推荐镜像：{proxy_url} ({speed:.1f}Mbps)")
            return 0
    
    print("\n⚠️  未找到可用的镜像")
    return 1

if __name__ == "__main__":
    exit(main())
