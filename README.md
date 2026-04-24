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
├── docker-compose.yml          # Docker Compose configuration
├── fix-docker-iptables.sh      # Fix for Docker iptables issue
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

### 2. Clone and configure

```bash
git clone https://github.com/falk0069/plex-alexa-skill-bridge.git
cd plex-alexa-skill-bridge

# Create your secrets file
cp secrets/plex_token.txt.example secrets/plex_token.txt
echo "YOUR_ACTUAL_PLEX_TOKEN" > secrets/plex_token.txt
```

Edit `docker-compose.yml` and replace all `YOUR_*` placeholders:

```yaml
environment:
  - SKILL_HOSTNAME=plex.YOUR_DOMAIN      # e.g. plex.example.com
  - PLEX_HOST=http://YOUR_PLEX_IP:32400  # e.g. http://192.168.1.100:32400
  - PLEX_PUBLIC_HOST=https://plex.YOUR_DOMAIN
```

### 3. Set up Apache reverse proxy

Copy `apache-vhost.conf` into your Apache config, replacing `YOUR_DOMAIN` and `YOUR_PLEX_IP` with your actual values:

```bash
# Copy to your Apache conf.d or add to your existing vhosts file
sudo cp apache-vhost.conf /etc/httpd/conf.d/plex-alexa.conf

# Test and reload
sudo apachectl configtest && sudo systemctl reload httpd
```

### 4. Add DNS record

Add a DNS A record for `plex.YOUR_DOMAIN` pointing to your server's public IP.

### 5. Start the container

```bash
docker compose up -d --build

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
4. In **Build → Interaction Model → JSON Editor**, paste the contents of `interaction_model.json`
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

### Container loses internet access after `docker compose up --build`
This is a known Docker bug on some Linux systems where the iptables FORWARD rules get wiped during a compose rebuild. Install the fix script:

```bash
sudo cp fix-docker-iptables.sh /usr/local/bin/fix-docker-iptables
sudo chmod +x /usr/local/bin/fix-docker-iptables

# Add cron job to auto-heal every 2 minutes
echo "*/2 * * * * root /usr/local/bin/fix-docker-iptables >> /var/log/fix-docker-iptables.log 2>&1" \
  | sudo tee /etc/cron.d/fix-docker-forward

# Run manually after any docker compose up --build
sudo fix-docker-iptables
```

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
| `PLEX_HOST` | Yes | Internal Plex server URL (e.g. `http://192.168.1.100:32400`) |
| `PLEX_TOKEN` | Yes | Plex authentication token (or path to Docker secret file) |
| `PLEX_PUBLIC_HOST` | Yes | Public HTTPS URL for Plex streaming (e.g. `https://plex.example.com`) |
| `PORT` | No | Port for Flask to listen on (default: `5001`) |
| `TZ` | No | Container timezone (default: `UTC`) |
| `DISABLE_REQUEST_VERIFY` | No | Set to `true` to skip Alexa signature verification (testing only) |

## Known Limitations

- Alexa's invocation model requires "ask Plex to..." — natural music commands like "Alexa, play X on Plex" are reserved for Amazon Music partners
- Queue state is in-memory — restarting the container clears all queues
- Decade search caps at 30 albums to avoid response timeouts
- Multi-device playback works but requires a single gunicorn worker (`--workers 1`) for shared queue state

## Contributing

Pull requests welcome. Please test against a real Plex library and Echo device before submitting.

## License

MIT
