#!/usr/bin/env bash
set -euo pipefail

RUNTIME_MODE="${1:-auto}"
QUALIFICATION_MODE="${2:-engineering}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EQUIV_DIR="${SCRIPT_DIR}/equivalence"
LOG_PATH="${IMX952_FULL_QUALIFICATION_LOG:-${ROOT_DIR}/imx952-full-qualification.log}"
REPORT_PATH="${IMX952_COMPARISON_REPORT:-${ROOT_DIR}/imx952-hardware-comparison.json}"
PROFILE_PATH="${IMX952_COMPARISON_PROFILE:-${EQUIV_DIR}/profiles/imx952_evk_b0_foundation.json}"
REFERENCE_EVIDENCE="${IMX952_REFERENCE_EVIDENCE:-}"
CANDIDATE_EVIDENCE="${IMX952_CANDIDATE_EVIDENCE:-}"

TESTS=(
    "tests/platforms/NXP_IMX952.robot"
    "tests/platforms/NXP_IMX952_FULL_EQUIVALENCE.robot"
)

has_built_repository_runner() {
    [[ -x "${ROOT_DIR}/test.sh" ]] && \
        find "${ROOT_DIR}/output/bin" -maxdepth 3 -name Renode.dll -print -quit 2>/dev/null | grep -q .
}

run_framework_checks() {
    cd "${ROOT_DIR}"
    python3 -m unittest discover \
        -s tools/imx952-digital-twin/equivalence/tests \
        -p 'test_*.py' \
        -v
    python3 tools/imx952-digital-twin/equivalence/qualification_gate.py \
        --mode engineering \
        --skip-tests
}

run_local_renode() {
    cd "${ROOT_DIR}"
    if ! has_built_repository_runner; then
        echo "[i.MX952] No built local Renode runtime found" >&2
        return 1
    fi
    ./test.sh --show-log "${TESTS[@]}"
}

run_docker_renode() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "[i.MX952] Docker is not installed" >&2
        return 1
    fi

    cd "${ROOT_DIR}"
    docker run --rm \
        -v "${ROOT_DIR}:/workspace" \
        -v "${ROOT_DIR}/scripts/pydev/nxp_imx952_system_manager.py:/opt/renode/scripts/pydev/nxp_imx952_system_manager.py:ro" \
        -v "${ROOT_DIR}/scripts/pydev/nxp_imx952_system_manager_full.py:/opt/renode/scripts/pydev/nxp_imx952_system_manager_full.py:ro" \
        -v "${ROOT_DIR}/scripts/pydev/nxp_imx952_ele.py:/opt/renode/scripts/pydev/nxp_imx952_ele.py:ro" \
        -v "${ROOT_DIR}/scripts/pydev/nxp_imx952_lpi2c7.py:/opt/renode/scripts/pydev/nxp_imx952_lpi2c7.py:ro" \
        -w /workspace \
        antmicro/renode:nightly-dotnet \
        renode-test --show-log "${TESTS[@]}"
}

run_renode_checks() {
    case "${RUNTIME_MODE}" in
        local)
            run_local_renode
            ;;
        docker)
            run_docker_renode
            ;;
        auto)
            if has_built_repository_runner; then
                run_local_renode
            else
                run_docker_renode
            fi
            ;;
        *)
            echo "Usage: bash $0 [auto|local|docker] [engineering|full-physical]" >&2
            return 2
            ;;
    esac
}

run_physical_gate() {
    if [[ "${QUALIFICATION_MODE}" != "full-physical" ]]; then
        return 0
    fi

    if [[ -z "${REFERENCE_EVIDENCE}" || -z "${CANDIDATE_EVIDENCE}" ]]; then
        echo "[i.MX952] Full physical qualification requires:" >&2
        echo "  IMX952_REFERENCE_EVIDENCE=/path/to/physical-board.json" >&2
        echo "  IMX952_CANDIDATE_EVIDENCE=/path/to/digital-twin.json" >&2
        return 2
    fi

    python3 "${EQUIV_DIR}/compare_evidence.py" \
        --reference "${REFERENCE_EVIDENCE}" \
        --candidate "${CANDIDATE_EVIDENCE}" \
        --profile "${PROFILE_PATH}" \
        --output "${REPORT_PATH}"

    python3 "${EQUIV_DIR}/qualification_gate.py" \
        --mode full-physical \
        --skip-tests \
        --comparison-report "${REPORT_PATH}"
}

run_all() {
    echo "[i.MX952] Qualification mode: ${QUALIFICATION_MODE}"
    echo "[i.MX952] Runtime mode: ${RUNTIME_MODE}"
    echo "[i.MX952] Log: ${LOG_PATH}"
    run_framework_checks
    run_renode_checks
    run_physical_gate
    echo "[i.MX952] Qualification completed successfully"
}

mkdir -p "$(dirname "${LOG_PATH}")"
run_all 2>&1 | tee "${LOG_PATH}"
