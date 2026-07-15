#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-auto}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEST_PATH="tests/platforms/NXP_IMX952.robot"
LOG_PATH="${IMX952_QUALIFICATION_LOG:-${ROOT_DIR}/imx952-qualification.log}"

has_local_runner() {
    command -v renode-test >/dev/null 2>&1 || [[ -x "${ROOT_DIR}/test.sh" ]]
}

run_local() {
    cd "${ROOT_DIR}"

    if command -v renode-test >/dev/null 2>&1; then
        echo "[i.MX952] Running qualification with installed renode-test"
        renode-test "${TEST_PATH}"
        return
    fi

    if [[ -x "${ROOT_DIR}/test.sh" ]]; then
        echo "[i.MX952] Running qualification with repository test.sh"
        ./test.sh "${TEST_PATH}"
        return
    fi

    echo "[i.MX952] No local Renode test runner found" >&2
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
        -w /workspace \
        antmicro/renode:nightly-dotnet \
        renode-test "${TEST_PATH}"
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
            if has_local_runner; then
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
