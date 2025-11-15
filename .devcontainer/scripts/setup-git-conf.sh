#!/bin/bash
set -e

# Script to set up git configuration and hooks within the dev container
# This is used to ensure that the git configuration and hooks are consistent
# between the host and the dev container.
# The script is called from the post-attach.sh script.

# Setup git configuration
echo "Setting up git configuration..."
HOST_GITCONFIG_FILE="/workspace/.devcontainer/.conf/.gitconfig"
CONTAINER_GITCONFIG_FILE=$HOME"/.gitconfig"
if [ -f "$HOST_GITCONFIG_FILE" ]; then
	echo "Applying git configuration from $HOST_GITCONFIG_FILE..."
	cp "$HOST_GITCONFIG_FILE" "$CONTAINER_GITCONFIG_FILE"
else
	echo "No git config file found, skipping git setup"
	echo "Run this from host's project root: .devcontainer/scripts/copy-host-user-conf.sh"
fi

# Setup SSH public key for signing
HOST_SSH_PUBKEY="/workspace/.devcontainer/.conf/id_ed25519_github.pub"
CONTAINER_SSH_DIR="$HOME/.ssh"
if [ -f "$HOST_SSH_PUBKEY" ]; then
	echo "Applying SSH public key from $HOST_SSH_PUBKEY..."
	mkdir -p "$CONTAINER_SSH_DIR"
	cp "$HOST_SSH_PUBKEY" "$CONTAINER_SSH_DIR/id_ed25519_github.pub"
	echo "SSH public key installed at $CONTAINER_SSH_DIR/id_ed25519_github.pub"
else
	echo "Warning: No SSH public key found at $HOST_SSH_PUBKEY"
	echo "Git commit signing may not work without this file"
	echo "Run this from host's project root: .devcontainer/scripts/copy-host-user-conf.sh"
fi

# Setup allowed-signers file
HOST_ALLOWED_SIGNERS_FILE="/workspace/.devcontainer/.conf/allowed-signers"
CONTAINER_ALLOWED_SIGNERS_DIR="$HOME/.config/git"
if [ -f "$HOST_ALLOWED_SIGNERS_FILE" ]; then
	echo "Applying allowed-signers file from $HOST_ALLOWED_SIGNERS_FILE..."
	mkdir -p "$CONTAINER_ALLOWED_SIGNERS_DIR"
	cp "$HOST_ALLOWED_SIGNERS_FILE" "$CONTAINER_ALLOWED_SIGNERS_DIR/allowed-signers"
	echo "Allowed-signers file installed at $CONTAINER_ALLOWED_SIGNERS_DIR/allowed-signers"
else
	echo "Warning: No allowed-signers file found at $HOST_ALLOWED_SIGNERS_FILE"
	echo "Git signature verification may not work without this file"
	echo "Run this from host's project root: .devcontainer/scripts/copy-host-user-conf.sh"
fi

# Verify SSH agent socket for git signing
# VS Code/Cursor automatically sets SSH_AUTH_SOCK, so we just verify it has the signing key
echo "Verifying SSH agent socket for git signing..."
if [ -f "$HOST_SSH_PUBKEY" ]; then
	# Get the expected key fingerprint
	EXPECTED_FINGERPRINT=$(ssh-keygen -l -f "$HOST_SSH_PUBKEY" 2>/dev/null | awk '{print $2}' || echo "")
	EXPECTED_KEY_COMMENT=$(ssh-keygen -l -f "$HOST_SSH_PUBKEY" 2>/dev/null | awk '{for(i=3;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ $//' || echo "")

	if [ -n "$EXPECTED_FINGERPRINT" ]; then
		echo "Looking for signing key: $EXPECTED_FINGERPRINT ($EXPECTED_KEY_COMMENT)"

		# Check if SSH_AUTH_SOCK is set and has the signing key
		if [ -n "$SSH_AUTH_SOCK" ] && [ -S "$SSH_AUTH_SOCK" ]; then
			echo "Current SSH_AUTH_SOCK: $SSH_AUTH_SOCK"
			if ssh-add -l 2>/dev/null | grep -q "$EXPECTED_FINGERPRINT"; then
				echo "✓ Git signing key is accessible in SSH agent"
				ssh-add -l 2>/dev/null | grep "$EXPECTED_FINGERPRINT" || true
			else
				echo "✗ Git signing key NOT found in current SSH agent"
				echo "Available keys in current socket:"
				ssh-add -l 2>/dev/null || echo "  (none - agent has no keys)"

				# Scan all available SSH sockets
				echo ""
				echo "Scanning all available SSH agent sockets..."
				FOUND_SOCKET=""
				SOCKET_COUNT=0

				# Find all potential SSH agent sockets
				for sock in /tmp/cursor-remote-ssh-*.sock /tmp/ssh-*/agent.* /run/user/*/openssh_agent; do
					[ ! -S "$sock" ] 2>/dev/null && continue
					SOCKET_COUNT=$((SOCKET_COUNT + 1))
					echo ""
					echo "Socket #$SOCKET_COUNT: $sock"
					if KEYS=$(SSH_AUTH_SOCK="$sock" ssh-add -l 2>/dev/null) && [ -n "$KEYS" ]; then
						echo "  Keys in this socket:"
						while IFS= read -r line; do echo "    $line"; done <<<"$KEYS"
						if echo "$KEYS" | grep -q "$EXPECTED_FINGERPRINT"; then
							FOUND_SOCKET="$sock"
							echo "  ✓ CONTAINS SIGNING KEY!"
						fi
					else
						echo "  (no keys or socket not accessible)"
					fi
				done

				if [ $SOCKET_COUNT -eq 0 ]; then
					echo "  No SSH agent sockets found"
				fi

				if [ -n "$FOUND_SOCKET" ]; then
					export SSH_AUTH_SOCK="$FOUND_SOCKET"
					echo ""
					echo "✓ Found SSH agent socket with signing key: $SSH_AUTH_SOCK"
					echo "  Updated SSH_AUTH_SOCK environment variable"
				else
					echo ""
					echo "✗ Could not find SSH agent socket with signing key"
					echo "  Git commit signing may not work. Ensure SSH agent forwarding is enabled."
				fi
			fi
		else
			echo "✗ SSH_AUTH_SOCK is not set or socket does not exist"
			if [ -n "$SSH_AUTH_SOCK" ]; then
				echo "  SSH_AUTH_SOCK=$SSH_AUTH_SOCK (socket does not exist)"
			else
				echo "  SSH_AUTH_SOCK is unset"
			fi

			# Scan all available SSH sockets
			echo ""
			echo "Scanning all available SSH agent sockets..."
			FOUND_SOCKET=""
			SOCKET_COUNT=0

			for sock in /tmp/cursor-remote-ssh-*.sock /tmp/ssh-*/agent.* /run/user/*/openssh_agent; do
				[ ! -S "$sock" ] 2>/dev/null && continue
				SOCKET_COUNT=$((SOCKET_COUNT + 1))
				echo ""
				echo "Socket #$SOCKET_COUNT: $sock"
				if KEYS=$(SSH_AUTH_SOCK="$sock" ssh-add -l 2>/dev/null) && [ -n "$KEYS" ]; then
					echo "  Keys in this socket:"
					while IFS= read -r line; do echo "    $line"; done <<<"$KEYS"
					if echo "$KEYS" | grep -q "$EXPECTED_FINGERPRINT"; then
						FOUND_SOCKET="$sock"
						echo "  ✓ CONTAINS SIGNING KEY!"
					fi
				else
					echo "  (no keys or socket not accessible)"
				fi
			done

			if [ $SOCKET_COUNT -eq 0 ]; then
				echo "  No SSH agent sockets found"
			fi

			if [ -n "$FOUND_SOCKET" ]; then
				export SSH_AUTH_SOCK="$FOUND_SOCKET"
				echo ""
				echo "✓ Found SSH agent socket with signing key: $SSH_AUTH_SOCK"
				echo "  Set SSH_AUTH_SOCK environment variable"
			else
				echo ""
				echo "✗ Could not find SSH agent socket with signing key"
				echo "  VS Code/Cursor should set SSH_AUTH_SOCK automatically."
				echo "  Git commit signing may not work. Ensure SSH agent forwarding is enabled."
			fi
		fi
	else
		echo "✗ Warning: Could not determine signing key fingerprint"
	fi
else
	echo "Skipping SSH agent socket verification (no signing key found)"
fi

# Setup git hooks
echo "Setting up git hooks..."
if [ -d .githooks ]; then
	git config core.hooksPath .githooks
	echo "Git hooks configured to use .githooks directory"
else
	echo "No .githooks directory found, using default git hooks"
fi
