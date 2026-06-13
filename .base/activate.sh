# shellcheck shell=bash

if [[ -z "${BANKBUDDY_ENV:-}" ]]; then
    export BANKBUDDY_ENV=dev
fi
