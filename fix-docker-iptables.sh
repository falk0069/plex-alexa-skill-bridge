#!/bin/bash
# fix-docker-iptables
# ─────────────────────────────────────────────────────────────────────────────
# Docker can lose its FORWARD chain rules after a compose rebuild, causing
# containers to lose outbound internet access. This script detects and fixes
# that condition without requiring a Docker restart.
#
# Install:
#   sudo cp fix-docker-iptables /usr/local/bin/fix-docker-iptables
#   sudo chmod +x /usr/local/bin/fix-docker-iptables
#
# Add to cron (runs every 2 minutes):
#   echo "*/2 * * * * root /usr/local/bin/fix-docker-iptables >> /var/log/fix-docker-iptables.log 2>&1" \
#     | sudo tee /etc/cron.d/fix-docker-forward
#
# Run manually after docker compose up --build:
#   sudo fix-docker-iptables
# ─────────────────────────────────────────────────────────────────────────────

if ! iptables -L FORWARD -n | grep -q "DOCKER-FORWARD"; then
    echo "$(date): Docker FORWARD rules missing, re-adding..."
    iptables -I FORWARD -j DOCKER-FORWARD
    iptables -I FORWARD -j DOCKER-USER
    echo "$(date): Done"
else
    echo "$(date): Docker FORWARD rules OK"
fi
