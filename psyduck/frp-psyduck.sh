#!/bin/bash
# ============================================
# Psyduck 全自动部署脚本（重构版）
# 版本：10.5
# ============================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
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
DEFAULT_SERVER_ADDR="nezha.sggg3326.top"
DEFAULT_SERVER_PORT=7000
DEFAULT_TOKEN="a1391959853-a1391959853"
DEBUG_MODE=false
CHECK_MODE=false
BINARY_PATTERN=""
IPV6_PREFIX_BASE="fdfa"
FASTEST_ALPINE_MIRROR="mirrors.aliyun.com"

GITHUB_PROXY_PREFIX="https://ghproxy.q114.top/"

SOCKS5_USER="xiaoz"
SOCKS5_PASS="a1391959853"
FRP_VERSION="0.70.1"
GOST_VERSION="3.2.6"

DEPLOY_MODE=""
SELECTED_INTERFACES=()
REMOTE_PORTS=()
SOCKS5_PORTS=()
NETWORKS=()
OLD_NETWORKS=()

[ "$EUID" -ne 0 ] && { log_error "请使用 root 权限"; exit 1; }

# ==================== 工具函数 ====================
detect_arch() {
    local arch=$(uname -m)
    case "$arch" in
        x86_64) BINARY_PATTERN="*x86_64*|*amd64*" ;;
        aarch64|arm64) BINARY_PATTERN="*aarch64*|*arm64*" ;;
        armv7l|armv8l) BINARY_PATTERN="*armv7*|*arm*" ;;
        i386|i686) BINARY_PATTERN="*i386*|*386*" ;;
        *) log_error "不支持架构 $arch"; exit 1 ;;
    esac
    log_info "系统架构: $arch"
}

get_physical_ifaces() {
    local ifaces=()
    local i
    for i in $(ls /sys/class/net/ | grep -vE '^lo$|^docker|^br-|^veth'); do
        if [[ "$i" =~ ^bond[0-9]+ ]]; then
            if ip addr show "$i" &>/dev/null && ip -4 addr show "$i" | grep -q 'inet'; then
                ifaces+=("$i")
            fi
        else
            [ -e "/sys/class/net/$i/device" ] && ip addr show "$i" &>/dev/null && ifaces+=("$i")
        fi
    done
    echo "${ifaces[@]}"
}

get_iface_info() {
    local iface=$1
    local ip subnet gw
    ip=$(ip -4 addr show "$iface" | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1 || true)
    subnet=$(echo "$ip" | awk -F. '{print $1"."$2"."$3".0/24"}')
    gw=$(ip route | grep "default" | grep "$iface" | awk '{print $3}' || true)
    [ -z "$gw" ] && gw=$(echo "$ip" | awk -F. '{print $1"."$2"."$3".1"}')
    echo "$ip|$subnet|$gw"
}

check_iface_ipv6() {
    local iface=$1
    local addrs
    addrs=$(ip -6 addr show "$iface" | grep -oP '(?<=inet6\s)[a-f0-9:]+' | grep -v '^fe80' || true)
    [ -z "$addrs" ] && return 1
    local addr
    for addr in $addrs; do
        case "$addr" in
            240e:*|2408:*|2409:*|240a:*) return 0 ;;
        esac
    done
    return 1
}

# ==================== 镜像版本检查 ====================
socks5_image_ok() {
    docker images --format "{{.Repository}}" | grep -q "^psyduck-socks5$" || return 1
    local img_frp img_gost
    img_frp=$(docker inspect -f '{{index .Config.Labels "frp_version"}}' psyduck-socks5 2>/dev/null || echo "")
    img_gost=$(docker inspect -f '{{index .Config.Labels "gost_version"}}' psyduck-socks5 2>/dev/null || echo "")
    [ "$img_frp" = "$FRP_VERSION" ] && [ "$img_gost" = "$GOST_VERSION" ]
}

ssh_image_ok() {
    docker images --format "{{.Repository}}" | grep -q "^psyduck-ssh$" || return 1
    local img_frp
    img_frp=$(docker inspect -f '{{index .Config.Labels "frp_version"}}' psyduck-ssh 2>/dev/null || echo "")
    [ "$img_frp" = "$FRP_VERSION" ]
}

# ==================== 1. APT 源 ====================
get_distro_info() {
    local distro_id="" distro_codename=""
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        distro_id="$ID"
        distro_codename="$VERSION_CODENAME"
        if [ -z "$distro_codename" ]; then
            if [[ "$VERSION" =~ \([a-z]+\) ]]; then
                distro_codename="${BASH_REMATCH[1]}"
            else
                case "$ID" in
                    debian) distro_codename=$(echo "$VERSION" | awk '{print $1}' | tr -d '()') ;;
                    ubuntu) distro_codename=$(echo "$VERSION" | awk '{print $2}' | tr -d '()') ;;
                esac
            fi
        fi
    elif [ -f /etc/lsb-release ]; then
        . /etc/lsb-release
        distro_id="$DISTRIB_ID"
        distro_codename="$DISTRIB_CODENAME"
    else
        log_error "无法识别系统发行版"; exit 1
    fi
    distro_id=$(echo "$distro_id" | tr '[:upper:]' '[:lower:]')
    distro_codename=$(echo "$distro_codename" | tr '[:upper:]' '[:lower:]')
    echo "$distro_id|$distro_codename"
}

check_and_set_mirrors() {
    log_step "检测并设置 APT 镜像源..."
    local info distro_id distro_codename
    info=$(get_distro_info)
    IFS='|' read -r distro_id distro_codename <<< "$info"
    log_info "发行版: $distro_id, 代号: $distro_codename"

    local china_mirrors="mirrors.(aliyun|tencent|tuna|ustc|163)"
    if grep -qE "$china_mirrors" /etc/apt/sources.list 2>/dev/null || \
       grep -qE "$china_mirrors" /etc/apt/sources.list.d/*.sources 2>/dev/null; then
        log_success "APT 源已为国内镜像，跳过替换"
        return
    fi

    local mirror="mirrors.aliyun.com"
    local timestamp=$(date +%Y%m%d%H%M%S)
    local backup_dir="/etc/apt/backup_$timestamp"
    mkdir -p "$backup_dir"
    cp -a /etc/apt/sources.list* "$backup_dir/" 2>/dev/null || true

    local new_sources=""
    case "$distro_id" in
        debian)
            [ -z "$distro_codename" ] && distro_codename="bookworm"
            new_sources="deb http://$mirror/debian $distro_codename main contrib non-free
deb http://$mirror/debian $distro_codename-updates main contrib non-free
deb http://security.debian.org/debian-security $distro_codename-security main contrib non-free"
            ;;
        ubuntu)
            [ -z "$distro_codename" ] && distro_codename="jammy"
            new_sources="deb http://$mirror/ubuntu $distro_codename main restricted universe multiverse
deb http://$mirror/ubuntu $distro_codename-updates main restricted universe multiverse
deb http://$mirror/ubuntu $distro_codename-backports main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu $distro_codename-security main restricted universe multiverse"
            ;;
        *)
            new_sources="deb http://$mirror/debian bookworm main contrib non-free
deb http://$mirror/debian bookworm-updates main contrib non-free
deb http://security.debian.org/debian-security bookworm-security main contrib non-free"
            ;;
    esac

    if [ -f /etc/apt/sources.list.d/debian.sources ] || [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then
        local f
        for f in /etc/apt/sources.list.d/*.sources; do
            [ -f "$f" ] && sed -i "s#URIs: https\?://[^/]*/#URIs: http://$mirror/#g" "$f"
        done
    else
        echo "$new_sources" > /etc/apt/sources.list
    fi
    apt-get update
    log_success "APT 源更新完成"
}

# ==================== 2. 安装 Docker ====================
install_docker() {
    log_step "检查并安装 Docker..."

    if command -v docker &>/dev/null; then
        log_info "检测到 Docker 已安装: $(docker --version 2>/dev/null || echo '版本未知')"
        if docker info &>/dev/null; then
            log_success "Docker 守护进程运行正常"
            return 0
        fi
        log_warning "Docker 守护进程未运行，尝试启动..."
        systemctl start docker &>/dev/null || true
        sleep 2
        if docker info &>/dev/null; then
            log_success "Docker 守护进程已启动"
            return 0
        fi
        log_error "Docker 无法启动，请手动检查：systemctl status docker"
        exit 1
    fi

    log_info "Docker 未安装，开始安装（阿里云镜像）..."
    local tmp_script; tmp_script=$(mktemp)
    local success=false i
    for i in 1 2 3; do
        if curl -fsSL --retry 3 --connect-timeout 10 "https://get.docker.com" -o "$tmp_script"; then
            success=true; break
        fi
        sleep 3
    done
    if [ "$success" = false ]; then
        rm -f "$tmp_script"
        log_error "下载 Docker 安装脚本失败"
        exit 1
    fi

    if ! sh "$tmp_script" --mirror Aliyun; then
        rm -f "$tmp_script"
        log_error "Docker 安装失败"
        exit 1
    fi
    rm -f "$tmp_script"

    systemctl enable --now docker &>/dev/null || true
    sleep 2

    if ! docker info &>/dev/null; then
        log_error "Docker 安装后无法通信"
        exit 1
    fi
    log_success "Docker 安装完成: $(docker --version 2>/dev/null || echo '版本未知')"
}

# ==================== 3. Docker 镜像加速 ====================
check_docker_mirror() {
    log_step "检查 Docker 镜像加速器..."
    local daemon="/etc/docker/daemon.json"
    local backup="/tmp/daemon.json.bak.$$"
    local target_mirrors=(
        "https://docker-registry.nmqu.com"
        "https://docker.m.daocloud.io"
        "https://hub1.nat.tf"
    )

    if ! command -v docker &>/dev/null || ! docker info &>/dev/null; then
        log_warning "Docker 不可用，跳过镜像加速检查"
        return 0
    fi

    local current
    current=$(docker info 2>/dev/null \
        | awk '/Registry Mirrors:/{f=1;next} f&&/^[[:space:]]+https?:/{print} f&&/^[^[:space:]]/{f=0}' \
        | tr -d ' ' || true)

    local m
    for m in "${target_mirrors[@]}"; do
        if echo "$current" | grep -qF "${m%/}"; then
            log_success "运行时已命中镜像加速：$m，跳过"
            return 0
        fi
    done

    log_info "运行时未命中，准备写入配置..."
    local had_backup=false
    [ -f "$daemon" ] && cp "$daemon" "$backup" && had_backup=true

    local merger=""
    if command -v python3 &>/dev/null; then
        merger="python3"
    elif command -v jq &>/dev/null; then
        merger="jq"
    else
        apt-get install -y jq &>/dev/null || true
        command -v jq &>/dev/null && merger="jq"
    fi
    if [ -z "$merger" ]; then
        log_warning "无 JSON 合并工具，跳过本步"
        return 0
    fi

    mkdir -p /etc/docker
    local tmp_json="/tmp/daemon.json.new.$$"
    if [ "$merger" = "python3" ]; then
        python3 - "$daemon" "$tmp_json" "${target_mirrors[@]}" <<'PY'
import json, sys, os
src, dst = sys.argv[1], sys.argv[2]
mirrors = sys.argv[3:]
data = {}
if os.path.exists(src):
    try:
        with open(src) as f: data = json.load(f)
    except Exception: data = {}
data["registry-mirrors"] = mirrors
with open(dst, "w") as f: json.dump(data, f, indent=2)
PY
    else
        if [ -f "$daemon" ]; then
            jq --argjson m "$(printf '%s\n' "${target_mirrors[@]}" | jq -R . | jq -s .)" \
               '. + {"registry-mirrors": $m}' "$daemon" > "$tmp_json"
        else
            printf '%s\n' "${target_mirrors[@]}" | jq -R . | jq -s '{["registry-mirrors"]: .}' > "$tmp_json"
        fi
    fi
    mv "$tmp_json" "$daemon"

    if ! systemctl restart docker &>/dev/null; then
        log_warning "Docker 重启失败，回滚配置..."
        if [ "$had_backup" = true ]; then
            cp "$backup" "$daemon"
        else
            rm -f "$daemon"
        fi
        systemctl restart docker &>/dev/null || log_warning "回滚后 Docker 仍无法启动"
        rm -f "$backup"
        return 0
    fi

    current=$(docker info 2>/dev/null \
        | awk '/Registry Mirrors:/{f=1;next} f&&/^[[:space:]]+https?:/{print} f&&/^[^[:space:]]/{f=0}' \
        | tr -d ' ' || true)
    for m in "${target_mirrors[@]}"; do
        if echo "$current" | grep -qF "${m%/}"; then
            log_success "镜像加速已生效：$m"
            rm -f "$backup"
            return 0
        fi
    done
    log_warning "写入后仍未命中，但 Docker 正常运行"
    rm -f "$backup"
    return 0
}

# ==================== 4. 安装 Git ====================
install_git() {
    if command -v git &>/dev/null; then
        log_success "Git 已安装: $(git --version)"
        return 0
    fi
    log_info "安装 Git..."
    apt-get install -y git
    if ! command -v git &>/dev/null; then
        log_error "Git 安装失败"
        exit 1
    fi
    log_success "Git 安装完成: $(git --version)"
}

# ==================== 5. 克隆仓库 ====================
normalize_origin_url() {
    local url
    url=$(git remote get-url origin 2>/dev/null || echo "")
    [ -z "$url" ] && return 0
    [[ "$url" =~ ^https://github\.com/ ]] && return 0
    if [[ "$url" == *"https://github.com/"* ]]; then
        local clean="https://github.com/${url##*https://github.com/}"
        log_info "origin 含代理前缀，重置为: $clean"
        git remote set-url origin "$clean"
    fi
    return 0
}

clone_and_build_main() {
    log_step "克隆/更新主仓库..."
    local repo="https://github.com/xoyoxoyo/relayApi.git"
    local proxy_flag=""
    [ -n "$GITHUB_PROXY_PREFIX" ] && proxy_flag="-c url.${GITHUB_PROXY_PREFIX}https://github.com/.insteadOf=https://github.com/"

    if [ -d relayApi ]; then
        log_info "更新仓库..."
        cd relayApi
        normalize_origin_url
        if ! timeout 180 git $proxy_flag pull; then
            log_warning "git pull 超时，3 秒后重试..."
            sleep 3
            timeout 180 git $proxy_flag pull || { log_error "git pull 再次失败"; exit 1; }
        fi
        cd ..
    else
        log_info "克隆仓库（3分钟超时）..."
        if ! timeout 180 git $proxy_flag clone "$repo" relayApi; then
            log_warning "代理克隆失败，尝试直连..."
            timeout 180 git clone "$repo" relayApi || { log_error "克隆失败"; exit 1; }
        fi
        cd relayApi
        normalize_origin_url
        cd ..
    fi

    cd relayApi
    if [ -f "psyduck" ] && [ -x "psyduck" ]; then
        log_success "psyduck 二进制已存在"
    else
        log_info "查找匹配的二进制文件..."
        local bin="" p
        local patterns=($(echo "$BINARY_PATTERN" | tr '|' ' '))
        for p in "${patterns[@]}"; do
            bin=$(find . -type f -name "$p" | head -1)
            [ -n "$bin" ] && break
        done
        [ -z "$bin" ] && bin=$(find . -type f -name "psyduck-*" | head -1)
        [ -z "$bin" ] && { log_error "未找到匹配的二进制文件"; exit 1; }
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

# ==================== 6. Alpine 源测速 ====================
test_alpine_mirrors() {
    log_step "测试 Alpine 镜像源速度..."

    local arch apk_arch
    arch=$(uname -m)
    case "$arch" in
        x86_64|amd64)      apk_arch="x86_64" ;;
        aarch64|arm64)     apk_arch="aarch64" ;;
        armv7l|armv8l|arm) apk_arch="armv7" ;;
        i386|i686)         apk_arch="x86" ;;
        *) log_warning "未知架构 $arch，跳过测速"; return 0 ;;
    esac

    local mirrors=(
        "mirrors.aliyun.com"
        "mirrors.tuna.tsinghua.edu.cn"
        "mirrors.ustc.edu.cn"
        "mirrors.163.com"
    )
    local best_speed=0
    local best_mirror="$FASTEST_ALPINE_MIRROR"

    local mirror
    for mirror in "${mirrors[@]}"; do
        local url="https://${mirror}/alpine/v3.19/main/${apk_arch}/APKINDEX.tar.gz"
        log_info "测试 $mirror ..."
        local speed
        speed=$(curl -o /dev/null -s -w '%{speed_download}' --max-time 10 "$url" 2>/dev/null || echo "0")
        local speed_int
        speed_int=$(awk "BEGIN {printf \"%d\", $speed+0}" 2>/dev/null || echo "0")
        if [ "$speed_int" -gt 0 ]; then
            local speed_kbs
            speed_kbs=$(awk "BEGIN {printf \"%.2f\", $speed/1024}")
            log_info "  速度: ${speed_kbs} KB/s"
            if [ "$speed_int" -gt "$best_speed" ]; then
                best_speed=$speed_int
                best_mirror=$mirror
            fi
        else
            log_warning "  测试失败"
        fi
        sleep 0.5
    done

    FASTEST_ALPINE_MIRROR="$best_mirror"
    if [ "$best_speed" -eq 0 ]; then
        log_warning "所有镜像测速失败，使用默认源 $FASTEST_ALPINE_MIRROR"
    else
        log_success "选择最快的 Alpine 镜像源: $FASTEST_ALPINE_MIRROR"
    fi
    return 0
}

# ==================== 7. 构建 SOCKS5 镜像 ====================
build_socks5_image() {
    if docker images --format "{{.Repository}}" | grep -q "^psyduck-socks5$"; then
        if socks5_image_ok; then
            log_success "SOCKS5 镜像已存在且版本匹配"
            return
        fi
        local img_frp img_gost
        img_frp=$(docker inspect -f '{{index .Config.Labels "frp_version"}}' psyduck-socks5 2>/dev/null || echo "未知")
        img_gost=$(docker inspect -f '{{index .Config.Labels "gost_version"}}' psyduck-socks5 2>/dev/null || echo "未知")
        log_warning "SOCKS5 镜像版本不匹配（镜像 frp=$img_frp gost=$img_gost，期望 frp=$FRP_VERSION gost=$GOST_VERSION），自动重建"
        docker rmi -f psyduck-socks5 2>/dev/null || true
    fi

    log_step "构建 SOCKS5 镜像..."

    local arch frp_arch gost_arch
    arch=$(uname -m)
    case "$arch" in
        x86_64)          frp_arch="amd64"; gost_arch="amd64" ;;
        aarch64|arm64)   frp_arch="arm64"; gost_arch="arm64" ;;
        armv7l|armv8l)   frp_arch="arm";   gost_arch="armv7" ;;
        *) log_error "不支持的架构: $arch"; exit 1 ;;
    esac

    local LOCAL_BIN_DIR="/opt/psyduck/bin"
    mkdir -p "$LOCAL_BIN_DIR"

    # --- frpc ---
    local frpc_ok=false
    if [ -x "$LOCAL_BIN_DIR/frpc" ]; then
        local cur_ver
        cur_ver=$("$LOCAL_BIN_DIR/frpc" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "")
        if [ "$cur_ver" = "$FRP_VERSION" ]; then
            frpc_ok=true
            log_info "frpc 已存在且版本匹配 ($cur_ver)"
        else
            log_warning "frpc 版本不符，重新下载"
        fi
    fi

    if [ "$frpc_ok" = false ]; then
        log_info "下载 frpc (${FRP_VERSION})..."
        local frp_tmp="/tmp/frp_${FRP_VERSION}_${frp_arch}.tar.gz"
        local frp_url="${GITHUB_PROXY_PREFIX}https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_${frp_arch}.tar.gz"
        local success=false i
        for i in 1 2 3; do
            if curl -L --fail --retry 3 --connect-timeout 10 -o "$frp_tmp" "$frp_url"; then
                success=true; break
            fi
            sleep 2
        done
        if [ "$success" = false ]; then
            frp_url="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_${frp_arch}.tar.gz"
            for i in 1 2 3; do
                if curl -L --fail --retry 3 --connect-timeout 10 -o "$frp_tmp" "$frp_url"; then
                    success=true; break
                fi
                sleep 2
            done
        fi
        if [ "$success" = true ]; then
            tar -xzf "$frp_tmp" -C /tmp
            local frp_dir=$(tar -tf "$frp_tmp" | head -1 | cut -d'/' -f1)
            mv "/tmp/$frp_dir/frpc" "$LOCAL_BIN_DIR/frpc"
            chmod +x "$LOCAL_BIN_DIR/frpc"
            rm -f "$frp_tmp"
            log_success "frpc 已下载"
        else
            log_warning "frpc 下载失败，将回退到 Alpine 仓库 frp"
        fi
    fi

    # --- gost ---
    local gost_ok=false
    if [ -x "$LOCAL_BIN_DIR/gost" ]; then
        local cur_ver
        cur_ver=$("$LOCAL_BIN_DIR/gost" -V 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "")
        if [ "$cur_ver" = "$GOST_VERSION" ]; then
            gost_ok=true
            log_info "gost 已存在且版本匹配 ($cur_ver)"
        fi
    fi

    if [ "$gost_ok" = false ]; then
        log_info "下载 gost (${GOST_VERSION})..."
        local gost_tmp="/tmp/gost_${GOST_VERSION}_${gost_arch}.tar.gz"
        local gost_url="${GITHUB_PROXY_PREFIX}https://github.com/go-gost/gost/releases/download/v${GOST_VERSION}/gost_${GOST_VERSION}_linux_${gost_arch}.tar.gz"
        local success=false i
        for i in 1 2 3; do
            if curl -L --fail --retry 3 --connect-timeout 10 -o "$gost_tmp" "$gost_url"; then
                success=true; break
            fi
            sleep 2
        done
        if [ "$success" = false ]; then
            gost_url="https://github.com/go-gost/gost/releases/download/v${GOST_VERSION}/gost_${GOST_VERSION}_linux_${gost_arch}.tar.gz"
            for i in 1 2 3; do
                if curl -L --fail --retry 3 --connect-timeout 10 -o "$gost_tmp" "$gost_url"; then
                    success=true; break
                fi
                sleep 2
            done
        fi
        if [ "$success" = false ]; then
            log_error "gost 下载失败，无法构建 SOCKS5 镜像"
            exit 1
        fi
        tar -xzf "$gost_tmp" -C /tmp
        local gost_file
        gost_file=$(find /tmp -maxdepth 1 -type f -name "gost*" ! -name "*.tar.gz" | head -1)
        [ -z "$gost_file" ] && { log_error "未找到 gost 二进制"; exit 1; }
        mv "$gost_file" "$LOCAL_BIN_DIR/gost"
        chmod +x "$LOCAL_BIN_DIR/gost"
        rm -f "$gost_tmp"
        log_success "gost 已下载"
    fi

    # --- 构建 ---
    local tmpd; tmpd=$(mktemp -d)
    cd "$tmpd"
    cp "$LOCAL_BIN_DIR/gost" .
    local frp_line
    if [ -x "$LOCAL_BIN_DIR/frpc" ]; then
        cp "$LOCAL_BIN_DIR/frpc" .
        frp_line="COPY frpc /usr/bin/frpc"
    else
        frp_line="RUN apk add --no-cache frp"
    fi

    cat > Dockerfile <<EOF
FROM alpine:3.19
LABEL frp_version="${FRP_VERSION}" gost_version="${GOST_VERSION}"
RUN sed -i 's#dl-cdn.alpinelinux.org#${FASTEST_ALPINE_MIRROR}#g' /etc/apk/repositories
RUN apk add --no-cache ca-certificates
${frp_line}
COPY gost /usr/bin/gost
COPY start.sh /start.sh
RUN chmod +x /start.sh /usr/bin/gost /usr/bin/frpc
EXPOSE 2233
CMD ["/start.sh"]
EOF

    cat > start.sh <<'EOF'
#!/bin/sh

MAX_RESTART=5
BASE_BACKOFF=2
STABLE_SECONDS=60

GOST_PID=""
FRPC_PID=""
GOST_RESTARTS=0
FRPC_RESTARTS=0
GOST_START_TS=0
FRPC_START_TS=0

now_ts() { date +%s; }

start_gost() {
    /usr/bin/gost -L "socks5://${SOCKS5_USER}:${SOCKS5_PASS}@:2233" &
    GOST_PID=$!
    GOST_START_TS=$(now_ts)
}

start_frpc() {
    /usr/bin/frpc -c /app/frpc.ini &
    FRPC_PID=$!
    FRPC_START_TS=$(now_ts)
}

cleanup() {
    kill "$GOST_PID" "$FRPC_PID" 2>/dev/null || true
    exit 0
}
trap cleanup TERM INT

start_gost
start_frpc

while true; do
    if ! kill -0 "$GOST_PID" 2>/dev/null; then
        alive=$(( $(now_ts) - GOST_START_TS ))
        [ "$alive" -ge "$STABLE_SECONDS" ] && GOST_RESTARTS=0
        GOST_RESTARTS=$((GOST_RESTARTS + 1))
        if [ "$GOST_RESTARTS" -gt "$MAX_RESTART" ]; then
            echo "[start.sh] gost 连续 ${MAX_RESTART} 次异常退出，容器退出"
            cleanup
        fi
        backoff=$((BASE_BACKOFF * GOST_RESTARTS))
        echo "[start.sh] gost 退出，${backoff}s 后第 ${GOST_RESTARTS} 次重启"
        sleep "$backoff"
        start_gost
    fi

    if ! kill -0 "$FRPC_PID" 2>/dev/null; then
        alive=$(( $(now_ts) - FRPC_START_TS ))
        [ "$alive" -ge "$STABLE_SECONDS" ] && FRPC_RESTARTS=0
        FRPC_RESTARTS=$((FRPC_RESTARTS + 1))
        if [ "$FRPC_RESTARTS" -gt "$MAX_RESTART" ]; then
            echo "[start.sh] frpc 连续 ${MAX_RESTART} 次异常退出，容器退出"
            cleanup
        fi
        backoff=$((BASE_BACKOFF * FRPC_RESTARTS))
        echo "[start.sh] frpc 退出，${backoff}s 后第 ${FRPC_RESTARTS} 次重启"
        sleep "$backoff"
        start_frpc
    fi

    sleep 2
done
EOF
    chmod +x start.sh
    docker build -t psyduck-socks5 .
    cd / && rm -rf "$tmpd"
    log_success "SOCKS5 镜像构建完成"
}

# ==================== 8. 构建 SSH 镜像 ====================
build_ssh_image() {
    if docker images --format "{{.Repository}}" | grep -q "^psyduck-ssh$"; then
        if ssh_image_ok; then
            log_success "SSH 镜像已存在且版本匹配"
            return
        fi
        local img_frp
        img_frp=$(docker inspect -f '{{index .Config.Labels "frp_version"}}' psyduck-ssh 2>/dev/null || echo "未知")
        log_warning "SSH 镜像版本不匹配（镜像 frp=$img_frp，期望 frp=$FRP_VERSION），自动重建"
        docker rmi -f psyduck-ssh 2>/dev/null || true
    fi

    log_step "构建 SSH 镜像..."
    local tmpd; tmpd=$(mktemp -d)
    cd "$tmpd"

    local frp_line
    if [ -x /opt/psyduck/bin/frpc ]; then
        cp /opt/psyduck/bin/frpc .
        frp_line="COPY frpc /usr/bin/frpc"
    else
        frp_line="RUN apk add --no-cache frp"
        log_warning "本地 frpc 缺失，回退到 Alpine 仓库 frp"
    fi

    cat > Dockerfile <<EOF
FROM alpine:3.19
LABEL frp_version="${FRP_VERSION}"
RUN sed -i 's#dl-cdn.alpinelinux.org#${FASTEST_ALPINE_MIRROR}#g' /etc/apk/repositories
RUN apk add --no-cache ca-certificates tzdata
RUN mkdir -p /app
${frp_line}
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh /usr/bin/frpc
ENTRYPOINT ["/entrypoint.sh"]
EOF

    cat > entrypoint.sh <<'EOF'
#!/bin/sh
exec /usr/bin/frpc -c /app/frpc.ini
EOF
    chmod +x entrypoint.sh

    docker build -t psyduck-ssh .
    cd / && rm -rf "$tmpd"
    log_success "SSH 镜像构建完成"
}

# ==================== 9. 清理与漂移 ====================
clean_all_containers() {
    local keep_ssh="${1:-false}"
    log_warning "清理容器与网络（保留 SSH: $keep_ssh）"

    local pattern
    if [ "$keep_ssh" = true ]; then
        pattern='^psyduck[0-9]+$|^psyduck[0-9]+-socks5$'
    else
        pattern='^psyduck[0-9]+$|^psyduck[0-9]+-socks5$|^psyduck[0-9]+-ssh$'
    fi

    local c
    for c in $(docker ps -a --format '{{.Names}}' | grep -E "$pattern" || true); do
        docker stop "$c" &>/dev/null || true
        docker rm "$c" &>/dev/null || true
        echo "已删除 $c"
    done

    local net_pattern='^psyduck$|^psyduck[0-9]+$'
    local n
    for n in $(docker network ls --format '{{.Name}}' | grep -E "$net_pattern" || true); do
        docker network rm "$n" &>/dev/null || true
        echo "已删除 $n"
    done
    return 0
}

write_config_snapshot() {
    cat >> "$CONFIG_FILE" <<EOF

# === 脚本变量快照 ===
SNAPSHOT_DEFAULT_SERVER_ADDR=$DEFAULT_SERVER_ADDR
SNAPSHOT_DEFAULT_SERVER_PORT=$DEFAULT_SERVER_PORT
SNAPSHOT_DEFAULT_TOKEN=$DEFAULT_TOKEN
SNAPSHOT_SOCKS5_USER=$SOCKS5_USER
SNAPSHOT_SOCKS5_PASS=$SOCKS5_PASS
SNAPSHOT_FRP_VERSION=$FRP_VERSION
SNAPSHOT_GOST_VERSION=$GOST_VERSION
SNAPSHOT_GITHUB_PROXY_PREFIX=$GITHUB_PROXY_PREFIX
EOF
}

check_config_drift() {
    [ -f "$CONFIG_FILE" ] || return 0

    local snap_addr snap_port snap_token snap_user snap_pass
    local snap_frp snap_gost snap_proxy
    snap_addr=$(grep '^SNAPSHOT_DEFAULT_SERVER_ADDR=' "$CONFIG_FILE" | cut -d= -f2- || true)
    snap_port=$(grep '^SNAPSHOT_DEFAULT_SERVER_PORT=' "$CONFIG_FILE" | cut -d= -f2- || true)
    snap_token=$(grep '^SNAPSHOT_DEFAULT_TOKEN=' "$CONFIG_FILE" | cut -d= -f2- || true)
    snap_user=$(grep '^SNAPSHOT_SOCKS5_USER=' "$CONFIG_FILE" | cut -d= -f2- || true)
    snap_pass=$(grep '^SNAPSHOT_SOCKS5_PASS=' "$CONFIG_FILE" | cut -d= -f2- || true)
    snap_frp=$(grep '^SNAPSHOT_FRP_VERSION=' "$CONFIG_FILE" | cut -d= -f2- || true)
    snap_gost=$(grep '^SNAPSHOT_GOST_VERSION=' "$CONFIG_FILE" | cut -d= -f2- || true)
    snap_proxy=$(grep '^SNAPSHOT_GITHUB_PROXY_PREFIX=' "$CONFIG_FILE" | cut -d= -f2- || true)

    local drift=false
    [ "$snap_addr" != "$DEFAULT_SERVER_ADDR" ] && drift=true
    [ "$snap_port" != "$DEFAULT_SERVER_PORT" ] && drift=true
    [ "$snap_token" != "$DEFAULT_TOKEN" ] && drift=true
    [ "$snap_user" != "$SOCKS5_USER" ] && drift=true
    [ "$snap_pass" != "$SOCKS5_PASS" ] && drift=true
    [ "$snap_frp" != "$FRP_VERSION" ] && drift=true
    [ "$snap_gost" != "$GOST_VERSION" ] && drift=true
    [ "$snap_proxy" != "$GITHUB_PROXY_PREFIX" ] && drift=true

    if [ "$drift" = false ]; then
        log_success "脚本变量与快照一致"
        return 0
    fi

    log_warning "检测到脚本变量变更，清除所有容器与网络"
    clean_all_containers false
    sed -i '/^# === 脚本变量快照 ===$/,$d' "$CONFIG_FILE"
    write_config_snapshot
    return 1
}

# ==================== 10. 网卡选择 ====================
select_deployment_mode() {
    log_step "探测网卡..."
    local all=($(get_physical_ifaces))
    [ ${#all[@]} -eq 0 ] && { log_error "未找到物理网卡"; exit 1; }

    local online=()
    local i
    for i in "${all[@]}"; do
        if check_iface_ipv6 "$i"; then
            online+=("$i")
            log_success "网卡 $i IPv6 正常"
        else
            log_warning "网卡 $i IPv6 不可用"
        fi
    done
    [ ${#online[@]} -eq 0 ] && { log_error "无可用 IPv6 网卡"; exit 1; }

    # 读旧配置（子 shell 隔离解析，避免 eval 引号冲突）
    local old_selected=()
    local old_networks=()
    if [ -f "$CONFIG_FILE" ]; then
        local _sel_str _net_str _l
        _sel_str=$(bash -c 'source "$1" 2>/dev/null; printf "%s\n" "${SELECTED_INTERFACES[@]}"' _ "$CONFIG_FILE" || true)
        _net_str=$(bash -c 'source "$1" 2>/dev/null; printf "%s\n" "${NETWORKS[@]}"' _ "$CONFIG_FILE" || true)
        while IFS= read -r _l; do
            [ -n "$_l" ] && old_selected+=("$_l")
        done <<< "$_sel_str"
        while IFS= read -r _l; do
            [ -n "$_l" ] && old_networks+=("$_l")
        done <<< "$_net_str"
    fi

    # 分类
    local keep_ifaces=() failed_ifaces=() new_ifaces=()
    local old cur found
    for old in "${old_selected[@]}"; do
        found=false
        for cur in "${online[@]}"; do [ "$cur" = "$old" ] && { found=true; break; }; done
        if [ "$found" = true ]; then keep_ifaces+=("$old"); else failed_ifaces+=("$old"); fi
    done
    for cur in "${online[@]}"; do
        found=false
        for old in "${old_selected[@]}"; do [ "$old" = "$cur" ] && { found=true; break; }; done
        [ "$found" = false ] && new_ifaces+=("$cur")
    done

    # 删失效
    local iface entry
    for iface in "${failed_ifaces[@]}"; do
        for entry in "${old_networks[@]}"; do
            local e_net e_iface e_rport
            IFS='|' read -r e_net e_iface _ _ e_rport _ _ <<< "$entry"
            if [ "$e_iface" = "$iface" ]; then
                local c
                for c in "psyduck${e_rport}" "psyduck${e_rport}-socks5" "psyduck${e_rport}-ssh"; do
                    if docker ps -a --format '{{.Names}}' | grep -qx "$c"; then
                        docker stop "$c" &>/dev/null || true
                        docker rm "$c" &>/dev/null || true
                        echo "已删除 $c"
                    fi
                done
                if docker network ls --format '{{.Name}}' | grep -qx "$e_net"; then
                    docker network rm "$e_net" &>/dev/null || true
                    echo "已删除 $e_net"
                fi
                break
            fi
        done
    done

    # 决定模式
    if [ ${#old_selected[@]} -eq 0 ]; then
        if [ ${#online[@]} -eq 1 ]; then
            DEPLOY_MODE="single"
            SELECTED_INTERFACES=("${online[0]}")
        else
            echo -e "${CYAN}检测到多个可用 IPv6 网卡，请选择：\n 1) 单网口\n 2) 多网口${NC}"
            local choice
            read -p "请输入 1 或 2 [默认1]: " choice < /dev/tty || choice="1"
            if [ "$choice" = "2" ]; then
                DEPLOY_MODE="multi"
                local j
                for j in "${!online[@]}"; do echo " $((j+1))) ${online[$j]}"; done
                local sel
                read -p "选择编号（如 1 2 3 或 all）: " sel < /dev/tty || sel="all"
                if [ "$sel" = "all" ]; then
                    SELECTED_INTERFACES=("${online[@]}")
                else
                    SELECTED_INTERFACES=()
                    local n
                    for n in $sel; do
                        [ "$n" -ge 1 ] && [ "$n" -le ${#online[@]} ] && SELECTED_INTERFACES+=("${online[$((n-1))]}")
                    done
                fi
            else
                DEPLOY_MODE="single"
                SELECTED_INTERFACES=("${online[0]}")
            fi
        fi
    else
        SELECTED_INTERFACES=("${keep_ifaces[@]}" "${new_ifaces[@]}")
        if [ ${#SELECTED_INTERFACES[@]} -eq 1 ]; then
            DEPLOY_MODE="single"
        else
            DEPLOY_MODE="multi"
        fi
    fi

    [ ${#SELECTED_INTERFACES[@]} -eq 0 ] && { log_error "无有效网卡"; exit 1; }

    OLD_NETWORKS=("${old_networks[@]}")
    log_info "部署模式: $DEPLOY_MODE, 网卡: ${SELECTED_INTERFACES[*]}"
}

# ==================== 11. 端口配置 ====================
configure_ports() {
    REMOTE_PORTS=()
    local iface entry e_iface e_rport
    for iface in "${SELECTED_INTERFACES[@]}"; do
        local existing_rport=""
        for entry in "${OLD_NETWORKS[@]}"; do
            IFS='|' read -r _ e_iface _ _ e_rport _ _ <<< "$entry"
            if [ "$e_iface" = "$iface" ]; then existing_rport="$e_rport"; break; fi
        done
        if [ -n "$existing_rport" ]; then
            REMOTE_PORTS+=("$existing_rport")
            log_info "网卡 $iface 使用已有端口 $existing_rport"
        else
            echo -e "${CYAN}为网卡 $iface 设置主容器端口:${NC}"
            local p
            while true; do
                read -p "主容器端口: " p < /dev/tty || { log_error "读取输入失败"; exit 1; }
                if [ -n "$p" ]; then break; fi
                log_warning "端口不能为空，请重新输入"
            done
            REMOTE_PORTS+=("$p")
        fi
    done

    SOCKS5_PORTS=()
    local r
    for r in "${REMOTE_PORTS[@]}"; do SOCKS5_PORTS+=("$((r + 1000))"); done
}

# ==================== 12. 保存配置 ====================
detect_and_save_config() {
    mkdir -p "$CONFIG_DIR"

    local net_entries=()
    local used_names=()
    local idx iface rport sport
    for idx in "${!SELECTED_INTERFACES[@]}"; do
        iface="${SELECTED_INTERFACES[$idx]}"
        rport="${REMOTE_PORTS[$idx]}"
        sport=$((rport + 1000))

        local net_name=""
        local entry
        for entry in "${OLD_NETWORKS[@]}"; do
            local e_net e_iface
            IFS='|' read -r e_net e_iface _ _ _ _ _ <<< "$entry"
            if [ "$e_iface" = "$iface" ]; then net_name="$e_net"; break; fi
        done

        if [ -z "$net_name" ]; then
            local n=0 candidate
            while true; do
                candidate="psyduck"
                [ "$n" -gt 0 ] && candidate="psyduck${n}"
                local taken=false
                docker network ls --format '{{.Name}}' | grep -qx "$candidate" && taken=true
                local un
                for un in "${used_names[@]}"; do
                    [ "$un" = "$candidate" ] && taken=true
                done
                if [ "$taken" = false ]; then net_name="$candidate"; break; fi
                n=$((n + 1))
            done
        fi
        used_names+=("$net_name")

        local info
        info=$(get_iface_info "$iface")
        local subnet gw
        IFS='|' read -r _ subnet gw <<< "$info"

        local ipv6_prefix="$IPV6_PREFIX_BASE"
        if [ "$idx" -gt 0 ]; then
            local prefix_hex
            prefix_hex=$(printf "%x" $((0x${IPV6_PREFIX_BASE:3} + idx)))
            ipv6_prefix="${IPV6_PREFIX_BASE:0:3}${prefix_hex}"
        fi
        net_entries+=("$net_name|$iface|$subnet|$gw|$rport|$sport|$ipv6_prefix")
    done

    {
        echo "DEPLOY_MODE=$DEPLOY_MODE"
        echo "SELECTED_INTERFACES=(${SELECTED_INTERFACES[*]})"
        echo "REMOTE_PORTS=(${REMOTE_PORTS[*]})"
        echo "SOCKS5_PORTS=(${SOCKS5_PORTS[*]})"
        printf 'NETWORKS=('
        local i
        for i in "${!net_entries[@]}"; do
            [ "$i" -gt 0 ] && printf ' '
            printf '"%s"' "${net_entries[$i]}"
        done
        echo ')'
    } > "$CONFIG_FILE"
    write_config_snapshot
    log_success "配置已保存到 $CONFIG_FILE"
}

# ==================== 13. macvlan 网络 ====================
create_macvlan_network() {
    local net_name=$1 iface=$2 subnet=$3 gw=$4 ipv6_prefix=$5
    if docker network ls --format '{{.Name}}' | grep -qx "$net_name"; then
        log_info "网络 $net_name 已存在，跳过创建"
        return 0
    fi
    if [[ "$ipv6_prefix" =~ : ]]; then
        ipv6_prefix=$(echo "$ipv6_prefix" | cut -d':' -f1-2 | tr -d ':')
    fi
    docker network create -d macvlan \
        --subnet="$subnet" \
        --gateway="$gw" \
        --ipv6 \
        --subnet="${ipv6_prefix}:5a35:6fce::/64" \
        -o parent="$iface" \
        "$net_name"
    log_success "创建网络 $net_name"
}

# ==================== 14. 主容器 ====================
deploy_main_container() {
    local net_name=$1 remote_port=$2
    local container_name="psyduck${remote_port}"

    if docker ps -a --format '{{.Names}}' | grep -qx "$container_name"; then
        log_info "主容器 $container_name 已存在"
        return
    fi

    local tmp="/tmp/frpc_${remote_port}.ini"
    cat > "$tmp" <<EOF
[common]
server_addr = ${DEFAULT_SERVER_ADDR}
server_port = ${DEFAULT_SERVER_PORT}
token = ${DEFAULT_TOKEN}
tls_enable = true

[psyduck${remote_port}]
type = http
local_ip = 127.0.0.1
local_port = 80
remote_port = ${remote_port}
EOF

    docker run -d --name "$container_name" \
        --restart unless-stopped \
        --network "$net_name" \
        -v "$tmp:/app/frpc.ini" \
        psyduck
    log_success "主容器 $container_name 已启动"
}

# ==================== 15. SOCKS5 容器 ====================
deploy_socks5_container() {
    local net_name=$1 rport=$2 sport=$3
    local container_name="psyduck${rport}-socks5"

    if docker ps -a --format '{{.Names}}' | grep -qx "$container_name"; then
        log_info "SOCKS5 容器 $container_name 已存在"
        return
    fi

    local workdir="/opt/psyduck/socks5_${rport}"
    rm -rf "$workdir" && mkdir -p "$workdir"

    cat > "$workdir/frpc.ini" <<EOF
[common]
server_addr = ${DEFAULT_SERVER_ADDR}
server_port = ${DEFAULT_SERVER_PORT}
token = ${DEFAULT_TOKEN}
tls_enable = true

[psyduck${rport}-socks5]
type = tcp
local_ip = 127.0.0.1
local_port = 2233
remote_port = ${sport}
EOF

    docker run -d --name "$container_name" \
        --restart unless-stopped \
        --network "$net_name" \
        -v "$workdir/frpc.ini:/app/frpc.ini" \
        -e SOCKS5_USER="${SOCKS5_USER}" \
        -e SOCKS5_PASS="${SOCKS5_PASS}" \
        psyduck-socks5
    log_success "SOCKS5 容器 $container_name 已启动"
}

# ==================== 16. SSH 容器 ====================
deploy_ssh_container() {
    local rport=$1
    local ssh_rport=$((rport + 2000))
    local container_name="psyduck${rport}-ssh"

    if docker ps -a --format '{{.Names}}' | grep -qx "$container_name"; then
        log_info "SSH 容器 $container_name 已存在"
        return
    fi

    local workdir="/opt/psyduck/ssh_${rport}"
    rm -rf "$workdir" && mkdir -p "$workdir"

    cat > "$workdir/frpc.ini" <<EOF
[common]
server_addr = ${DEFAULT_SERVER_ADDR}
server_port = ${DEFAULT_SERVER_PORT}
token = ${DEFAULT_TOKEN}
tls_enable = true

[psyduck${rport}-ssh]
type = tcp
local_ip = 127.0.0.1
local_port = 22
remote_port = ${ssh_rport}
EOF

    docker run -d --name "$container_name" \
        --restart unless-stopped \
        --network host \
        -v "$workdir/frpc.ini:/app/frpc.ini" \
        psyduck-ssh
    log_success "SSH 容器 $container_name 已启动（端口 $ssh_rport）"
}

# ==================== 17. 维护脚本 ====================
generate_maintenance_script() {
    cat > "$SCRIPT_PATH" <<'EOF'
#!/bin/bash
source /opt/psyduck/psyduck.conf

for c in $(docker ps -a --format '{{.Names}}' \
    | grep -E '^psyduck[0-9]+$|^psyduck[0-9]+-socks5$'); do
    if docker restart "$c" &>/dev/null; then
        echo "[$(date '+%F %T')] 已重启 $c"
    else
        echo "[$(date '+%F %T')] 重启失败 $c"
    fi
done
EOF
    chmod +x "$SCRIPT_PATH"
    log_success "维护脚本已生成: $SCRIPT_PATH"
}

# ==================== 18. systemd 定时器 ====================
setup_systemd_timer() {
    cat > /etc/systemd/system/psyduck-maintenance.service <<'EOF'
[Unit]
Description=Psyduck Maintenance
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/psyduck_maintenance.sh
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/psyduck-maintenance.timer <<'EOF'
[Unit]
Description=Psyduck Daily Maintenance

[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

    systemctl daemon-reload
    systemctl enable --now psyduck-maintenance.timer
    log_success "systemd 定时器已设置（每天 04:00）"
}

# ==================== 19. 验证主容器 ====================
verify_main_containers() {
    log_step "验证主容器是否可用..."
    local main_containers
    main_containers=$(docker ps -a --format '{{.Names}}' | grep -E '^psyduck[0-9]+$' || true)

    local c
    for c in $main_containers; do
        local ip
        ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$c" 2>/dev/null || echo "")
        if [ -z "$ip" ]; then
            log_warning "容器 $c 无法获取 IP"
            continue
        fi
        local ok=false i
        for i in 1 2 3; do
            if docker exec "$c" curl -fsS --max-time 5 "http://$ip/ipv6" &>/dev/null; then
                ok=true; break
            fi
            sleep 3
        done
        if [ "$ok" = true ]; then
            log_success "容器 $c 验证通过"
        else
            log_warning "容器 $c 验证失败"
        fi
    done
}

# ==================== 主流程 ====================
main() {
    local arg
    for arg in "$@"; do
        case "$arg" in
            --debug) DEBUG_MODE=true ;;
            --check) CHECK_MODE=true ;;
        esac
    done

    if [ "$CHECK_MODE" = true ]; then
        log_info "检查模式暂未实现，仅提示"
        exit 0
    fi

    if [ "$DEBUG_MODE" = true ]; then
        log_warning "调试模式：删除除 SSH 外的所有容器与网络"
        clean_all_containers true
    fi

    log_step "开始完整部署"
    check_and_set_mirrors
    install_docker
    check_docker_mirror
    install_git
    clone_and_build_main

    local need_build=false
    socks5_image_ok || need_build=true
    ssh_image_ok || need_build=true
    if [ "$need_build" = true ]; then
        test_alpine_mirrors
    else
        log_info "SOCKS5 和 SSH 镜像均已存在且版本匹配，跳过 Alpine 源测速"
    fi
    build_socks5_image
    build_ssh_image

    if ! check_config_drift; then
        log_info "已清除旧容器与网络，将使用已有端口重新部署"
    fi

    select_deployment_mode
    configure_ports
    detect_and_save_config
    source "$CONFIG_FILE"

    local entry
    for entry in "${NETWORKS[@]}"; do
        local net_name iface subnet gw rport sport ipv6_prefix
        IFS='|' read -r net_name iface subnet gw rport sport ipv6_prefix <<< "$entry"
        create_macvlan_network "$net_name" "$iface" "$subnet" "$gw" "$ipv6_prefix"
        deploy_main_container "$net_name" "$rport"
        deploy_socks5_container "$net_name" "$rport" "$sport"
    done

    for entry in "${NETWORKS[@]}"; do
        local net_name iface subnet gw rport sport ipv6_prefix
        IFS='|' read -r net_name iface subnet gw rport sport ipv6_prefix <<< "$entry"
        deploy_ssh_container "$rport"
    done

    log_step "重启所有非 SSH 容器以确保配置生效..."
    local c
    for c in $(docker ps -a --format '{{.Names}}' | grep -E '^psyduck[0-9]+$|^psyduck[0-9]+-socks5$' || true); do
        if docker restart "$c" &>/dev/null; then
            log_info "已重启 $c"
        else
            log_warning "重启 $c 失败"
        fi
    done

    generate_maintenance_script
    setup_systemd_timer
    verify_main_containers
    touch "$DEPLOY_FLAG"
    log_success "部署完成"
}

main "$@"