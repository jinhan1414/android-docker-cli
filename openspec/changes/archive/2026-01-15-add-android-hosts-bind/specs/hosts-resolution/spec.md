## ADDED Requirements
### Requirement: Provide Android /etc/hosts bind with localhost mappings
When running in an Android/Termux environment, the system SHALL create a host-side `/etc/hosts` file and bind it into the container at `/etc/hosts`, ensuring entries for `127.0.0.1 localhost` and `::1 localhost`.

#### Scenario: Container sees localhost entries
- **WHEN** a container is started in Android/Termux
- **THEN** the container `/etc/hosts` includes `127.0.0.1 localhost` and `::1 localhost`

### Requirement: Preserve rootfs hosts entries
When generating the Android `/etc/hosts` bind file, the system SHALL preserve any existing entries from the rootfs `/etc/hosts` and add missing localhost entries only.

#### Scenario: Custom host entries remain
- **WHEN** the rootfs `/etc/hosts` contains `10.0.0.5 internal-service`
- **THEN** the container `/etc/hosts` contains `10.0.0.5 internal-service` along with localhost entries
