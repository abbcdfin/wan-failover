#!/bin/sh

# enable lte module
if [ ! -d /sys/class/gpio/gpio129 ]; then
    echo 129 > /sys/class/gpio/export
fi
echo out > /sys/class/gpio/gpio129/direction
echo 1 > /sys/class/gpio/gpio129/value

FILE_PATH="/apps/btNC/down"

if [ ! -f "$FILE_PATH" ]; then
    echo -e 'AT+CFUN=6\r\n' > /dev/ttyUSB1
    sleep 13
fi
