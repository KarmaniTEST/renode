#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-auto}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEST_PATH="tests/platforms/NXP_IMX952.robot"
LOG_PATH="${IMX952_QUALIFICATION_LOG:-${ROOT_DIR}/imx952-qualification.log}"

has_built_repository_runner() {
    [[ -x "${ROOT_DIR}/test.sh" ]] && \
        find "${ROOT_DIR}/output/bin" -maxdepth 3 -name Renode.dll -print -quit 2>/dev/null | grep -q .
}

run_local() {
    cd "${ROOT_DIR}"

    if has_built_repository_runner; then
        echo "[i.MX952] Running qualification with the built repository test runner"
        ./test.sh --show-log "${TEST_PATH}"
        return
    fi

    echo "[i.MX952] No built local Renode runtime found; use Docker mode or build Renode first" >&2
    return 1
}

run_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "[i.MX952] Docker is not installed" >&2
        return 1
    fi

    echo "[i.MX952] Running qualification in antmicro/renode:nightly-dotnet"
    docker run --rm \
        -v "${ROOT_DIR}:/workspace" \
        -v "${ROOT_DIR}/scripts/pydev/nxp_imx952_system_manager.py:/opt/renode/scripts/pydev/nxp_imx952_system_manager.py:ro" \
        -v "${ROOT_DIR}/scripts/pydev/nxp_imx952_ele.py:/opt/renode/scripts/pydev/nxp_imx952_ele.py:ro" \
        -v "${ROOT_DIR}/scripts/pydev/nxp_imx952_lpi2c7.py:/opt/renode/scripts/pydev/nxp_imx952_lpi2c7.py:ro" \
        -w /workspace \
        antmicro/renode:nightly-dotnet \
        renode-test --show-log "${TEST_PATH}"
}

run_selected() {
    case "${MODE}" in
        local)
            run_local
            ;;
        docker)
            run_docker
            ;;
        auto)
            if has_built_repository_runner; then
                run_local
            else
                run_docker
            fi
            ;;
        *)
            echo "Usage: $0 [auto|local|docker]" >&2
            return 2
            ;;
    esac
}

mkdir -p "$(dirname "${LOG_PATH}")"
echo "[i.MX952] Qualification log: ${LOG_PATH}"
run_selected 2>&1 | tee "${LOG_PATH}"
echo "[i.MX952] Qualification completed successfully"
