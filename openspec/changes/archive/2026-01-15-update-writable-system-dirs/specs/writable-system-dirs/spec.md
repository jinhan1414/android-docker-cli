## ADDED Requirements
### Requirement: Seed writable directory structure from rootfs
When Android writable system directory support is enabled, the system SHALL mirror the directory structure from the rootfs path into the host-side writable directory before binding.

#### Scenario: Nginx directories are preserved
- **WHEN** the rootfs contains `/var/log/nginx` and `/var/cache/nginx`
- **THEN** the host writable directories for `/var/log` and `/var/cache` contain `nginx` subdirectories before the bind mounts are applied

### Requirement: Preserve existing writable directory contents
When a host-side writable directory already exists from a previous run, the system SHALL preserve its contents and only create missing directories.

#### Scenario: Existing log files remain
- **WHEN** the host writable `/var/log` directory already contains `nginx/error.log`
- **THEN** preparing writable directories does not remove or overwrite `nginx/error.log`
