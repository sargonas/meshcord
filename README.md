# Meshcord - Meshtastic Discord Bridge

[![Tests](https://github.com/sargonas/meshcord/actions/workflows/ci.yml/badge.svg)](https://github.com/sargonas/meshcord/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A reliable Discord bridge for Meshtastic networks that automatically forwards messages and network activity to a Discord channel. Stay connected to your mesh network even when you're away from your radio!

## Features

### Dual Connection Methods
- **Serial Connection** (Recommended): 99.9% message reliability with direct USB connection
- **HTTP API Connection**: Network-based connection for WiFi-enabled radios
- **Multi-Radio Support**: Monitor multiple Meshtastic devices simultaneously

### Smart Message Handling
- **Real-time Discord integration** - Messages appear instantly in your Discord channel
- **Signal strength reporting** - Optional SNR and RSSI data display
- **Discord timestamps** - Shows time in each user's local timezone
- **Duplicate prevention** - Automatic deduplication of repeat messages
- **Persistent node database** - Remembers node names across restarts
- **Custom radio names** - Friendly display names for multi-radio setups

### Flexible Message Filtering
- **Granular control** - Choose which message types to forward
- **Smart node identification** - Shows friendly node names instead of hex IDs
- **Enhanced message formatting** - Rich Discord messages with radio source identification

### Data Management
- **Automatic database cleanup** - Configurable retention for processed messages
- **Node information tracking** - Stores and displays node names and details
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
- Docker and Docker Compose
- Discord bot token and channel ID
- Meshtastic device with network access or USB connection

### 1. Clone and Configure
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

### 3. Configure Environment
Edit `.env` with your settings:
```bash
# Required
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here

# Connection method
CONNECTION_METHOD=http  # or 'serial'
MESHTASTIC_HOST=192.168.1.100  # Your radio's IP
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

# Check logs
docker logs -f meshcord-bot
```

#### Option B: Using Docker Compose with Pre-built Image
Create a simple `docker-compose.yml`:
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

#### Serial Connection (Recommended)
```bash
CONNECTION_METHOD=serial
SERIAL_PORT=/dev/ttyUSB0  # Linux/macOS
# SERIAL_PORT=COM3        # Windows
```

#### HTTP Connection
```bash
CONNECTION_METHOD=http
MESHTASTIC_HOST=192.168.1.100
MESHTASTIC_PORT=80
RADIO_NAME=HomeRadio
RADIO_DISPLAY_NAME="Home Base Station"  # Optional: Custom name for Discord
POLL_INTERVAL=2.0  # Seconds between polls
```

#### Multiple Radio Monitoring
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

## Development Setup

### Local Development
```bash
# Clone repository
git clone https://github.com/sargonas/meshcord.git
cd meshcord

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Run the bot
python meshcord_bot.py
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run unit tests only
pytest tests/test_meshcord.py -v

# Run integration tests only
pytest tests/integration/ -v
```

### Docker Development
```bash
# Build development image
docker build -t meshcord:dev .

# Run with development settings
docker run -it --env-file .env meshcord:dev
```

## Troubleshooting

### Common Issues

#### No Messages Appearing
1. **Check Discord Permissions**: Ensure bot has "Send Messages" permission
2. **Verify Channel ID**: Confirm `DISCORD_CHANNEL_ID` is correct
3. **Connection Issues**: Check radio IP/connectivity for HTTP mode
4. **Message Filtering**: Verify enabled message types in configuration

#### Serial Connection Problems
```bash
# Check device permissions
ls -la /dev/tty*
sudo usermod -a -G dialout $USER

# Verify device path
dmesg | grep tty
```

#### High CPU Usage
```bash
# Check polling interval
echo $POLL_INTERVAL  # Should be ≥ 1.0 for production

# Monitor resource usage
docker stats meshcord-bot
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

## Connection Method Comparison

| Method | Reliability | Setup Difficulty | Use Case |
|--------|-------------|------------------|----------|
| Serial | 99.9% | Easy | Direct USB connection |
| HTTP | ~85-90% | Medium | Network/WiFi connection |

Serial connection is recommended for maximum reliability as it receives every message in real-time without polling limitations.

If you must use HTTP, optimize with:
```bash
POLL_INTERVAL=1.0  # Faster polling
DEBUG_MODE=true    # Monitor for missed messages
```

The HTTP API only holds one message at a time, so faster polling helps reduce message loss.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`pytest tests/`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guidelines
- Add tests for new functions
- Update documentation for new features
- Use conventional commit messages

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Meshtastic Project** - For the amazing mesh networking platform
- **Discord.py** - For the excellent Discord API library
- **Contributors** - Everyone who helps improve Meshcord

## Related Projects

- [Meshtastic](https://meshtastic.org/) - The mesh networking platform
- [Meshtastic Python](https://github.com/meshtastic/Meshtastic-python) - Python API library
- [Discord.py](https://github.com/Rapptz/discord.py) - Discord API wrapper

## Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/sargonas/meshcord/issues)
- **Discord**: [Meshtastic Discord Community](https://discord.gg/ktMAKGBnBs)

---

<div align="center">

**Made with ❤️ for the Meshtastic community**

[⭐ Star this project](https://github.com/sargonas/meshcord) | [🐛 Report issues](https://github.com/sargonas/meshcord/issues) | [💡 Request features](https://github.com/sargonas/meshcord/issues/new)

</div>