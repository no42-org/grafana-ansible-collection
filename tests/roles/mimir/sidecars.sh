#!/usr/bin/env bash
#
# Start the S3-compatible object store Mimir's blocks storage needs.
#
# The retired mimir-molecule.yml workflow created this with plain `docker run`
# rather than through Molecule, so nothing Molecule-specific is being replaced
# here: the same two commands simply move into the harness.
#
# ROLE_TEST_NETWORK and ROLE_TEST_LABEL are exported by tools/role-test.sh. The
# label is what makes cleanup exhaustive without enumerating containers.

set -euo pipefail

docker run -d \
  --name "${ROLE_TEST_NETWORK}-minio" \
  --label "${ROLE_TEST_LABEL}" \
  --network "${ROLE_TEST_NETWORK}" \
  --network-alias minio \
  -e "MINIO_ROOT_USER=testtest" \
  -e "MINIO_ROOT_PASSWORD=testtest" \
  -e "MINIO_DEFAULT_BUCKETS=mimir" \
  bitnamilegacy/minio:latest >/dev/null

# Mimir fails to start if the bucket is not yet reachable, so wait for the
# store to answer rather than racing it.
for _ in $(seq 1 60); do
  if docker run --rm --network "${ROLE_TEST_NETWORK}" \
      --label "${ROLE_TEST_LABEL}" \
      curlimages/curl:latest -sf "http://minio:9000/minio/health/live" >/dev/null 2>&1; then
    exit 0
  fi
  sleep 2
done

echo >&2 "minio did not become healthy"
exit 1
