#!/bin/zsh
set -u

APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
WEB_ROOT="$APP_ROOT/web"
LOG_DIR="$APP_ROOT/logs"

PHP_BIN="${BIBLE_GEMATRIA_PHP:-/Applications/MAMP/bin/php/php/bin/php}"
MYSQLD_SAFE="/Applications/MAMP/Library/bin/mysql80/bin/mysqld_safe"
MYSQL_DATADIR="/Applications/MAMP/db/mysql80"
MYSQL_SOCKET="/Applications/MAMP/tmp/mysql/mysql.sock"
MYSQL_PID="/Applications/MAMP/tmp/mysql/mysql.pid"
MYSQL_LOG="/Applications/MAMP/logs/mysql_error.log"

PHP_HOST="${BIBLE_GEMATRIA_HOST:-127.0.0.1}"
PHP_PORT="${BIBLE_GEMATRIA_PORT:-8888}"
LOCAL_URL="http://127.0.0.1:${PHP_PORT}/index.php?book=Gen&chapter=1&verse=1"
PHP_PID_FILE="$LOG_DIR/php_server_${PHP_PORT}.pid"

escape_applescript() {
    printf '%s' "$1" | /usr/bin/sed 's/\\/\\\\/g; s/"/\\"/g'
}

show_dialog() {
    local msg
    msg="$(escape_applescript "$1")"
    /usr/bin/osascript -e "display dialog \"$msg\" buttons {\"OK\"} default button \"OK\" with title \"Bible Gematria\"" >/dev/null 2>&1 || true
}

fail() {
    local msg="$1"
    echo ""
    echo "Bible Gematria could not start:"
    echo "$msg"
    show_dialog "$msg"
    if [[ "${BIBLE_GEMATRIA_NO_PAUSE:-0}" != "1" ]]; then
        echo ""
        read -k 1 "?Press any key to close this window..."
    fi
    exit 1
}

is_port_open() {
    /usr/sbin/lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

read_config_value() {
    local key="$1"
    local default="$2"
    local value
    value="$(APP_CONFIG="$WEB_ROOT/config.php" "$PHP_BIN" -r '$cfgPath = getenv("APP_CONFIG"); $key = $argv[1]; $default = $argv[2]; $cfg = is_file($cfgPath) ? require $cfgPath : []; $value = $cfg[$key] ?? $default; echo is_bool($value) ? ($value ? "1" : "0") : $value;' "$key" "$default" 2>/dev/null || true)"
    printf '%s' "${value:-$default}"
}

network_urls() {
    /sbin/ifconfig 2>/dev/null \
        | /usr/bin/awk '/inet / && $2 != "127.0.0.1" { print "  http://" $2 ":'"${PHP_PORT}"'/index.php?book=Gen&chapter=1&verse=1" }'
}

echo "Bible Gematria local app"
echo "Project: $APP_ROOT"
echo ""

[[ -d "$WEB_ROOT" ]] || fail "The web folder was not found. Keep this launcher inside the BibleGematria project folder."
[[ -x "$PHP_BIN" ]] || fail "MAMP PHP was not found at $PHP_BIN. Install MAMP, or set BIBLE_GEMATRIA_PHP to your PHP binary."
[[ -x "$MYSQLD_SAFE" ]] || fail "MAMP MySQL was not found at $MYSQLD_SAFE. Install MAMP first."

DB_PORT="$(read_config_value port 8889)"
DB_NAME="$(read_config_value database stepbible)"

mkdir -p "$LOG_DIR" /Applications/MAMP/tmp/mysql /Applications/MAMP/logs

if is_port_open "$DB_PORT"; then
    echo "MySQL is already running on port $DB_PORT."
else
    echo "Starting MAMP MySQL on port $DB_PORT..."
    nohup "$MYSQLD_SAFE" \
        --port="$DB_PORT" \
        --socket="$MYSQL_SOCKET" \
        --pid-file="$MYSQL_PID" \
        --log-error="$MYSQL_LOG" \
        --datadir="$MYSQL_DATADIR" >/dev/null 2>&1 &

    for _ in {1..45}; do
        is_port_open "$DB_PORT" && break
        sleep 1
    done

    is_port_open "$DB_PORT" || fail "MySQL did not start on port $DB_PORT. Open MAMP once, start MySQL there, then try this launcher again."
fi

if is_port_open "$PHP_PORT"; then
    echo "A local web server is already running on port $PHP_PORT."
else
    echo "Starting Bible Gematria web server on ${PHP_HOST}:${PHP_PORT}..."
    nohup "$PHP_BIN" -S "${PHP_HOST}:${PHP_PORT}" -t "$WEB_ROOT" > "$LOG_DIR/php_server.log" 2>&1 &
    echo $! > "$PHP_PID_FILE"

    for _ in {1..20}; do
        is_port_open "$PHP_PORT" && break
        sleep 0.5
    done

    is_port_open "$PHP_PORT" || fail "The Bible Gematria web server did not start. Check logs/php_server.log in the project folder."
fi

echo ""
echo "Database: $DB_NAME"
echo "Opening: $LOCAL_URL"
/usr/bin/open "$LOCAL_URL" >/dev/null 2>&1 || true

if [[ "${BIBLE_GEMATRIA_SHARE:-0}" == "1" ]]; then
    echo ""
    echo "iPhone URLs on your local network:"
    network_urls
    echo ""
    echo "Use one of those URLs in Safari on your iPhone while your Mac is awake and connected to the same hotspot/Wi-Fi."
fi

echo ""
echo "Keep MAMP installed. The local app stores the private Bible database on this Mac; it is not uploaded."
echo "To stop the web server later, run: kill \$(cat \"$PHP_PID_FILE\")"

if [[ "${BIBLE_GEMATRIA_NO_PAUSE:-0}" != "1" ]]; then
    echo ""
    read -k 1 "?Press any key to close this window..."
fi
