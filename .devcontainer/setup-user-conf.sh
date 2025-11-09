#!/usr/bin/env bash
set -euo pipefail

# Check if we're running inside the dev container
if [ "${IN_CONTAINER:-}" = "true" ]; then
	echo "This script must be run outside the container"
	exit 1
fi

CONF_DIR="$(dirname "$0")/.conf"
mkdir -p "$CONF_DIR"

# Generate a valid .gitconfig from effective config in current directory
GITCONFIG_OUT="$CONF_DIR/.gitconfig"
GITCONFIG_GLOBAL="$CONF_DIR/.gitconfig.global"

git config --list --global --include >"$GITCONFIG_GLOBAL"

# Parse key-value pairs and reconstruct .gitconfig with correct section/subsection syntax
awk -F= '
  function print_section(section, subsection) {
    if (section != "") {
      if (subsection != "") {
        print "[" section " \"" subsection "\"]"
      } else {
        print "[" section "]"
      }
    }
  }
  {
    key = $1
    val = $2
    if (key ~ /^includeif\./) next
    split(key, arr, ".")
    section = arr[1]
    # Handle subsection (e.g., filter.lfs.clean)
    if (length(arr) > 2) {
      subsection = arr[2]
      subkey = arr[3]
      # Special case for diff.lfs.textconv
      if (section == "diff" && subsection == "lfs" && subkey == "textconv") {
        if (section != last_section || subsection != last_subsection) {
          if (last_section != "") print ""
          print_section(section, subsection)
          last_section = section
          last_subsection = subsection
        }
        print "    textconv = " val
        next
      }
      # General case for filter.lfs.*
      if (section == "filter" && subsection == "lfs") {
        if (section != last_section || subsection != last_subsection) {
          if (last_section != "") print ""
          print_section(section, subsection)
          last_section = section
          last_subsection = subsection
        }
        print "    " subkey " = " val
        next
      }
    }
    # Handle normal section.key
    subsection = ""
    if (section != last_section || subsection != last_subsection) {
      if (last_section != "") print ""
      print_section(section, subsection)
      last_section = section
      last_subsection = subsection
    }
    # Remove section. from key
    subkey = substr(key, length(section) + 2)
    print "    " subkey " = " val
  }
' "$GITCONFIG_GLOBAL" >"$GITCONFIG_OUT"

echo "Generated valid .gitconfig at $GITCONFIG_OUT from effective config in current directory"
