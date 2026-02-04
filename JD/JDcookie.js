/**
 * 京东Cookie获取并自动提交到API服务器（修复版：严格变化检测）
 * 功能：
 * 1. 保存到 BoxJS 的 CookiesJD（原功能）
 * 2. 只有Cookie真正变化时才提交到远程API服务器
 * 3. 无论是否有变化都发送QX通知
 * 日期：2026年2月5日（修复版本）
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
    let newCookie = `pt_key=${pt_key};pt_pin=${pt_pin};`;

    console.log(`提取到的 pt_pin: ${pt_pin}`);
    console.log(`提取到的 pt_key: ${pt_key}`);

    // 1. 检查Cookie是否有变化
    let changeResult = checkCookieChange(pt_pin, newCookie);
    
    // 2. 无论是否有变化都保存到BoxJS并发送通知
    saveToBoxJS(pt_pin, newCookie, changeResult.changeType);
    
    // 3. 根据变化结果决定是否提交到API
    if (changeResult.changed) {
        console.log(`检测到Cookie变化，类型: ${changeResult.changeType}`);
        
        // 提交到远程API
        submitToAPI(pt_pin, pt_key, newCookie, changeResult.changeType);
    } else {
        console.log(`Cookie无变化，跳过远程API提交`);
        // 发送无变化通知
        sendNoChangeNotification(pt_pin);
        $done({});
    }
} else {
    console.log("无法提取 pt_pin 或 pt_key");
    $done({});
}

// 检查Cookie是否有变化
function checkCookieChange(pt_pin, newCookie) {
    let result = {
        changed: false,
        changeType: "none" // "none", "updated", "added"
    };
    
    try {
        // 获取现有的Cookies列表
        let cookiesListRaw = $prefs.valueForKey("CookiesJD");
        if (!cookiesListRaw) {
            // 如果没有任何存储，说明是新增
            result.changed = true;
            result.changeType = "added";
            console.log("首次使用，检测为新账号");
            return result;
        }
        
        let cookiesList;
        try {
            cookiesList = JSON.parse(cookiesListRaw);
        } catch (e) {
            console.log("解析 CookiesJD 失败，视为新账号");
            result.changed = true;
            result.changeType = "added";
            return result;
        }
        
        // 查找现有账号
        for (let i = 0; i < cookiesList.length; i++) {
            if (cookiesList[i].userName === pt_pin) {
                // 找到账号，比较Cookie
                if (cookiesList[i].cookie !== newCookie) {
                    result.changed = true;
                    result.changeType = "updated";
                    console.log(`账号 ${pt_pin} 的 Cookie 有变化`);
                } else {
                    console.log(`账号 ${pt_pin} 的 Cookie 无变化`);
                }
                return result;
            }
        }
        
        // 没找到账号，说明是新增
        result.changed = true;
        result.changeType = "added";
        console.log(`新增账号: ${pt_pin}`);
        return result;
        
    } catch (e) {
        console.log("检查Cookie变化时出错: " + e);
        // 出错时保守起见，视为有变化
        result.changed = true;
        result.changeType = "updated";
        return result;
    }
}

// 保存到 BoxJS（QX 版本）- 无论变化都保存
function saveToBoxJS(pt_pin, newCookie, changeType) {
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
                cookiesList[i].cookie = newCookie;
                found = true;
                console.log(`更新账号 ${pt_pin} 的 Cookie`);
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
            console.log(`✅ 成功保存 Cookie 至 BoxJS (${changeType})`);
            return true;
        } else {
            console.log("❌ 写入 CookiesJD 失败");
            return false;
        }
    } catch (e) {
        console.log("保存到 BoxJS 时出错: " + e);
        return false;
    }
}

// 提交到 API（QX 版本）
function submitToAPI(pt_pin, pt_key, cookie, changeType) {
    console.log(`正在提交到 API: ${API_URL} (${changeType})`);

    // 根据您的 API 代码，尝试不同的数据格式
    const formatTests = [
        {
            name: "格式1: JSON对象包含pt_key和pt_pin",
            body: JSON.stringify({
                pt_key: pt_key,
                pt_pin: pt_pin,
                change_type: changeType // 添加变化类型，便于服务器识别
            }),
            headers: {
                'Content-Type': 'application/json'
            }
        },
        {
            name: "格式2: JSON对象包含cookie字段",
            body: JSON.stringify({
                cookie: cookie,
                change_type: changeType
            }),
            headers: {
                'Content-Type': 'application/json'
            }
        },
        {
            name: "格式3: 纯JSON字符串",
            body: JSON.stringify({
                cookie: cookie,
                change_type: changeType
            }),
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

    // 测试第一种格式（JSON对象）
    testFormat(0);

    function testFormat(index) {
        if (index >= formatTests.length) {
            console.log("所有格式测试失败");
            notifyResult(pt_pin, false, "所有格式测试失败", changeType);
            $done({});
            return;
        }

        const test = formatTests[index];
        console.log(`\n尝试 ${test.name}`);

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
                        
                        // 在成功消息中添加变化类型
                        const changeText = changeType === "added" ? "新增账号" : "更新Cookie";
                        resultMessage = `${changeText} - ${resultMessage}`;

                        notifyResult(pt_pin, true, resultMessage, changeType);
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

// 发送无变化通知（QX 版本）
function sendNoChangeNotification(pt_pin) {
    let title = "🔵 京东Cookie无变化";
    let subtitle = "账号: " + pt_pin;
    let body = "本地Cookie与上次相同，未提交到远程服务器";

    console.log(`${title} - ${subtitle} - ${body}`);

    // Quantumult X 使用 $notify
    if (typeof $notify !== 'undefined') {
        $notify(title, subtitle, body);
    }
}

// 发送变化结果通知（QX 版本）- 只在提交到API时调用
function notifyResult(pt_pin, success, message, changeType) {
    let title = success ? "✅ 京东Cookie提交成功" : "❌ 京东Cookie提交失败";
    let subtitle = "账号: " + pt_pin;
    let body = message;

    console.log(`${title} - ${subtitle} - ${body}`);

    // Quantumult X 使用 $notify
    if (typeof $notify !== 'undefined') {
        $notify(title, subtitle, body);
    }
}
