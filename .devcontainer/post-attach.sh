#!/bin/bash

# Post-attach script - runs when container is attached
# This script is called from postAttachCommand

set -e

echo "Running post-attach setup..."

# Setup git configuration
echo "Setting up git configuration..."
HOST_GITCONFIG_FILE="/workspace/.devcontainer/.conf/.gitconfig"
CONTAINER_GITCONFIG_FILE=$HOME"/.gitconfig"
if [ -f "$HOST_GITCONFIG_FILE" ]; then
	echo "Applying git configuration from $HOST_GITCONFIG_FILE..."
	cp "$HOST_GITCONFIG_FILE" "$CONTAINER_GITCONFIG_FILE"
else
	echo "No git config file found, skipping git setup"
	echo "Run this from host's project root: .devcontainer/setup-user-conf.sh"
fi

# Setup git hooks
echo "Setting up git hooks..."
if [ -d .githooks ]; then
	git config core.hooksPath .githooks
	echo "Git hooks configured to use .githooks directory"
else
	echo "No .githooks directory found, using default git hooks"
fi

# Setup pre-commit hooks
echo "Setting up pre-commit hooks..."
if command -v pre-commit &>/dev/null; then
	if [ -f .pre-commit-config.yaml ]; then
		echo "Installing pre-commit hooks..."
		pre-commit install-hooks
		echo "Pre-commit hooks installed successfully"
	else
		echo "No .pre-commit-config.yaml found, skipping pre-commit setup"
	fi
else
	echo "Pre-commit not found, skipping pre-commit setup"
fi

echo "Post-attach setup complete"
