/**
 * 京东Cookie获取并自动提交到API服务器（优化版：变化检测）
 * 功能：
 * 1. 保存到 BoxJS 的 CookiesJD（原功能）
 * 2. 只有Cookie真正变化时才提交到远程API服务器
 * 2026年2月5日更新
 *v2.12
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

    // 1. 保存到BoxJS，并获取保存结果（是否发生变化）
    let saveResult = saveToBoxJS(pt_pin, newCookie);
    
    // 2. 只有Cookie发生变化时，才提交到远程API
    if (saveResult.changed) {
        console.log(`检测到Cookie变化，准备提交到远程API`);
        submitToAPI(pt_pin, pt_key, newCookie, saveResult.changeType);
    } else {
        console.log(`Cookie无变化，跳过远程API提交`);
        notifyResult(pt_pin, false, "本地Cookie无变化，未提交远程");
        $done({});
    }
} else {
    console.log("无法提取 pt_pin 或 pt_key");
    $done({});
}

// 保存到 BoxJS（QX 版本）
// 返回一个对象，包含是否发生变化和变化类型
function saveToBoxJS(pt_pin, newCookie) {
    let result = {
        changed: false,
        changeType: "none", // "none", "updated", "added"
        oldCookie: null
    };
    
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
                    // 记录旧Cookie
                    result.oldCookie = cookiesList[i].cookie;
                    // 更新为新Cookie
                    cookiesList[i].cookie = newCookie;
                    result.changed = true;
                    result.changeType = "updated";
                    console.log(`账号 ${pt_pin} 的 Cookie 已更新`);
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
            result.changed = true;
            result.changeType = "added";
            console.log(`新增账号 ${pt_pin}`);
        }

        // 只有在发生变化时才写入存储
        if (result.changed) {
            // QX 使用 $prefs.setValueForKey
            let success = $prefs.setValueForKey(JSON.stringify(cookiesList), "CookiesJD");
            if (success) {
                console.log("✅ 成功写入 CookiesJD 至 BoxJS (QX)");
            } else {
                console.log("❌ 写入 CookiesJD 失败");
            }
        }
        
        return result;
    } catch (e) {
        console.log("处理 BoxJS 时出错: " + e);
        return result;
    }
}

// 提交到 API（QX 版本）- 增加changeType参数
function submitToAPI(pt_pin, pt_key, cookie, changeType) {
    console.log(`检测到变化类型: ${changeType}，正在提交到 API: ${API_URL}`);

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
                        
                        // 在成功消息中添加变化类型
                        resultMessage = `${changeType === "added" ? "新增账号" : "更新Cookie"} - ${resultMessage}`;

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