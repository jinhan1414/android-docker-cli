# Release v1.2.7 - Android Startup Compatibility

- Improve Android/Termux container startup compatibility for images that expect to start as root and then drop privileges (for example, images that `chown` mounted paths and use supervisord).
- Add an update helper script for Termux: `scripts/update.sh`.

Install:
```bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/v1.2.7/scripts/install.sh | sh
```

Update:
```bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/main/scripts/update.sh | sh
```

