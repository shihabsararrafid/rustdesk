# Management Deployment

## Release Boundary

Deploy to staging first. This adds the management API, console, employee-client
source, and recording upload/processing backend. Automatic desktop screen and
employee-microphone capture is NOT wired in. Native Rust/Flutter builds and real
Windows, Linux, and macOS acceptance tests remain required.

Keep existing official hbbs/hbbr containers and their data unchanged. Use a
separate checkout and Compose project for management. Existing customer clients
do not require replacement. Ordinary clients with known passwords can bypass
employee-app restrictions and auditing.

## Start The Services

Requirements: Docker with Compose, Git, a hostname pointing to the VPS, HTTPS,
and sufficient private storage. Media quota defaults to 20 GiB; allow additional
scratch and backup capacity. The worker is limited to one CPU and 2 GiB RAM.

Check existing services and port ownership before proceeding:

```sh
docker ps
docker compose version
ss -lntp
git clone https://github.com/shihabsararrafid/rustdesk.git /opt/sasthotech-remote
cd /opt/sasthotech-remote
cp management/.env.example management/.env
```

For a private repository, use a deploy key or credential helper, not a token in
the clone URL. Set these values in `management/.env`, replacing the hostname:

```dotenv
MANAGEMENT_PUBLIC_ORIGIN=https://management.yourdomain.com
MANAGEMENT_SESSION_SECONDS=28800
```

Use the exact HTTPS origin without a trailing slash or path. All commands below
run from the checkout root. Preserve the project name on subsequent deployments.

```sh
docker compose -p sasthotech-management --env-file management/.env -f management/compose.yml up -d --build
docker compose -p sasthotech-management --env-file management/.env -f management/compose.yml ps
curl --fail http://127.0.0.1:21114/readyz
docker compose -p sasthotech-management --env-file management/.env -f management/compose.yml logs --tail=100 management media-worker
```

Port 21114 is bound only to host loopback. If already occupied, change the host
port and reverse-proxy destination together. Do not change hbbs/hbbr ports.

## HTTPS

Use your existing HTTPS proxy if present. For host-installed Nginx, start with
`nginx-http.conf.example`, replace its hostname, test and reload Nginx, then obtain
a certificate. On an otherwise suitable Debian/Ubuntu host:

```sh
sudo apt-get update
sudo apt-get install nginx certbot python3-certbot-nginx
sudo cp management/deploy/nginx-http.conf.example /etc/nginx/sites-available/sasthotech-management
sudo nano /etc/nginx/sites-available/sasthotech-management
sudo ln -s /etc/nginx/sites-available/sasthotech-management /etc/nginx/sites-enabled/sasthotech-management
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d management.yourdomain.com --redirect
```

Do not install a competing proxy if Caddy, Traefik, Coolify, or another service
already owns ports 80/443. A containerized proxy cannot reach the host through
its own `127.0.0.1`; configure host routing explicitly. Verify certificate renewal
and add login rate limits using `nginx.conf.example`. Do not log authorization
headers or request bodies. Do not expose the backend port publicly.

## Bootstrap And Employee Builds

Create the first administrator interactively with a strong unique password:

```sh
docker compose -p sasthotech-management --env-file management/.env -f management/compose.yml exec management python -m app.cli create-admin --username admin
```

Open `https://management.yourdomain.com/console`, create employee accounts and
import client metadata. There are no default administrator credentials.

Run the GitHub Actions **Sasthotech Desktop Build** workflow with employee mode
enabled and the HTTPS management URL. Leave employee mode disabled for customer
builds. Complete `docs/employee-management-acceptance.md` before employee rollout.
Deployment of media endpoints alone does not enable automatic recording.

## Backup, Cleanup, And Updates

Back up BOTH named volumes: `sasthotech-management_management-data` and
`sasthotech-management_management-media`. Stop both services for a consistent
paired volume snapshot, store backups encrypted and access-restricted, and test
restoration in a separate Compose project. The database-only recovery scripts
are not a complete media backup. Never run `docker compose down -v` on live data.

Preview retention cleanup:

```sh
docker compose -p sasthotech-management --env-file management/.env -f management/compose.yml exec management python -m app.cli cleanup-recordings --dry-run
```

Use `--apply` only after reviewing the preview and backups. Schedule this command
with your operations scheduler: retention is not automatic. Default retention is
30 days. Abandoned recordings and pending reservations become eligible after
that inactivity period; recent uploads are preserved. Monitor quota exhaustion,
disk space, worker failures, and stalled uploads. Native spool recovery and
automatic backup scheduling remain unfinished.

For updates, back up first, review changes, use `git pull --ff-only`, and repeat
the `up -d --build` command. A rollback involving schema changes requires a
compatible paired backup, not just an older image.
