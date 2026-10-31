#!/usr/bin/env sh
# Rebuilds examples/vouch/output.txt from the two VOUCHED.td files in this folder.
# proj-a trusts proj-b. Nobody here trusts proj-x.
set -e
cd "$(dirname "$0")"
work=$(mktemp -d)
for p in proj-a proj-b proj-x; do opentrust keygen --project $p --out "$work/$p" > /dev/null; done
opentrust trust --project proj-a --out "$work/proj-a" --target proj-b --weight 0.9 > /dev/null
printf '{"projects": [{"id": "proj-a", "path": "proj-a"}, {"id": "proj-b", "path": "proj-b"}, {"id": "proj-x", "path": "proj-x"}]}\n' > "$work/manifest.json"
{
  echo '$ opentrust import-td --project proj-b --file proj-b.VOUCHED.td'
  opentrust import-td --project proj-b --out "$work/proj-b" --file proj-b.VOUCHED.td --no-llm
  echo '$ opentrust import-td --project proj-x --file proj-x.VOUCHED.td'
  opentrust import-td --project proj-x --out "$work/proj-x" --file proj-x.VOUCHED.td --no-llm
  echo
  echo '$ opentrust score --subject github:@new-dev --viewer proj-a'
  opentrust score --manifest "$work/manifest.json" --subject github:@new-dev --viewer proj-a
  echo
  echo '$ opentrust export-td --project proj-b'
  opentrust export-td --manifest "$work/manifest.json" --project proj-b
} > output.txt
rm -rf "$work"
