#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-auto}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TEST_PATH="tests/platforms/NXP_IMX952.robot"

run_local() {
    if command -v renode-test >/dev/null 2>&1; then
        echo "[i.MX952] Running qualification with installed renode-test"
        cd "${ROOT_DIR}"
        renode-test "${TEST_PATH}"
        return
    fi

    if [[ -x "${ROOT_DIR}/test.sh" ]]; then
        echo "[i.MX952] Running qualification with repository test.sh"
        cd "${ROOT_DIR}"
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
        bash -lc "renode-test ${TEST_PATH}"
}

case "${MODE}" in
    local)
        run_local
        ;;
    docker)
        run_docker
        ;;
    auto)
        if ! run_local; then
            run_docker
        fi
        ;;
    *)
        echo "Usage: $0 [auto|local|docker]" >&2
        exit 2
        ;;
esac

echo "[i.MX952] Qualification completed successfully"
