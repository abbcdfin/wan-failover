#!/bin/sh

# restart lte module

# To check if lte0 is enabled.
FILE_PATH="/apps/btNC/down"
if [[ -f "$FILE_PATH" ]]; then
    exit 0
fi

# TODO:
# Check if lte0 has been enabled or not.

# Reset lte0 module and reenable it.
echo -e 'AT+CRESET\r\n' > /dev/ttyUSB1
sleep 13s
echo -e 'AT+DIALMODE=0\r\n' > /dev/ttyUSB1
sleep 10s
echo -e 'AT+NETOPEN\r\n' > /dev/ttyUSB1
