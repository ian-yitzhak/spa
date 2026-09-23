#!/usr/bin/env bash
# Push local code to the VPS and restart. Usage: ./deploy.sh
# Requires: sshpass (or SSH keys — then drop the sshpass prefix).
set -euo pipefail
HOST="root@164.68.114.113"
APP="/home/beautyflow/app"
SSH="ssh -o StrictHostKeyChecking=no"
: "${SSHPASS:?export SSHPASS='<root password>' first}"

echo "→ syncing code"
sshpass -e rsync -az --delete -e "$SSH" \
  --exclude .venv --exclude db.sqlite3 --exclude media --exclude staticfiles \
  --exclude __pycache__ --exclude '*.pyc' --exclude .env --exclude .git --exclude backups.json \
  ./ "$HOST:$APP/"

echo "→ installing, migrating, collecting static, restarting"
sshpass -e $SSH "$HOST" "export LC_ALL=C.UTF-8; set -e
chown -R beautyflow:beautyflow $APP
sudo -u beautyflow -H bash -c 'cd $APP && /home/beautyflow/venv/bin/pip install -q -r requirements.txt && (/home/beautyflow/venv/bin/pip-audit --progress-spinner off 2>&1 | tail -2 || true) && /home/beautyflow/venv/bin/python manage.py migrate --noinput && /home/beautyflow/venv/bin/python manage.py collectstatic --noinput | tail -1'
systemctl reload beautyflow && sleep 3 && systemctl is-active beautyflow  # graceful: no 502 window
curl -s -o /dev/null -w 'https://beautyflow.co.ke -> %{http_code}\n' --max-time 20 https://beautyflow.co.ke/"
