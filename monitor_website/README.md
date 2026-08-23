# 🖥️ 服务健康监控面板

监控 FRPS、青龙面板、API 服务端的健康状态。

## 🚀 快速启动

```bash
cd /home/zxj/jd-ios-ck/monitor_website

# 安装依赖
pip3 install -r requirements.txt

# 启动服务
./start.sh
# 或
python3 monitor_server.py
```

## 🌐 访问地址

启动后访问：**http://127.0.0.1:5000**

## 📊 监控目标

| 服务 | 地址 | 检测方式 |
|------|------|----------|
| FRPS | `1.sggg3326.top:7500` | HTTP `/api/proxy/tcp` |
| 青龙面板 | `1.sggg3326.top:12121` | HTTP `/` |
| API 服务端 | `1.sggg3326.top:9090` | HTTP `/health` |

## 📁 项目结构

```
monitor_website/
├── monitor_server.py    # 主服务器
├── templates/
│   └── index.html       # 监控页面
├── static/
│   ├── style.css        # 样式
│   └── script.js        # 前端交互
├── requirements.txt     # 依赖
├── start.sh            # 启动脚本
└── README.md           # 说明文档
```

## ⚙️ 配置

编辑 `monitor_server.py` 修改配置：

```python
SERVICES = {
    'frps': {'host': '...', 'port': ...},
    'qinglong': {'host': '...', 'port': ...},
    'api': {'host': '...', 'port': ...}
}

CHECK_INTERVAL = 30  # 检查间隔（秒）
SERVER_PORT = 5000   # 监控面板端口
```

## 📊 功能

- ✅ 实时监控 3 个服务状态
- ✅ 显示响应时间
- ✅ TCP 端口连通性检测
- ✅ FRPS 代理统计（在线数量、SOCKS5、SSH）
- ✅ 自动刷新（30 秒）
- ✅ 手动刷新按钮
- ✅ 整体状态指示

---

**启动命令：**
```bash
cd /home/zxj/jd-ios-ck/monitor_website
python3 monitor_server.py
```
