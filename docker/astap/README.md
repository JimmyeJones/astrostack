# ASTAP plate solver

AstroStack uses [ASTAP](https://www.hnsky.org/astap.htm) for local plate
solving. The app runs fine without it — frames simply stay "unsolved" until a
solver is available, and you can still preview and stack already-solved data.

## Bundled automatically in the Docker image

The Dockerfile runs [`install-astap.sh`](../install-astap.sh), which downloads
the headless Linux CLI binary (`astap_cli`) and the **d05** star database
(500 stars/sq.deg; sufficient for the Seestar's ~1.3° field of view). No manual
steps required.

The installer is deliberately robust:

- It tries **several download sources** in turn (the SourceForge command-line
  zip, a mirror URL, then the full `.deb` package), with retries/backoff, so a
  single flaky or moved URL doesn't break the build.
- It **verifies the binary actually runs** (catching missing libraries, a wrong
  architecture, or a truncated download) and **fails the build loudly** if it
  can't — so you never get a silently solver-less image.

Pick a different star database at build time:

```bash
docker compose -f docker/docker-compose.yml build --build-arg ASTAP_DB=d20
```

Valid values: `d05` (default), `d20`, `d50`, `d80` (denser = larger).

## Override at runtime (optional)

If you need a different star database (e.g. h18 for wide-field targets) or
want to pin a specific ASTAP version, mount your own install over `/opt/astap`
in `docker-compose.yml`:

```yaml
volumes:
  - /mnt/tank/apps/astap:/opt/astap:ro
```

Make sure `/opt/astap/astap` is the executable and the star DB `.290` files
live in the same directory.

You can also override the path in the **Settings** page of the web UI
(`astap_path` setting) without rebuilding the image.
