#!/data/data/com.termux/files/usr/bin/sh

# Automated installer for android-docker-cli on Termux

# --- Configuration ---
GITHUB_REPO="https://github.com/jinhan1414/android-docker-cli"
INSTALL_DIR="$HOME/.android-docker-cli"
CMD_NAME="docker"
CMD_PATH="$PREFIX/bin/$CMD_NAME"
DOCKER_COMPOSE_CMD_NAME="docker-compose"
DOCKER_COMPOSE_CMD_PATH="$PREFIX/bin/$DOCKER_COMPOSE_CMD_NAME"

# --- Version Detection ---
# Detect version from script URL or environment variable
# Priority: INSTALL_VERSION env var > URL path > "main"
INSTALL_VERSION="${INSTALL_VERSION:-}"

if [ -z "$INSTALL_VERSION" ]; then
    # Try to detect from script URL (if available via $0 or other means)
    # This works when script is piped from curl
    if [ -n "$BASH_SOURCE" ]; then
        SCRIPT_URL="$BASH_SOURCE"
    else
        SCRIPT_URL="${0}"
    fi
    
    # Extract version from URL pattern like /v1.1.0/ or /v1.2.0/
    INSTALL_VERSION=$(echo "$SCRIPT_URL" | grep -oE '/v[0-9]+\.[0-9]+\.[0-9]+/' | tr -d '/')
fi

# Default to "main" if no version detected
if [ -z "$INSTALL_VERSION" ]; then
    INSTALL_VERSION="main"
fi

# --- Helper Functions ---
echo_info() {
    echo "[INFO] $1"
}

echo_error() {
    echo "[ERROR] $1" >&2
    exit 1
}

# --- Main Script ---

# 1. Welcome Message
echo_info "Starting installation of android-docker-cli..."
echo_info "Installing version: $INSTALL_VERSION"

# Resolve wrapper shell path.
# Prefer Termux's shell when available; otherwise fall back to portable /usr/bin/env sh.
if [ -n "${PREFIX:-}" ] && [ -x "$PREFIX/bin/sh" ]; then
    WRAPPER_SHEBANG="#!$PREFIX/bin/sh"
else
    WRAPPER_SHEBANG="#!/usr/bin/env sh"
fi

# 2. Check Dependencies
echo_info "Checking dependencies..."
for cmd in git python; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo_error "Dependency '$cmd' is not installed. Please install it with 'pkg install $cmd' and run this script again."
    fi
done
echo_info "✓ Dependencies are satisfied."

# 3. Clone the Repository
if [ -d "$INSTALL_DIR" ]; then
    echo_info "Existing installation found. Removing old version..."
    rm -rf "$INSTALL_DIR"
fi
echo_info "Cloning repository into $INSTALL_DIR..."

# Clone specific version or main branch/commit.
if [ "$INSTALL_VERSION" = "main" ]; then
    git clone "$GITHUB_REPO" "$INSTALL_DIR"
else
    # Try fast branch/tag clone first.
    if ! git clone --branch "$INSTALL_VERSION" --depth 1 "$GITHUB_REPO" "$INSTALL_DIR"; then
        echo_info "Ref '$INSTALL_VERSION' is not a branch/tag. Trying commit-ish checkout..."
        git clone "$GITHUB_REPO" "$INSTALL_DIR" || echo_error "Failed to clone repository for commit checkout."
        (
            cd "$INSTALL_DIR" &&
            git checkout "$INSTALL_VERSION"
        ) || echo_error "Ref '$INSTALL_VERSION' not found. Check the target branch/tag/SHA."
    fi
fi

if [ $? -ne 0 ]; then
    echo_error "Failed to clone the repository. Please check your internet connection and permissions."
fi
echo_info "✓ Repository cloned successfully."

# 4. Install Python Dependencies
echo_info "Installing Python dependencies..."
if command -v pip >/dev/null 2>&1; then
    pip install PyYAML
elif command -v pip3 >/dev/null 2>&1; then
    pip3 install PyYAML
else
    echo_error "pip or pip3 is not installed. Please install it (e.g., 'pkg install python-pip' in Termux) and run this script again."
fi
echo_info "✓ Python dependencies installed."

# 5. Create the Wrapper Script
echo_info "Creating command wrapper at $CMD_PATH..."
cat > "$CMD_PATH" << EOF
$WRAPPER_SHEBANG

# Wrapper script for docker_cli.py
# This allows running the tool with the 'docker' command.

# Set the installation directory
INSTALL_DIR="$INSTALL_DIR"

# Path to the main python script
PYTHON_SCRIPT="\$INSTALL_DIR/android_docker/docker_cli.py"

# Check if the main script exists
if [ ! -f "\$PYTHON_SCRIPT" ]; then
    echo "Error: The main script was not found at \$PYTHON_SCRIPT" >&2
    echo "Please try reinstalling the tool." >&2
    exit 1
fi

# Execute the python script with all passed arguments
exec env PYTHONPATH="\$INSTALL_DIR" python -m android_docker.docker_cli "\$@"
EOF
if [ $? -ne 0 ]; then
    echo_error "Failed to create the wrapper script. Please check permissions for $PREFIX/bin."
fi

# 6. Make the Wrapper Executable
chmod +x "$CMD_PATH"
if [ $? -ne 0 ]; then
    echo_error "Failed to make the command executable. Please check permissions."
fi
echo_info "✓ Command wrapper created and made executable."

# 7. Create docker-compose Wrapper
echo_info "Creating command wrapper at $DOCKER_COMPOSE_CMD_PATH..."
cat > "$DOCKER_COMPOSE_CMD_PATH" << EOF
$WRAPPER_SHEBANG
# Wrapper for docker_compose_cli.py
INSTALL_DIR="$INSTALL_DIR"
PYTHON_SCRIPT="\$INSTALL_DIR/android_docker/docker_compose_cli.py"
if [ ! -f "\$PYTHON_SCRIPT" ]; then
    echo "Error: The main script was not found at \$PYTHON_SCRIPT" >&2
    exit 1
fi
exec env PYTHONPATH="\$INSTALL_DIR" python -m android_docker.docker_compose_cli "\$@"
EOF
chmod +x "$DOCKER_COMPOSE_CMD_PATH"
echo_info "✓ docker-compose command wrapper created."

# 8. Final Success Message
echo_info "-------------------------------------------------"
echo_info "  Installation successful!"
echo_info "  Version: $INSTALL_VERSION"
echo_info "  You can now run the tool by typing: docker"
echo_info "  And manage services with: docker-compose"
echo_info "  Example: docker run alpine:latest echo 'Hello'"
echo_info "-------------------------------------------------"
