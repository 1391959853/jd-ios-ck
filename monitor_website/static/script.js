// 服务监控面板

const CHECK_INTERVAL = 30000;
let autoRefreshTimer = null;

document.addEventListener('DOMContentLoaded', function() {
    loadStatus();
    startAutoRefresh();
});

async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        renderDashboard(data);
    } catch (error) {
        console.error('加载失败:', error);
    }
}

function renderDashboard(data) {
    // 更新时间
    document.getElementById('last-update').textContent = 
        data.last_update || '--';
    
    // 整体状态
    renderOverallStatus(data);
    
    // 目标服务
    renderTargetServices(data.target_services || {});
    
    // 统计信息
    renderStats(data.proxy_groups || {});
    
    // 代理组
    renderProxyGroups(data.proxy_groups || {});
}

function renderOverallStatus(data) {
    const container = document.getElementById('overall-status');
    const title = document.getElementById('overall-title');
    const desc = document.getElementById('overall-desc');
    
    container.className = 'status-card';
    
    const groups = data.proxy_groups || {};
    const totalGroups = Object.keys(groups).length;
    const healthyGroups = Object.values(groups).filter(g => g.health === 'all_online').length;
    
    const services = data.target_services || {};
    const onlineServices = Object.values(services).filter(s => s.status === 'online').length;
    const totalServices = Object.keys(services).length;
    
    switch(data.overall_status) {
        case 'all_online':
            container.classList.add('all-online');
            title.textContent = '全部正常';
            desc.textContent = `${healthyGroups}/${totalGroups} 代理组 · ${onlineServices}/${totalServices} 服务`;
            break;
        case 'partial':
            container.classList.add('partial');
            title.textContent = '部分异常';
            desc.textContent = `${healthyGroups}/${totalGroups} 代理组 · ${onlineServices}/${totalServices} 服务`;
            break;
        case 'all_offline':
            container.classList.add('all-offline');
            title.textContent = '全部异常';
            desc.textContent = '所有服务无法访问';
            break;
        default:
            title.textContent = '初始化中';
            desc.textContent = '正在连接监控服务...';
    }
}

function renderTargetServices(services) {
    const container = document.getElementById('target-services');
    const list = Object.values(services);
    
    if (list.length === 0) {
        container.innerHTML = '';
        return;
    }
    
    container.innerHTML = list.map(s => {
        const online = s.status === 'online';
        const cls = online ? 'online' : 'offline';
        
        return `
            <div class="service-card ${cls}">
                <div class="service-header">
                    <span class="service-name">${s.name}</span>
                    <span class="service-status ${cls}">${online ? '在线' : '离线'}</span>
                </div>
                <div class="service-info">
                    <div><span class="label">响应:</span> ${s.response_time || '-'}ms</div>
                    <div><span class="label">端口:</span> ${s.port}</div>
                    <div><span class="label">检查:</span> ${s.last_check}</div>
                </div>
            </div>
        `;
    }).join('');
}

function renderStats(groups) {
    const ids = Object.keys(groups);
    const total = ids.length;
    const healthy = ids.filter(id => groups[id].health === 'all_online').length;
    
    let main = 0, socks5 = 0, ssh = 0;
    ids.forEach(id => {
        const g = groups[id];
        if (g.main) main++;
        if (g.socks5) socks5++;
        if (g.ssh) ssh++;
    });
    
    document.getElementById('total-groups').textContent = total;
    document.getElementById('healthy-groups').textContent = healthy;
    document.getElementById('main-count').textContent = main;
    document.getElementById('socks5-count').textContent = socks5;
    document.getElementById('ssh-count').textContent = ssh;
    document.getElementById('group-badge').textContent = total;
}

function renderProxyGroups(groups) {
    const container = document.getElementById('proxy-groups');
    const ids = Object.keys(groups).sort();
    
    if (ids.length === 0) {
        container.innerHTML = '';
        return;
    }
    
    container.innerHTML = ids.map(id => {
        const g = groups[id];
        const healthCls = {
            'all_online': 'all-online',
            'partial': 'partial',
            'all_offline': 'all-offline'
        }[g.health] || 'all-offline';
        
        const healthText = {
            'all_online': '正常',
            'partial': '部分',
            'all_offline': '异常'
        }[g.health] || '未知';
        
        return `
            <div class="group-card">
                <div class="group-header">
                    <span class="group-id">组 ${id}</span>
                    <span class="group-health ${healthCls}">${healthText}</span>
                </div>
                <div class="group-services">
                    ${renderService(g.main, '主容器')}
                    ${renderService(g.socks5, 'SOCKS5')}
                    ${renderService(g.ssh, 'SSH')}
                </div>
            </div>
        `;
    }).join('');
}

function renderService(svc, type) {
    if (!svc) return '';
    const online = svc.status === 'online';
    return `
        <div class="group-service">
            <div>
                <span class="service-type">${type}</span>
                <div class="service-detail">${svc.port}</div>
            </div>
            <div>
                <span class="service-status-dot ${online ? 'online' : 'offline'}"></span>
                ${online ? '在线' : '离线'}
            </div>
        </div>
    `;
}

async function manualCheck() {
    const btn = document.getElementById('refresh-btn');
    btn.disabled = true;
    btn.style.opacity = '0.5';
    
    try {
        await fetch('/api/check', { method: 'POST' });
        await loadStatus();
    } catch (e) {
        console.error(e);
    } finally {
        btn.disabled = false;
        btn.style.opacity = '1';
    }
}

function startAutoRefresh() {
    autoRefreshTimer = setInterval(loadStatus, CHECK_INTERVAL);
}

document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        if (autoRefreshTimer) clearInterval(autoRefreshTimer);
    } else {
        startAutoRefresh();
        loadStatus();
    }
});
