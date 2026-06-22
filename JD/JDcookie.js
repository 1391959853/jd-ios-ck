/**
 * 京东Cookie和wskey获取并自动提交到API服务器
 * 修改：去除本地Cookie存储，使用 pin_hash ↔ pt_pin 映射配对，映射固定不更新
 * 修复：反向映射必须 pin_hash 非空（防止 undefined 误匹配）
版本:9.4（重构版）
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

function getPinMap() {
    let raw = $prefs.valueForKey("JD_PinMap");
    return raw ? JSON.parse(raw) : {};
}
function savePinMap(map) {
    $prefs.setValueForKey(JSON.stringify(map), "JD_PinMap");
}

function establishMappingIfAbsent(pin_hash, pt_pin) {
    if (!pin_hash || !pt_pin) return false;
    let pinMap = getPinMap();
    let revMap = {};
    for (let ph in pinMap) {
        revMap[pinMap[ph]] = ph;
    }
    if (pinMap[pin_hash] || revMap[pt_pin]) {
        return false;
    }
    pinMap[pin_hash] = pt_pin;
    savePinMap(pinMap);
    console.log(`🔗 首次建立映射: pin_hash(${pin_hash}) -> pt_pin(${pt_pin})，已固化`);
    return true;
}

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
        let revMap = {};
        for (let ph in pinMap) {
            revMap[pinMap[ph]] = ph;
        }

        while (wskeyQueue.length > 0 && ptkeyQueue.length > 0) {
            let wskeyItem = wskeyQueue[0];
            let ptkeyItem = ptkeyQueue[0];
            let { wskey, pin_hash } = wskeyItem;
            let { pt_pin, pt_key } = ptkeyItem;

            console.log(`🔄 尝试配对: pin_hash:${pin_hash} <-> pt_pin:${pt_pin}`);

            let matched = false;

            if (pin_hash && pinMap[pin_hash] === pt_pin) {
                matched = true;
            }
            else if (pin_hash && pt_pin && revMap[pt_pin] === pin_hash) {
                matched = true;
            }
            else if (pin_hash && pt_pin && 
                     !pinMap[pin_hash] && !revMap[pt_pin] &&
                     Math.abs(wskeyItem.timestamp - ptkeyItem.timestamp) <= 10) {
                if (establishMappingIfAbsent(pin_hash, pt_pin)) {
                    matched = true;
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
            combineAndSubmit(pt_pin, pt_key, wskey);

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

function combineAndSubmit(pt_pin, pt_key, wskey) {
    if (!pt_pin || !pt_key || !wskey) {
        console.log(`❌ 提交被阻止：pt_pin="${pt_pin}", pt_key="${pt_key}", wskey="${wskey}" 存在空值`);
        return;
    }

    let newCookie = `pt_key=${pt_key};pt_pin=${pt_pin};`;
    if (wskey) newCookie += ` wskey=${wskey};`;
    console.log(`✅ 成功匹配！组合后的 cookie: ${newCookie.substring(0, 80)}...`);

    pendingAsyncTasks++;
    submitToAPI(pt_pin, pt_key, wskey, newCookie);
    sendLocalNotification("京东Cookie获取成功", `账号: ${pt_pin}`, "已成功获取并提交Cookie和wskey");
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