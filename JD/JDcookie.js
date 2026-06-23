/**
 * 京东Cookie和wskey获取并自动提交到API服务器
 * 修改：去除本地Cookie存储，使用 pin_hash ↔ pt_pin 映射配对，映射固定不更新
 * 修复：反向映射必须 pin_hash 非空（防止 undefined 误匹配）
 * 版本:9.6（服务端校验状态标记，已验证绑定不可覆盖，未验证可覆盖）
 */

const API_URL = "http://1.sggg3326.top:9090/jd/raw_ck";

let cookie = $request.headers['Cookie'] || $request.headers['cookie'];
let requestUrl = $request.url || '';
let host = $request.headers['Host'] || '';
let currentTimestamp = Math.floor(Date.now() / 1000);
let currentTime = new Date().toISOString();

console.log(`请求时间: ${currentTime}`);
console.log(`时间戳: ${currentTimestamp}`);
console.log(`Host: ${host}`);
console.log(`请求URL: ${requestUrl.substring(0, 80)}...`);

let ptPinMatch = cookie.match(/pt_pin=([^; ]+)(?=;?)/);
let ptKeyMatch = cookie.match(/pt_key=([^; ]+)(?=;?)/);
let wskeyMatch = cookie.match(/wskey=([^; ]+)(?=;?)/);
let pinHashMatch = cookie.match(/pin_hash=([^; ]+)(?=;?)/);

let pt_pin = ptPinMatch ? decodeURIComponent(ptPinMatch[1]) : '';
let pt_key = ptKeyMatch ? ptKeyMatch[1] : '';
let wskey = wskeyMatch ? wskeyMatch[1] : '';
let pin_hash = pinHashMatch ? pinHashMatch[1] : '';

let isWskeyRequest = /sh\.jd\.com/.test(host);
let isPtKeyRequest = /^https?:\/\/api\.m\.jd\.com\/client\.action\?functionId=(wareBusiness|serverConfig|basicConfig)/.test(requestUrl);

let pendingAsyncTasks = 0;

if (isWskeyRequest && wskey) {
    console.log(`✅ 检测到 wskey 请求，wskey: ${wskey.substring(0,15)}...`);
    handleWskeyRequest(wskey, pin_hash, currentTimestamp);
} else if (isPtKeyRequest && pt_pin && pt_key) {
    console.log(`✅ 检测到 pt_key 请求，pt_pin: ${pt_pin}`);
    handlePtKeyRequest(pt_pin, pt_key, currentTimestamp);
} else {
    console.log(`❌ 非目标请求或Cookie不完整，跳过处理`);
    $done({});
}

// ========== 映射表操作 (格式: { pin_hash: { pt_pin: "xxx", verified: true/false } }) ==========
function getPinMap() {
    let raw = $prefs.valueForKey("JD_PinMap");
    return raw ? JSON.parse(raw) : {};
}
function savePinMap(map) {
    $prefs.setValueForKey(JSON.stringify(map), "JD_PinMap");
}

/**
 * 根据 pt_pin 查找对应的 pin_hash (从 PinMap 中反向查找)
 */
function findPinHashByPin(pt_pin) {
    let pinMap = getPinMap();
    for (let ph in pinMap) {
        if (pinMap[ph].pt_pin === pt_pin) {
            return ph;
        }
    }
    return null;
}

/**
 * 建立或更新绑定关系 (仅在未验证时允许覆盖)
 * @returns {boolean} 是否成功建立 (即映射已存在且有效，或新建成功)
 */
function establishOrUpdateMapping(pin_hash, pt_pin) {
    if (!pin_hash || !pt_pin) return false;
    let pinMap = getPinMap();
    let existing = pinMap[pin_hash];

    if (existing) {
        if (existing.verified) {
            // 已验证，不可覆盖，直接返回 true (已存在且可信)
            console.log(`映射已验证，不可覆盖: ${pin_hash} -> ${existing.pt_pin}`);
            return true;
        } else {
            // 未验证，允许覆盖
            console.log(`覆盖未验证映射: ${pin_hash} -> ${pt_pin} (旧: ${existing.pt_pin})`);
            pinMap[pin_hash] = { pt_pin: pt_pin, verified: false };
            savePinMap(pinMap);
            return true;
        }
    } else {
        // 全新映射
        console.log(`建立未验证映射: ${pin_hash} -> ${pt_pin}`);
        pinMap[pin_hash] = { pt_pin: pt_pin, verified: false };
        savePinMap(pinMap);
        return true;
    }
}

/**
 * 将指定 pin_hash 对应的映射标记为已验证 (校验通过后调用)
 */
function markMappingVerified(pin_hash) {
    if (!pin_hash) return;
    let pinMap = getPinMap();
    let entry = pinMap[pin_hash];
    if (entry && !entry.verified) {
        entry.verified = true;
        savePinMap(pinMap);
        console.log(`映射已标记为验证通过: ${pin_hash} -> ${entry.pt_pin}`);
    }
}

// ========== 队列操作 ==========
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

function handleWskeyRequest(wskey, pin_hash, timestamp) {
    try {
        let queue = getWskeyQueue();
        queue.push({ wskey, pin_hash, timestamp });
        let now = Math.floor(Date.now() / 1000);
        queue = cleanExpired(queue, now);
        saveWskeyQueue(queue);
        console.log(`✅ wskey 已加入队列，当前队列长度: ${queue.length}`);
        tryMatch();
    } catch (e) {
        console.log("处理 wskey 失败: " + e);
        $done({});
    }
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
        let pinMap = getPinMap();

        while (wskeyQueue.length > 0 && ptkeyQueue.length > 0) {
            let wskeyItem = wskeyQueue[0];
            let ptkeyItem = ptkeyQueue[0];
            let { wskey, pin_hash } = wskeyItem;
            let { pt_pin, pt_key } = ptkeyItem;

            console.log(`🔄 尝试配对: pin_hash:${pin_hash} <-> pt_pin:${pt_pin}`);

            let matched = false;

            // 优先使用已验证的映射
            if (pin_hash && pinMap[pin_hash] && pinMap[pin_hash].verified && pinMap[pin_hash].pt_pin === pt_pin) {
                matched = true;
                console.log(`使用已验证映射配对: ${pin_hash} -> ${pt_pin}`);
            }
            // 其次使用未验证的映射（包括新建）
            else if (pin_hash && pt_pin) {
                let existing = pinMap[pin_hash];
                if (existing && existing.verified) {
                    // 已验证但 pt_pin 不匹配，不配对
                    console.log(`已验证映射与当前 pt_pin 不一致，跳过`);
                } else {
                    // 未验证或不存在，尝试建立/覆盖
                    if (establishOrUpdateMapping(pin_hash, pt_pin)) {
                        // 检查时间戳差值是否在10秒内（仅未验证时要求）
                        if (Math.abs(wskeyItem.timestamp - ptkeyItem.timestamp) <= 10) {
                            matched = true;
                            console.log(`时间差满足，配对成功`);
                        } else {
                            console.log(`时间差不满足，配对失败`);
                        }
                    }
                }
            }

            if (!matched) {
                console.log(`❌ 配对条件不满足，保留队列`);
                break;
            }

            if (checkIfProcessed(pt_pin, pt_key, wskey)) {
                console.log(`🔵 该组合已处理过，丢弃队列头部`);
                wskeyQueue.shift();
                ptkeyQueue.shift();
                continue;
            }

            recordProcessed(pt_pin, pt_key, wskey);
            combineAndSubmit(pt_pin, pt_key, wskey, pin_hash);

            wskeyQueue.shift();
            ptkeyQueue.shift();
        }

        saveWskeyQueue(wskeyQueue);
        savePtKeyQueue(ptkeyQueue);
    } catch (e) {
        console.log("匹配失败: " + e);
    }
    if (pendingAsyncTasks === 0) {
        $done({});
    }
}

function checkIfProcessed(pt_pin, pt_key, wskey) {
    try {
        let raw = $prefs.valueForKey("JD_Processed_Records");
        if (!raw) return false;
        let data = JSON.parse(raw);
        let key = generateRecordKey(pt_pin, pt_key, wskey);
        let record = data[key];
        let now = Math.floor(Date.now() / 1000);
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

function sendLocalNotification(title, subtitle, message) {
    console.log(`🔵 ${title} - ${subtitle} - ${message}`);
    if (typeof $notify !== 'undefined') {
        $notify(`🔵 ${title}`, subtitle, message);
    }
}

function combineAndSubmit(pt_pin, pt_key, wskey, pin_hash) {
    if (!pt_pin || !pt_key || !wskey) {
        console.log(`❌ 提交被阻止：pt_pin="${pt_pin}", pt_key="${pt_key}", wskey="${wskey}" 存在空值`);
        return;
    }

    let newCookie = `pt_key=${pt_key};pt_pin=${pt_pin};`;
    if (wskey) newCookie += ` wskey=${wskey};`;
    console.log(`✅ 成功匹配！组合后的 cookie: ${newCookie.substring(0, 80)}...`);

    // 提交到API（异步），携带 pin_hash 以便回调时标记验证状态
    pendingAsyncTasks++;
    submitToAPI(pt_pin, pt_key, wskey, newCookie, pin_hash);
    sendLocalNotification("京东Cookie获取成功", `账号: ${pt_pin}`, "已成功获取并提交Cookie和wskey");
}

function submitToAPI(pt_pin, pt_key, wskey, cookie, pin_hash) {
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

            // 检查是否返回“校验失败，京东账号: xxx”
            if (data.startsWith("校验失败，京东账号: ")) {
                let match = data.match(/校验失败，京东账号: (.+)/);
                let failedPin = match ? match[1].trim() : pt_pin;
                console.log(`检测到校验失败，账号: ${failedPin}`);
                // 删除未验证的绑定关系（已验证的不删）
                removeBindingIfUnverified(failedPin, pin_hash);
                pendingAsyncTasks--;
                if (pendingAsyncTasks === 0) $done({});
                return;
            }

            // 校验通过 (服务端返回了同步成功/失败信息，但没有校验失败头)
            // 标记映射为已验证
            if (pin_hash) {
                markMappingVerified(pin_hash);
            }

            // 原有的通知逻辑
            if (data.includes("ok")) {
                console.log(`✅ Cookie提交成功`);
                sendLocalNotification("API提交成功", `账号: ${pt_pin}`, data);
            } else {
                console.log(`❌ API返回失败: ${data}`);
                sendLocalNotification("API提交失败", `账号: ${pt_pin}`, data);
            }
            pendingAsyncTasks--;
            if (pendingAsyncTasks === 0) $done({});
        },
        function(reason) {
            console.log(`API提交失败: ${reason.error || reason}`);
            sendLocalNotification("API提交失败", `账号: ${pt_pin}`, reason.error || "网络错误");
            pendingAsyncTasks--;
            if (pendingAsyncTasks === 0) $done({});
        }
    );
}

/**
 * 仅当绑定关系为“未验证”时才删除，已验证的映射保留。
 */
function removeBindingIfUnverified(pt_pin, pin_hash) {
    if (!pt_pin) return;
    let pinMap = getPinMap();
    let targetHash = pin_hash || findPinHashByPin(pt_pin);
    if (!targetHash) {
        console.log(`未找到 ${pt_pin} 的绑定关系，无需删除`);
        return;
    }

    let entry = pinMap[targetHash];
    if (entry && entry.verified) {
        console.log(`绑定已验证，跳过删除: ${targetHash} -> ${entry.pt_pin}`);
        return;
    }

    // 删除映射
    if (entry) {
        delete pinMap[targetHash];
        savePinMap(pinMap);
        console.log(`已删除未验证映射: ${targetHash} -> ${pt_pin}`);
    }

    // 清理队列
    let wskeyQueue = getWskeyQueue();
    let wskeyLenBefore = wskeyQueue.length;
    wskeyQueue = wskeyQueue.filter(item => item.pin_hash !== targetHash);
    if (wskeyQueue.length < wskeyLenBefore) {
        saveWskeyQueue(wskeyQueue);
        console.log(`已从 wskey 队列中移除 pin_hash: ${targetHash}`);
    }

    let ptkeyQueue = getPtKeyQueue();
    let ptkeyLenBefore = ptkeyQueue.length;
    ptkeyQueue = ptkeyQueue.filter(item => item.pt_pin !== pt_pin);
    if (ptkeyQueue.length < ptkeyLenBefore) {
        savePtKeyQueue(ptkeyQueue);
        console.log(`已从 ptkey 队列中移除 ${pt_pin}`);
    }
}
