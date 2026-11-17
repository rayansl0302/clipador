#!/bin/sh
set -eu

mc alias set local http://minio:9000 "$S3_ACCESS_KEY_ID" "$S3_SECRET_ACCESS_KEY"
mc mb --ignore-existing "local/${S3_BUCKET}"
echo "bucket ${S3_BUCKET} pronto"
