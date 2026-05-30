#!/usr/bin/env sh

set -eu

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd -P)
VERSION=2.14.1
ZIP_PATH="$ROOT_DIR/.gradle-bootstrap/gradle-$VERSION-bin.zip"
UNZIP_DIR="$ROOT_DIR/.gradle-bootstrap"
GRADLE_BIN="$UNZIP_DIR/gradle-$VERSION/bin/gradle"
WRAPPER_JAR="$ROOT_DIR/gradle/wrapper/gradle-wrapper.jar"

mkdir -p "$UNZIP_DIR" "$ROOT_DIR/gradle/wrapper"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-$ROOT_DIR/.gradle-user-home}"
export GRADLE_OPTS="${GRADLE_OPTS:-"-Xmx2G -Dfile.encoding=UTF-8 -Dorg.gradle.native=false"}"

if [ -z "${JAVA_HOME:-}" ] && [ "$(uname -s)" = "Darwin" ] && [ -x /usr/libexec/java_home ]; then
  JAVA8_HOME=$(/usr/libexec/java_home -v 1.8 2>/dev/null || true)
  if [ -n "$JAVA8_HOME" ]; then
    export JAVA_HOME="$JAVA8_HOME"
  fi
fi

if [ ! -f "$ZIP_PATH" ]; then
  curl -L "https://services.gradle.org/distributions/gradle-$VERSION-bin.zip" -o "$ZIP_PATH"
fi

if [ ! -x "$GRADLE_BIN" ]; then
  unzip -q -o "$ZIP_PATH" -d "$UNZIP_DIR"
fi

"$GRADLE_BIN" --no-daemon wrapper --gradle-version "$VERSION"

echo "Installed $WRAPPER_JAR"
