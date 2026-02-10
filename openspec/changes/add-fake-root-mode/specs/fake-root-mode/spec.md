## ADDED Requirements

### Requirement: Default to fake-root mode on Android/Termux proot runs
When running in an Android/Termux environment, the system SHALL execute containers in a fake-root mode where the container process identity is root (uid 0) inside the proot environment.

#### Scenario: Image requiring root startup can drop privileges without user intervention
- **WHEN** a user starts a container in Android/Termux
- **AND** the image entrypoint attempts to `chown` bind-mounted paths and then drop privileges (for example via supervisord)
- **THEN** the container startup proceeds past privilege drop without failing solely due to running as a non-root user

### Requirement: Provide an internal escape hatch to disable Android fake-root
The system SHALL allow disabling fake-root mode on Android/Termux runs via an environment-variable configuration.

#### Scenario: Fake-root disabled for troubleshooting
- **WHEN** a container is started in Android/Termux with the escape hatch set to disable fake-root
- **THEN** the generated proot command does not include the fake-root option

### Requirement: Preserve effective fake-root setting across restart/start for detached containers
When a detached container is created, the system SHALL persist the effective fake-root setting used for that container and reuse it when the container is started or restarted.

#### Scenario: Restart reuses original effective setting
- **WHEN** a user creates a detached container in Android/Termux
- **AND** the user later runs `docker restart X` (or `docker start X`)
- **THEN** the container is executed with the same fake-root setting that was used when it was created

