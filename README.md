# Meshcord - Meshtastic Discord Bridge

[![Tests](https://github.com/sargonas/meshcord/actions/workflows/ci.yml/badge.svg)](https://github.com/sargonas/meshcord/actions/workflows/ci.yml)
[![GitHub Container Registry](https://img.shields.io/badge/ghcr.io-container-blue?logo=docker)](https://github.com/sargonas/meshcord/pkgs/container/meshcord)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A reliable Discord bridge for Meshtastic networks that automatically forwards messages and network activity to a Discord channel. Stay up to date with what's happening on your mesh network even when you're away from your radio!

## Features

### Dual Connection Methods
- **HTTP API Connection** (Good): Network-based connection for WiFi-enabled radios
- **Serial Connection**: (Best) Direct USB connection for maximum reliability
- **Multi-Radio Support**: Monitor multiple Meshtastic devices simultaneously (when using http)

### Smart Message Handling
- **Real-time Discord integration** - Messages appear instantly in your Discord channel
- **Signal strength reporting** - Optional SNR and RSSI data display
- **Discord timestamps** - Shows time in each user's local timezone
- **Duplicate prevention** - Automatic deduplication of repeat messages
- **Persistent node database** - Remembers node names across restarts and matches them to radio hashes
- **Custom radio names** - Friendly display names for multi-radio setups

### Flexible Message Filtering
- **Granular control** - Choose which message types to forward to Discord
- **Smart node identification** - Shows friendly node names instead of their hex IDs (once at least one info packet has been received from that node)
- **Enhanced message formatting** - Rich Discord messages with radio source identification, and location links (when available)

### Data Management
- **Automatic database cleanup** - Configurable retention for processed messages
- **Node information tracking** - Stores and displays node names and details based on info packets
- **Message deduplication** - Prevents duplicate messages across polling cycles

## Message Types & Icons

| Type | Description | Icon | Default |
|------|-------------|------|---------|
| Text Messages | Chat messages between nodes | 💬 | Enabled |
| Position Updates | GPS location broadcasts | 📍 | Enabled |
| Node Information | Device information and friendly names | ℹ️ | Enabled |
| Telemetry | Battery, temperature, and system metrics | 📊 | Enabled |
| Admin Messages | Administrative commands and responses | ⚙️ | Enabled |
| Detection Sensor | Motion/presence detection alerts | 🚨 | Enabled |
| Range Testing | Signal testing and range validation | 📏 | Enabled |
| Store & Forward | Delayed message delivery notifications | 💾 | Enabled |
| Routing | Network routing information | 🔄 | Disabled |
| Unknown | Unrecognized message types | ❓ | Disabled |

## Quick Start

### Prerequisites
- Docker and Docker Compose (recommended) OR Python 3.8+ and python modules from requirements.txt
- Discord bot token and channel ID
- Meshtastic device with network access or USB serial connection

### 1. Clone and Configure (optional)
```bash
git clone https://github.com/sargonas/meshcord.git
cd meshcord
cp .env.example .env
```

### 2. Set Up Discord Bot
1. Create a Discord application at [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a bot and copy the token
3. Add bot to your server with "Send Messages" permission
4. Get your channel ID (Enable Developer Mode → Right-click channel → Copy ID)

### 3. Configure Environment (Only needed if optional step 1 chosen, otherwise these values are set in Docker Compose)
Edit `.env` with your settings:
```bash
# Required
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here

# Connection method (http is default)
CONNECTION_METHOD=http  # or 'serial'
MESHTASTIC_HOST=192.168.1.100  # Your radio's IP (for HTTP mode)
```

### 4. Deploy

#### Option A: Using Pre-built Docker Image (Recommended)
```bash
# Create data volume
docker volume create meshcord_data

# Run with Docker directly
docker run -d \
  --name meshcord-bot \
  --restart unless-stopped \
  -e DISCORD_BOT_TOKEN=your_bot_token_here \
  -e DISCORD_CHANNEL_ID=your_channel_id_here \
  -e CONNECTION_METHOD=http \
  -e MESHTASTIC_HOST=192.168.1.100 \
  -v meshcord_data:/app/data \
  ghcr.io/sargonas/meshcord:latest

# For serial connection, add device mapping:
docker run -d \
  --name meshcord-bot \
  --restart unless-stopped \
  --device=/dev/ttyUSB0:/dev/ttyUSB0 \
  -e DISCORD_BOT_TOKEN=your_bot_token_here \
  -e DISCORD_CHANNEL_ID=your_channel_id_here \
  -e CONNECTION_METHOD=serial \
  -e SERIAL_PORT=/dev/ttyUSB0 \
  -v meshcord_data:/app/data \
  ghcr.io/sargonas/meshcord:latest

# Check logs
docker logs -f meshcord-bot
```

#### Option B: Using Docker Compose with Pre-built Image
Create a simple `docker-compose.yml`:

**For HTTP Connection:**
```yaml
services:
  meshcord:
    image: ghcr.io/sargonas/meshcord:latest
    container_name: meshcord-bot
    restart: unless-stopped
    environment:
      DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN}
      DISCORD_CHANNEL_ID: ${DISCORD_CHANNEL_ID}
      CONNECTION_METHOD: ${CONNECTION_METHOD:-http}
      MESHTASTIC_HOST: ${MESHTASTIC_HOST:-meshtastic.local}
      MESHTASTIC_PORT: ${MESHTASTIC_PORT:-80}
      RADIO_NAME: ${RADIO_NAME:-Radio}
      POLL_INTERVAL: ${POLL_INTERVAL:-2.0}
      DEBUG_MODE: ${DEBUG_MODE:-false}
    volumes:
      - meshcord_data:/app/data

volumes:
  meshcord_data:
    external: true
```

**For Serial Connection:**
```yaml
services:
  meshcord:
    image: ghcr.io/sargonas/meshcord:latest
    container_name: meshcord-bot
    restart: unless-stopped
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0"  # Map your USB device
    environment:
      DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN}
      DISCORD_CHANNEL_ID: ${DISCORD_CHANNEL_ID}
      CONNECTION_METHOD: serial
      SERIAL_PORT: /dev/ttyUSB0
      DEBUG_MODE: ${DEBUG_MODE:-false}
    volumes:
      - meshcord_data:/app/data

volumes:
  meshcord_data:
    external: true
```

Then run:
```bash
docker-compose up -d
docker-compose logs -f meshcord
```

#### Option C: Build from Source
```bash
# Create data volume
docker volume create meshcord_data

# Start the service
docker-compose up -d

# Check logs
docker-compose logs -f meshcord
```

## Configuration Options

### Connection Methods

#### HTTP Connection (Default)
```bash
CONNECTION_METHOD=http
MESHTASTIC_HOST=192.168.1.100
MESHTASTIC_PORT=80
RADIO_NAME=HomeRadio
RADIO_DISPLAY_NAME="Home Base Station"  # Optional: Custom name for Discord
POLL_INTERVAL=2.0  # Seconds between polls. Note that messages received between polling periods can be overwritten by new incomming messages and lost
```

#### Serial Connection
```bash
CONNECTION_METHOD=serial
SERIAL_PORT=/dev/ttyUSB0  # Linux/macOS
or
SERIAL_PORT=COM3        # Windows (when running natively)
```

**Serial Connection Requirements:**
- Direct USB connection to Meshtastic device
- Proper device permissions (see troubleshooting section)
- Meshtastic Python library installed (`pip install meshtastic` or simply `pip install -r requirements.txt` if source code was pulled)

#### Multiple Radio Monitoring (HTTP Only)
```bash
RADIOS: |
  [
    {"name": "radio1", "host": "192.168.1.100", "port": "80", "display_name": "Home Base Station"},
    {"name": "radio2", "host": "192.168.1.101", "port": "80", "display_name": "Mobile Unit"},
    {"name": "radio3", "host": "10.0.0.50", "port": "80", "display_name": "Remote Repeater"}
  ]
```

### Message Filtering
```bash
# Control which message types are forwarded to Discord
SHOW_TEXT_MESSAGES=true        # Chat messages between nodes
SHOW_POSITION_UPDATES=true     # GPS location broadcasts
SHOW_NODE_INFO=true            # Device information and names
SHOW_TELEMETRY=true            # Battery, temperature, etc.
SHOW_ROUTING=false             # Network routing information (usually noisy)
SHOW_ADMIN=true                # Administrative commands
SHOW_DETECTION_SENSOR=true     # Motion/presence detection
SHOW_RANGE_TEST=true           # Signal testing messages
SHOW_STORE_FORWARD=true        # Delayed message delivery
SHOW_UNKNOWN=false             # Unrecognized message types

# Signal strength reporting (optional)
SHOW_SIGNAL_STRENGTH=true      # Include SNR and RSSI data in messages
```

## Message Format Examples

### Text Message (with signal strength)
```
📻 **Home Base Station (192.168.1.100)** | **Alice (12345678)** | <t:1640995200:t>
💬 Hello from the mesh network!
📶 SNR: 5.2 | RSSI: -85
```

### Text Message (without signal strength)
```
📻 **Home Base Station (192.168.1.100)** | **Alice (12345678)** | <t:1640995200:t>
💬 Hello from the mesh network!
```

### Position Update
```
📻 **Mobile Repeater (192.168.1.101)** | **Bob's Radio (87654321)** | <t:1640995300:t>
📍 Position update
📶 SNR: 3.1 | RSSI: -92
```

### Telemetry Data
```
📻 **Remote Cabin (10.0.0.50)** | **Weather Station (abcdef12)** | <t:1640995400:t>
📊 Telemetry data
📶 SNR: 7.8 | RSSI: -78
```

## Troubleshooting

### Common Issues

#### No Messages Appearing
1. **Check Discord Permissions**: Ensure bot has "Send Messages" permission
2. **Verify Channel ID**: Confirm `DISCORD_CHANNEL_ID` is correct
3. **Connection Issues**: Check radio IP/connectivity for HTTP mode
4. **Message Filtering**: Verify enabled message types in configuration

#### Serial Connection Problems

**Device Permission Issues:**
```bash
# Check device permissions (Linux/macOS)
ls -la /dev/tty*

# For macOS, you might need:
sudo dseditgroup -o edit -a $USER -t user wheel

# Verify device path
dmesg | grep tty  # Linux
system_profiler SPUSBDataType | grep -A 5 -B 5 "Meshtastic"  # macOS
```

**Docker Serial Connection:**
```bash
# Ensure device is mapped correctly
docker run --device=/dev/ttyUSB0:/dev/ttyUSB0 ...

# For Docker Compose, ensure devices section is correct:
devices:
  - "/dev/ttyUSB0:/dev/ttyUSB0"

# For Linux, ensure permissions are correct
sudo chmod a+rw /dev/ttyUSB0
```

**Serial Port Detection:**
```bash
# Test Meshtastic connection
meshtastic --port /dev/ttyUSB0 --info
```

#### HTTP Connection Problems
```bash
# Test radio connectivity
curl http://192.168.1.100/api/v1/fromradio

# Check radio web interface
# Navigate to http://192.168.1.100 in browser
```

#### Database Issues
```bash
# Check database integrity
docker exec meshcord-bot sqlite3 /app/data/message_tracking.db "PRAGMA integrity_check;"

# Manual cleanup
docker exec meshcord-bot sqlite3 /app/data/message_tracking.db "VACUUM;"
```

### Debug Mode
Enable comprehensive logging:
```bash
DEBUG_MODE=true
```

### Connection Method Decision Guide

**Choose Serial When:**
- You have direct USB access to the Meshtastic device
- Maximum reliability is required
- You want real-time message delivery
- Device doesn't have WiFi or network connectivity

**Choose HTTP When:**
- Device is network-connected but not locally accessible via USB
- You want to monitor multiple radios simultaneously
- Device is in a remote location
- You're running Meshcord on a different machine than the radio

## Connection Method Comparison

| Method | Reliability | Setup Difficulty | Multi-Radio | Use Case |
|--------|-------------|------------------|-------------|----------|
| Serial | ~99%* | Easy | No | Direct USB connection |
| HTTP | ~80-90% | Medium | Yes | Network/WiFi connection |

**Serial Connection Notes:**
- Uses the Meshtastic Python library for direct device communication
- Receives packets in real-time as they arrive
- Requires physical USB connection to the device
- Single radio per instance
- **Built-in resilience**: Automatic error recovery and connection health monitoring
- All messages received by radio are queued up and passed along in sequence without fail

**HTTP Connection Notes:**
- Polls the device's web API for new messages
- API only holds one message at a time, so some messages may be missed with slow polling
- Can monitor multiple radios from one instance
- Works over network/WiFi connections

*\*Serial reliability note: While the underlying serial connection can experience occasional data corruption and protocol errors (common with USB/serial communications), Meshcord includes robust error handling that automatically recovers from these issues. You may see occasional parsing errors in the logs, but these are safely handled and do not affect message forwarding.*

If you must use HTTP, optimize with:
```bash
POLL_INTERVAL=1.0  # Faster polling (minimum recommended)
DEBUG_MODE=true    # Monitor for missed messages
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`python -m pytest tests/`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Meshtastic Project** - For the amazing mesh networking platform
- **Discord.py** - For the excellent Discord API library
- **Contributors** - Everyone who helps improve Meshcord

## Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/sargonas/meshcord/issues)
- **Comments and Feedback**: [Non-issues can be opened in Discussions](https://github.com/sargonas/meshcord/discussions)
---
