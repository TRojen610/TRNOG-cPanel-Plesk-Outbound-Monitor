#!/usr/bin/env bash
set -euo pipefail

APP_NAME="trnog-outbound-monitor"
INSTALL_DIR="/opt/${APP_NAME}"
CONFIG_DIR="/etc/${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
PURGE="${1:-}"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "This script must run as root."
    exit 1
  fi
}

remove_whm_plugin() {
  if [[ ! -d /usr/local/cpanel/whostmgr/docroot ]]; then
    return
  fi

  rm -f /usr/local/cpanel/whostmgr/docroot/cgi/trnog_outbound_monitor.cgi
  rm -f /usr/local/cpanel/whostmgr/docroot/addon_plugins/trnog-outbound-monitor.png

  if [[ -x /usr/local/cpanel/bin/unregister_appconfig ]]; then
    if [[ -f /var/cpanel/apps/trnog-outbound-monitor.conf ]]; then
      /usr/local/cpanel/bin/unregister_appconfig /var/cpanel/apps/trnog-outbound-monitor.conf || true
    else
      /usr/local/cpanel/bin/unregister_appconfig trnog-outbound-monitor || true
    fi
  fi
}

main() {
  require_root

  systemctl stop "${APP_NAME}.service" 2>/dev/null || true
  systemctl disable "${APP_NAME}.service" 2>/dev/null || true
  rm -f "${SERVICE_FILE}"
  systemctl daemon-reload
  systemctl reset-failed || true

  remove_whm_plugin

  rm -rf "${INSTALL_DIR}"

  if [[ "${PURGE}" == "--purge" ]]; then
    rm -rf "${CONFIG_DIR}" "/var/lib/${APP_NAME}" "/var/log/${APP_NAME}"
  fi

  echo "Removed ${APP_NAME}."
  if [[ "${PURGE}" != "--purge" ]]; then
    echo "Configuration and collected logs were preserved."
    echo "Run ./scripts/uninstall.sh --purge to remove them as well."
  fi
}

main "$@"
