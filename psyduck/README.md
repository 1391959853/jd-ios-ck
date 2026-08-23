# 🦆 可达鸭 FRP 一键部署

自动测速代理 → 部署 FRP + SSH 容器

---

## ⚡ 快速开始

### 方式 1: 首次部署（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/1391959853/jd-ios-ck/X/psyduck/frp-psyduck.sh | bash
```

**适用**: 全新安装  
**行为**: 自动测速 → 选最快代理 → 完整部署

---

### 方式 2: 强制重建（调试）

```bash
curl -fsSL https://raw.githubusercontent.com/1391959853/jd-ios-ck/X/psyduck/frp-psyduck.sh | bash -s -- --debug
```

**适用**: 容器异常、配置错误  
**行为**: 删除所有容器（保留 SSH）→ 重新部署

---

## 📊 部署流程

```
1. 检查 /opt/psyduck/.deployed
   ├─ 存在 → 跳过部署
   └─ 不存在 → 执行部署

2. 代理测速
   └─ 选择最快节点

3. 部署容器
   ├─ FRPS 服务器
   ├─ SSH 容器（可选）
   └─ 配置持久化
```

---

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `frp-psyduck.sh` | 主部署脚本 |
| `/opt/psyduck/` | 安装目录 |
| `/opt/psyduck/.deployed` | 部署标志 |

---

## 🔧 常用命令

```bash
# 查看日志
docker logs frps

# 重启服务
docker restart frps

# 清理重建
curl ... | bash -s -- --debug
```

---

**详细**: [查看完整脚本](./frp-psyduck.sh)
