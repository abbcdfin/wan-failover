import dbus
import time
import subprocess
import logging
import sys
import os
from typing import List, Optional
import yaml

# Default configuration
DEFAULT_CONFIG = {
    'backup_connection_name': 'lte0',
    'check_host': '8.8.8.8',
    'check_interval': 30,
    'failover_threshold': 2,
    'log_file': '/var/log/wan-failover.log',
    'log_level': 'DEBUG',
    'enable_backup_script': '/bin/enable_lte.sh'
}

VERSION = "V0.1.0-RC0"

def load_config(config_path: str = '/etc/wan-failover/config.yaml') -> dict:
    """Load configuration from YAML file"""
    config = DEFAULT_CONFIG.copy()
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    config.update(file_config)
        except Exception as e:
            print(f"Warning: Failed to load config file {config_path}: {e}")
    
    return config

def setup_logging(config: dict):
    """Setup logging based on configuration"""
    log_level = getattr(logging, config['log_level'].upper(), logging.INFO)

    handlers = [logging.StreamHandler(sys.stdout)]
    if 'log_file' in config:
        handlers.append(logging.FileHandler(config['log_file']))
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=handlers
    )

class NetworkManagerFailover:
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.bus = dbus.SystemBus()
        self.nm_proxy = self.bus.get_object('org.freedesktop.NetworkManager', 
                                           '/org/freedesktop/NetworkManager')
        self.nm_interface = dbus.Interface(self.nm_proxy, 
                                          'org.freedesktop.NetworkManager')
        self.nm_props = dbus.Interface(self.nm_proxy, 
                                      'org.freedesktop.DBus.Properties')
        
        # Configuration
        self.backup_connection_name = config['backup_connection_name']
        self.check_host = config['check_host']
        self.check_interval = config['check_interval']
        self.enable_backup_script = config['enable_backup_script']
        self.failover_threshold = config['failover_threshold']
        
        # State tracking
        self.consecutive_failure_count = 0
        
        # Configure NetworkManager connectivity checking
        self.configure_nm_connectivity_check()
        
        # Configure backup connection settings
        self.configure_backup_connection()
        
    def configure_nm_connectivity_check(self):
        """Configure NetworkManager connectivity checking"""
        try:
            # Calculate connectivity check interval (half of failover check interval)
            connectivity_interval = max(1, self.check_interval // 2)
            
            # Configure connectivity checking
            self.nm_props.Set('org.freedesktop.NetworkManager', 'ConnectivityCheckEnabled', True)
            self.nm_props.Set('org.freedesktop.NetworkManager', 'ConnectivityCheckInterval', 
                             dbus.UInt32(connectivity_interval))
            
            self.logger.info(f"Configured NetworkManager connectivity checking with {connectivity_interval}s interval")
        except Exception as e:
            self.logger.warning(f"Failed to configure NetworkManager connectivity checking: {e}")
    
    def configure_backup_connection(self):
        """Configure backup connection with autoconnect=False and metric=90"""
        try:
            connections = self.get_connections()
            backup_conn = None
            
            # Find backup connection
            for conn in connections:
                if conn['id'] == self.backup_connection_name:
                    backup_conn = conn
                    break
            
            if not backup_conn:
                self.logger.warning(f"Backup connection '{self.backup_connection_name}' not found")
                return
            
            # Get connection settings proxy
            connection_proxy = self.bus.get_object('org.freedesktop.NetworkManager', 
                                                 backup_conn['path'])
            connection_settings = dbus.Interface(connection_proxy, 
                                               'org.freedesktop.NetworkManager.Settings.Connection')
            
            # Get current settings
            settings = connection_settings.GetSettings()
            
            # Modify settings
            settings['connection']['autoconnect'] = False
            
            # Set IPv4 routing metric
            if 'ipv4' not in settings:
                settings['ipv4'] = {}
            settings['ipv4']['route-metric'] = dbus.UInt32(90)
            
            # Set IPv6 routing metric if IPv6 is configured
            if 'ipv6' not in settings:
                settings['ipv6'] = {}
            settings['ipv6']['route-metric'] = dbus.UInt32(90)
            
            # Update connection with new settings
            connection_settings.Update(settings)
            self.logger.info(f"Configured backup connection '{self.backup_connection_name}' "
                           f"with autoconnect=False and route-metric=90")
                           
        except Exception as e:
            self.logger.error(f"Failed to configure backup connection: {e}")
    
    def get_connections(self) -> List[dict]:
        """Get all connections from NetworkManager"""
        settings_proxy = self.bus.get_object('org.freedesktop.NetworkManager', 
                                           '/org/freedesktop/NetworkManager/Settings')
        settings_interface = dbus.Interface(settings_proxy, 
                                          'org.freedesktop.NetworkManager.Settings')
        
        connections = []
        for connection_path in settings_interface.ListConnections():
            connection_proxy = self.bus.get_object('org.freedesktop.NetworkManager', 
                                                 connection_path)
            connection_interface = dbus.Interface(connection_proxy, 
                                                'org.freedesktop.NetworkManager.Settings.Connection')
            settings = connection_interface.GetSettings()
            
            connections.append({
                'path': connection_path,
                'id': str(settings['connection']['id']),
                'type': str(settings['connection']['type']),
                'uuid': str(settings['connection']['uuid'])
            })
            
        return connections
    
    def get_active_connections(self) -> List[dict]:
        """Get all active connections from NetworkManager"""
        active_connections_paths = self.nm_props.Get('org.freedesktop.NetworkManager', 
                                                    'ActiveConnections')
        
        active_connections = []
        for path in active_connections_paths:
            try:
                active_conn_proxy = self.bus.get_object('org.freedesktop.NetworkManager', path)
                active_conn_props = dbus.Interface(active_conn_proxy, 
                                                  'org.freedesktop.DBus.Properties')
                
                # Get connection details
                connection_path = active_conn_props.Get('org.freedesktop.NetworkManager.Connection.Active', 
                                                       'Connection')
                connection_proxy = self.bus.get_object('org.freedesktop.NetworkManager', 
                                                     connection_path)
                connection_interface = dbus.Interface(connection_proxy, 
                                                    'org.freedesktop.NetworkManager.Settings.Connection')
                settings = connection_interface.GetSettings()
                
                # Get device paths
                devices_paths = active_conn_props.Get('org.freedesktop.NetworkManager.Connection.Active', 
                                                     'Devices')
                
                # Get device interfaces
                devices = []
                for device_path in devices_paths:
                    device_proxy = self.bus.get_object('org.freedesktop.NetworkManager', 
                                                      device_path)
                    device_props = dbus.Interface(device_proxy, 
                                                 'org.freedesktop.DBus.Properties')
                    try:
                        interface_name = device_props.Get('org.freedesktop.NetworkManager.Device', 
                                                         'Interface')
                        devices.append(str(interface_name))
                    except dbus.DBusException:
                        pass
                
                active_connections.append({
                    'path': path,
                    'id': str(settings['connection']['id']),
                    'type': str(settings['connection']['type']),
                    'devices': devices
                })
            except dbus.DBusException:
                continue
                
        return active_connections
    
    def is_connected_to_internet(self, interface: Optional[str] = None) -> bool:
        """Check if we have internet connectivity"""
        try:
            cmd = ['ping', '-c', '3', '-W', '3']
            if interface:
                cmd.extend(['-I', interface])
            cmd.append(self.check_host)
            
            result = subprocess.run(cmd, 
                                  stdout=subprocess.DEVNULL, 
                                  stderr=subprocess.DEVNULL)
            return result.returncode == 0
        except Exception as e:
            self.logger.debug(f"Ping failed: {e}")
            return False
    
    def activate_connection(self, connection_name: str) -> bool:
        """Activate a connection by name"""
        try:
            connections = self.get_connections()
            target_connection = None
            
            for conn in connections:
                if conn['id'] == connection_name:
                    target_connection = conn
                    break
            
            if not target_connection:
                self.logger.error(f"Connection '{connection_name}' not found")
                return False
            
            # Activate the connection
            self.nm_interface.ActivateConnection(
                target_connection['path'],
                "/",  # Device (auto-detect)
                "/"   # Specific object
            )
            
            self.logger.info(f"Activated connection '{connection_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to activate connection '{connection_name}': {e}")
            return False
    
    def deactivate_connection(self, connection_name: str) -> bool:
        """Deactivate a connection by name"""
        try:
            active_connections = self.get_active_connections()
            target_connection = None
            
            for conn in active_connections:
                if conn['id'] == connection_name:
                    target_connection = conn
                    break
            
            if not target_connection:
                self.logger.warning(f"Connection '{connection_name}' is not active")
                return False
            
            # Deactivate the connection
            self.nm_interface.DeactivateConnection(target_connection['path'])
            self.logger.info(f"Deactivated connection '{connection_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to deactivate connection '{connection_name}': {e}")
            return False
    
    def get_primary_connections(self) -> List[str]:
        """Get list of non-backup connection names that should be monitored"""
        connections = self.get_connections()
        primary_connections = []
        
        for conn in connections:
            # Skip backup connection and some system connections
            if (conn['id'] != self.backup_connection_name and 
                conn['type'] in ['802-3-ethernet', '802-11-wireless']):
                primary_connections.append(conn['id'])
                
        return primary_connections
    
    def monitor_and_failover(self):
        """Main monitoring loop"""
        self.logger.info("Starting WAN failover monitoring")
        
        backup_active = False
        
        while True:
            try:
                # Check if we currently have internet connectivity
                current_internet_status = self.is_connected_to_internet()

                # Get active connections
                active_connections = self.get_active_connections()
                active_connection_names = [conn['id'] for conn in active_connections]
                
                # Check if any primary connection is active
                primary_connections = self.get_primary_connections()
                primary_active = any(conn in active_connection_names for conn in primary_connections)
                
                self.logger.debug(f"Primary connections: {primary_connections}")
                self.logger.debug(f"Active connections: {active_connection_names}")
                self.logger.debug(f"Internet status: {current_internet_status}")
                self.logger.debug(f"Backup active: {backup_active}")
                self.logger.debug(f"Consecutive failure count: {self.consecutive_failure_count}")
                
                # Case 1: Primary connection is active but no internet
                if not current_internet_status and not backup_active:
                    self.consecutive_failure_count += 1
                    self.logger.info(f"No internet and backup connection is down - failure count: {self.consecutive_failure_count}")
                    
                    # Only activate backup after consecutive failures
                    if self.consecutive_failure_count >= self.failover_threshold:
                        self.logger.info("Activating backup connection after consecutive failures")
                        if self.activate_connection(self.backup_connection_name):
                            backup_active = True
                            self.consecutive_failure_count = 0  # Reset counter
                            # Run backup enable script
                            try:
                                subprocess.run([self.enable_backup_script], 
                                             stdout=subprocess.DEVNULL, 
                                             stderr=subprocess.DEVNULL)
                            except Exception as e:
                                self.logger.warning(f"Failed to run {self.enable_backup_script}: {e}")
                    else:
                        self.logger.debug("Waiting for consecutive failures before activating backup")
                
                # Case 2: Backup is active, check if primary connections have restored internet
                elif backup_active:
                    # Reset failure counter when backup is active
                    self.consecutive_failure_count = 0
                    
                    # Test if we can reach internet through primary interfaces
                    primary_has_internet = False
                    for conn in active_connections:
                        if conn['id'] in primary_connections and conn['devices']:
                            # Try pinging through the first device of this connection
                            if self.is_connected_to_internet(conn['devices'][0]):
                                primary_has_internet = True
                                self.logger.info(f"Primary connection {conn['id']} has internet access")
                                break
                    
                    if primary_has_internet:
                        self.logger.info("Primary connection restored - deactivating backup")
                        if self.deactivate_connection(self.backup_connection_name):
                            backup_active = False

                    elif not current_internet_status:
                        self.logger.info("Backup connection up, no internet, reset backup connection.")
                            
                # Case 3: Primary connection is active and has internet
                else:
                    # Reset failure counter when primary has internet
                    self.consecutive_failure_count = 0
                    self.logger.debug("Primary connection active with internet - reset failure counter")
                
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                self.logger.info("Stopping WAN failover monitoring")
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.check_interval)

def main():
    # Load configuration
    config_path = '/etc/wan-failover/config.yaml'
    if len(sys.argv) > 1 and sys.argv[1].startswith('--config='):
        config_path = sys.argv[1].split('=', 1)[1]
    
    config = load_config(config_path)
    
    # Setup logging
    setup_logging(config)
    logger = logging.getLogger(__name__)
    
    # Create failover instance
    failover = NetworkManagerFailover(config)
    
    # Handle command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--check":
            # Simple connectivity check mode
            if failover.is_connected_to_internet():
                print("Connected to internet")
                sys.exit(0)
            else:
                print("No internet connection")
                sys.exit(1)
        elif sys.argv[1].startswith('--config='):
            # Config already loaded, continue with monitoring
            pass
        else:
            print("Usage: wan_failover.py [--check] [--config=/path/to/config.yaml]")
            sys.exit(1)
    
    # Run continuous monitoring
    failover.monitor_and_failover()

if __name__ == "__main__":
    main()
