# 🖥️ 服务监控面板

监控 FRPS、青龙、API 的健康状态

---

## ⚡ 快速启动

```bash
cd monitor_website
pip3 install -r requirements.txt
./start.sh
```

访问：**http://127.0.0.1:5000**

---

## 📊 监控目标

| 服务 | 地址 | 检测 |
|------|------|------|
| FRPS | `1.sggg3326.top:7500` | `/api/proxy/tcp` |
| 青龙 | `1.sggg3326.top:12121` | `/` |
| API | `1.sggg3326.top:9090` | `/health` |

---

## 📁 结构

```
monitor_website/
├── monitor_server.py   # 主程序
├── templates/          # HTML 页面
├── static/             # CSS/JS
└── requirements.txt    # 依赖
```

---

## ⚙️ 配置

编辑 `monitor_server.py` 修改监控地址

---

**详细**: [查看完整文档](./README.md)
