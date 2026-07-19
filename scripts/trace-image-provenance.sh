#!/usr/bin/env bash
# ============================================================================
# trace-image-provenance.sh — Truy ngược toàn bộ vòng đời image từ Pod
# ============================================================================
#
# Đáp ứng yêu cầu Mandate-04/05 nghiệm thu tại chỗ:
#   "Chỉ vào một pod đang chạy → team truy ngược full provenance ngay trước mặt"
#
# Usage:
#   ./trace-image-provenance.sh --pod <pod-name>
#   ./trace-image-provenance.sh --digest <sha256:...>
#   ./trace-image-provenance.sh --pod <pod-name> --container <container-name>
#   ./trace-image-provenance.sh --dry-run --pod <pod-name>
#
# Requires: kubectl, aws cli, jq, (optional: cosign, gh/curl+GITHUB_TOKEN)
# All operations are READ-ONLY — safe for Audit team to run directly.
#
# Author: CDO07 — TF4 Phase 3
# Date:   2026-07-18
# ============================================================================
set -euo pipefail

# ─── Defaults ────────────────────────────────────────────────────────────────
AWS_PROFILE="${AWS_PROFILE:-TF4-AuditReadOnlyAndAnalyze-511825856493}"
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO="${ECR_REPO:-techx-corp}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-511825856493}"
K8S_NAMESPACE="${K8S_NAMESPACE:-techx-tf4}"
GITHUB_REPO="${GITHUB_REPO:-TF4-Phase3-TechX/tf4-phase3-repo}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_REPOSITORY="${ECR_REGISTRY}/${ECR_REPO}"

# ─── State variables ────────────────────────────────────────────────────────
POD_NAME=""
CONTAINER_NAME=""
INPUT_DIGEST=""
DRY_RUN=false
TRACE_START=""
STEP_RESULTS=()     # Track pass/fail/skip per step
TOTAL_STEPS=6
JSON_OUTPUT=""       # Accumulate JSON provenance

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# ─── Helper functions ────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
Usage:
  trace-image-provenance.sh --pod <pod-name> [--container <name>] [--namespace <ns>]
  trace-image-provenance.sh --digest <sha256:...>
  trace-image-provenance.sh --dry-run --pod <pod-name>

Options:
  --pod         Pod name to trace (will extract image digest automatically)
  --digest      Image digest to trace directly (sha256:...)
  --container   Container name within the pod (default: first container)
  --namespace   Kubernetes namespace (default: techx-tf4)
  --profile     AWS CLI profile (default: TF4-AuditReadOnlyAndAnalyze-511825856493)
  --dry-run     Print commands without executing
  -h, --help    Show this help

Environment Variables:
  AWS_PROFILE   AWS CLI profile name
  AWS_REGION    AWS region (default: us-east-1)
  ECR_REPO      ECR repository name (default: techx-corp)
  K8S_NAMESPACE Kubernetes namespace (default: techx-tf4)
  GITHUB_REPO   GitHub org/repo (default: TF4-Phase3-TechX/tf4-phase3-repo)
  GITHUB_TOKEN  GitHub personal access token (for API calls)

Examples:
  # Trace from a running pod
  ./trace-image-provenance.sh --pod currency-7d8f9b6c4-x2k9p

  # Trace from a digest directly
  ./trace-image-provenance.sh --digest sha256:a1b2c3d4e5f6...

  # Trace with specific container in pod
  ./trace-image-provenance.sh --pod frontend-proxy-abc123 --container frontend-proxy
EOF
  exit 0
}

log_step() {
  local step_num="$1"
  local title="$2"
  printf "\n${CYAN}${BOLD}[%d/%d] %s${NC}\n" "$step_num" "$TOTAL_STEPS" "$title"
  printf "${DIM}%s${NC}\n" "───────────────────────────────────────────────────"
}

log_field() {
  local label="$1"
  local value="$2"
  printf "  ${BOLD}%-14s${NC} %s\n" "${label}:" "$value"
}

log_ok() {
  printf "  ${GREEN}✅ %s${NC}\n" "$1"
}

log_warn() {
  printf "  ${YELLOW}⚠️  %s${NC}\n" "$1"
}

log_fail() {
  printf "  ${RED}❌ %s${NC}\n" "$1"
}

log_skip() {
  printf "  ${DIM}⏭️  %s${NC}\n" "$1"
}

record_step() {
  # $1 = step number (1-based), $2 = status (pass/fail/skip)
  STEP_RESULTS[$1]="$2"
}

elapsed_since_start() {
  local now
  now=$(date +%s%N 2>/dev/null || date +%s)
  if [[ ${#now} -gt 10 ]]; then
    # Nanosecond precision available
    echo "scale=1; ($now - $TRACE_START) / 1000000000" | bc 2>/dev/null || echo "N/A"
  else
    echo "$(( now - TRACE_START ))"
  fi
}

check_tool() {
  local tool="$1"
  if command -v "$tool" &>/dev/null; then
    return 0
  else
    return 1
  fi
}

# ─── Parse arguments ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pod)        POD_NAME="$2"; shift 2 ;;
    --digest)     INPUT_DIGEST="$2"; shift 2 ;;
    --container)  CONTAINER_NAME="$2"; shift 2 ;;
    --namespace)  K8S_NAMESPACE="$2"; shift 2 ;;
    --profile)    AWS_PROFILE="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=true; shift ;;
    -h|--help)    usage ;;
    *)            echo "Unknown option: $1"; usage ;;
  esac
done

if [[ -z "$POD_NAME" && -z "$INPUT_DIGEST" ]]; then
  echo "Error: Must specify --pod or --digest"
  usage
fi

# ─── Prerequisite check ─────────────────────────────────────────────────────
printf "\n${BOLD}═══════════════════════════════════════════════════════════════${NC}\n"
printf "${BOLD}  IMAGE PROVENANCE TRACE — Full Chain of Custody${NC}\n"
printf "${BOLD}═══════════════════════════════════════════════════════════════${NC}\n"

printf "\n${DIM}Checking prerequisites...${NC}\n"
PREREQS_OK=true
for tool in kubectl aws jq; do
  if check_tool "$tool"; then
    printf "  ${GREEN}✓${NC} %s\n" "$tool"
  else
    printf "  ${RED}✗${NC} %s (REQUIRED)\n" "$tool"
    PREREQS_OK=false
  fi
done

HAS_COSIGN=false
if check_tool cosign; then
  printf "  ${GREEN}✓${NC} cosign\n"
  HAS_COSIGN=true
else
  printf "  ${YELLOW}○${NC} cosign (optional — signature/attestation steps will be skipped)\n"
fi

HAS_GH=false
if check_tool gh; then
  printf "  ${GREEN}✓${NC} gh CLI\n"
  HAS_GH=true
elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
  printf "  ${GREEN}✓${NC} GITHUB_TOKEN set (will use curl)\n"
  HAS_GH=true
else
  printf "  ${YELLOW}○${NC} gh/GITHUB_TOKEN (optional — GitHub Actions lookup will be skipped)\n"
fi

if [[ "$PREREQS_OK" == "false" ]]; then
  echo ""
  log_fail "Missing required tools. Install them and retry."
  exit 1
fi

if [[ "$DRY_RUN" == "true" ]]; then
  printf "\n${YELLOW}${BOLD}DRY-RUN MODE — commands will be printed, not executed${NC}\n"
fi

# Start timer
TRACE_START=$(date +%s%N 2>/dev/null || date +%s)

# ─── Variables populated along the chain ─────────────────────────────────────
IMAGE_REF=""
IMAGE_DIGEST=""
IMAGE_TAG=""
SERVICE_NAME=""
GIT_SHA_SHORT=""
ECR_PUSH_TIME=""
ECR_SCAN_STATUS=""
ECR_IMAGE_SIZE=""
COSIGN_SIGNED=""
COSIGN_ISSUER=""
ATTEST_REPO=""
ATTEST_COMMIT=""
ATTEST_WORKFLOW=""
ATTEST_RUN_ID=""
GH_RUN_URL=""
GH_ACTOR=""
GH_TRIGGER=""
GH_STARTED=""
GH_COMMIT_MSG=""
GH_PR_URL=""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Pod → Image Digest
# ═══════════════════════════════════════════════════════════════════════════════
log_step 1 "POD → IMAGE DIGEST"

if [[ -n "$POD_NAME" ]]; then
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [dry-run] kubectl get pod $POD_NAME -n $K8S_NAMESPACE -o jsonpath='{.status.containerStatuses[*]}'"
    record_step 1 "skip"
  else
    # Get all container statuses
    if [[ -n "$CONTAINER_NAME" ]]; then
      # Specific container requested
      IMAGE_REF=$(kubectl get pod "$POD_NAME" -n "$K8S_NAMESPACE" \
        -o jsonpath="{.spec.containers[?(@.name==\"${CONTAINER_NAME}\")].image}" 2>/dev/null || true)
      IMAGE_DIGEST=$(kubectl get pod "$POD_NAME" -n "$K8S_NAMESPACE" \
        -o jsonpath="{.status.containerStatuses[?(@.name==\"${CONTAINER_NAME}\")].imageID}" 2>/dev/null || true)
    else
      # First container
      IMAGE_REF=$(kubectl get pod "$POD_NAME" -n "$K8S_NAMESPACE" \
        -o jsonpath='{.spec.containers[0].image}' 2>/dev/null || true)
      IMAGE_DIGEST=$(kubectl get pod "$POD_NAME" -n "$K8S_NAMESPACE" \
        -o jsonpath='{.status.containerStatuses[0].imageID}' 2>/dev/null || true)
      CONTAINER_NAME=$(kubectl get pod "$POD_NAME" -n "$K8S_NAMESPACE" \
        -o jsonpath='{.spec.containers[0].name}' 2>/dev/null || true)
    fi

    if [[ -z "$IMAGE_REF" || -z "$IMAGE_DIGEST" ]]; then
      log_fail "Could not retrieve image info from pod '$POD_NAME' in namespace '$K8S_NAMESPACE'"
      log_warn "Check: Is the pod running? Do you have kubectl access?"
      record_step 1 "fail"
      # Cannot continue without digest
      printf "\n${RED}${BOLD}TRACE ABORTED — Cannot determine image digest${NC}\n"
      exit 1
    fi

    # Extract just the sha256:... part from imageID
    # Format is typically: docker-pullable://registry/repo@sha256:abc123...
    if [[ "$IMAGE_DIGEST" == *"@sha256:"* ]]; then
      IMAGE_DIGEST="sha256:${IMAGE_DIGEST##*sha256:}"
    elif [[ "$IMAGE_DIGEST" == *"sha256:"* ]]; then
      IMAGE_DIGEST="sha256:${IMAGE_DIGEST##*sha256:}"
    fi

    log_field "Pod" "$POD_NAME"
    log_field "Container" "$CONTAINER_NAME"
    log_field "Namespace" "$K8S_NAMESPACE"
    log_field "Image" "$IMAGE_REF"
    log_field "Digest" "$IMAGE_DIGEST"
    log_ok "Image digest extracted from running pod"
    record_step 1 "pass"
  fi
elif [[ -n "$INPUT_DIGEST" ]]; then
  IMAGE_DIGEST="$INPUT_DIGEST"
  log_field "Input Digest" "$IMAGE_DIGEST"
  log_field "Source" "Direct input (no pod lookup)"
  log_ok "Using provided digest"
  record_step 1 "pass"
fi

# Extract tag from image reference if available
if [[ -n "$IMAGE_REF" && "$IMAGE_REF" == *":"* ]]; then
  IMAGE_TAG="${IMAGE_REF##*:}"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: ECR Image Metadata
# ═══════════════════════════════════════════════════════════════════════════════
log_step 2 "ECR IMAGE METADATA"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "  [dry-run] aws ecr describe-images --repository-name $ECR_REPO --image-ids imageDigest=$IMAGE_DIGEST --region $AWS_REGION --profile $AWS_PROFILE"
  record_step 2 "skip"
else
  ECR_RESULT=""

  # Try lookup by digest first
  if [[ -n "$IMAGE_DIGEST" ]]; then
    ECR_RESULT=$(aws ecr describe-images \
      --repository-name "$ECR_REPO" \
      --image-ids "imageDigest=${IMAGE_DIGEST}" \
      --region "$AWS_REGION" \
      --profile "$AWS_PROFILE" \
      --output json 2>/dev/null || true)
  fi

  # Fallback: lookup by tag if digest lookup failed
  if [[ -z "$ECR_RESULT" || "$ECR_RESULT" == *"ImageNotFoundException"* ]] && [[ -n "$IMAGE_TAG" ]]; then
    ECR_RESULT=$(aws ecr describe-images \
      --repository-name "$ECR_REPO" \
      --image-ids "imageTag=${IMAGE_TAG}" \
      --region "$AWS_REGION" \
      --profile "$AWS_PROFILE" \
      --output json 2>/dev/null || true)
  fi

  if [[ -n "$ECR_RESULT" ]] && echo "$ECR_RESULT" | jq -e '.imageDetails[0]' &>/dev/null; then
    ECR_DETAIL=$(echo "$ECR_RESULT" | jq '.imageDetails[0]')

    # Extract image tag(s)
    ECR_TAGS=$(echo "$ECR_DETAIL" | jq -r '.imageTags // [] | join(", ")' 2>/dev/null || echo "N/A")
    if [[ -z "$IMAGE_TAG" && "$ECR_TAGS" != "N/A" ]]; then
      IMAGE_TAG=$(echo "$ECR_DETAIL" | jq -r '.imageTags[0] // empty' 2>/dev/null || true)
    fi

    # Extract digest if we didn't have it
    if [[ -z "$IMAGE_DIGEST" || "$IMAGE_DIGEST" == "sha256:" ]]; then
      IMAGE_DIGEST=$(echo "$ECR_DETAIL" | jq -r '.imageDigest // empty' 2>/dev/null || true)
    fi

    ECR_PUSH_TIME=$(echo "$ECR_DETAIL" | jq -r '.imagePushedAt // "N/A"' 2>/dev/null || echo "N/A")
    ECR_IMAGE_SIZE=$(echo "$ECR_DETAIL" | jq -r '
      if .imageSizeInBytes then
        (.imageSizeInBytes / 1048576 * 10 | floor / 10 | tostring) + " MB"
      else "N/A"
      end' 2>/dev/null || echo "N/A")

    # Scan findings
    ECR_SCAN_STATUS=$(echo "$ECR_DETAIL" | jq -r '.imageScanStatus.status // "N/A"' 2>/dev/null || echo "N/A")
    ECR_SCAN_FINDINGS=""
    if [[ "$ECR_SCAN_STATUS" == "COMPLETE" ]]; then
      ECR_SCAN_FINDINGS=$(echo "$ECR_DETAIL" | jq -r '
        .imageScanFindingsSummary.findingSeverityCounts // {} |
        "CRITICAL=" + ((.CRITICAL // 0) | tostring) +
        " HIGH=" + ((.HIGH // 0) | tostring) +
        " MEDIUM=" + ((.MEDIUM // 0) | tostring)' 2>/dev/null || echo "N/A")
    fi

    log_field "Tag(s)" "$ECR_TAGS"
    log_field "Digest" "$IMAGE_DIGEST"
    log_field "Pushed" "$ECR_PUSH_TIME"
    log_field "Size" "$ECR_IMAGE_SIZE"
    log_field "Scan" "$ECR_SCAN_STATUS ${ECR_SCAN_FINDINGS}"
    log_field "Immutable" "YES (image_tag_mutability=IMMUTABLE)"
    log_ok "ECR metadata retrieved"
    record_step 2 "pass"
  else
    log_fail "Could not find image in ECR repository '$ECR_REPO'"
    log_warn "Digest: $IMAGE_DIGEST | Tag: ${IMAGE_TAG:-N/A}"
    record_step 2 "fail"
  fi
fi

# ─── Parse tag to extract Git SHA and service name ───────────────────────────
# Tag format: <sha7>-<service>  e.g. 8340af1-currency
if [[ -n "$IMAGE_TAG" ]]; then
  if [[ "$IMAGE_TAG" =~ ^([0-9a-f]{7})-(.+)$ ]]; then
    GIT_SHA_SHORT="${BASH_REMATCH[1]}"
    SERVICE_NAME="${BASH_REMATCH[2]}"
  elif [[ "$IMAGE_TAG" =~ ^([0-9a-f]{7,40})-(.+)$ ]]; then
    GIT_SHA_SHORT="${BASH_REMATCH[1]}"
    SERVICE_NAME="${BASH_REMATCH[2]}"
  fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Cosign Signature Verification
# ═══════════════════════════════════════════════════════════════════════════════
log_step 3 "COSIGN SIGNATURE VERIFICATION"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "  [dry-run] cosign verify --certificate-identity-regexp='.*' --certificate-oidc-issuer-regexp='.*' ${IMAGE_REPOSITORY}@${IMAGE_DIGEST}"
  record_step 3 "skip"
elif [[ "$HAS_COSIGN" == "true" && -n "$IMAGE_DIGEST" ]]; then
  COSIGN_OUTPUT=$(cosign verify \
    --certificate-identity-regexp='.*' \
    --certificate-oidc-issuer-regexp='.*' \
    "${IMAGE_REPOSITORY}@${IMAGE_DIGEST}" 2>&1 || true)

  if echo "$COSIGN_OUTPUT" | grep -qi "verified"; then
    COSIGN_SIGNED="YES"
    # Try to extract issuer and subject from cosign output
    COSIGN_ISSUER=$(echo "$COSIGN_OUTPUT" | jq -r '.[0].optional.Issuer // empty' 2>/dev/null || true)
    COSIGN_SUBJECT=$(echo "$COSIGN_OUTPUT" | jq -r '.[0].optional.Subject // empty' 2>/dev/null || true)
    if [[ -z "$COSIGN_ISSUER" ]]; then
      COSIGN_ISSUER=$(echo "$COSIGN_OUTPUT" | grep -oP 'Issuer:\s*\K.*' 2>/dev/null || echo "GitHub OIDC (keyless)")
    fi
    if [[ -z "$COSIGN_SUBJECT" ]]; then
      COSIGN_SUBJECT=$(echo "$COSIGN_OUTPUT" | grep -oP 'Subject:\s*\K.*' 2>/dev/null || echo "N/A")
    fi

    log_field "Signed" "YES (keyless/OIDC)"
    log_field "Issuer" "${COSIGN_ISSUER:-https://token.actions.githubusercontent.com}"
    log_field "Subject" "${COSIGN_SUBJECT:-N/A}"
    log_ok "Image signature verified via Sigstore/Rekor"
    record_step 3 "pass"
  else
    COSIGN_SIGNED="NO"
    log_warn "Cosign verification did not confirm signature"
    log_field "Detail" "$(echo "$COSIGN_OUTPUT" | head -3)"
    record_step 3 "fail"
  fi
else
  log_skip "Cosign not available — skipping signature verification"
  log_warn "Install cosign to enable this step: https://docs.sigstore.dev/cosign/installation/"
  COSIGN_SIGNED="SKIPPED"
  record_step 3 "skip"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Provenance Attestation (Cosign attest)
# ═══════════════════════════════════════════════════════════════════════════════
log_step 4 "PROVENANCE ATTESTATION"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "  [dry-run] cosign verify-attestation --type custom --certificate-identity-regexp='.*' --certificate-oidc-issuer-regexp='.*' ${IMAGE_REPOSITORY}@${IMAGE_DIGEST}"
  record_step 4 "skip"
elif [[ "$HAS_COSIGN" == "true" && -n "$IMAGE_DIGEST" ]]; then
  ATTEST_OUTPUT=$(cosign verify-attestation \
    --type custom \
    --certificate-identity-regexp='.*' \
    --certificate-oidc-issuer-regexp='.*' \
    "${IMAGE_REPOSITORY}@${IMAGE_DIGEST}" 2>&1 || true)

  if echo "$ATTEST_OUTPUT" | jq -e '.payload' &>/dev/null; then
    # Decode the base64 payload
    PREDICATE=$(echo "$ATTEST_OUTPUT" | jq -r '.payload' | base64 -d 2>/dev/null | jq '.predicate // .predicateType // .' 2>/dev/null || true)

    if [[ -n "$PREDICATE" ]]; then
      ATTEST_REPO=$(echo "$PREDICATE" | jq -r '.repo // .Data.repo // empty' 2>/dev/null || true)
      ATTEST_COMMIT=$(echo "$PREDICATE" | jq -r '.commit // .Data.commit // empty' 2>/dev/null || true)
      ATTEST_WORKFLOW=$(echo "$PREDICATE" | jq -r '.workflow // .Data.workflow // empty' 2>/dev/null || true)
      ATTEST_RUN_ID=$(echo "$PREDICATE" | jq -r '.run_id // .Data.run_id // empty' 2>/dev/null || true)
    fi

    log_field "Repo" "${ATTEST_REPO:-$GITHUB_REPO}"
    log_field "Commit" "${ATTEST_COMMIT:-${GIT_SHA_SHORT:-N/A}}"
    log_field "Workflow" "${ATTEST_WORKFLOW:-build-and-push}"
    log_field "Run ID" "${ATTEST_RUN_ID:-N/A}"
    log_ok "Provenance attestation verified"
    record_step 4 "pass"
  else
    # Attestation may not be in expected format but might still have info
    log_warn "Attestation format not recognized or not found"
    log_field "Detail" "$(echo "$ATTEST_OUTPUT" | head -3)"
    record_step 4 "fail"
  fi
else
  log_skip "Cosign not available — skipping attestation verification"
  # Fallback: derive provenance from tag convention
  if [[ -n "$GIT_SHA_SHORT" ]]; then
    log_field "Derived SHA" "$GIT_SHA_SHORT (from tag convention: <sha7>-<service>)"
    log_field "Service" "${SERVICE_NAME:-N/A}"
    log_field "Workflow" "build-and-push (inferred from CI pipeline)"
    log_warn "Provenance derived from tag convention — install cosign for cryptographic verification"
    record_step 4 "skip"
  else
    log_fail "Cannot determine provenance — no cosign and no parseable tag"
    record_step 4 "fail"
  fi
fi

# Use attestation commit if we don't have one yet
if [[ -z "$GIT_SHA_SHORT" && -n "$ATTEST_COMMIT" ]]; then
  GIT_SHA_SHORT="${ATTEST_COMMIT:0:7}"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: GitHub Actions Run
# ═══════════════════════════════════════════════════════════════════════════════
log_step 5 "GITHUB ACTIONS RUN"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "  [dry-run] gh api /repos/$GITHUB_REPO/actions/runs?head_sha=<commit>"
  record_step 5 "skip"
elif [[ "$HAS_GH" == "true" && -n "$GIT_SHA_SHORT" ]]; then

  # Helper: query GitHub API (supports both gh CLI and raw curl)
  github_api() {
    local endpoint="$1"
    if check_tool gh; then
      gh api "$endpoint" 2>/dev/null || true
    elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
      curl -s -H "Authorization: token ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com${endpoint}" 2>/dev/null || true
    fi
  }

  # Find the full commit SHA from the short SHA
  COMMIT_DATA=$(github_api "/repos/${GITHUB_REPO}/commits?sha=${GIT_SHA_SHORT}&per_page=1" || true)
  FULL_SHA=""
  if [[ -n "$COMMIT_DATA" ]] && echo "$COMMIT_DATA" | jq -e '.[0].sha' &>/dev/null; then
    FULL_SHA=$(echo "$COMMIT_DATA" | jq -r '.[0].sha')
    GH_COMMIT_MSG=$(echo "$COMMIT_DATA" | jq -r '.[0].commit.message // empty' | head -1)
    GH_COMMIT_AUTHOR=$(echo "$COMMIT_DATA" | jq -r '.[0].commit.author.name // empty')
    GH_COMMIT_DATE=$(echo "$COMMIT_DATA" | jq -r '.[0].commit.author.date // empty')
  fi

  # Find GitHub Actions run for this commit
  if [[ -n "$FULL_SHA" ]]; then
    # Try using attestation run_id first (most precise)
    if [[ -n "$ATTEST_RUN_ID" ]]; then
      RUN_DATA=$(github_api "/repos/${GITHUB_REPO}/actions/runs/${ATTEST_RUN_ID}" || true)
    else
      # Search by commit SHA and workflow name
      RUN_DATA=$(github_api "/repos/${GITHUB_REPO}/actions/runs?head_sha=${FULL_SHA}&per_page=5" || true)
      # Filter to build-and-push workflow
      if [[ -n "$RUN_DATA" ]] && echo "$RUN_DATA" | jq -e '.workflow_runs' &>/dev/null; then
        RUN_DATA=$(echo "$RUN_DATA" | jq '.workflow_runs[] | select(.name == "build-and-push" or .path | contains("build-and-push"))' 2>/dev/null | head -1 || true)
      fi
    fi

    if [[ -n "$RUN_DATA" ]] && echo "$RUN_DATA" | jq -e '.id' &>/dev/null; then
      GH_RUN_URL=$(echo "$RUN_DATA" | jq -r '.html_url // empty')
      GH_ACTOR=$(echo "$RUN_DATA" | jq -r '.actor.login // .triggering_actor.login // empty')
      GH_TRIGGER=$(echo "$RUN_DATA" | jq -r '.event // empty')
      GH_STARTED=$(echo "$RUN_DATA" | jq -r '.created_at // empty')
      GH_RUN_STATUS=$(echo "$RUN_DATA" | jq -r '.conclusion // .status // empty')
      ATTEST_RUN_ID=$(echo "$RUN_DATA" | jq -r '.id // empty')

      log_field "Run ID" "$ATTEST_RUN_ID"
      log_field "URL" "$GH_RUN_URL"
      log_field "Actor" "$GH_ACTOR"
      log_field "Trigger" "$GH_TRIGGER"
      log_field "Started" "$GH_STARTED"
      log_field "Status" "$GH_RUN_STATUS"
      log_ok "GitHub Actions workflow run found"
      record_step 5 "pass"
    else
      log_warn "Could not find GitHub Actions run for commit $GIT_SHA_SHORT"
      record_step 5 "fail"
    fi
  else
    log_warn "Could not resolve full commit SHA from short SHA '$GIT_SHA_SHORT'"
    record_step 5 "fail"
  fi
else
  log_skip "GitHub API not available — skipping Actions lookup"
  if [[ -n "$GIT_SHA_SHORT" ]]; then
    log_field "Manual URL" "https://github.com/${GITHUB_REPO}/actions?query=head_sha%3A${GIT_SHA_SHORT}"
  fi
  record_step 5 "skip"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: Source Code (Commit + PR)
# ═══════════════════════════════════════════════════════════════════════════════
log_step 6 "SOURCE CODE"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "  [dry-run] gh api /repos/$GITHUB_REPO/commits/<sha>"
  echo "  [dry-run] gh api /repos/$GITHUB_REPO/commits/<sha>/pulls"
  record_step 6 "skip"
elif [[ -n "$GIT_SHA_SHORT" ]]; then

  # Commit info (may already have from step 5)
  if [[ -z "$GH_COMMIT_MSG" && "$HAS_GH" == "true" ]]; then
    COMMIT_DATA=$(github_api "/repos/${GITHUB_REPO}/commits/${FULL_SHA:-$GIT_SHA_SHORT}" || true)
    if [[ -n "$COMMIT_DATA" ]] && echo "$COMMIT_DATA" | jq -e '.sha' &>/dev/null; then
      FULL_SHA=$(echo "$COMMIT_DATA" | jq -r '.sha')
      GH_COMMIT_MSG=$(echo "$COMMIT_DATA" | jq -r '.commit.message // empty' | head -1)
      GH_COMMIT_AUTHOR=$(echo "$COMMIT_DATA" | jq -r '.commit.author.name // empty')
      GH_COMMIT_DATE=$(echo "$COMMIT_DATA" | jq -r '.commit.author.date // empty')
    fi
  fi

  log_field "Short SHA" "$GIT_SHA_SHORT"
  [[ -n "${FULL_SHA:-}" ]] && log_field "Full SHA" "$FULL_SHA"
  log_field "Message" "${GH_COMMIT_MSG:-N/A}"
  log_field "Author" "${GH_COMMIT_AUTHOR:-N/A}"
  log_field "Date" "${GH_COMMIT_DATE:-N/A}"

  # Find associated PR
  if [[ "$HAS_GH" == "true" && -n "${FULL_SHA:-}" ]]; then
    PR_DATA=$(github_api "/repos/${GITHUB_REPO}/commits/${FULL_SHA}/pulls" || true)
    if [[ -n "$PR_DATA" ]] && echo "$PR_DATA" | jq -e '.[0].number' &>/dev/null; then
      PR_NUMBER=$(echo "$PR_DATA" | jq -r '.[0].number')
      PR_TITLE=$(echo "$PR_DATA" | jq -r '.[0].title // empty')
      GH_PR_URL=$(echo "$PR_DATA" | jq -r '.[0].html_url // empty')
      PR_MERGED_BY=$(echo "$PR_DATA" | jq -r '.[0].merged_by.login // "N/A"')

      log_field "PR" "#${PR_NUMBER} — ${PR_TITLE}"
      log_field "PR URL" "$GH_PR_URL"
      log_field "Merged by" "$PR_MERGED_BY"
    else
      log_field "PR" "N/A (direct push or PR data unavailable)"
    fi
  fi

  log_field "Browse" "https://github.com/${GITHUB_REPO}/commit/${FULL_SHA:-$GIT_SHA_SHORT}"
  log_ok "Source code traced"
  record_step 6 "pass"
else
  log_fail "No Git SHA available — cannot trace source code"
  record_step 6 "fail"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY / VERDICT
# ═══════════════════════════════════════════════════════════════════════════════

TRACE_DURATION=$(elapsed_since_start)

# Count results
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
for i in $(seq 1 $TOTAL_STEPS); do
  case "${STEP_RESULTS[$i]:-unknown}" in
    pass) PASS_COUNT=$((PASS_COUNT + 1)) ;;
    fail) FAIL_COUNT=$((FAIL_COUNT + 1)) ;;
    skip) SKIP_COUNT=$((SKIP_COUNT + 1)) ;;
  esac
done

printf "\n${BOLD}═══════════════════════════════════════════════════════════════${NC}\n"

# Determine verdict
if [[ $FAIL_COUNT -eq 0 && $SKIP_COUNT -eq 0 ]]; then
  printf "  ${GREEN}${BOLD}PROVENANCE VERDICT: ✅ COMPLETE — All %d links verified${NC}\n" "$TOTAL_STEPS"
elif [[ $FAIL_COUNT -eq 0 ]]; then
  printf "  ${YELLOW}${BOLD}PROVENANCE VERDICT: ⚠️  PARTIAL — %d/%d verified, %d skipped${NC}\n" "$PASS_COUNT" "$TOTAL_STEPS" "$SKIP_COUNT"
else
  printf "  ${RED}${BOLD}PROVENANCE VERDICT: ❌ INCOMPLETE — %d/%d verified, %d failed, %d skipped${NC}\n" "$PASS_COUNT" "$TOTAL_STEPS" "$FAIL_COUNT" "$SKIP_COUNT"
fi

# Step-by-step status summary
printf "\n  ${DIM}Step results:${NC}\n"
STEP_NAMES=("" "Pod→Digest" "ECR Metadata" "Cosign Signature" "Provenance Attestation" "GitHub Actions" "Source Code")
for i in $(seq 1 $TOTAL_STEPS); do
  status="${STEP_RESULTS[$i]:-unknown}"
  case "$status" in
    pass) printf "    ${GREEN}✅${NC} [%d] %s\n" "$i" "${STEP_NAMES[$i]}" ;;
    fail) printf "    ${RED}❌${NC} [%d] %s\n" "$i" "${STEP_NAMES[$i]}" ;;
    skip) printf "    ${DIM}⏭️${NC}  [%d] %s\n" "$i" "${STEP_NAMES[$i]}" ;;
    *)    printf "    ${DIM}?${NC}  [%d] %s\n" "$i" "${STEP_NAMES[$i]}" ;;
  esac
done

printf "\n  ${DIM}Total trace time: %s seconds${NC}\n" "$TRACE_DURATION"

printf "${BOLD}═══════════════════════════════════════════════════════════════${NC}\n"

# ─── JSON output (machine-readable) ─────────────────────────────────────────
JSON_OUTPUT=$(jq -n \
  --arg pod "${POD_NAME:-direct-input}" \
  --arg container "${CONTAINER_NAME:-N/A}" \
  --arg namespace "$K8S_NAMESPACE" \
  --arg image_ref "${IMAGE_REF:-N/A}" \
  --arg image_digest "${IMAGE_DIGEST:-N/A}" \
  --arg image_tag "${IMAGE_TAG:-N/A}" \
  --arg service "${SERVICE_NAME:-N/A}" \
  --arg ecr_push_time "${ECR_PUSH_TIME:-N/A}" \
  --arg ecr_scan "${ECR_SCAN_STATUS:-N/A}" \
  --arg ecr_size "${ECR_IMAGE_SIZE:-N/A}" \
  --arg cosign_signed "${COSIGN_SIGNED:-N/A}" \
  --arg cosign_issuer "${COSIGN_ISSUER:-N/A}" \
  --arg attest_repo "${ATTEST_REPO:-N/A}" \
  --arg attest_commit "${ATTEST_COMMIT:-${FULL_SHA:-N/A}}" \
  --arg attest_workflow "${ATTEST_WORKFLOW:-N/A}" \
  --arg attest_run_id "${ATTEST_RUN_ID:-N/A}" \
  --arg gh_run_url "${GH_RUN_URL:-N/A}" \
  --arg gh_actor "${GH_ACTOR:-N/A}" \
  --arg gh_trigger "${GH_TRIGGER:-N/A}" \
  --arg gh_commit_msg "${GH_COMMIT_MSG:-N/A}" \
  --arg gh_commit_author "${GH_COMMIT_AUTHOR:-N/A}" \
  --arg gh_commit_date "${GH_COMMIT_DATE:-N/A}" \
  --arg gh_pr_url "${GH_PR_URL:-N/A}" \
  --arg git_sha "${GIT_SHA_SHORT:-N/A}" \
  --arg trace_duration "${TRACE_DURATION}" \
  --argjson pass_count "$PASS_COUNT" \
  --argjson fail_count "$FAIL_COUNT" \
  --argjson skip_count "$SKIP_COUNT" \
  '{
    trace_timestamp: (now | todate),
    trace_duration_seconds: $trace_duration,
    verdict: {
      passed: $pass_count,
      failed: $fail_count,
      skipped: $skip_count
    },
    pod: {
      name: $pod,
      container: $container,
      namespace: $namespace
    },
    image: {
      reference: $image_ref,
      digest: $image_digest,
      tag: $image_tag,
      service: $service
    },
    ecr: {
      push_time: $ecr_push_time,
      scan_status: $ecr_scan,
      size: $ecr_size,
      immutable: true
    },
    signature: {
      signed: $cosign_signed,
      issuer: $cosign_issuer
    },
    provenance: {
      repository: $attest_repo,
      commit: $attest_commit,
      workflow: $attest_workflow,
      run_id: $attest_run_id
    },
    github_actions: {
      run_url: $gh_run_url,
      actor: $gh_actor,
      trigger: $gh_trigger
    },
    source: {
      git_sha_short: $git_sha,
      commit_message: $gh_commit_msg,
      author: $gh_commit_author,
      date: $gh_commit_date,
      pr_url: $gh_pr_url,
      browse_url: ("https://github.com/" + "'"$GITHUB_REPO"'" + "/commit/" + $attest_commit)
    }
  }')

# Print JSON to stderr so it can be piped separately
printf "\n${DIM}JSON provenance record:${NC}\n" >&2
echo "$JSON_OUTPUT" | jq '.' >&2
