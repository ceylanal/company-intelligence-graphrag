#!/usr/bin/env sh
set -eu

: "${SOURCE_IMAGE:?SOURCE_IMAGE is required}"
: "${DESTINATION_IMAGE:?DESTINATION_IMAGE is required}"
: "${IMAGE_DIGEST:?IMAGE_DIGEST is required}"
: "${GITHUB_TOKEN:?GITHUB_TOKEN is required}"
: "${GITHUB_ACTOR:?GITHUB_ACTOR is required}"
: "${GCRANE_BIN:=gcrane}"

case "$IMAGE_DIGEST" in
  sha256:*) ;;
  *) echo "IMAGE_DIGEST must start with sha256:" >&2; exit 2 ;;
esac

source_ref="${SOURCE_IMAGE}@${IMAGE_DIGEST}"
destination_tag="mirror-$(printf '%s' "${IMAGE_DIGEST#sha256:}" | cut -c1-12)"
destination_ref="${DESTINATION_IMAGE}:${destination_tag}"
destination_registry="${DESTINATION_IMAGE%%/*}"

# GHCR needs the workflow token even for a repository whose package visibility
# changes later. The token never appears in a command argument or log output.
printf '%s' "$GITHUB_TOKEN" | "$GCRANE_BIN" auth login ghcr.io \
  --username "$GITHUB_ACTOR" \
  --password-stdin >/dev/null
gcloud auth configure-docker "$destination_registry" --quiet >/dev/null

# gcrane's default platform is "all", so the published OCI index is copied
# without rebuilding or collapsing its linux/amd64 and linux/arm64 manifests.
"$GCRANE_BIN" cp "$source_ref" "$destination_ref"
destination_digest="$("$GCRANE_BIN" digest "$destination_ref")"
if [ "$destination_digest" != "$IMAGE_DIGEST" ]; then
  echo "Mirrored digest mismatch: expected $IMAGE_DIGEST, got $destination_digest" >&2
  exit 1
fi

printf '%s\n' "$destination_ref"
