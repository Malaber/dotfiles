#!/bin/sh
set -eu

# This script builds and installs podsmute.
# It assumes the podsmute source code is in ~/.podsmute, cloned by chezmoi.

PODSMUTE_DIR="$HOME/.podsmute"
INSTALL_TARGET="$HOME/.local/bin"

if ! command -v xcodegen >/dev/null 2>&1; then
    echo "xcodegen not found. Please install with 'brew install xcodegen'" >&2
    exit 1
fi

if [ ! -d "$PODSMUTE_DIR" ]; then
    echo "Directory $PODSMUTE_DIR not found." >&2
    echo "Please run 'chezmoi apply' again to fetch the podsmute source code." >&2
    exit 1
fi

cd "$PODSMUTE_DIR"

echo "Generating Xcode project for podsmute..."
xcodegen generate

echo "Building PodsMute..."
xcodebuild build -scheme PodsMute -configuration Release

BINARY_PATH="build/Release/podsmute"

if [ ! -f "$BINARY_PATH" ]; then
    echo "Build failed or binary not found at expected location: $BINARY_PATH" >&2
    exit 1
fi

echo "Installing podsmute to $INSTALL_TARGET..."

INSTALL_DIR=$(dirname "$INSTALL_TARGET")
if [ -w "$INSTALL_DIR" ]; then
    cp "$BINARY_PATH" "$INSTALL_TARGET"
fi

echo "podsmute installed successfully."

# Go back to the original directory
cd -

# Clean up build artifacts
rm -rf "$PODSMUTE_DIR/build"
rm -rf "$PODSMUTE_DIR/PodsMute.xcodeproj"
