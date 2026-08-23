# 📱 iOS 端部署

支持 Quantumult X / Surge / Loon

---

## ⚡ Quantumult X（推荐）⭐

### Step 1. 添加重写

```
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie2qx.conf
```

### Step 2. 添加脚本

```
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie.js
```

### Step 3. MitM 配置

域名：`api.m.jd.com`, `sh.jd.com`

### Step 4. 信任证书

设置 → 通用 → 证书信任设置

---

## 📲 Surge

```
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie2api.sgmodule
```

---

## 📲 Loon

```ini
[Remote]
https://raw.githubusercontent.com/1391959853/jd-ios-ck/main/ios/JDcookie2loon.conf
```

---

## 🔧 配置修改

编辑 `JDcookie.js` 第 5 行：

```javascript
const API_URL = "http://你的服务器:9090/jd/raw_ck";
```

---

## ❓ 故障排查

| 问题 | 解决 |
|------|------|
| 配对失败 | 清空 `$prefs.valueForKey("JD_PinMap")` |
| API 失败 | 检查服务器是否运行 |
| 无响应 | 确认证书已信任 |

**详细**: [查看完整文档](./README.md#故障排查)
