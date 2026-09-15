#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT=${1:-"$HOME/Applications/Codex Web GPT Menu.app"}
CONTENTS="$OUT/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
if [ -e "$OUT" ]; then
  echo "Refusing to replace an existing menu app: $OUT" >&2
  exit 1
fi
mkdir -p "$MACOS" "$RESOURCES"
cp "$ROOT/src/CodexWebGPTMenu.swift" "$RESOURCES/CodexWebGPTMenu.swift"
swiftc -parse-as-library -O "$RESOURCES/CodexWebGPTMenu.swift" -o "$MACOS/Codex Web GPT Menu"
plutil -create xml1 "$CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string local.codex-web-gpt.common-menu' "$CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundleName string Codex Web GPT Menu' "$CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundleExecutable string Codex Web GPT Menu' "$CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundlePackageType string APPL' "$CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :LSUIElement bool true' "$CONTENTS/Info.plist"
codesign --force --deep --sign - "$OUT" >/dev/null
codesign --verify --deep --strict "$OUT"
printf '%s\n' "Built: $OUT"
