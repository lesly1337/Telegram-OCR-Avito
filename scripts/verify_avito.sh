#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

was_running=0
restore_bot() {
    local status=$?
    trap - EXIT
    if [[ "$was_running" == 1 ]]; then
        echo "Запускаю бота снова..."
        if ! docker compose start bot; then
            echo "Не удалось запустить бота. Выполните: docker compose start bot" >&2
            status=1
        fi
    fi
    exit "$status"
}
trap restore_bot EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -n "$(docker compose ps --status running --quiet bot)" ]]; then
    echo "Останавливаю бота на время проверки Avito..."
    was_running=1
    docker compose stop bot
fi

echo "Пройдите проверку Avito в открывшемся окне и закройте браузер."
docker compose run --rm --no-deps -e "DISPLAY=${DISPLAY:-:0}" \
    -v /mnt/wslg/.X11-unix:/tmp/.X11-unix \
    -v "$PWD/scripts/avito_verify.py:/app/scripts/avito_verify.py:ro" \
    --entrypoint python bot -m scripts.avito_verify
