# ASTAP plate solver (optional bundle)

AstroStack uses [ASTAP](https://www.hnsky.org/astap.htm) for local plate
solving. The app runs fine without it — frames simply stay "unsolved" until a
solver is available, and you can still preview and stack already-solved data.

You have two ways to provide ASTAP:

## Option A — bundle it into the image (build time)

Place these files in this directory **before** building the image:

```
docker/astap/astap        # the headless Linux CLI binary (astap_cli), renamed to `astap`
docker/astap/*.290         # a star database, e.g. the small g05 (g05_*.290) set
```

They are copied to `/opt/astap/` and `SEESTACK_ASTAP_PATH=/opt/astap/astap` is
set automatically. For the Seestar's ~1.3° field of view the small **g05** (or
**d05**) database is plenty; bundle **h18** only if you also solve wide/sparse
fields.

## Option B — mount it at runtime

Leave this directory empty and instead mount your ASTAP install over
`/opt/astap` in `docker-compose.yml`:

```yaml
volumes:
  - /mnt/tank/apps/astap:/opt/astap:ro
```

Make sure `/opt/astap/astap` is the executable and the star DB lives alongside
it (or point `astap_path` in Settings at the right location).
