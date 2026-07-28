#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quantumult X 规则自动同步脚本
从 zqzess/rule_for_quantumultX 同步 rewrite/、rules/、snippet/ 三个文件夹
统计规则条数（全局去重），并自动生成文档
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple
from datetime import datetime, timezone, timedelta

# ==================== 配置 ====================
UPSTREAM_REPO = "https://github.com/zqzess/rule_for_quantumultX.git"
TEMP_DIR = Path("./temp_repo")
TARGET_DIR = Path("./qx")
DIRS_TO_SYNC = ["rewrite", "rules", "snippet"]

# App 名称映射表（文件名 → 显示名称）
APP_MAPPING = {
    "FanQieNovel": "番茄小说",
    "TikTok": "TikTok",
    "YouTube": "YouTube",
    "WeChat": "微信",
    "BiliBili": "哔哩哔哩",
    "DiDi": "滴滴出行",
    "Eleme": "饿了么",
    "JD": "京东",
    "Kuwo": "酷我音乐",
    "Meituan": "美团",
    "NetEaseMusic": "网易云音乐",
    "Pinduoduo": "拼多多",
    "Taobao": "淘宝",
    "Weibo": "微博",
    "Zhihu": "知乎",
    "Apple": "Apple",
    "Google": "Google",
    "Microsoft": "Microsoft",
    "Telegram": "Telegram",
    "Spotify": "Spotify",
    "QMusic": "QQ音乐",
    "backiee": "backiee",
    "ad_uni": "广告联盟",
    "baiduApp": "百度App",
}
# =============================================


def run_cmd(cmd: List[str], cwd: Path = None) -> Tuple[str, str]:
    """执行命令并返回 (stdout, stderr)"""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()


def clone_upstream() -> bool:
    """使用 sparse-checkout 克隆上游仓库的指定目录"""
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)

    print(f"📥 克隆上游仓库: {UPSTREAM_REPO}")
    # 初始化仓库
    TEMP_DIR.mkdir(parents=True)
    run_cmd(["git", "init"], cwd=TEMP_DIR)
    run_cmd(["git", "remote", "add", "origin", UPSTREAM_REPO], cwd=TEMP_DIR)
    run_cmd(["git", "config", "core.sparseCheckout", "true"], cwd=TEMP_DIR)

    # 配置 sparse-checkout 只拉取需要的目录
    sparse_file = TEMP_DIR / ".git" / "info" / "sparse-checkout"
    sparse_file.parent.mkdir(parents=True, exist_ok=True)
    with open(sparse_file, "w") as f:
        for d in DIRS_TO_SYNC:
            f.write(f"QuantumultX/{d}/\n")

    # 拉取
    stdout, stderr = run_cmd(
        ["git", "pull", "--depth=1", "origin", "master"],
        cwd=TEMP_DIR
    )
    if "fatal" in stderr.lower() or "error" in stderr.lower():
        print(f"❌ 克隆失败: {stderr}")
        return False

    print("✅ 克隆成功")
    return True


def extract_valid_lines(file_path: Path) -> List[str]:
    """
    提取文件中的有效规则行
    忽略：空行、# 开头的注释行、; 开头的注释行
    """
    lines = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and not stripped.startswith(";"):
                    lines.append(stripped)
    except UnicodeDecodeError:
        # 部分文件可能不是 UTF-8，尝试其他编码
        try:
            with open(file_path, "r", encoding="gbk") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and not stripped.startswith(";"):
                        lines.append(stripped)
        except Exception as e:
            print(f"⚠️ 无法读取文件 {file_path}: {e}")
    return lines


def infer_app_name(filename: str, file_path: Path = None) -> str:
    """推断文件对应的 App 名称"""
    # 1. 尝试从文件名提取
    name_part = Path(filename).stem  # 去掉扩展名
    if name_part in APP_MAPPING:
        return APP_MAPPING[name_part]

    # 2. 尝试从文件内容首行注释提取
    if file_path and file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith(";"):
                        # 尝试匹配常见格式: # 番茄小说 或 ; 番茄小说广告
                        match = re.search(r"([#;])\s*(.+?)(?:广告|规则|去广告|版|$)", stripped)
                        if match:
                            return match.group(2).strip()
                        # 直接取注释内容
                        content = stripped.lstrip("#;").strip()
                        if content and len(content) < 20:
                            return content
                    break  # 只读首行
        except Exception:
            pass

    return name_part


def sync_files() -> bool:
    """将上游文件同步到目标目录"""
    upstream_qx = TEMP_DIR / "QuantumultX"

    if not upstream_qx.exists():
        print("❌ 上游 QuantumultX 目录不存在")
        return False

    # 清空目标目录（保留 README.md）
    if TARGET_DIR.exists():
        for item in TARGET_DIR.iterdir():
            if item.name != "README.md":
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
    else:
        TARGET_DIR.mkdir(parents=True)

    # 复制三个目录
    for d in DIRS_TO_SYNC:
        src = upstream_qx / d
        dst = TARGET_DIR / d
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"📂 同步: {d}/")
        else:
            print(f"⚠️ 上游目录不存在: {d}/")

    return True


def collect_stats() -> Dict:
    """
    统计规则条数
    - 全局去重：对所有文件的有效行进行全局去重
    - 文件级统计：每个文件自身的有效行数（不去重）
    """
    rewrite_set: Set[str] = set()
    rules_set: Set[str] = set()
    file_stats: List[Dict] = []

    # 1. 处理 rewrite 目录
    rewrite_dir = TARGET_DIR / "rewrite"
    if rewrite_dir.exists():
        for file in sorted(rewrite_dir.glob("*.qxrewrite")):
            lines = extract_valid_lines(file)
            rewrite_set.update(lines)
            file_stats.append({
                "category": "rewrite",
                "name": file.name,
                "app": infer_app_name(file.name, file),
                "count": len(lines),
            })

    # 2. 处理 rules 目录
    rules_dir = TARGET_DIR / "rules"
    if rules_dir.exists():
        for file in sorted(rules_dir.glob("*.list")):
            lines = extract_valid_lines(file)
            rules_set.update(lines)
            file_stats.append({
                "category": "rules",
                "name": file.name,
                "app": infer_app_name(file.name, file),
                "count": len(lines),
            })

    # 3. 统计 snippet 文件数量
    snippet_dir = TARGET_DIR / "snippet"
    snippet_files = []
    if snippet_dir.exists():
        snippet_files = sorted(snippet_dir.glob("*.snippet"))
        # snippet 文件也加入 file_stats（不统计规则条数）
        for file in snippet_files:
            # 统计文件行数（含注释）
            line_count = 0
            try:
                with open(file, "r", encoding="utf-8") as f:
                    line_count = sum(1 for _ in f)
            except Exception:
                line_count = 0
            file_stats.append({
                "category": "snippet",
                "name": file.name,
                "app": infer_app_name(file.name, file),
                "count": line_count,  # 显示行数而非规则条数
                "is_snippet": True,
            })

    return {
        "rewrite_total": len(rewrite_set),
        "rules_total": len(rules_set),
        "snippet_count": len(snippet_files),
        "file_stats": file_stats,
        "total_files": len(file_stats),
        "last_sync": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
    }


def generate_sub_readme(stats: Dict) -> str:
    """生成 /qx/README.md 的内容"""
    lines = [
        "# QX 规则文件说明",
        "",
        f"> 最后更新：{stats['last_sync']}",
        "",
        "---",
        "",
    ]

    # 按分类分组
    categories = {
        "rewrite": ("rewrite/", "重写规则"),
        "rules": ("rules/", "分流/筛选规则"),
        "snippet": ("snippet/", "QX 规则配置片段"),
    }

    for cat_key, (dir_name, display_name) in categories.items():
        files = [f for f in stats["file_stats"] if f["category"] == cat_key]
        if not files:
            continue

        lines.append(f"## {dir_name}（{display_name}）")
        lines.append("")
        lines.append("| 文件名 | 对应 App | 规则条数 |")
        lines.append("|--------|----------|----------|")

        for f in files:
            if f.get("is_snippet"):
                # snippet 文件显示行数
                lines.append(f"| {f['name']} | {f['app']} | {f['count']} 行 |")
            else:
                lines.append(f"| {f['name']} | {f['app']} | {f['count']} |")

        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> 📌 说明：")
    lines.append("> - **规则条数**：每个文件自身的有效规则行数（不去重）")
    lines.append("> - **snippet 文件**：显示为文件行数（含注释），非规则条数")
    lines.append("> - 上游规则来源：[zqzess/rule_for_quantumultX](https://github.com/zqzess/rule_for_quantumultX)")

    return "\n".join(lines)


def update_main_readme(stats: Dict):
    """更新主 README.md 中的同步状态区块"""
    readme_path = Path("./README.md")

    if not readme_path.exists():
        print("⚠️ 主 README.md 不存在，跳过更新")
        return

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 定义同步状态占位符替换
    status_block = f"""## 📊 同步状态

- **最后同步时间**：{stats['last_sync']}
- **重写规则**（去重后）：{stats['rewrite_total']} 条
- **分流规则**（去重后）：{stats['rules_total']} 条
- **规则片段**（snippet）：{stats['snippet_count']} 个
- **规则文件总数**：{stats['total_files']} 个"""

    # 尝试替换现有的同步状态区块
    pattern = r"## 📊 同步状态[\s\S]*?(?=\n## |\Z)"
    if re.search(pattern, content):
        content = re.sub(pattern, status_block, content)
    else:
        # 如果没有找到，追加到文件末尾
        content += f"\n\n{status_block}\n"

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("✅ 已更新主 README.md")


def cleanup():
    """清理临时目录"""
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
        print("🧹 已清理临时文件")


def main():
    print("🚀 开始同步 QX 规则...")
    print("=" * 50)

    try:
        # 1. 克隆上游
        if not clone_upstream():
            cleanup()
            exit(1)

        # 2. 同步文件
        if not sync_files():
            cleanup()
            exit(1)

        # 3. 统计规则
        stats = collect_stats()
        print(f"\n📊 统计结果:")
        print(f"   - 重写规则（去重后）: {stats['rewrite_total']} 条")
        print(f"   - 分流规则（去重后）: {stats['rules_total']} 条")
        print(f"   - snippet 文件: {stats['snippet_count']} 个")
        print(f"   - 文件总数: {stats['total_files']} 个")

        # 4. 生成子文档
        sub_readme = generate_sub_readme(stats)
        with open(TARGET_DIR / "README.md", "w", encoding="utf-8") as f:
            f.write(sub_readme)
        print("✅ 已生成 /qx/README.md")

        # 5. 更新主 README
        update_main_readme(stats)

        # 6. 清理
        cleanup()

        print("\n✅ 同步完成！")
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        cleanup()
        exit(1)


if __name__ == "__main__":
    main()
