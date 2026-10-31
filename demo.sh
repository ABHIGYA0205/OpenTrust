#!/usr/bin/env bash
# OpenTrust live demo: the whole Problem 07 story in about three minutes.
#
#   ./demo.sh              pauses between steps (press Enter to go on)
#   DEMO_FAST=1 ./demo.sh  runs straight through (used for examples/demo-output.txt)
#
# Uses the committed 40-project network in network/. Works with or without Ollama:
# with both models running you also get Tier-2 similarity and the model-written
# summary; without them every step still runs on the deterministic code.
set -euo pipefail
cd "$(dirname "$0")"

MANIFEST=network/manifest.json
INCOMING=network/incoming

step() {
  printf '\n\033[1m== %s\033[0m\n' "$1"
  if [ -z "${DEMO_FAST:-}" ]; then read -r -p "(Enter) " _; fi
}
run() {
  local line="$*"
  if [ -n "${work:-}" ]; then line="${line//$work\//}"; fi
  printf '$ %s\n' "$line"
  "$@" || true # campaigns exits 1 when it finds one; that's the point of the demo
}

if opentrust models | grep -q "both models reachable"; then
  MODELS=1
else
  MODELS=
  echo "Ollama models not reachable: running on the deterministic fallback only."
fi

step "1. Forty projects, each with its own signed trust records. Nothing central."
printf '$ opentrust sync --manifest %s\n' "$MANIFEST"
opentrust sync --manifest "$MANIFEST" | sed -n '1,6p;$p'

step "2. A spam campaign hits the network. No single maintainer could see it."
if [ -n "$MODELS" ]; then
  run opentrust campaigns --incoming "$INCOMING" --tier2 --narrate
else
  run opentrust campaigns --incoming "$INCOMING"
fi

step "3. @new-dev, seen from proj-a: let in on a vouch from proj-b, which proj-a trusts. proj-x's denouncement is ignored."
run opentrust score --manifest "$MANIFEST" --subject github:@new-dev --viewer proj-a

step "4. Same person, seen from proj-x. proj-x's opinion only governs proj-x."
run opentrust score --manifest "$MANIFEST" --subject github:@new-dev --viewer proj-x

step "5. A genuinely bad account, denounced by three projects proj-a trusts, with evidence."
run opentrust score --manifest "$MANIFEST" --subject github:@slop-account --viewer proj-a

step "6. A newcomer nobody knows yet: unknown, not rejected."
run opentrust score --manifest "$MANIFEST" --subject github:@newcomer-05 --viewer proj-a

step "7. One vague denouncement from a trusted project is an allegation, not a block."
work=$(mktemp -d)
work=${work%/}
trap 'rm -rf "$work"' EXIT
for p in proj-a proj-b proj-c; do opentrust keygen --project "$p" --out "$work/$p" > /dev/null; done
opentrust trust --project proj-a --out "$work/proj-a" --target proj-b --weight 0.9 > /dev/null
opentrust trust --project proj-a --out "$work/proj-a" --target proj-c --weight 0.9 > /dev/null
printf '{"projects": [{"id": "proj-a", "path": "proj-a"}, {"id": "proj-b", "path": "proj-b"}, {"id": "proj-c", "path": "proj-c"}]}\n' > "$work/manifest.json"
NO_LLM=()
if [ -z "$MODELS" ]; then NO_LLM=(--no-llm); fi
run opentrust denounce --project proj-b --out "$work/proj-b" --subject github:@accused \
  --reason "Low quality contribution." --evidence https://github.com/example/proj-b/pull/12 \
  --severity high ${NO_LLM[@]+"${NO_LLM[@]}"}
run opentrust score --manifest "$work/manifest.json" --subject github:@accused --viewer proj-a

step "8. A second trusted project independently says the same thing: now it counts."
run opentrust denounce --project proj-c --out "$work/proj-c" --subject github:@accused \
  --reason "Same copy-paste PR as proj-b received." --evidence https://github.com/example/proj-c/pull/40 \
  --severity high ${NO_LLM[@]+"${NO_LLM[@]}"}
run opentrust score --manifest "$work/manifest.json" --subject github:@accused --viewer proj-a

step "9. And with no AI model at all, it still works."
run opentrust campaigns --incoming "$INCOMING"
run opentrust analyse --kind denounce --reason "Low quality contribution." --no-llm

printf '\nDone. Every verdict above came from deterministic code; the models only supplied inputs and the summary.\n'
