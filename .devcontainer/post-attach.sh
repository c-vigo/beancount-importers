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

# Setup GPG key import
echo "Setting up GPG key import..."

# Check if there's a GPG keys file created by setup-user-conf.sh
GPG_HOST_KEYS_FILE="/workspace/.devcontainer/.conf/gpg-public-keys.asc"
GPG_OWNERTRUST_FILE="/workspace/.devcontainer/.conf/gpg-ownertrust.txt"
if [ -f "$GPG_HOST_KEYS_FILE" ]; then
	echo "Importing GPG keys from host..."
	mkdir -p $HOME/.gnupg
	chmod 700 $HOME/.gnupg
	if gpg --import --batch --quiet "$GPG_HOST_KEYS_FILE"; then
		echo "GPG keys imported successfully"
		if [ -f "$GPG_OWNERTRUST_FILE" ]; then
			echo "Importing GPG ownertrust from host..."
			gpg --import-ownertrust "$GPG_OWNERTRUST_FILE"
			echo "GPG ownertrust imported successfully"
		else
			echo "No GPG ownertrust file found, trust will need to be set manually"
		fi
	else
		echo "Warning: Failed to import GPG keys"
	fi
else
	echo "No GPG keys file found, keys will need to be imported manually"
	echo "Run this from host: gpg --export -a | podman exec -i <container> gpg --import -"
fi

echo "Post-attach setup complete"
