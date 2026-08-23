#!/bin/bash
# ============================================
#   Psyduck 全自动部署脚本（重构版）
#   版本：9.32
#   功能：
#         - 修复 Docker 安装脚本下载失败问题（增加重试与备用源）
#         - 移除用户组权限设置（按用户要求）
#         - 保持原有顺序，Docker 加速器检查在安装前
#         - 修复：Docker 未安装时不执行重启
#         - 优化 APT 源备份与更新，兼容 Debian/Ubuntu 新旧版本
#         - 仅在需要构建镜像时测速 Alpine 源
#         - 部署完成后自动重启所有非 SSH 容器
#         - 快速检查使用临时容器测试 /ipv6 端点
#         - SOCKS5 镜像改用 gost + frp（账户可配置）
#         - SOCKS5 镜像构建自适应架构（amd64/arm64/armv7）
#         - 针对 armv7/arm64 自动使用 ubuntu-ports 源（阿里云）
#         - 前置代理测速：下载 50MB 文件，每个代理最多 5 秒
#         - 代理测速仅首次部署和 --debug 时执行
#         - 所有 GitHub 下载统一使用最优代理
#         - 重构：.sources 格式仅替换域名保留路径
#         - 重构：git clone/pull 增加 3 分钟超时与重试
#         - 重构：网卡检测仅认可四大运营商公网 IPv6 前缀（240e/2408/2409/240a）
#         - 重构：docker network rm 增加 -f 强制删除
#         - 重构：quick_check 修复流程增加删除 SOCKS5 容器
#         - 重构：DEBUG 模式预先清理非 SSH 容器
#         - 重构：select_deployment_mode 先检测可用网卡，仅一个时自动单网口
#         - 修复：test_proxies 进度条显示
#         - 修复：所有 bc 依赖替换为 awk
#         - 修复：get_physical_ifaces 同时支持 IPv4/IPv6
#         - 修复：build_socks5_image 不再依赖宿主机发行版
#   使用：sudo ./frp-psyduck.sh [--debug|--check]
# ============================================
set -euo pipefail

# ---------- 颜色与日志 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()    { echo -e "${CYAN}[STEP]${NC} $1"; }

# ---------- 全局变量 ----------
DEPLOY_FLAG="/opt/psyduck/.deployed"
CONFIG_DIR="/opt/psyduck"
CONFIG_FILE="${CONFIG_DIR}/psyduck.conf"
SCRIPT_PATH="/usr/local/bin/psyduck_maintenance.sh"
DEFAULT_SERVER_ADDR="1.sggg3326.top"
DEFAULT_SERVER_PORT=7000
DEFAULT_TOKEN="a1391959853-a1391959853"
DEBUG_MODE=false
CHECK_MODE=false
BINARY_PATTERN=""
IPV6_PREFIX_BASE="fdfa"
FASTEST_ALPINE_MIRROR="mirrors.aliyun.com"

# ---------- GitHub 前置代理列表 ----------
PROXY_LIST=(
    "https://gh-proxy.com/"
    "https://ghproxy.net/"
    "https://ghp.ci/"
    "https://moeyy.cn/gh-proxy/"
    "https://ghproxy.homeboyc.cn/"
    "https://v6.gh-proxy.org/"
    "https://gh.zwy.one/"
    "https://gh.llkk.cc/"
    "https://githubproxy.cc/"
    "https://ghfast.top/"
    "https://gh.api.99988866.xyz/"
    "https://gitproxy.click/"
    "https://hub.gitmirror.com/"
    "https://gh.ddlc.top/"
)

# ---------- SOCKS5 配置变量 ----------
SOCKS5_USER="xiaoz"
SOCKS5_PASS="a1391959853"
FRP_VERSION="0.70.1"
GOST_VERSION="2.12.0"

# ---------- 全局代理前缀（由 test_proxies 设置） ----------
GITHUB_PROXY_PREFIX=""

[ "$EUID" -ne 0 ] && { log_error "请使用 root 权限"; exit 1; }

# ==================== 1. 检测系统架构 ====================
detect_arch() {
    local arch=$(uname -m)
    case "$arch" in
        x86_64)  BINARY_PATTERN="*x86_64*|*amd64*" ;;
        aarch64|arm64) BINARY_PATTERN="*aarch64*|*arm64*" ;;
        armv7l|armv8l) BINARY_PATTERN="*armv7*|*arm*" ;;
        i386|i686) BINARY_PATTERN="*i386*|*386*" ;;
        *) log_error "不支持架构 $arch"; exit 1 ;;
    esac
    log_info "系统架构: $arch, 匹配模式: $BINARY_PATTERN"
}

# ==================== 2. 代理速度测试 ====================
test_proxies() {
    log_step "正在测试 GitHub 代理速度（共 ${#PROXY_LIST[@]} 个，每个最多 5 秒）..."

    local -A speeds
    local total=${#PROXY_LIST[@]}
    local index=0
    local TEST_URL="https://github.com/docker/docker-ce/releases/download/v26.1.4/docker-ce_26.1.4-1_amd64.deb"

    for proxy in "${PROXY_LIST[@]}"; do
        index=$((index + 1))
        echo -e "\n[INFO] 测试代理 ${index}/${total} ..."

        local speed=$(curl --max-time 5 --progress-bar -o /dev/null -w "%{speed_download}" "${proxy}${TEST_URL}")

        if [ -z "$speed" ] || [ "$speed" = "0" ] || [ "$speed" -lt 1024 ]; then
            echo "[WARNING] 失败"
            speeds["$proxy"]=0
        else
            if [ "$speed" -ge 1048576 ]; then
                local speed_show=$(awk "BEGIN {printf \"%.2f\", $speed/1048576}")
                echo "[SUCCESS] 速度: ${speed_show} MB/s"
            else
                local speed_show=$(awk "BEGIN {printf \"%.2f\", $speed/1024}")
                echo "[SUCCESS] 速度: ${speed_show} KB/s"
            fi
            speeds["$proxy"]=$speed
        fi
    done

    echo ""
    local best=""
    local best_speed=0
    for proxy in "${!speeds[@]}"; do
        if [ "${speeds[$proxy]}" -gt "$best_speed" ]; then
            best_speed=${speeds[$proxy]}
            best="$proxy"
        fi
    done

    if [ -z "$best" ]; then
        log_warning "所有代理均不可用，将使用直连"
        GITHUB_PROXY_PREFIX=""
    else
        GITHUB_PROXY_PREFIX="$best"
        if [ "$best_speed" -ge 1048576 ]; then
            local best_show=$(awk "BEGIN {printf \"%.2f\", $best_speed/1048576}")
            log_success "已选择最快代理（速度 ${best_show} MB/s）"
        else
            local best_show=$(awk "BEGIN {printf \"%.2f\", $best_speed/1024}")
            if [ "$best_speed" -lt 512000 ]; then
                log_warning "最快代理速度仅 ${best_show} KB/s，低于 500 KB/s，下载可能较慢"
            else
                log_success "已选择最快代理（速度 ${best_show} KB/s）"
            fi
        fi
        log_info "所有后续 GitHub 下载将使用此代理"
    fi
}

# ==================== 3. APT 源检测与替换（宿主机） ====================
get_distro_info() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO_ID="$ID"
        DISTRO_CODENAME="$VERSION_CODENAME"
        if [ -z "$DISTRO_CODENAME" ]; then
            if [[ "$VERSION" =~ \([a-z]+\) ]]; then
                DISTRO_CODENAME="${BASH_REMATCH[1]}"
            else
                case "$ID" in
                    debian)
                        DISTRO_CODENAME=$(echo "$VERSION" | awk '{print $1}' | tr -d '()')
                        ;;
                    ubuntu)
                        DISTRO_CODENAME=$(echo "$VERSION" | awk '{print $2}' | tr -d '()')
                        ;;
                esac
            fi
        fi
    elif [ -f /etc/lsb-release ]; then
        . /etc/lsb-release
        DISTRO_ID="$DISTRIB_ID"
        DISTRO_CODENAME="$DISTRIB_CODENAME"
    else
        log_error "无法识别系统发行版"
        exit 1
    fi
    DISTRO_ID=$(echo "$DISTRO_ID" | tr '[:upper:]' '[:lower:]')
    DISTRO_CODENAME=$(echo "$DISTRO_CODENAME" | tr '[:upper:]' '[:lower:]')
    log_info "检测到发行版: $DISTRO_ID, 代号: $DISTRO_CODENAME"
}

check_and_set_mirrors() {
    log_step "检测并设置 APT 镜像源（兼容新旧系统）..."
    get_distro_info

    local china_mirrors="mirrors.(aliyun|tencent|tuna|ustc|163)"
    if grep -qE "$china_mirrors" /etc/apt/sources.list 2>/dev/null || \
       grep -qE "$china_mirrors" /etc/apt/sources.list.d/*.sources 2>/dev/null; then
        log_success "APT 源已为国内镜像，跳过替换"
        return
    fi

    local mirror="mirrors.aliyun.com"
    log_info "替换 APT 源为 $mirror"
    local timestamp=$(date +%Y%m%d%H%M%S)
    local backup_dir="/etc/apt/backup_$timestamp"
    mkdir -p "$backup_dir"
    cp -a /etc/apt/sources.list* "$backup_dir/" 2>/dev/null || true
    log_info "已备份 APT 源文件到 $backup_dir"

    local new_sources=""
    case "$DISTRO_ID" in
        debian)
            if [ -z "$DISTRO_CODENAME" ]; then
                DISTRO_CODENAME="bookworm"
                log_warning "无法获取 Debian 代号，默认使用 bookworm"
            fi
            new_sources="deb http://$mirror/debian $DISTRO_CODENAME main contrib non-free
deb http://$mirror/debian $DISTRO_CODENAME-updates main contrib non-free
deb http://security.debian.org/debian-security $DISTRO_CODENAME-security main contrib non-free"
            ;;
        ubuntu)
            if [ -z "$DISTRO_CODENAME" ]; then
                DISTRO_CODENAME="jammy"
                log_warning "无法获取 Ubuntu 代号，默认使用 jammy"
            fi
            new_sources="deb http://$mirror/ubuntu $DISTRO_CODENAME main restricted universe multiverse
deb http://$mirror/ubuntu $DISTRO_CODENAME-updates main restricted universe multiverse
deb http://$mirror/ubuntu $DISTRO_CODENAME-backports main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu $DISTRO_CODENAME-security main restricted universe multiverse"
            ;;
        *)
            new_sources="deb http://$mirror/debian bookworm main contrib non-free
deb http://$mirror/debian bookworm-updates main contrib non-free
deb http://security.debian.org/debian-security bookworm-security main contrib non-free"
            log_warning "未知发行版 $DISTRO_ID，使用 Debian bookworm 配置"
            ;;
    esac

    if [ -f /etc/apt/sources.list.d/debian.sources ] || [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then
        for f in /etc/apt/sources.list.d/*.sources; do
            if [ -f "$f" ]; then
                sed -i "s#URIs: https\?://[^/]*/#URIs: http://$mirror/#g" "$f"
                log_success "已修改 $f"
            fi
        done
        log_info "系统使用 .sources 格式，不创建传统 sources.list"
    else
        echo "$new_sources" > /etc/apt/sources.list
        log_success "已创建 sources.list"
    fi

    apt-get update
    log_success "APT 源更新完成"
}

# ==================== 4. Docker 镜像加速检查 ====================
check_docker_mirror() {
    log_step "检查 Docker 镜像加速器..."
    local daemon="/etc/docker/daemon.json"
    if [ -f "$daemon" ] && grep -q "docker.1ms.run" "$daemon"; then
        log_success "Docker 加速器已存在"
        return
    fi
    
    mkdir -p /etc/docker
    echo '{"registry-mirrors": ["https://docker.1ms.run"]}' > "$daemon"
    log_success "Docker 加速器配置已写入"
    
    if command -v docker &>/dev/null; then
        log_info "Docker 已安装，重启 Docker 使配置生效"
        systemctl restart docker
    else
        log_info "Docker 尚未安装，配置将在安装 Docker 后生效"
    fi
}

# ==================== 5. Alpine 镜像源测速 ====================
test_alpine_mirrors() {
    log_step "测速 Alpine 镜像源（使用 frp 包索引）..."
    local arch=$(uname -m)
    local alpine_arch=""
    case "$arch" in
        x86_64)  alpine_arch="x86_64" ;;
        aarch64|arm64) alpine_arch="aarch64" ;;
        armv7l|armv8l) alpine_arch="armv7" ;;
        i386|i686) alpine_arch="x86" ;;
        *) alpine_arch="x86_64" ;;
    esac
    local mirrors=(
        "mirrors.aliyun.com"
        "mirrors.ustc.edu.cn"
        "mirrors.tuna.tsinghua.edu.cn"
        "mirrors.cloud.tencent.com"
        "mirrors.163.com"
    )
    local test_file="alpine/v3.19/main/${alpine_arch}/APKINDEX.tar.gz"
    local best_speed=0
    local best_mirror="mirrors.aliyun.com"
    
    for mirror in "${mirrors[@]}"; do
        local url="http://${mirror}/${test_file}"
        log_info "测试 $mirror ..."
        local speed=$(curl -4 -L --connect-timeout 3 --max-time 10 -o /dev/null -w "%{speed_download}" "$url" 2>/dev/null)
        if [ -n "$speed" ] && [ "$speed" != "0" ]; then
            local speed_kbs=$(awk "BEGIN {printf \"%.2f\", $speed/1024}")
            log_info "  速度: ${speed_kbs} KB/s"
            if [ "$speed" -gt "$best_speed" ]; then
                best_speed=$speed
                best_mirror=$mirror
            fi
        else
            log_warning "  测试失败"
        fi
        sleep 0.5
    done
    
    FASTEST_ALPINE_MIRROR="$best_mirror"
    log_success "选择最快的 Alpine 镜像源: $FASTEST_ALPINE_MIRROR (速度 $((best_speed / 1024)) KB/s)"
}

# ==================== 6. 安装 Docker ====================
install_docker() {
    if command -v docker &>/dev/null; then
        log_success "Docker 已安装: $(docker --version)"
        return
    fi
    log_info "安装 Docker（使用阿里云镜像）..."
    
    local tmp_script=$(mktemp)
    local success=false
    for i in {1..3}; do
        log_info "尝试下载安装脚本 (第 $i 次)..."
        if curl -fsSL --retry 3 --connect-timeout 10 "https://get.docker.com" -o "$tmp_script"; then
            success=true
            break
        fi
        log_warning "下载失败，等待 3 秒后重试..."
        sleep 3
    done
    
    if [ "$success" = false ]; then
        log_error "下载 Docker 安装脚本失败，请检查网络或手动安装 Docker。"
        exit 1
    fi
    
    sh "$tmp_script" --mirror Aliyun
    local install_status=$?
    rm -f "$tmp_script"
    
    if [ $install_status -ne 0 ]; then
        log_error "Docker 安装失败，请手动安装"
        exit 1
    fi
    
    systemctl enable --now docker 2>/dev/null || true
    
    if [ -f /etc/docker/daemon.json ] && grep -q "docker.1ms.run" /etc/docker/daemon.json; then
        systemctl restart docker
        log_info "Docker 已安装，重启使其使用镜像加速"
    fi
    
    log_success "Docker 安装完成"
}

# ==================== 7. 安装 Git ====================
install_git() {
    if command -v git &>/dev/null; then
        log_success "Git 已安装: $(git --version)"
        return
    fi
    apt-get install -y git
}

# ==================== 8. 克隆仓库与构建主镜像 ====================
clone_and_build_main() {
    local repo="https://github.com/xoyoxoyo/relayApi.git"
    
    if [ -d relayApi ]; then
        log_info "更新仓库..."
        cd relayApi
        if [ -n "$GITHUB_PROXY_PREFIX" ]; then
            if ! timeout 180 git -c url."${GITHUB_PROXY_PREFIX}https://github.com/".insteadOf="https://github.com/" pull; then
                log_warning "代理 git pull 超时，等待 3 秒后重试..."
                sleep 3
                if ! timeout 180 git -c url."${GITHUB_PROXY_PREFIX}https://github.com/".insteadOf="https://github.com/" pull; then
                    log_error "git pull 再次超时，退出"
                    exit 1
                fi
            fi
        else
            if ! timeout 180 git pull; then
                log_warning "git pull 超时，等待 3 秒后重试..."
                sleep 3
                if ! timeout 180 git pull; then
                    log_error "git pull 再次超时，退出"
                    exit 1
                fi
            fi
        fi
        cd ..
    else
        log_info "克隆仓库（3分钟超时）..."
        if [ -n "$GITHUB_PROXY_PREFIX" ]; then
            if ! timeout 180 git -c url."${GITHUB_PROXY_PREFIX}https://github.com/".insteadOf="https://github.com/" clone "$repo" relayApi; then
                log_warning "代理克隆失败，尝试直连..."
                timeout 180 git clone "$repo" relayApi || { log_error "克隆失败"; exit 1; }
            fi
        else
            timeout 180 git clone "$repo" relayApi || { log_error "克隆失败"; exit 1; }
        fi
    fi
    
    cd relayApi
    if [ -f "psyduck" ] && [ -x "psyduck" ]; then
        log_success "psyduck 二进制已存在，跳过查找"
    else
        log_info "查找匹配的二进制文件..."
        local bin=""
        local patterns=($(echo "$BINARY_PATTERN" | tr '|' ' '))
        for p in "${patterns[@]}"; do
            bin=$(find . -type f -name "$p" | head -1)
            [ -n "$bin" ] && break
        done
        if [ -z "$bin" ]; then
            bin=$(find . -type f -name "psyduck-*" | head -1)
        fi
        [ -z "$bin" ] && { log_error "未找到匹配的二进制文件"; ls -la .; exit 1; }
        mv "$bin" psyduck && chmod +x psyduck
        log_success "二进制文件已重命名为 psyduck"
    fi
    if ! docker images --format "{{.Repository}}" | grep -q "^psyduck$"; then
        log_info "构建主镜像..."
        docker build -t psyduck .
    else
        log_success "主镜像已存在"
    fi
    cd ..
}

# ==================== 9. 构建 SOCKS5 镜像（仅根据架构决定源） ====================
build_socks5_image() {
    if docker images --format "{{.Repository}}" | grep -q "^psyduck-socks5$"; then
        log_success "SOCKS5 镜像已存在，无需构建"
        return
    fi

    local arch=$(uname -m)
    local frp_arch=""
    local gost_arch=""
    local apt_source=""

    case "$arch" in
        x86_64)
            frp_arch="amd64"
            gost_arch="amd64"
            apt_source='RUN sed -i "s#http://archive.ubuntu.com/ubuntu/#http://mirrors.aliyun.com/ubuntu/#g" /etc/apt/sources.list'
            ;;
        aarch64|arm64)
            frp_arch="arm64"
            gost_arch="arm64"
            apt_source='RUN sed -i "s#http://archive.ubuntu.com/ubuntu/#http://mirrors.aliyun.com/ubuntu-ports/#g" /etc/apt/sources.list'
            ;;
        armv7l|armv8l)
            frp_arch="arm"
            gost_arch="armv7"
            apt_source='RUN sed -i "s#http://archive.ubuntu.com/ubuntu/#http://mirrors.aliyun.com/ubuntu-ports/#g" /etc/apt/sources.list'
            ;;
        *)
            log_error "不支持的架构: $arch"
            exit 1
            ;;
    esac

    log_info "检测到架构: $arch, frp 包后缀: $frp_arch, gost 包后缀: $gost_arch"
    log_info "构建 SOCKS5 镜像（gost + frp）"

    local tmpd=$(mktemp -d)
    cd "$tmpd"

    cat > Dockerfile <<EOF
FROM ubuntu:22.04

$apt_source

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y curl && \
    apt-get clean

ARG GITHUB_PROXY_PREFIX
ARG FRP_ARCH
ARG GOST_ARCH

ENV GITHUB_PROXY_PREFIX=\${GITHUB_PROXY_PREFIX}
ENV FRP_ARCH=\${FRP_ARCH}
ENV GOST_ARCH=\${GOST_ARCH}
ENV SOCKS_USER=$SOCKS5_USER
ENV SOCKS_PASS=$SOCKS5_PASS
ENV FRP_VERSION=$FRP_VERSION
ENV GOST_VERSION=$GOST_VERSION

RUN if [ -n "\$GITHUB_PROXY_PREFIX" ]; then \
        FRP_URL="\${GITHUB_PROXY_PREFIX}https://github.com/fatedier/frp/releases/download/v\${FRP_VERSION}/frp_\${FRP_VERSION}_linux_\${FRP_ARCH}.tar.gz"; \
        GOST_URL="\${GITHUB_PROXY_PREFIX}https://github.com/ginuerzh/gost/releases/download/v\${GOST_VERSION}/gost_\${GOST_VERSION}_linux_\${GOST_ARCH}.tar.gz"; \
    else \
        FRP_URL="https://github.com/fatedier/frp/releases/download/v\${FRP_VERSION}/frp_\${FRP_VERSION}_linux_\${FRP_ARCH}.tar.gz"; \
        GOST_URL="https://github.com/ginuerzh/gost/releases/download/v\${GOST_VERSION}/gost_\${GOST_VERSION}_linux_\${GOST_ARCH}.tar.gz"; \
    fi && \
    curl -L --retry 5 --retry-delay 5 "\$FRP_URL" | tar xz -C /tmp && \
    mv /tmp/frp_*/frpc /usr/local/bin/ && \
    chmod +x /usr/local/bin/frpc && \
    curl -L --retry 5 --retry-delay 5 "\$GOST_URL" | tar xz -C /tmp && \
    find /tmp -name "gost*" -exec mv {} /usr/local/bin/gost \; && \
    chmod +x /usr/local/bin/gost

RUN printf '#!/bin/bash\n/usr/local/bin/gost -L "socks5://\${SOCKS_USER}:\${SOCKS_PASS}@:2233" &\nsleep 2\nexec /usr/local/bin/frpc -c /app/frpc.ini\n' > /start.sh && \
    chmod +x /start.sh

EXPOSE 2233
CMD ["/start.sh"]
EOF

    docker build \
        --build-arg GITHUB_PROXY_PREFIX="${GITHUB_PROXY_PREFIX}" \
        --build-arg FRP_ARCH="${frp_arch}" \
        --build-arg GOST_ARCH="${gost_arch}" \
        -t psyduck-socks5 .
    
    cd / && rm -rf "$tmpd"
    log_success "SOCKS5 镜像构建完成"
}
# ==================== 10. 构建 SSH 镜像 ====================
build_ssh_image() {
    if docker images --format "{{.Repository}}" | grep -q "^psyduck-ssh$"; then
        log_success "SSH 镜像已存在"
        return
    fi
    log_info "构建 SSH 镜像（使用 ${FASTEST_ALPINE_MIRROR}）..."
    local tmpd=$(mktemp -d)
    cd "$tmpd"
    cat > Dockerfile <<EOF
FROM alpine:latest
RUN sed -i 's/dl-cdn.alpinelinux.org/${FASTEST_ALPINE_MIRROR}/g' /etc/apk/repositories && \\
    apk add --no-cache frp
WORKDIR /app
COPY entrypoint.sh ./
CMD ["/app/entrypoint.sh"]
EOF
    cat > entrypoint.sh <<'EOF'
#!/bin/sh
exec /usr/bin/frpc -c /app/frpc.ini
EOF
    chmod +x entrypoint.sh
    docker build -t psyduck-ssh .
    cd / && rm -rf "$tmpd"
}

# ==================== 11. 网卡探测与 macvlan 网络创建 ====================
get_physical_ifaces() {
    local ifaces=()
    for i in $(ls /sys/class/net/ | grep -vE 'lo|docker|br-|veth'); do
        [ -e "/sys/class/net/$i/device" ] && ip addr show "$i" &>/dev/null && ifaces+=("$i")
    done
    echo "${ifaces[@]}"
}

get_iface_info() {
    local iface=$1
    local ip=$(ip -4 addr show "$iface" | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
    local subnet=$(echo "$ip" | awk -F. '{print $1"."$2"."$3".0/24"}')
    local gw=$(ip route | grep "default" | grep "$iface" | awk '{print $3}')
    [ -z "$gw" ] && gw=$(echo "$ip" | awk -F. '{print $1"."$2"."$3".1"}')
    echo "$ip|$subnet|$gw"
}

create_macvlan_network() {
    local net_name=$1
    local iface=$2
    local subnet=$3
    local gw=$4
    local ipv6_prefix=$5
    if [[ "$ipv6_prefix" =~ : ]]; then
        ipv6_prefix=$(echo "$ipv6_prefix" | cut -d':' -f1-2 | tr -d ':')
        log_warning "修正 IPv6 前缀为 $ipv6_prefix"
    fi
    docker network rm -f "$net_name" 2>/dev/null || true
    docker network create -d macvlan \
        --subnet="$subnet" \
        --gateway="$gw" \
        --ipv6 \
        --subnet="${ipv6_prefix}:5a35:6fce::/64" \
        -o parent="$iface" \
        "$net_name"
    log_success "创建网络 $net_name (IPv6 ${ipv6_prefix}:5a35:6fce::/64)"
}

# ==================== 12. 部署主容器 ====================
deploy_main_container() {
    local net_name=$1
    local remote_port=$2
    local gw=$3
    local container_name="psyduck${remote_port}"
    [ "$DEBUG_MODE" = true ] && docker rm -f "$container_name" 2>/dev/null || true
    if ! docker ps -a --format '{{.Names}}' | grep -qx "$container_name"; then
        local tmp="/tmp/frpc_${remote_port}.ini"
        cat > "$tmp" <<EOF
[common]
server_addr = $DEFAULT_SERVER_ADDR
token = $DEFAULT_TOKEN
server_port = $DEFAULT_SERVER_PORT
[${container_name}]
type = tcp
local_ip = 127.0.0.1
local_port = 24678
remote_port = $remote_port
EOF
        docker run -d \
            --name "$container_name" \
            --restart=always \
            --privileged \
            --network "$net_name" \
            -e GATEWAY="$gw" \
            psyduck
        sleep 2
        docker cp "$tmp" "$container_name:/root/frpc.ini"
        docker restart "$container_name"
        rm -f "$tmp"
        log_success "主容器 $container_name 部署成功"
    else
        log_info "主容器 $container_name 已存在，启动..."
        docker start "$container_name" 2>/dev/null || true
    fi
    local c_gw=$(docker exec "$container_name" ip route show default 2>/dev/null | awk '{print $3}')
    if [ -n "$c_gw" ] && [ "$c_gw" != "$gw" ]; then
        log_warning "容器 $container_name 路由 $c_gw 与预期 $gw 不一致，修复中..."
        docker exec "$container_name" ip route del default 2>/dev/null || true
        docker exec "$container_name" ip route add default via "$gw" 2>/dev/null || {
            log_error "修复失败，重建容器"
            docker rm -f "$container_name"
            local tmp="/tmp/frpc_${remote_port}.ini"
            cat > "$tmp" <<EOF
[common]
server_addr = $DEFAULT_SERVER_ADDR
token = $DEFAULT_TOKEN
server_port = $DEFAULT_SERVER_PORT
[${container_name}]
type = tcp
local_ip = 127.0.0.1
local_port = 24678
remote_port = $remote_port
EOF
            docker run -d \
                --name "$container_name" \
                --restart=always \
                --privileged \
                --network "$net_name" \
                -e GATEWAY="$gw" \
                psyduck
            sleep 2
            docker cp "$tmp" "$container_name:/root/frpc.ini"
            docker restart "$container_name"
            rm -f "$tmp"
        }
    fi
}

# ==================== 13. 部署 SOCKS5 容器 ====================
deploy_socks5_container() {
    local net_name=$1
    local remote_port=$2
    local socks5_port=$3
    local iface=$4
    local container_name="psyduck${remote_port}-socks5"
    local workdir="/opt/psyduck-socks5-${iface}"
    
    if ! docker images --format "{{.Repository}}" | grep -q "^psyduck-socks5$"; then
        log_warning "SOCKS5 镜像缺失，正在构建..."
        build_socks5_image
    fi
    
    docker rm -f "$container_name" 2>/dev/null || true
    rm -rf "$workdir" && mkdir -p "$workdir"
    
    cat > "$workdir/frpc.ini" <<EOF
[common]
server_addr = $DEFAULT_SERVER_ADDR
server_port = $DEFAULT_SERVER_PORT
token = $DEFAULT_TOKEN
tls_enable = true
[${container_name}]
type = tcp
local_ip = 127.0.0.1
local_port = 2233
remote_port = $socks5_port
use_encryption = true
use_compression = true
EOF

    docker run -d \
        --name "$container_name" \
        --restart always \
        --network "$net_name" \
        -v "$workdir/frpc.ini:/app/frpc.ini:ro" \
        --add-host host.docker.internal:host-gateway \
        -e TZ=Asia/Shanghai \
        psyduck-socks5
    
    log_success "SOCKS5 容器 $container_name 部署成功（gost + frp）"
}

# ==================== 14. 部署 SSH 容器 ====================
deploy_ssh_container() {
    local remote_ports=("$@")
    local port_str=$(printf "%s-" "${remote_ports[@]}"); port_str=${port_str%-}
    local container_name="psyduck-ssh-${port_str}"
    [ ${#remote_ports[@]} -eq 1 ] && container_name="psyduck-ssh-${remote_ports[0]}"
    local workdir="/opt/psyduck-ssh"
    if [ "$DEBUG_MODE" = true ]; then
        if docker ps -a --format '{{.Names}}' | grep -qx "$container_name"; then
            log_info "调试模式：保留 SSH 容器 $container_name"
        else
            docker rm -f "$container_name" 2>/dev/null || true
        fi
    fi
    if ! docker ps -a --format '{{.Names}}' | grep -qx "$container_name"; then
        mkdir -p "$workdir"
        cat > "$workdir/entrypoint.sh" <<'EOF'
#!/bin/sh
exec /usr/bin/frpc -c /app/frpc.ini
EOF
        chmod +x "$workdir/entrypoint.sh"
        cat > "$workdir/frpc.ini" <<EOF
[common]
server_addr = $DEFAULT_SERVER_ADDR
server_port = $DEFAULT_SERVER_PORT
token = $DEFAULT_TOKEN
tls_enable = true
[${container_name}]
type = tcp
local_ip = host.docker.internal
local_port = 22
remote_port = 0
use_encryption = true
use_compression = true
EOF
        cat > "$workdir/Dockerfile" <<EOF
FROM alpine:latest
RUN sed -i 's/dl-cdn.alpinelinux.org/${FASTEST_ALPINE_MIRROR}/g' /etc/apk/repositories && \\
    apk add --no-cache frp
WORKDIR /app
COPY entrypoint.sh ./
CMD ["/app/entrypoint.sh"]
EOF
        docker build -t psyduck-ssh "$workdir"
        docker run -d \
            --name "$container_name" \
            --restart always \
            --network bridge \
            -v "$workdir/frpc.ini:/app/frpc.ini:ro" \
            --add-host host.docker.internal:host-gateway \
            -e TZ=Asia/Shanghai \
            psyduck-ssh
        log_success "SSH 容器 $container_name 部署成功"
    else
        log_info "SSH 容器 $container_name 已存在，启动..."
        docker start "$container_name" 2>/dev/null || true
        if ! grep -q "server_addr = $DEFAULT_SERVER_ADDR" "$workdir/frpc.ini" 2>/dev/null; then
            log_info "更新 SSH 配置..."
            cat > "$workdir/frpc.ini" <<EOF
[common]
server_addr = $DEFAULT_SERVER_ADDR
server_port = $DEFAULT_SERVER_PORT
token = $DEFAULT_TOKEN
tls_enable = true
[${container_name}]
type = tcp
local_ip = host.docker.internal
local_port = 22
remote_port = 0
use_encryption = true
use_compression = true
EOF
            docker cp "$workdir/frpc.ini" "$container_name:/app/frpc.ini"
            docker restart "$container_name"
        fi
    fi
    sleep 2
    local remote_port=$(docker logs "$container_name" 2>&1 | grep -oP "\[$container_name\] .*?remote port: \K\d+" | head -1)
    if [ -n "$remote_port" ]; then
        sed -i "s/^SSH_REMOTE_PORT=.*/SSH_REMOTE_PORT=$remote_port/" "$CONFIG_FILE" 2>/dev/null || echo "SSH_REMOTE_PORT=$remote_port" >> "$CONFIG_FILE"
        log_success "SSH 远程端口: $remote_port"
    else
        log_warning "未获取 SSH 远程端口"
    fi
}

# ==================== 15. IPv6 网卡检测函数 ====================
check_iface_ipv6() {
    local iface=$1
    local addrs=$(ip -6 addr show "$iface" | grep -oP '(?<=inet6\s)[a-f0-9:]+' | grep -v '^fe80')
    [ -z "$addrs" ] && return 1

    local public_addr=""
    for addr in $addrs; do
        case "$addr" in
            240e:*|2408:*|2409:*|240a:*) public_addr="$addr"; break ;;
        esac
    done
    [ -z "$public_addr" ] && return 1

    for host in sggg3326.top ipv6.nucdn.co test6.ustc.edu.cn 6.ipw.cn ipv6.test-ipv6.com; do
        ping -6 -c 1 -W 2 -I "$iface" "$host" &>/dev/null && return 0
    done
    ping -6 -c 1 -W 2 -I "$iface" 2001:4860:4860::8888 &>/dev/null && return 0
    ping -6 -c 1 -W 2 -I "$iface" 2606:4700:4700::1111 &>/dev/null && return 0
    return 1
}

# ==================== 16. 核心交互与配置 ====================
select_deployment_mode() {
    local all=($(get_physical_ifaces))
    if [ ${#all[@]} -eq 0 ]; then
        log_error "未找到物理网卡"
        exit 1
    fi

    local online=()
    for i in "${all[@]}"; do
        if check_iface_ipv6 "$i"; then
            online+=("$i")
            log_success "网卡 $i IPv6 连通性正常"
        else
            log_warning "网卡 $i IPv6 不可用"
        fi
    done

    if [ ${#online[@]} -eq 0 ]; then
        log_error "无可用 IPv6 网卡"
        exit 1
    elif [ ${#online[@]} -eq 1 ]; then
        DEPLOY_MODE="single"
        SELECTED_INTERFACES=("${online[0]}")
        log_info "仅一个网卡可通过 IPv6 测试，自动单网口模式，使用 ${online[0]}"
        return
    else
        echo -e "${CYAN}检测到多个可用 IPv6 网卡，请选择部署模式：\n  1) 单网口\n  2) 多网口${NC}"
        read -p "请输入 1 或 2 [默认1]: " choice
        if [[ "$choice" == "2" ]]; then
            DEPLOY_MODE="multi"
            echo -e "${CYAN}可用 IPv6 网卡："
            for i in "${!online[@]}"; do echo "  $((i+1))) ${online[$i]}"; done
            read -p "选择编号（如 1 2 3 或 all）: " sel
            if [ "$sel" = "all" ]; then
                SELECTED_INTERFACES=("${online[@]}")
            else
                SELECTED_INTERFACES=()
                for n in $sel; do
                    [ "$n" -ge 1 ] && [ "$n" -le ${#online[@]} ] && SELECTED_INTERFACES+=("${online[$((n-1))]}")
                done
            fi
            [ ${#SELECTED_INTERFACES[@]} -eq 0 ] && { log_error "无效选择"; exit 1; }
            log_success "已选: ${SELECTED_INTERFACES[*]}"
        else
            DEPLOY_MODE="single"
            SELECTED_INTERFACES=("${online[0]}")
            log_info "单网口模式，使用 ${online[0]}"
        fi
    fi
}

configure_ports() {
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
        [ -n "${REMOTE_PORTS:-}" ] && return
    fi
    if [ "$DEPLOY_MODE" = "single" ]; then
        read -p "主容器端口: " p; REMOTE_PORTS=($p)
        read -p "SOCKS5 端口: " s; SOCKS5_PORTS=($s)
    else
        REMOTE_PORTS=(); SOCKS5_PORTS=()
        for i in "${!SELECTED_INTERFACES[@]}"; do
            echo "为 ${SELECTED_INTERFACES[$i]} 设置端口"
            read -p "主容器端口: " p; REMOTE_PORTS+=($p)
            read -p "SOCKS5 端口: " s; SOCKS5_PORTS+=($s)
        done
    fi
}

detect_and_save_config() {
    mkdir -p "$CONFIG_DIR"
    local net_entries=()
    if [ "$DEPLOY_MODE" = "single" ]; then
        local iface="${SELECTED_INTERFACES[0]}"
        local info=($(get_iface_info "$iface" | tr '|' ' '))
        local subnet="${info[1]}"; local gw="${info[2]}"
        local ipv6_prefix="$IPV6_PREFIX_BASE"
        net_entries=("psyduck|$iface|$subnet|$gw|${REMOTE_PORTS[0]}|${SOCKS5_PORTS[0]}|$ipv6_prefix")
    else
        for idx in "${!SELECTED_INTERFACES[@]}"; do
            local iface="${SELECTED_INTERFACES[$idx]}"
            local info=($(get_iface_info "$iface" | tr '|' ' '))
            local subnet="${info[1]}"; local gw="${info[2]}"
            local net_name="psyduck"; [ $idx -ne 0 ] && net_name="psyduck$idx"
            local prefix_hex=$(printf "%x" $((0x${IPV6_PREFIX_BASE:3} + idx)))
            local ipv6_prefix="${IPV6_PREFIX_BASE:0:3}${prefix_hex}"
            net_entries+=("$net_name|$iface|$subnet|$gw|${REMOTE_PORTS[$idx]}|${SOCKS5_PORTS[$idx]}|$ipv6_prefix")
        done
    fi
    cat > "$CONFIG_FILE" <<EOF
DEPLOY_MODE="$DEPLOY_MODE"
REMOTE_PORTS=(${REMOTE_PORTS[@]})
SOCKS5_PORTS=(${SOCKS5_PORTS[@]})
SERVER_ADDR="$DEFAULT_SERVER_ADDR"
SERVER_PORT=$DEFAULT_SERVER_PORT
TOKEN="$DEFAULT_TOKEN"
SSH_REMOTE_PORT=""
NETWORKS=(
$(printf '  "%s"\n' "${net_entries[@]}")
)
EOF
    log_success "配置已保存"
}

# ==================== 17. 主部署流程 ====================
deploy_all() {
    if [ "$DEBUG_MODE" = true ]; then
        log_warning "调试模式：清理所有非 SSH 的现有 psyduck 容器..."
        for c in $(docker ps -a --format '{{.Names}}' | grep -E '^psyduck' | grep -v 'psyduck-ssh'); do
            docker rm -f "$c" 2>/dev/null || true
        done
    fi

    log_step "开始完整部署"
    check_and_set_mirrors
    check_docker_mirror
    install_docker
    install_git
    clone_and_build_main
    
    local need_build=false
    if ! docker images --format "{{.Repository}}" | grep -q "^psyduck-socks5$"; then
        need_build=true
    fi
    if ! docker images --format "{{.Repository}}" | grep -q "^psyduck-ssh$"; then
        need_build=true
    fi
    if [ "$need_build" = true ]; then
        test_alpine_mirrors
    else
        log_info "SOCKS5 和 SSH 镜像均已存在，跳过 Alpine 源测速"
    fi
    
    build_socks5_image
    build_ssh_image
    
    select_deployment_mode
    configure_ports
    detect_and_save_config
    source "$CONFIG_FILE"

    for entry in "${NETWORKS[@]}"; do
        IFS='|' read -r net_name iface subnet gw rport sport ipv6_prefix <<< "$entry"
        create_macvlan_network "$net_name" "$iface" "$subnet" "$gw" "$ipv6_prefix"
        deploy_main_container "$net_name" "$rport" "$gw"
        deploy_socks5_container "$net_name" "$rport" "$sport" "$iface"
    done

    deploy_ssh_container "${REMOTE_PORTS[@]}"

    log_step "重启所有非 SSH 容器以确保配置生效..."
    local restart_list=$(docker ps -a --format '{{.Names}}' | grep -E '^psyduck' | grep -v 'psyduck-ssh')
    if [ -n "$restart_list" ]; then
        for c in $restart_list; do
            if docker restart "$c" &>/dev/null; then
                log_info "已重启 $c"
            else
                log_warning "重启 $c 失败"
            fi
        done
    else
        log_info "无需重启的容器"
    fi

    generate_maintenance_script
    setup_systemd_timer
    setup_autostart
    touch "$DEPLOY_FLAG"
    log_success "部署完成"
}

# ==================== 18. 快速检查模式 ====================
quick_check() {
    log_step "快速检查模式：使用临时容器测试 /ipv6 端点"
    if [ ! -f "$CONFIG_FILE" ]; then
        log_error "配置文件不存在，请先部署"
        exit 1
    fi
    source "$CONFIG_FILE"

    # 确保 alpine 镜像存在
    if ! docker image inspect alpine &>/dev/null; then
        log_info "拉取 alpine 基础镜像..."
        docker pull alpine
    fi

    for entry in "${NETWORKS[@]}"; do
        IFS='|' read -r net_name iface subnet gw rport sport ipv6_prefix <<< "$entry"
        container="psyduck${rport}"
        socks5_container="psyduck${rport}-socks5"
        
        log_info "检查容器 $container ..."
        docker restart "$container" 2>/dev/null || {
            log_warning "容器 $container 不存在，重新部署"
            create_macvlan_network "$net_name" "$iface" "$subnet" "$gw" "$ipv6_prefix"
            deploy_main_container "$net_name" "$rport" "$gw"
        }

        local container_ipv4=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$container" 2>/dev/null)
        local test_passed=false
        
        if [ -n "$container_ipv4" ]; then
            if docker run --rm --network "$net_name" alpine sh -c "wget -q -O- http://$container_ipv4:24678/ipv6" &>/dev/null; then
                log_success "容器 $container /ipv6 端点 (IPv4) 可达"
                test_passed=true
            else
                log_warning "容器 $container /ipv6 端点 (IPv4) 不可达"
            fi
        fi

        if [ "$test_passed" = false ]; then
            local container_ipv6=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.GlobalIPv6Address}}{{end}}' "$container" 2>/dev/null)
            if [ -n "$container_ipv6" ]; then
                if docker run --rm --network "$net_name" alpine sh -c "wget -q -O- http://[$container_ipv6]:24678/ipv6" &>/dev/null; then
                    log_success "容器 $container /ipv6 端点 (IPv6) 可达"
                    test_passed=true
                else
                    log_warning "容器 $container /ipv6 端点 (IPv6) 不可达"
                fi
            fi
        fi

        if [ "$test_passed" = false ]; then
            log_warning "容器 $container /ipv6 端点不可达，执行修复（删除容器并重建网络）..."
            
            docker rm -f "$container" 2>/dev/null || true
            docker rm -f "$socks5_container" 2>/dev/null || true
            log_info "已删除容器: $container, $socks5_container"
            
            create_macvlan_network "$net_name" "$iface" "$subnet" "$gw" "$ipv6_prefix"
            
            deploy_main_container "$net_name" "$rport" "$gw"
            deploy_socks5_container "$net_name" "$rport" "$sport" "$iface"
            
            container_ipv4=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$container" 2>/dev/null)
            if [ -n "$container_ipv4" ] && docker run --rm --network "$net_name" alpine sh -c "wget -q -O- http://$container_ipv4:24678/ipv6" &>/dev/null; then
                log_success "修复后容器 $container /ipv6 端点可达"
            else
                log_error "修复后仍不可达，请手动检查"
            fi
        fi
    done

    for c in $(docker ps -a --format '{{.Names}}' | grep -E 'psyduck[0-9]+-socks5|psyduck-ssh'); do
        docker restart "$c" 2>/dev/null
    done
    log_success "快速检查完成"
}

# ==================== 19. 维护脚本生成 ====================
generate_maintenance_script() {
    cat > "$SCRIPT_PATH" <<'EOF'
#!/bin/bash
LOG="/var/log/psyduck_maintenance.log"
echo "$(date) 开始维护重启" >> "$LOG"
for c in $(docker ps -a --format '{{.Names}}' | grep -E '^psyduck'); do
    docker restart "$c" >> "$LOG" 2>&1
done
echo "$(date) 维护完成" >> "$LOG"
EOF
    chmod +x "$SCRIPT_PATH"
    log_success "维护脚本生成（每天3点重启所有容器）"
}

# ==================== 20. systemd timer 设置 ====================
setup_systemd_timer() {
    local service_name="psyduck-maintenance.service"
    local timer_name="psyduck-maintenance.timer"
    local service_file="/etc/systemd/system/${service_name}"
    local timer_file="/etc/systemd/system/${timer_name}"

    cat > "$service_file" <<EOF
[Unit]
Description=Psyduck Container Maintenance
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=${SCRIPT_PATH}
EOF

    cat > "$timer_file" <<EOF
[Unit]
Description=Run Psyduck maintenance daily at 03:00
Requires=${service_name}

[Timer]
OnCalendar=daily
OnCalendar=03:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable "$timer_name"
    systemctl start "$timer_name"
    log_success "systemd timer 已启用（每天 03:00 执行）"
}

# ==================== 21. 开机自启 ====================
setup_autostart() {
    local f="/etc/systemd/system/psyduck-boot.service"
    cat > "$f" <<EOF
[Unit]
Description=Psyduck Boot Check
After=network.target docker.service
Requires=docker.service
[Service]
Type=oneshot
ExecStart=$(realpath "$0") --check
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable psyduck-boot.service 2>/dev/null || true
    log_success "开机自启已配置"
}

# ==================== 命令行参数处理 ====================
while [[ $# -gt 0 ]]; do
    case "$1" in
        --debug) DEBUG_MODE=true ;;
        --check) CHECK_MODE=true ;;
    esac
    shift
done

# ==================== 主入口 ====================
main() {
    if [ "$CHECK_MODE" = true ]; then
        quick_check
        exit 0
    fi

    detect_arch

    if [ "$DEBUG_MODE" = true ]; then
        log_warning "调试模式：将重新部署所有容器（SSH 容器会保留）"
        test_proxies
        deploy_all
        exit 0
    fi

    if [ -f "$DEPLOY_FLAG" ]; then
        quick_check
    else
        log_info "首次部署，正在测试代理速度..."
        test_proxies
        deploy_all
    fi
}

main "$@"
