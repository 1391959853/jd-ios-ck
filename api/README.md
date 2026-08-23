# 🔧 服务端 API

Flask API - 接收 iOS Cookie 并同步到青龙

---

## ⚡ 快速部署

### Docker

```bash
docker-compose up -d
```

### 直接运行

```bash
pip install -r requirements.txt
python3 app.py
```

---

## 🔧 配置

编辑 `app.py`：

```python
# 第 30 行
QL_BASE_URL = "http://青龙地址：5700"
QL_CLIENT_ID = "你的 ID"
QL_CLIENT_SECRET = "你的 KEY"
```

---

## 📡 API 接口

### POST /jd/raw_ck

```json
{
  "pt_key": "xxx",
  "pt_pin": "xxx",
  "wskey": "xxx"
}
```

**响应**:
```json
{"code": 200, "match": true, "synced": true}
```

---

## ❓ 故障排查

| 问题 | 解决 |
|------|------|
| 青龙连接失败 | 检查 URL 和凭证 |
| 转换失败 | 测试代理节点 |
| API 无法访问 | 检查端口 9090 |

**详细**: [查看完整文档](./README.md#故障排查)
