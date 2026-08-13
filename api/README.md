## 🔍 故障排查

### 🔴 问题 1: 青龙连接失败

**症状**: 健康检查返回 `qinglong_connected: false`

**解决方案**:
```bash
# 1. 检查青龙地址
curl http://192.168.188.183:5800/open/envs

# 2. 验证凭证
curl "http://192.168.188.183:5800/open/auth/token?client_id=你的 ID&client_secret=你的 KEY"

# 3. 测试 API
curl http://ql-host:5700/open/envs -H "Authorization: Bearer 你的 token"
```

---

### 🔴 问题 2: wskey 转换失败

**症状**: 日志显示 "所有代理及直连均无法获取 cookie"

**解决方案**:
```bash
# 1. 检查 FRPS API
curl http://frps-host:7500/api/proxy/tcp

# 2. 测试代理节点
curl -x socks5://proxy:port https://api.m.jd.com

# 3. 查看 API 日志
docker-compose logs | grep "FRPS"
```

---

### 🔴 问题 3: API 无法访问

**症状**: 连接超时或拒绝连接

**解决方案**:
```bash
# 1. 检查端口
netstat -tlnp | grep 9090

# 2. 检查防火墙
ufw status | grep 9090

# 3. 查看日志
docker-compose logs -f
```
| 配置 | 建议值 | 说明 |
|------|--------|------|
| 代理数量 | 2~5 个 | 过多会增加延迟 |
| 冷却时间 | 4 小时 | 避免触发京东风控 |
| 并发请求 | ≤ 10/s | 防止服务器过载 |

---

## 🔗 相关链接

| 资源 | 地址 |
|------|------|
| iOS 端文档 | [../JD/README.md](../JD/README.md) |
| 青龙面板 | https://github.com/whyour/qinglong |
| FRPS 文档 | https://gofrp.org |

---

**最后更新**: 2026 年 8 月 14 日
