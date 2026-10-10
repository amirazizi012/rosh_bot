#!/usr/bin/env bash
# نصب بات «رشد» روی اوبونتو/دبیان (با کاربر root اجرا شود).
# استفاده:  bash deploy/install.sh
set -euo pipefail

APP_DIR=/opt/rosh_bot
APP_USER=rosh

if [ "$(id -u)" -ne 0 ]; then
  echo "این اسکریپت را با کاربر root اجرا کنید."; exit 1
fi

SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> نصب بسته‌های لازم"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip unzip ufw

echo "==> ساخت کاربر سرویس ($APP_USER)"
id -u "$APP_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$APP_USER"

echo "==> کپی پروژه در $APP_DIR"
mkdir -p "$APP_DIR"
if [ "$SRC" != "$APP_DIR" ]; then
  cp -a "$SRC"/. "$APP_DIR"/
fi
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

echo "==> ساخت محیط پایتون و نصب وابستگی‌ها"
sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && python3 -m venv venv && venv/bin/pip install --upgrade pip && venv/bin/pip install -r requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  echo "==> تنظیمات"
  read -r -s -p "توکن بات بله (هنگام تایپ نمایش داده نمی‌شود): " TOKEN; echo
  read -r -p "شناسه‌ی عددی بله‌ی مدیر یا مدیران (با ویرگول جدا کنید): " ADMINS
  if [ -z "$TOKEN" ]; then echo "توکن خالی است."; exit 1; fi
  cat > "$APP_DIR/.env" <<ENVEOF
BALE_TOKEN=$TOKEN
ADMIN_IDS=$ADMINS
DATA_DIR=./data
GRACE_MINUTES=20
LATE_WINDOW_HOURS=24
STREAK_SIZE=6
REMINDER_HOURS=3
PANEL_HOST=127.0.0.1
PANEL_PORT=8080
ENVEOF
  chown "$APP_USER":"$APP_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
else
  echo "==> فایل .env از قبل وجود دارد و دست نخورد."
fi

echo "==> نصب سرویس‌های systemd"
install -m 644 "$APP_DIR/deploy/rosh-bot.service" /etc/systemd/system/rosh-bot.service
install -m 644 "$APP_DIR/deploy/rosh-panel.service" /etc/systemd/system/rosh-panel.service
systemctl daemon-reload
systemctl enable --now rosh-bot

echo "==> فایروال (فقط SSH باز می‌ماند؛ پنل وب فقط روی خود سرور است)"
ufw allow OpenSSH >/dev/null 2>&1 || ufw allow 22/tcp
ufw --force enable

sleep 3
echo
systemctl --no-pager --lines=8 status rosh-bot || true
echo
echo "تمام شد. لاگ زنده:   journalctl -u rosh-bot -f"
echo "فعال‌سازی پنل وب:   systemctl enable --now rosh-panel   (دسترسی با تونل SSH؛ راهنما در README)"
