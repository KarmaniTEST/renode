#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-demo}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RENODE_BIN="${RENODE_BIN:-renode}"

if [[ "${MODE}" == "qualify" ]]; then
    exec "${SCRIPT_DIR}/qualify.sh" "${2:-auto}"
fi

if ! command -v "${RENODE_BIN}" >/dev/null 2>&1; then
    if [[ -x "${ROOT_DIR}/renode" ]]; then
        RENODE_BIN="${ROOT_DIR}/renode"
    else
        echo "[i.MX952] Renode executable not found. Set RENODE_BIN or add renode to PATH." >&2
        exit 1
    fi
fi

case "${MODE}" in
    demo)
        SCRIPT="${ROOT_DIR}/scripts/single-node/nxp_imx952_evk_heterogeneous_demo.resc"
        ;;
    platform)
        SCRIPT="${ROOT_DIR}/scripts/single-node/nxp_imx952_evk.resc"
        ;;
    *)
        echo "Usage: $0 [demo|platform|qualify] [auto|local|docker]" >&2
        exit 2
        ;;
esac

echo "[i.MX952] Starting ${MODE} with ${RENODE_BIN}"
exec "${RENODE_BIN}" --console "${SCRIPT}"
