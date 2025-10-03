#!/bin/sh

sudo ln -sf /home/raftadmin/network-utils/wan-failover/wan-failover.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable wan-failover

