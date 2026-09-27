# Windows restart and LAN incident — 2026-09-27/28

This follow-up records what failed when the existing Windows deployment was restarted. It is operational evidence for Mac development and future Windows updates. It does not contain Docker data, model keys, account records or raw benchmark tasks.

## What happened

1. Docker Desktop stopped before its Linux engine became available. WSL reported `Wsl/Service/CreateInstance/MountDisk/HCS/E_ACCESSDENIED` for `E:\DK\DockerDesktopWSL\main\ext4.vhdx`. Both that file and `E:\DK\DockerDesktopWSL\disk\docker_data.vhdx` were owned by `BUILTIN\Administrators`; the normal Windows login was not elevated. ACLs allowed authenticated users to read/write, but WSL still refused the mount.
2. The small `ext4.vhdx` was copied to a separate E: backup path before repair. An elevated `icacls /setowner` changed only its owner to the current Windows user. WSL could then start the `docker-desktop` distribution, but Docker's backend log showed a second `E_ACCESSDENIED` while attaching `docker_data.vhdx`. Its owner was changed in the same way, without deleting or reformatting the data disk. Docker Desktop then reached `running`; `docker info` showed the Linux engine. This sequence supports file ownership as the cause on this host, but a later access-denied error still needs its own diagnosis (including disk availability or endpoint security).
3. The Mac remained at `192.168.31.155`, while Windows had only Ethernet `192.168.0.107`; its Wi-Fi had disconnected. Reconnecting the saved `Xiaomi_10016` profile restored Windows Wi-Fi address `192.168.31.208/24`.
4. Docker Compose could publish `127.0.0.1:3023/8018`, but publishing directly to `192.168.31.208` failed with `ports are not available`. A Windows TCP listener could bind both Wi-Fi ports, so this was specific to Docker Desktop port publishing on that interface. The running configuration now keeps Compose on localhost and uses Windows `netsh interface portproxy` from `192.168.31.208:3023/8018` to `127.0.0.1:3023/8018`. The Windows firewall rule allows only `192.168.31.0/24` to those two ports. This is LAN HTTP, not public internet exposure.

## Verified after recovery

- API, Web, PostgreSQL, Redis and Ollama were healthy; Worker was running. Local and Wi-Fi URLs returned HTTP 200 for `/login` and `/health`.
- The Docker data VHDX and Compose named volumes remain on E:; no `down -v`, WSL unregister, image prune or database restore was used.
- The Wi-Fi profile is set to connect automatically. The portproxy and firewall rule persist in Windows, but depend on the host retaining `192.168.31.208`. If DHCP changes this address, update the listener and `ASTERIA_LAN_BIND_HOST` together, and retest from another device.
- Docker Desktop's `AutoStart` setting was enabled, then a controlled Docker stop/start was tested. The new restart script recovered all services and the LAN URL. A full Windows reboot has not yet been tested.
- The Mac and any other `192.168.31.x` device still need a browser-side test after a future reboot; a successful request from Windows alone does not prove router client isolation or device-to-device reachability.

## Permanent deployment changes

- Set host-only `deploy/.env` value `ASTERIA_LAN_MODE=portproxy` on this Windows machine. This prevents `deploy/update-windows.ps1` and `deploy/restart-windows.ps1` from adding `deploy/compose.lan.yaml`; the existing Windows portproxy owns the Wi-Fi listeners. The setting and secrets stay off GitHub.
- `deploy/restart-windows.ps1` starts Docker Desktop when needed, reuses existing images and volumes, waits for health checks, and verifies localhost plus the configured LAN URL. A VHD mount failure prints the two disk owners and stops without deleting or repairing data automatically.
- `deploy/update-windows-latest.ps1` fetches `origin/main`, pins its full commit SHA and invokes the existing guarded update path. It runs the preflight first; the lower-level updater checks active work, backs up PostgreSQL to E:, preserves rollback image tags, builds and validates the target, and restores the old images if activation fails. It does not update on every GitHub push.
- GitHub HTTPS was unreachable directly from this Windows shell, while the configured local system proxy at `127.0.0.1:7890` worked. The dedicated `E:\AsteriaDeploy` checkout uses that proxy in its **repo-local** Git config. Future updates require the proxy service to be running; a failed fetch leaves the deployed containers untouched.

## Recovery checks on this host

```powershell
docker desktop status
docker info --format '{{.ServerVersion}} {{.OSType}}'
Get-Acl 'E:\DK\DockerDesktopWSL\main\ext4.vhdx','E:\DK\DockerDesktopWSL\disk\docker_data.vhdx' | Select-Object Path,Owner
netsh interface portproxy show v4tov4
powershell -ExecutionPolicy Bypass -File .\deploy\restart-windows.ps1
```

If Docker reports `E_ACCESSDENIED` again, check the exact VHDX path, owner, disk health and security software before any repair. Do not unregister the `docker-desktop` WSL distribution or delete either VHDX. If the LAN request fails but localhost works, check that Windows rejoined the correct Wi-Fi and retained the portproxy listener IP. The GitHub update path is documented in [the Windows update runbook](../operations/github-handoff-windows-update.md).
