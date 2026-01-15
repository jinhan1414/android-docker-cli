## ADDED Requirements
### Requirement: Preserve executable permissions during Android layer extraction
When extracting OCI or Docker layers in an Android or Termux environment, the system SHALL preserve executable permissions for files so that executables remain runnable in the rootfs.

#### Scenario: Executable file remains executable
- **WHEN** a layer entry for /bin/busybox includes execute permission bits
- **THEN** the extracted rootfs file at /bin/busybox is executable
