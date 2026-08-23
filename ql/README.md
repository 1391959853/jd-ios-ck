# 🐉 青龙脚本

## 📂 文件

| 文件 | 用途 |
|------|------|
| `wskey-update.py` | wskey 转换 pt_key |
| `psyduck-ipv6.py` | IPv6 支持 |

---

## ⚡ 快速部署

### Step 1. 添加脚本

青龙面板 → 脚本管理 → 新建 → 复制 `wskey-update.py`

### Step 2. 环境变量

| 变量 | 说明 |
|------|------|
| `FRPS_API_URL` | FRPS 接口地址 |
| `FRPS_API_AUTH` | FRPS 认证 |
| `XIEQU_UID` | 携趣 UID |
| `XIEQU_UKEY` | 携趣 UKey |
| `BARK_SERVER` | Bark 地址（可选） |

### Step 3. 定时任务

```crontab
0 */4 * * *
```

---

## ❓ 故障排查

| 问题 | 解决 |
|------|------|
| 转换失败 | 检查 FRPS API |
| 无通知 | 测试 Bark 服务 |
| 携趣错误 | 验证 UID/UKey |

**详细**: [查看完整文档](./README.md#故障排查)
