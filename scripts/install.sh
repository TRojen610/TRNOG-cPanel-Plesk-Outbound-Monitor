#!/usr/bin/env bash
set -euo pipefail

APP_NAME="trnog-outbound-monitor"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/opt/${APP_NAME}"
CONFIG_DIR="/etc/${APP_NAME}"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
DATA_DIR="/var/lib/${APP_NAME}"
LOG_DIR="/var/log/${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
APP_CONFIG_SOURCE="${INSTALL_DIR}/cpanel/whm/appconfig/trnog-outbound-monitor.conf"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "This installer must run as root."
    exit 1
  fi
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

detect_pkg_manager() {
  if command_exists apt-get; then
    PKG_MGR="apt"
  elif command_exists dnf; then
    PKG_MGR="dnf"
  elif command_exists yum; then
    PKG_MGR="yum"
  else
    echo "Unsupported package manager."
    exit 1
  fi
}

install_system_dependencies() {
  echo "Installing system dependencies..."
  if [[ "${PKG_MGR}" == "apt" ]]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y \
      python3 python3-venv python3-pip rsyslog curl ca-certificates \
      python3-bpfcc bpfcc-tools "linux-headers-$(uname -r)" || true
  elif [[ "${PKG_MGR}" == "dnf" ]]; then
    dnf install -y epel-release || true
    dnf install -y \
      python3 python3-pip rsyslog curl ca-certificates \
      bcc bcc-tools python3-bcc kernel-devel kernel-headers || true
  else
    yum install -y epel-release || true
    yum install -y \
      python3 python3-pip rsyslog curl ca-certificates \
      bcc bcc-tools python3-bcc kernel-devel kernel-headers || true
  fi
}

copy_project() {
  echo "Copying project files to ${INSTALL_DIR}..."
  rm -rf "${INSTALL_DIR}"
  install -d "${INSTALL_DIR}" "${CONFIG_DIR}" "${DATA_DIR}" "${LOG_DIR}"
  tar \
    --exclude=".git" \
    --exclude="repo" \
    --exclude="__pycache__" \
    --exclude="*.pyc" \
    -C "${PROJECT_ROOT}" \
    -cf - . | tar -C "${INSTALL_DIR}" -xf -
}

install_python_dependencies() {
  echo "Creating virtual environment..."
  python3 -m venv "${INSTALL_DIR}/.venv"
  "${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip wheel
  "${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
}

install_config() {
  if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "Installing default configuration..."
    install -m 0640 "${INSTALL_DIR}/config/config.example.yaml" "${CONFIG_FILE}"
  else
    echo "Keeping existing configuration at ${CONFIG_FILE}"
  fi
}

install_systemd_unit() {
  echo "Installing systemd service..."
  install -m 0644 "${INSTALL_DIR}/deploy/systemd/trnog-outbound-monitor.service" "${SERVICE_FILE}"
  systemctl daemon-reload
  systemctl enable --now "${APP_NAME}.service"
}

install_whm_plugin() {
  if [[ ! -d /usr/local/cpanel/whostmgr/docroot ]]; then
    echo "cPanel/WHM not detected. Skipping WHM integration."
    return
  fi

  echo "Installing WHM integration..."
  install -d /usr/local/cpanel/whostmgr/docroot/cgi
  install -d /usr/local/cpanel/whostmgr/docroot/addon_plugins
  install -m 0755 \
    "${INSTALL_DIR}/cpanel/whm/cgi/trnog_outbound_monitor.cgi" \
    /usr/local/cpanel/whostmgr/docroot/cgi/trnog_outbound_monitor.cgi
  install -m 0644 \
    "${INSTALL_DIR}/cpanel/whm/assets/trnog-outbound-monitor.png" \
    /usr/local/cpanel/whostmgr/docroot/addon_plugins/trnog-outbound-monitor.png
  if [[ -x /usr/local/cpanel/bin/register_appconfig ]]; then
    /usr/local/cpanel/bin/register_appconfig "${APP_CONFIG_SOURCE}"
  fi
}

show_result() {
  echo
  echo "Installation completed."
  echo
  echo "Config: ${CONFIG_FILE}"
  echo "Service: systemctl status ${APP_NAME}"
  echo "Health: curl http://127.0.0.1:15155/health"
  echo "Dashboard: http://127.0.0.1:15155/"
  echo "Logs: ${LOG_DIR}"
}

main() {
  require_root
  detect_pkg_manager
  install_system_dependencies
  copy_project
  install_python_dependencies
  install_config
  install_systemd_unit
  install_whm_plugin
  show_result
}

main "$@"
