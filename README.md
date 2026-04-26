# Plex Alexa Skill Bridge

A self-hosted Alexa skill that replaces the discontinued official Plex Alexa skill. Stream music from your personal Plex library to any Alexa device by voice.

> **Origin:** Built through a collaborative session with Claude AI as a replacement for the Plex Alexa skill after Plex announced its removal. See [CHANGELOG.md](CHANGELOG.md) for development history.

## Features

- 🎵 **Play by artist** — "Alexa, ask Plex to play the artist Creed"
- 💿 **Play by album** — "Alexa, ask Plex to play the album Dirt"
- 🎶 **Play by song** — "Alexa, ask Plex to play the song Africa"
- 📋 **Play playlists** — "Alexa, ask Plex to play the playlist Road Trip"
- 🔀 **Shuffle artists** — "Alexa, ask Plex to shuffle Fleetwood Mac"
- 📅 **Play by decade** — "Alexa, ask Plex to play music from the 1990s"
- 🎸 **Play by genre** — "Alexa, ask Plex to play some Rock"
- 🕐 **Recently played** — "Alexa, ask Plex to play music" starts your recently played, shuffled
- ⭐ **Most played** — "Alexa, ask Plex to play my most played music"
- ✨ **Recently added** — "Alexa, ask Plex to play recently added music"
- ⏭️ **Queue controls** — next, pause, resume all work naturally
- 🖼️ **Echo Show support** — album art and track metadata displayed
- 👨‍👩‍👧 **Multi-device** — each Echo device maintains its own independent queue

## Architecture

```
Alexa voice request
    ↓
Alexa Cloud → https://plex.YOUR_DOMAIN/skill (POST)
    ↓
Apache reverse proxy → Flask/Gunicorn (port 5001)
    ↓
Plex API search (internal LAN: YOUR_PLEX_IP:32400)
    ↓
AudioPlayer directive with stream URL returned to Alexa
    ↓
Alexa fetches audio → https://plex.YOUR_DOMAIN/library/parts/...
    ↓
Apache reverse proxy → Plex streaming server (port 32400)
```

## Prerequisites

- A running Plex Media Server with a music library
- A server with Docker and Apache (or nginx) with a public HTTPS domain
- An Amazon Developer account (free) to create the Alexa skill
- A wildcard or multi-domain SSL certificate for your domain

## Getting a domain, dynamic DNS, and SSL certificate

Alexa requires a publicly reachable HTTPS endpoint. If you're self-hosting at home on a residential ISP (where your public IP changes periodically), here's a low-cost, fully automated path to get there.

### 1. Register a domain (~$11/year)

[Cloudflare Registrar](https://www.cloudflare.com/products/registrar/) sells domains at cost with no markup — a `.com` typically runs around $10–11/year. Registration automatically includes Cloudflare's DNS management, which is what makes the rest of this easy.

- Go to [dash.cloudflare.com](https://dash.cloudflare.com) → **Domain Registration → Register a domain**
- Once registered, your domain is immediately on Cloudflare's nameservers

### 2. Keep your DNS record current when your IP changes

Residential ISPs periodically reassign your public IP. A DDNS (Dynamic DNS) client runs on your server and updates your Cloudflare DNS record automatically whenever the IP changes.

**ddclient** is the most widely used option on Linux:

- [github.com/ddclient/ddclient](https://github.com/ddclient/ddclient) — supports Cloudflare natively
- Create a Cloudflare API token with `Zone → DNS → Edit` permission, then add a config block like:

```
protocol=cloudflare
zone=YOUR_DOMAIN
login=token
password=YOUR_CLOUDFLARE_API_TOKEN
plex.YOUR_DOMAIN
```

- Run it as a systemd service or cron job; it will check your IP every few minutes and update the record only when it changes

**Other options:**

- [inadyn](https://github.com/troglobit/inadyn) — another solid DDNS client with Cloudflare support
- Many home routers (Asus, Synology, UniFi) have built-in DDNS clients that support Cloudflare directly — no separate software needed

### 3. Get a free SSL certificate via Let's Encrypt

[Let's Encrypt](https://letsencrypt.org/) issues free, trusted SSL certificates that auto-renew every 90 days via the ACME protocol. Because the skill endpoint and audio streams both require HTTPS, this is the standard approach for self-hosted setups.

**Recommended: acme.sh with Cloudflare DNS challenge**

[acme.sh](https://github.com/acmesh-official/acme.sh) is a lightweight shell script that handles issuance and renewal without any dependencies. Using the Cloudflare DNS-01 challenge means port 80 never needs to be open — renewal happens entirely through Cloudflare's API, which is ideal for home servers behind firewalls.

```bash
# Install acme.sh
curl https://get.acme.sh | sh

# Issue a certificate using Cloudflare DNS validation
export CF_Token="YOUR_CLOUDFLARE_API_TOKEN"
~/.acme.sh/acme.sh --issue --dns dns_cf -d plex.YOUR_DOMAIN

# Install into your web server cert path and reload on renewal
~/.acme.sh/acme.sh --install-cert -d plex.YOUR_DOMAIN \
  --cert-file      /etc/letsencrypt/live/YOUR_DOMAIN/cert.pem \
  --key-file       /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem \
  --fullchain-file /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem \
  --reloadcmd      "systemctl reload nginx"  # or httpd
```

acme.sh installs a cron job automatically; certificates renew silently in the background before they expire.

**Alternative: Certbot**

[Certbot](https://certbot.eff.org/) is the EFF's official ACME client and has a Cloudflare DNS plugin. It's a good choice if you prefer a more guided setup or are already using Certbot elsewhere.

```bash
pip install certbot certbot-dns-cloudflare
certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials ~/.secrets/cloudflare.ini \
  -d plex.YOUR_DOMAIN
```

Both tools place certificates in paths that match the `apache-vhost.conf` and `nginx-vhost.conf` configs included in this repo.

## Directory Structure

```
plex-alexa-skill-bridge/
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── app.py              # Flask application entry point
│       ├── plex/
│       │   └── client.py       # Plex API client (search, streaming)
│       └── skill/
│           ├── handler.py      # Alexa skill request handlers
│           └── queue.py        # In-memory per-device queue manager
├── apache-vhost.conf           # Apache reverse proxy config
├── nginx-vhost.conf            # nginx reverse proxy config
├── docker-compose.yml          # Docker Compose configuration
├── interaction_model.json      # Alexa skill interaction model
├── secrets/
│   └── plex_token.txt.example  # Copy to plex_token.txt and add your token
└── README.md
```

## Setup

### 1. Get your Plex token

1. Open Plex Web in your browser and play any media item
2. Open browser dev tools (F12) → Network tab
3. Find any request to your Plex server
4. Look for `X-Plex-Token` in the URL or request headers
5. Copy the token value

### 2. Download and configure

```bash
# Download the compose file
curl -O https://raw.githubusercontent.com/falk0069/plex-alexa-skill-bridge/main/docker-compose.yml

# Create the secrets directory and token file
mkdir -p secrets
echo "YOUR_ACTUAL_PLEX_TOKEN" > secrets/plex_token.txt
```

Edit `docker-compose.yml` and replace all `YOUR_*` placeholders:

```yaml
environment:
  - SKILL_HOSTNAME=plex.YOUR_DOMAIN      # e.g. plex.example.com (Alexa only allow https port 443)
  - PLEX_URL=http://YOUR_PLEX_IP:32400  # e.g. your local URL where Plex is at: http://192.168.1.100:32400
  - PLEX_PUBLIC_HOSTNAME=plex.YOUR_DOMAIN    # e.g. plex.example.com (suggest this be the same as the SKILL_HOSTNAME)
```

### 3. Set up your reverse proxy

Download the config for your web server, replace `YOUR_DOMAIN` and `YOUR_PLEX_IP` with your actual values, then install it.

**Apache:**
```bash
curl -O https://raw.githubusercontent.com/falk0069/plex-alexa-skill-bridge/main/apache-vhost.conf

# Edit the file, then install
sudo cp apache-vhost.conf /etc/httpd/conf.d/plex-alexa.conf

# Test and reload
sudo apachectl configtest && sudo systemctl reload httpd
```

**nginx:**
```bash
curl -O https://raw.githubusercontent.com/falk0069/plex-alexa-skill-bridge/main/nginx-vhost.conf

# Edit the file, then install
sudo cp nginx-vhost.conf /etc/nginx/conf.d/plex-alexa.conf

# Test and reload
sudo nginx -t && sudo systemctl reload nginx
```

### 4. Add DNS record

Add a DNS CNAME or A record for `plex.YOUR_DOMAIN` pointing to your server's public IP.

### 5. Start the container

```bash
docker compose pull
docker compose up -d

# Verify it's running and can reach Plex
curl https://plex.YOUR_DOMAIN/status
```

You should see "Connected" for the Plex server status.

### 6. Create the Alexa skill

1. Go to [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask)
2. Click **Create Skill**
   - Name: `Plex`
   - Language: `English (US)`
   - Model: `Custom`
   - Hosting: `Provision your own`
3. In **Build → Interfaces**, enable **Audio Player**
4. In **Build → Interaction Model → JSON Editor**, paste the contents of [`interaction_model.json`](https://raw.githubusercontent.com/falk0069/plex-alexa-skill-bridge/main/interaction_model.json)
5. Click **Save Model** then **Build Model**
6. In **Build → Endpoint**:
   - Select **HTTPS**
   - Default endpoint: `https://plex.YOUR_DOMAIN/skill`
   - Certificate: **My development endpoint has a certificate from a trusted certificate authority**
7. Click **Save Endpoints**
8. In the **Test** tab, set testing to **Development**

### 7. Test it

Say to your Echo: **"Alexa, ask Plex to play the artist [any artist in your library]"**

Watch the logs: `docker logs plex-alexa-skill -f`

## Voice Commands

| Say | What happens |
|-----|-------------|
| `ask Plex to play the artist Taylor Swift` | Shuffles all Taylor Swift songs |
| `ask Plex to play the album Rumours` | Plays album in order |
| `ask Plex to play the song Africa` | Plays that song |
| `ask Plex to play the playlist Road Trip` | Plays playlist |
| `ask Plex to shuffle Bon Jovi` | Shuffles all Bon Jovi songs |
| `ask Plex to play music from the 1980s` | Shuffles 80s music |
| `ask Plex to play music from the nineties` | Shuffles 90s music |
| `ask Plex to play some Rock` | Shuffles up to 100 Rock tracks |
| `ask Plex to play Jazz music` | Shuffles up to 100 Jazz tracks |
| `ask Plex to play music` | Shuffles your 100 most recently played tracks (falls back to random if no history) |
| `ask Plex to play recently played music` | Same as above |
| `ask Plex to play my most played music` | Shuffles your 100 most-played tracks |
| `ask Plex to play recently added music` | Plays newest tracks (30-day window, falls back to 1 year) |
| `ask Plex to play what's new` | Same as recently added |
| `Alexa, next` | Skips to next track |
| `Alexa, pause` | Pauses playback |
| `Alexa, resume` | Resumes playback |
| `ask Plex for help` | Lists available commands |

## Troubleshooting

### "I couldn't find that artist/song"
- Plex search is case-insensitive but spelling matters
- Try the exact name as it appears in your Plex library
- Check logs: `docker logs plex-alexa-skill -f`

### "There was a problem with the requested skill's response"
- Check the skill has AudioPlayer interface enabled in the developer console
- Verify the endpoint URL is saved correctly in the skill
- Check Apache logs for 403/502 errors

### Container loses internet access after `docker compose up`
If the container can't reach the internet (visible on the `/status` page), the most common causes are host firewall rules or Docker networking misconfiguration. Things to check:

- **Host firewall / iptables** — verify your firewall isn't blocking forwarded traffic from Docker's bridge network. Check `sudo iptables -L FORWARD -n` and make sure there's an `ACCEPT` rule for the `docker0` interface or the container subnet.
- **Docker bridge network** — run `docker network ls` and `docker network inspect bridge` to confirm the container has an IP and gateway assigned correctly.
- **Docker daemon restart** — sometimes Docker's internal routing gets into a bad state after a host reboot or network change. `sudo systemctl restart docker` followed by `docker compose up -d` often resolves it.
- **DNS inside the container** — if the container resolves hostnames but can't route packets, check `/etc/docker/daemon.json` for a custom `dns` entry and make sure it's reachable from the host.

### Alexa request verification fails / worker timeout
The skill verifier needs to fetch Amazon's certificate from the internet. If your container can't reach the internet, add `DISABLE_REQUEST_VERIFY=true` to docker-compose temporarily while debugging network issues.

### Audio plays but wrong artist keeps appearing
Make sure you're using `--workers 1` in the Dockerfile CMD. Multiple workers have separate in-memory queues and will mix up playback state.

## Security Notes

- The Plex token appears in stream URLs — this is unavoidable since Alexa fetches audio directly and cannot use custom headers
- Apache is configured to only allow `/skill`, `/status`, `/library/parts/`, and `/library/metadata/` — everything else returns 403
- `/skill` only accepts POST requests
- `/library/parts/` and `/library/metadata/` only accept GET/HEAD requests
- Consider rotating your Plex token periodically (update `secrets/plex_token.txt` and restart the container)
- Consider creating a dedicated Plex managed user with access only to the music library for an isolated token

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SKILL_HOSTNAME` | Yes | Public hostname for the skill endpoint (e.g. `plex.example.com`) |
| `PLEX_URL` | Yes | Internal Plex server URL (e.g. `http://192.168.1.100:32400`) |
| `PLEX_TOKEN` | Yes | Plex authentication token (or path to Docker secret file) |
| `PLEX_PUBLIC_HOSTNAME` | Yes | Public hostname for Plex streaming — FQDN only, no scheme (e.g. `plex.example.com`) |
| `PORT` | No | Port for Flask to listen on (default: `5001`) |
| `TZ` | No | Container timezone (default: `UTC`) other e.g America/Chicago |
| `ENABLE_STATUS_PAGE` | No | Set to `true` to enable the `/status` diagnostic page (disabled by default) |
| `DISABLE_REQUEST_VERIFY` | No | Set to `true` to skip Alexa signature verification (testing only) |

## Known Limitations

- Alexa's invocation model requires "ask Plex to..." — natural music commands like "Alexa, play X on Plex" are reserved for Amazon Music partners
- Queue state is in-memory — restarting the container clears all queues
- Decade search caps at 30 albums to avoid response timeouts
- Multi-device playback works but requires a single gunicorn worker (`--workers 1`) for shared queue state

## Building from source

If you want to modify the skill or experiment with the code:

```bash
git clone https://github.com/falk0069/plex-alexa-skill-bridge.git
cd plex-alexa-skill-bridge

# Create your secrets file
cp secrets/plex_token.txt.example secrets/plex_token.txt
echo "YOUR_ACTUAL_PLEX_TOKEN" > secrets/plex_token.txt
```

Edit `docker-compose.yml`, comment out the `image:` line, and uncomment `build: ./app`:

```yaml
services:
  plex-alexa-skill:
    # image: ghcr.io/falk0069/plex-alexa-skill-bridge:latest
    build: ./app
```

Then build and run:

```bash
docker compose up -d --build
```

If your container loses internet access after a rebuild, see the [Docker networking troubleshooting](#container-loses-internet-access-after-docker-compose-up) section.

## Contributing

Pull requests welcome. Please test against a real Plex library and Echo device before submitting.

## License

MIT
