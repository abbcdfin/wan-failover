#!/bin/sh

# enable lte module
echo 129 > /sys/class/gpio/export
echo out > /sys/class/gpio/gpio129/direction
echo 1 > /sys/class/gpio/gpio129/value

FILE_PATH="/apps/btNC/down"

if [ ! -f "$FILE_PATH" ]; then
    sleep 15s
    ip_address=$(ip -o -4 addr show lte0 2>/dev/null | awk '{print $4}' | cut -d '/' -f1)
    if [ -n "$ip_address" ]; then
	net_segment=$(echo "$ip_address" | cut -d '.' -f3)
    else
	net_segment=""
    fi

    if [ "$net_segment" -ne 99 ]; then
	echo -e 'AT+USBNETIP=0,99,10,200\r\n' > /dev/ttyUSB1
	sleep 2s
	echo -e 'AT+CFUN=6\r\n' > /dev/ttyUSB1
	sleep 15s
    fi

    echo -e 'AT+DIALMODE=0\r\n' > /dev/ttyUSB1
    sleep 2s
    echo -e 'AT+NETOPEN\r\n' > /dev/ttyUSB1
    sync
fi
