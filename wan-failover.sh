# Configuration
PRIMARY_IF="lan0"
PRIMARY_CONN="lan0"  # Name from 'nmcli con show'
BACKUP_CONN="lte0"   # Name from 'nmcli con show'
CHECK_HOST="8.8.8.8" # A reliable IP to ping

# Ping the check host via the primary interface
if ping -c 3 -W 3 -I "${PRIMARY_IF}" "${CHECK_HOST}" &> /dev/null; then
    # Internet on primary is OK. Ensure it's active.
    # We simply 'up' the connection. If it's already up, no harm is done.
    # This ensures its low-metric route is in the table.
    if nmcli connection show --active | grep -q "${BACKUP_CONN}"; then
	echo "${PRIMARY_IF} conn check succeeded, shut down ${BACKUP_CONN}."
	nmcli connection down "${BACKUP_CONN}" > /dev/null 2>&1
    fi
    exit 0
else
    # Check if backup connection is active or not. If not, activate it.
    if ! nmcli connection show --active | grep -q "${BACKUP_CONN}"; then
        echo "Turn up ${BACKUP_CONN}."
        nmcli connection up "${BACKUP_CONN}"
	/bin/enable_lte.sh
	exit 0
    fi

    # Internet on primary is down. Ensure backup is active.
    # nmcli will automatically bring this up if needed.
    # The primary connection's route will be dropped by NM's connectivity check,
    # or we can be more aggressive and bring it down.
    # For this script, we'll just ensure the backup is up.
    ping -c 3 -W 3 "${CHECK_HOST}" &> /dev/null
    CONNECTIVITY_STATUS=$?

    if [[ $CONNECTIVITY_STATUS != 0 ]]; then
        echo "${BACKUP_CONN} conn check failed, shut down ${BACKUP_CONN}."

        # BACKUP_CONN reset
	nmcli connection down "${BACKUP_CONN}"
        /bin/enable_lte.sh
    fi
fi
