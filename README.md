# Meshcord

A Discord bot that monitors Meshtastic radios via HTTP API and forwards all, or some, messages to a Discord channel. Perfect for keeping track of your mesh network activity in real-time.

## Features

- **Complete Message Coverage** - Captures ALL messages your radios receive (text, position, telemetry, node info)
- **Multi-Radio Support** - Monitor multiple Meshtastic devices simultaneously
- **No Message Filtering** - Unlike MQTT, gets private messages and everything else
- **Docker Ready** - Easy deployment with Docker Compose
- **Signal Information** - Shows SNR and RSSI for each message
- **Smart Deduplication** - Prevents duplicate messages using SQLite tracking
- **Real-time Monitoring** - Configurable polling interval (default 10 seconds)

## Preview

```
📻 **Home Radio** | `4abc1234` | 14:23:45
💬 Anyone copy? Testing from the trail
📶 SNR: 8.5 | RSSI: -45

📻 **Mobile Unit** | `5def5678` | 14:24:12
📍 Position update
📶 SNR: 12.2 | RSSI: -38
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Meshtastic radio(s) on your local network with HTTP API enabled
- Discord bot token and channel ID

### 1. Clone Repository

```bash
git clone https://github.com/sargonas/meshcord.git
cd meshcord
```

### 2. Configure

Edit `docker-compose.yml`:

```yaml
environment:
  # Required
  - DISCORD_BOT_TOKEN=your_discord_bot_token_here
  - DISCORD_CHANNEL_ID=your_discord_channel_id_here
  
  # Your radio(s)
  - RADIOS=[{"name": "Home Radio", "host": "192.168.1.100", "port": "80"}]
```

### 3. Run

```bash
mkdir data
docker-compose up -d
```

### 4. Check Logs

```bash
docker-compose logs -f
```

## Configuration

### Multiple Radios

```yaml
- RADIOS=[
    {"name": "Base Station", "host": "192.168.1.100", "port": "80"},
    {"name": "Mobile Unit", "host": "192.168.1.101", "port": "80"},
    {"name": "Repeater", "host": "meshtastic.local", "port": "80"}
  ]
```

### Single Radio (Alternative)

```yaml
- MESHTASTIC_HOST=192.168.1.100
- MESHTASTIC_PORT=80
- RADIO_NAME=My Radio
```

### Polling Interval

```yaml
- POLL_INTERVAL=10  # Check every 10 seconds (default)
- POLL_INTERVAL=5   # Faster polling
- POLL_INTERVAL=30  # Slower polling
```

### Message Type Controls

Control which message types get forwarded to Discord:

```yaml
# Core message types (default: enabled)
- SHOW_TEXT_MESSAGES=true           # Chat messages
- SHOW_POSITION_UPDATES=true        # GPS coordinates
- SHOW_NODE_INFO=true               # Device announcements  
- SHOW_TELEMETRY=true               # Battery, signal stats

# Advanced message types (default: enabled)
- SHOW_ADMIN=true                   # Admin/config messages
- SHOW_DETECTION_SENSOR=true       # Motion/sensor alerts
- SHOW_RANGE_TEST=true              # Range testing
- SHOW_STORE_FORWARD=true          # Store & forward

# Noisy message types (default: disabled)
- SHOW_ROUTING=false                # Network routing
- SHOW_UNKNOWN=false                # Unknown message types
```

**Common configuration scenarios:**

**Text messages only:**
```yaml
- SHOW_TEXT_MESSAGES=true
- SHOW_POSITION_UPDATES=false
- SHOW_NODE_INFO=false
- SHOW_TELEMETRY=false
```

**Everything except position spam:**
```yaml
- SHOW_POSITION_UPDATES=false
# (all others default to true)
```

**Emergency/important only:**
```yaml
- SHOW_TEXT_MESSAGES=true
- SHOW_DETECTION_SENSOR=true
- SHOW_ADMIN=true
# (disable the rest)
```

## Setup Guide

### Discord Bot Setup

1. **Create Bot Application:**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Click "New Application" and give it a name (e.g., "Meshtastic Monitor")
   - Go to "Bot" section in the left sidebar
   - Click "Add Bot" or "Create Bot"
   - Copy the bot token and save it securely

2. **Set Bot Permissions:**
   - In the Bot section, scroll down to "Privileged Gateway Intents"
   - Enable "Message Content Intent" (required to read message content)
   - Go to "OAuth2" → "URL Generator" in the left sidebar
   - Under "Scopes", check "bot"
   - Under "Bot Permissions", check:
     - **View Channels** (required - see the channel)
     - **Send Messages** (required - post Meshtastic messages)
     - **Send Messages in Threads** (recommended - if channel uses threads)
     - **Embed Links** (recommended - for rich message formatting)
     - **Attach Files** (optional - for future file attachments)
     - **Read Message History** (recommended - for troubleshooting)
     - **Use External Emojis** (optional - for custom emojis in messages)
     - **Add Reactions** (optional - for message reactions)
     - **Mention Everyone** (optional - if you want @everyone capabilities)

3. **Generate Invite URL:**
   - Copy the generated URL at the bottom
   - Open the URL in your browser
   - Select your Discord server
   - Click "Authorize"

4. **Get Channel ID:**
   - In Discord, go to User Settings → Advanced
   - Enable "Developer Mode"
   - Right-click your target channel → "Copy Channel ID"
   - Save this numeric ID

**Required Permissions Summary:**
- View Channels ✅
- Send Messages ✅
- Message Content Intent ✅ (in Bot settings)

**Recommended Permissions:**
- Send Messages in Threads
- Embed Links
- Read Message History
- Use External Emojis

**Optional Permissions:**
- Attach Files
- Add Reactions
- Mention Everyone

### Finding Radio IP Addresses

**Method 1: Router/DHCP**
Check your router's device list for "Meshtastic" devices.

**Method 2: Network Scan**
```bash
nmap -p 80 192.168.1.0/24 | grep -B5 "80/tcp open"
```

**Method 3: Test Connection**
```bash
# Test JSON endpoint
curl http://192.168.1.100/json/report
```

### Verify HTTP API Access

Test connectivity using the correct endpoints:

```bash
# Check if device responds (should return JSON with device info)
curl http://192.168.1.100/json/report

# Test the main data endpoint (returns protobuf binary data)
curl http://192.168.1.100/api/v1/fromradio
```

If these fail, check:
- Radio is powered on and connected to WiFi
- Correct IP address
- No firewall blocking port 80
- Radio firmware supports HTTP API (v2.0+)

## Message Types

The bot captures and displays:

- **Text Messages** - All chat messages and direct messages
- **Position Updates** - GPS coordinates and altitude
- **Node Information** - Device announcements and info
- **Telemetry** - Battery, voltage, channel utilization
- **Other** - Any other packet types with basic info

## Troubleshooting

### Bot Not Receiving Messages

1. **Check radio connectivity:**
   ```bash
   curl http://your-radio-ip/json/report
   ```

2. **Verify logs:**
   ```bash
   docker-compose logs -f
   ```

3. **Common issues:**
   - HTTP API disabled on radio
   - Wrong IP address (DHCP changes)
   - Radio powered off or unreachable
   - Wrong port (try 443 for HTTPS)

### Discord Issues

- Verify bot token is correct
- Check channel ID is numeric (no quotes)
- Ensure bot has "Send Messages" permission
- Confirm bot is added to the server

## Security

- Bot runs with host networking to access local radios
- Only message IDs stored for deduplication (no content)
- Consider firewall rules for radio access
- Database automatically cleans up old entries

## Architecture

```
┌─────────────────┐    HTTP API     ┌─────────────────┐
│  Meshtastic     │◄──────────────► │   Discord Bot   │
│  Radio(s)       │   (Port 80/443) │   (Container)   │
└─────────────────┘                 └─────────────────┘
                                            │
                                            ▼
                                    ┌─────────────────┐
                                    │ Discord Channel │
                                    └─────────────────┘
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | - | Discord bot token |
| `DISCORD_CHANNEL_ID` | Yes | - | Discord channel ID (numeric) |
| `RADIOS` | No | - | JSON array of radio configs |
| `MESHTASTIC_HOST` | No | `meshtastic.local` | Single radio host (fallback) |
| `MESHTASTIC_PORT` | No | `80` | Single radio port (fallback) |
| `RADIO_NAME` | No | `Radio` | Single radio name (fallback) |
| `POLL_INTERVAL` | No | `10` | Polling interval in seconds |
| **Message Type Controls** | | | |
| `SHOW_TEXT_MESSAGES` | No | `true` | Show chat messages |
| `SHOW_POSITION_UPDATES` | No | `true` | Show GPS updates |
| `SHOW_NODE_INFO` | No | `true` | Show device announcements |
| `SHOW_TELEMETRY` | No | `true` | Show battery/signal data |
| `SHOW_ADMIN` | No | `true` | Show admin messages |
| `SHOW_DETECTION_SENSOR` | No | `true` | Show sensor alerts |
| `SHOW_RANGE_TEST` | No | `true` | Show range tests |
| `SHOW_STORE_FORWARD` | No | `true` | Show store & forward |
| `SHOW_ROUTING` | No | `false` | Show routing messages |
| `SHOW_UNKNOWN` | No | `false` | Show unknown message types |# Meshtastic Discord Bot

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the Apache 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Meshtastic Project](https://meshtastic.org/) for the amazing mesh networking platform
- [Discord.py](https://discordpy.readthedocs.io/) for the Discord API wrapper

## Support

If you find this project helpful, please give it a star! For issues and feature requests, please use the [GitHub Issues](https://github.com/yourusername/meshtastic-discord-bot/issues) page.