/**
 * @file       京东 Cookie 获取 & 自动提交 API（含变更检测）
 * @desp       获取京东 pt_key/pt_pin，写入 BoxJS，并自动提交到 API。
 * @env        CookiesJD
 * @author     魔改：https://raw.githubusercontent.com/Lxi0707/Scripts/refs/heads/X/pt_key.js
 * @updated    2025-11-13
 * @version    v0.0.1
 * @link       https://raw.githubusercontent.com/randomshit699/surge/refs/heads/main/JD/JDcookie.js
 * ❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖
 * 主要功能：
 * 🔵 自动抓取京东 Cookie（pt_key + pt_pin）
 * 🔵 自动写入 BoxJS → CookiesJD
 * 🔵 自动识别该账号 Cookie  → 自动提交到 API：  
 *       https://frp0721.dynv6.net/jd/raw_ck
 * 🔵 提交成功会显示：昵称、是否新增、是否同步青龙成功
 * 🔵 支持 Surge / Quantumult X / Loon
 * ❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀
 *
 * 📌 获取 Cookie 方法：
 *  打开京东 App
 *  
 *
 * 💬 BoxJs 变量：
 *  - CookiesJD  → 存储多账号 pt_key/pt_pin 列表
 *
 * ⚙ Surge 配置
 * ------------------------------------------
 * [Script]
 * # 京东 cookie 获取 & API 提交（含变更判断）
 * a-JD_pt_key = type=http-request, pattern=^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig), script-path=https://raw.githubusercontent.com/randomshit699/surge/refs/heads/main/JD/JDcookie.js
 *
 * [MITM]
 * hostname = %APPEND% api.m.jd.com
 *
 * ⚙ Quantumult X 配置
 * ------------------------------------------
 * [rewrite_local]
 * ^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig) url script-request-header https://raw.githubusercontent.com/randomshit699/surge/refs/heads/main/JD/JDcookie.js
 *
 * [mitm]
 * hostname = api.m.jd.com
 *
 * ⚙ Loon 配置
 * ------------------------------------------
 * [Script]
 * http-request ^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig) script-path=https://raw.githubusercontent.com/randomshit699/surge/refs/heads/main/JD/JDcookie.js, timeout=10, tag=京东Cookie获取
 *
 * [MITM]
 * hostname = api.m.jd.com
 *
 * ❗ 提示
 * - 获取 Cookie 后无需频繁触发；只有 pt_key 变更时才会自动推送 & 提交 API。
 * - 使用 QX 时如出现“重写关闭”的提示，需开启 rewrite & MITM。
 *
 * ❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖
 */



/**
 * 京东Cookie获取并自动提交到API服务器
 * 功能：
 * 1. 保存到 BoxJS 的 CookiesJD（原功能）
 * 2. 自动提交到远程API服务器（新功能）
 * 日期：2025年1月11日
 */

// ==================== 配置区 ====================
const API_URL = "https://frp0721.dynv6.net/jd/raw_ck";  // API服务器地址

// ==================== 主逻辑 ====================
let cookie = $request.headers['Cookie'] || $request.headers['cookie'];
let ptPinMatch = cookie.match(/pt_pin=([^; ]+)(?=;?)/);
let ptKeyMatch = cookie.match(/pt_key=([^; ]+)(?=;?)/);

if (ptPinMatch && ptKeyMatch) {
    let pt_pin = ptPinMatch[1];
    let pt_key = ptKeyMatch[1];
    let newCookie = `pt_key=${pt_key};pt_pin=${pt_pin};`;

    // ==================== 功能1: 保存到 BoxJS（原功能）====================
    let cookiesListRaw = $persistentStore.read("CookiesJD");
    let cookiesList = [];

    try {
        cookiesList = cookiesListRaw ? JSON.parse(cookiesListRaw) : [];
    } catch (e) {
        console.log("CookiesJD JSON 解析失败，将初始化为新数组");
        cookiesList = [];
    }

    let index = cookiesList.findIndex(item => item.userName === pt_pin);
    if (index !== -1) {
        if (cookiesList[index].cookie !== newCookie) {
            cookiesList[index].cookie = newCookie;
            console.log(`更新已有账号 [${pt_pin}] 的 Cookie`);
        } else {
            console.log(`账号 [${pt_pin}] Cookie 无变动`);
        }
    } else {
        cookiesList.push({
            userName: pt_pin,
            cookie: newCookie
        });
        console.log(`新增账号 [${pt_pin}]`);
    }

    console.log(`Cookie 内容：${newCookie}`);

    let writeSuccess = $persistentStore.write(JSON.stringify(cookiesList), "CookiesJD");
    if (writeSuccess) {
        console.log("✅ 成功写入 CookiesJD 至 BoxJS");
    } else {
        console.log("❌ 写入 CookiesJD 失败");
    }

    // ==================== 功能2: 提交到API服务器（新功能）====================
    submitToAPI(newCookie, pt_pin);

} else {
    let errMsg = "无法提取 pt_pin 或 pt_key。请确认请求头中包含有效的京东 Cookie。";
    console.log(errMsg);
    if (typeof $notify !== 'undefined') {
        $notify("Cookie 错误", "", errMsg);
    } else if (typeof $notification !== 'undefined') {
        $notification.post("Cookie 错误", "", errMsg);
    }
    $done({});
}

// ==================== 提交到API服务器 ====================
function submitToAPI(cookie, pt_pin) {
    const requestBody = cookie;

    const options = {
        url: API_URL,
        headers: {
            'Content-Type': 'text/plain'
        },
        body: JSON.stringify(requestBody)
    };

    console.log(`🚀 正在提交到API服务器: ${API_URL}`);

    $httpClient.post(options, function(error, response, data) {
        if (error) {
            console.log(`❌ API提交失败: ${error}`);
            notifyResult(pt_pin, false, `网络错误: ${error}`);
        } else {
            try {
                const result = data;
                
                if (result.includes("ok,") {
                    console.log(`✅ API提交成功`);
                    notifyResult(pt_pin, true, "成功");
                } else {
                    console.log(`❌ API提交失败`);
                    notifyResult(pt_pin, false, "失败");
                }
            } catch (e) {
                console.log(`❌ 解析API返回失败: ${e}`);
                notifyResult(pt_pin, false, "解析返回数据失败");
            }
        }
        $done({});
    });
}

// ==================== 通知 ====================
function notifyResult(pt_pin, success, message) {
    let title = success ? "京东Cookie提交成功 ✅" : "京东Cookie提交失败 ❌";
    let subtitle = `账号: ${pt_pin}`;
    let body = message;

    if (typeof $notify !== 'undefined') {
        $notify(title, subtitle, body);
    } else if (typeof $notification !== 'undefined') {
        $notification.post(title, subtitle, body);
    }
}
