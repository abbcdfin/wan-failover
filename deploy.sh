#!/bin/sh

sudo nmcli connection modify "lte0" ipv4.route-metric 100
sudo nmcli connection modify "lan0" ipv4.route-metric 200

sudo ln -sf /home/raftadmin/network-utils/wan-failover/wan-failover.service /etc/systemd/system/
sudo ln -sf /home/raftadmin/network-utils/wan-failover/wan-failover.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now wan-failover.timer

