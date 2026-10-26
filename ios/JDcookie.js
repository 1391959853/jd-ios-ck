/**
 * 京东Cookie和wskey获取并自动提交到API服务器 (极速防死锁最终版)
 * 1. 废除时间差限制。
 * 2. 绝对串行提交防并发。
 * 3. 入队去重覆盖，队列存活时间 10 秒。
 * 4. 队首不匹配自动丢弃较旧项，彻底防死锁。
 * 5. 服务端校验失败，强制删除本地映射。
 * 6. 原版弹窗格式，保留 pt_pin URL 编码。
 */

const API_URL = "http://nezha.sggg3326.top:9090/jd/raw_ck";

// ================= 全局防并发锁 =================
let isProcessing = false;

// ================= 抓包拦截与解析 =================
let cookie = $request.headers['Cookie'] || $request.headers['cookie'] || '';
let requestUrl = $request.url || '';
let bodyStr = $request.body || '';
let host = $request.headers['Host'] || '';
let currentTimestamp = Math.floor(Date.now() / 1000);
let currentTime = new Date().toISOString();

try {
    console.log(`请求时间: ${currentTime}`);
    console.log(`时间戳: ${currentTimestamp}`);
    console.log(`Host: ${host}`);
    console.log(`请求URL: ${requestUrl.substring(0, 80)}...`);

    let ptPinMatch = cookie.match(/pt_pin=([^; ]+)(?=;?)/);
    let ptKeyMatch = cookie.match(/pt_key=([^; ]+)(?=;?)/);
    let wskeyMatch = cookie.match(/wskey=([^; ]+)(?=;?)/);
    
    let pinHashMatch = cookie.match(/pin_hash=([^; ]+)(?=;?)/) 
                    || requestUrl.match(/pin_hash=([^&]+)/) 
                    || bodyStr.match(/pin_hash=([^&]+)/) 
                    || bodyStr.match(/"pin_hash":"([^"]+)"/);

    let pt_pin = ptPinMatch ? decodeURIComponent(ptPinMatch[1]) : '';
    let pt_key = ptKeyMatch ? ptKeyMatch[1] : '';
    let wskey = wskeyMatch ? wskeyMatch[1] : '';
    let pin_hash = pinHashMatch ? pinHashMatch[1] : '';

    let isWskeyRequest = !!wskey;
    let isPtKeyRequest = !!(pt_key && pt_pin);

    if (isWskeyRequest) {
        console.log(`✅ 检测到 wskey 请求，加入队列`);
        handleWskeyRequest(wskey, pin_hash, currentTimestamp);
    } else if (isPtKeyRequest) {
        console.log(`✅ 检测到 pt_key 请求，加入队列`);
        handlePtKeyRequest(pt_pin, pt_key, currentTimestamp);
    } else {
        console.log(`❌ 非目标请求或Cookie不完整，跳过处理`);
        $done({});
    }
} catch (e) {
    console.log("脚本初始化异常: " + e);
    $done({});
}

// ========== 映射表操作 ==========
function getPinMap() {
    let raw = $prefs.valueForKey("JD_PinMap");
    return raw ? JSON.parse(raw) : {};
}

function savePinMap(map) {
    $prefs.setValueForKey(JSON.stringify(map), "JD_PinMap");
}

function establishOrUpdateMapping(pin_hash, pt_pin) {
    if (!pin_hash || !pt_pin) return false;
    let pinMap = getPinMap();
    let existing = pinMap[pin_hash];

    if (existing) {
        if (existing.pt_pin === pt_pin) return true;
        if (existing.verified) {
            console.log(`映射已存在且已验证，冲突跳过: ${pin_hash} -> ${existing.pt_pin}`);
            return false;
        } else {
            console.log(`覆盖未验证映射: ${pin_hash} -> ${pt_pin}`);
            pinMap[pin_hash] = { pt_pin: pt_pin, verified: false };
            savePinMap(pinMap);
            return true;
        }
    } else {
        console.log(`建立未验证映射: ${pin_hash} -> ${pt_pin}`);
        pinMap[pin_hash] = { pt_pin: pt_pin, verified: false };
        savePinMap(pinMap);
        return true;
    }
}

function markMappingVerified(pin_hash) {
    if (!pin_hash) return;
    let pinMap = getPinMap();
    if (pinMap[pin_hash] && !pinMap[pin_hash].verified) {
        pinMap[pin_hash].verified = true;
        savePinMap(pinMap);
        console.log(`映射标记为已验证: ${pin_hash}`);
    }
}

// ========== 队列操作（极速过期版） ==========
function getWskeyQueue() { return JSON.parse($prefs.valueForKey("JD_Wskey_Queue") || "[]"); }
function saveWskeyQueue(q) { $prefs.setValueForKey(JSON.stringify(q), "JD_Wskey_Queue"); }
function getPtKeyQueue() { return JSON.parse($prefs.valueForKey("JD_PtKey_Queue") || "[]"); }
function savePtKeyQueue(q) { $prefs.setValueForKey(JSON.stringify(q), "JD_PtKey_Queue"); }

function handleWskeyRequest(wskey, pin_hash, timestamp) {
    let queue = getWskeyQueue();
    
    // 覆盖旧的
    let existingIndex = queue.findIndex(item => item.pin_hash === pin_hash);
    if (existingIndex !== -1) {
        console.log(`🔄 覆盖队列中旧的 wskey (pin_hash: ${pin_hash})`);
        queue.splice(existingIndex, 1);
    }

    queue.push({ wskey, pin_hash, timestamp });
    // 【修改点】：存活时间 10 秒
    saveWskeyQueue(queue.filter(item => (timestamp - item.timestamp) <= 10));
    tryMatch();
}

function handlePtKeyRequest(pt_pin, pt_key, timestamp) {
    let queue = getPtKeyQueue();
    
    // 覆盖旧的
    let existingIndex = queue.findIndex(item => item.pt_pin === pt_pin);
    if (existingIndex !== -1) {
        console.log(`🔄 覆盖队列中旧的 pt_key (pt_pin: ${pt_pin})`);
        queue.splice(existingIndex, 1);
    }

    queue.push({ pt_pin, pt_key, timestamp });
    // 【修改点】：存活时间 10 秒
    savePtKeyQueue(queue.filter(item => (timestamp - item.timestamp) <= 10));
    tryMatch();
}

// ========== 核心：绝对串行配对与提交（极速防死锁版） ==========
function tryMatch() {
    if (isProcessing) {
        console.log(`⏳ 正在处理上一批提交，请稍候...`);
        return;
    }

    let wskeyQueue = getWskeyQueue();
    let ptkeyQueue = getPtKeyQueue();

    if (wskeyQueue.length === 0 || ptkeyQueue.length === 0) {
        $done({});
        return;
    }

    let matched = false;
    let pinMap = getPinMap();
    
    let wskeyItem = wskeyQueue[0];
    let ptkeyItem = ptkeyQueue[0];
    let { wskey, pin_hash } = wskeyItem;
    let { pt_pin, pt_key } = ptkeyItem;

    console.log(`🔄 尝试配对: pin_hash:${pin_hash} <-> pt_pin:${pt_pin}`);

    if (pin_hash && pinMap[pin_hash] && pinMap[pin_hash].verified && pinMap[pin_hash].pt_pin === pt_pin) {
        matched = true;
        console.log(`使用已验证映射配对成功`);
    } else if (pin_hash && pt_pin) {
        if (establishOrUpdateMapping(pin_hash, pt_pin)) {
            matched = true;
            console.log(`废除时间差，无条件配对成功`);
        }
    }

    if (!matched) {
        // 队首对不上，立刻淘汰旧的
        if (ptkeyItem.timestamp <= wskeyItem.timestamp) {
            console.log(`⚠️ 队首配对失败，丢弃较旧的 pt_key (账号: ${pt_pin})`);
            ptkeyQueue.shift();
            savePtKeyQueue(ptkeyQueue);
        } else {
            console.log(`⚠️ 队首配对失败，丢弃较旧的 wskey (pin_hash: ${pin_hash})`);
            wskeyQueue.shift();
            saveWskeyQueue(wskeyQueue);
        }
        tryMatch(); 
        return;
    }

    // 配对成功，出队
    wskeyQueue.shift();
    ptkeyQueue.shift();
    saveWskeyQueue(wskeyQueue);
    savePtKeyQueue(ptkeyQueue);

    // 【修改点】：防重时间同步缩短为 10 秒
    if (checkIfProcessed(pt_pin, pt_key, wskey)) {
        console.log(`🔵 该组合已处理过，丢弃队列头部`);
        tryMatch();
        return;
    }
    recordProcessed(pt_pin, pt_key, wskey);

    isProcessing = true;
    combineAndSubmit(pt_pin, pt_key, wskey, pin_hash);
}

// ========== 防重记录 ==========
function checkIfProcessed(pt_pin, pt_key, wskey) {
    try {
        let raw = $prefs.valueForKey("JD_Processed_Records");
        if (!raw) return false;
        let data = JSON.parse(raw);
        let key = generateRecordKey(pt_pin, pt_key, wskey);
        let record = data[key];
        let now = Math.floor(Date.now() / 1000);
        // 【修改点】：10 秒内不重复提交
        return record && (now - record.timestamp) < 10;
    } catch (e) { return false; }
}

function recordProcessed(pt_pin, pt_key, wskey) {
    try {
        let raw = $prefs.valueForKey("JD_Processed_Records");
        let data = raw ? JSON.parse(raw) : {};
        let key = generateRecordKey(pt_pin, pt_key, wskey);
        data[key] = { timestamp: Math.floor(Date.now() / 1000), requestTime: new Date().toISOString() };
        let keys = Object.keys(data);
        if (keys.length > 20) {
            let oldest = keys[0];
            for (let k of keys) if (data[k].timestamp < data[oldest].timestamp) oldest = k;
            delete data[oldest];
        }
        $prefs.setValueForKey(JSON.stringify(data), "JD_Processed_Records");
    } catch (e) {}
}

function generateRecordKey(pt_pin, pt_key, wskey) {
    let hash = 0;
    let str = pt_key.substring(0, 16) + wskey.substring(0, 16);
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash = hash & hash;
    }
    return pt_pin + "_" + hash.toString(36);
}

// ========== 通知与提交 ==========
function sendLocalNotification(title, subtitle, message) {
    console.log(`🔵 ${title} - ${subtitle} - ${message}`);
    if (typeof $notify !== 'undefined') {
        $notify(`🔵 ${title}`, subtitle, message);
    }
}

function combineAndSubmit(pt_pin, pt_key, wskey, pin_hash) {
    if (!pt_pin || !pt_key || !wskey) {
        console.log(`❌ 提交被阻止：pt_pin="${pt_pin}", pt_key="${pt_key}", wskey="${wskey}" 存在空值`);
        isProcessing = false;
        tryMatch();
        return;
    }

    let newCookie = `pt_key=${pt_key};pt_pin=${pt_pin};`;
    if (wskey) newCookie += ` wskey=${wskey};`;
    
    console.log(`❚  🚀 准备提交 -> pt_pin: ${pt_pin}, pt_key: ${pt_key.substring(0,10)}..., wskey: ${wskey.substring(0,10)}...`);
    console.log(`✅ 成功匹配！组合后的 cookie: ${newCookie.substring(0, 80)}...`);

    sendLocalNotification("京东Cookie获取成功", `账号: ${pt_pin}`, "已成功获取并提交Cookie和wskey");

    submitToAPI(pt_pin, pt_key, wskey, newCookie, pin_hash);
}

function submitToAPI(pt_pin, pt_key, wskey, cookie, pin_hash) {
    console.log(`正在提交到 API: ${API_URL}`);
    const request = {
        url: API_URL,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            pt_key, 
            pt_pin: encodeURIComponent(pt_pin),
            wskey: wskey || '', 
            cookie,
            pin_hash: pin_hash || ''
        }),
        timeout: 10000
    };

    $task.fetch(request).then(
        function(response) {
            let data = response.body || "";
            console.log(`API返回完整内容: ${data}`);

            if (data.startsWith("校验失败，京东账号: ")) {
                let match = data.match(/校验失败，京东账号: (.+)/);
                let failedPin = match ? match[1].trim() : pt_pin;
                console.log(`❌ 服务端校验失败，强制删除本地映射: ${failedPin}`);
                
                removeBindingIfUnverified(failedPin, pin_hash);
                sendLocalNotification("API提交失败", `账号: ${pt_pin}`, data);
            } else if (data.includes("ok")) {
                console.log(`✅ Cookie提交成功`);
                if (pin_hash) markMappingVerified(pin_hash);
                sendLocalNotification("API提交成功", `账号: ${pt_pin}`, data);
            } else {
                console.log(`❌ API返回未知状态: ${data}`);
                sendLocalNotification("API提交失败", `账号: ${pt_pin}`, data);
            }
            
            isProcessing = false;
            tryMatch();
        },
        function(reason) {
            console.log(`❌ API请求异常: ${reason.error || reason}`);
            sendLocalNotification("API提交失败", `账号: ${pt_pin}`, reason.error || "网络错误");
            
            isProcessing = false;
            tryMatch();
        }
    );
}

// ========== 失败清理逻辑 ==========
function removeBindingIfUnverified(pt_pin, pin_hash) {
    if (!pt_pin) return;
    let pinMap = getPinMap();
    let targetHash = pin_hash;

    if (!targetHash) {
        for (let ph in pinMap) {
            if (pinMap[ph].pt_pin === pt_pin) {
                targetHash = ph;
                break;
            }
        }
    }

    if (!targetHash) {
        console.log(`未找到 ${pt_pin} 的绑定关系，无需删除`);
        return;
    }

    if (pinMap[targetHash]) {
        delete pinMap[targetHash];
        savePinMap(pinMap);
        console.log(`✅ 已彻底删除错误映射: ${targetHash} -> ${pt_pin}`);
    }

    let wskeyQueue = getWskeyQueue();
    let wskeyLenBefore = wskeyQueue.length;
    wskeyQueue = wskeyQueue.filter(item => item.pin_hash !== targetHash);
    if (wskeyQueue.length < wskeyLenBefore) {
        saveWskeyQueue(wskeyQueue);
    }

    let ptkeyQueue = getPtKeyQueue();
    let ptkeyLenBefore = ptkeyQueue.length;
    ptkeyQueue = ptkeyQueue.filter(item => item.pt_pin !== pt_pin);
    if (ptkeyQueue.length < ptkeyLenBefore) {
        savePtKeyQueue(ptkeyQueue);
    }
}