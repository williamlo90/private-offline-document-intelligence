# Linux service templates

Render with `python -m scripts.render_systemd --root /opt/project07 --release
<name> --output local/<new-directory>`. This only writes inactive unit files. Copy
and enable them in the Phase 7 Linux acceptance lab after runtime packages,
model, service user, secrets and writable state paths have been provisioned.

`/etc/project07/api.env` must be readable only by the service account and set
`PRIVATE_LAB_CONFIG` and `PRIVATE_OLLAMA_PROFILE` for the current native harness.
The API's memory repository loses state on restart; these templates are not a
production deployment. The worker shares the API repository only when
`PRIVATE_WORKER_CONFIG` is also set in the API environment file. All server
listeners bind loopback; systemd restricts IP addresses to localhost.

Render and `systemd-analyze verify` were checked statically in a WSL lab. No
unit was installed, started or enabled. Actual startup, reboot, database
durability, alerts and recovery remain Phase 7 acceptance.
