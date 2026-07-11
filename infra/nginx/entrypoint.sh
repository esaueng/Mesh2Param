#!/bin/sh
set -eu

api_url=${MESH2PARAM_API_URL:-http://api:8000}
max_upload_mb=${MESH2PARAM_MAX_UPLOAD_MB:-100}

if ! printf '%s\n' "$api_url" | grep -Eq '^http://[A-Za-z0-9][A-Za-z0-9.-]*:[0-9]{1,5}$'; then
    printf '%s\n' 'MESH2PARAM_API_URL must be an internal http://host:port URL' >&2
    exit 64
fi

api_port=${api_url##*:}
if [ "$api_port" -lt 1 ] || [ "$api_port" -gt 65535 ]; then
    printf '%s\n' 'MESH2PARAM_API_URL contains an invalid port' >&2
    exit 64
fi

case "$max_upload_mb" in
    ''|*[!0-9]*)
        printf '%s\n' 'MESH2PARAM_MAX_UPLOAD_MB must contain decimal digits only' >&2
        exit 64
        ;;
esac
if [ "$max_upload_mb" -lt 1 ] || [ "$max_upload_mb" -gt 1024 ]; then
    printf '%s\n' 'MESH2PARAM_MAX_UPLOAD_MB must be between 1 and 1024' >&2
    exit 64
fi

export MESH2PARAM_API_URL="$api_url"
export MESH2PARAM_MAX_UPLOAD_MB="$max_upload_mb"
envsubst '${MESH2PARAM_API_URL} ${MESH2PARAM_MAX_UPLOAD_MB}' \
    < /etc/mesh2param/nginx.conf.template \
    > /tmp/nginx.conf

exec "$@"
