# Release v1.2.10 - Supervisord Unix Socket Workaround (Android)

- Work around Android/Termux hard-link restrictions that can cause `supervisord` to loop printing `Unlinking stale socket /var/run/supervisor.sock`.
- On Android/Termux, automatically comment out `[unix_http_server]` and `[supervisorctl]` sections in `/etc/supervisord.conf` (when present) so `supervisord` can still manage programs without creating a unix control socket.

Install:
```bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/v1.2.10/scripts/install.sh | sh
```

Update:
```bash
curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/main/scripts/update.sh | sh
```

