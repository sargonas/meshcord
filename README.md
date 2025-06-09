# Meshcord 📻➡️💬

**A Discord bridge for Meshtastic networks**

Meshcord connects your Meshtastic radio network to Discord, automatically forwarding messages and network activity to a Discord channel. Stay connected to your mesh network even when you're away from your radio!

[![CI Status](https://github.com/yourusername/meshcord/workflows/Meshcord%20CI/badge.svg)](https://github.com/yourusername/meshcord/actions)
[![Docker Image](https://img.shields.io/docker/image-size/yourusername/meshcord)](https://hub.docker.com/r/yourusername/meshcord)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## ✨ Features

- **📱 Real-time Discord integration** - Messages appear instantly in your Discord channel
- **🔗 Multiple connection methods** - HTTP API or direct serial connection
- **📡 Multi-radio support** - Monitor multiple Meshtastic devices simultaneously
- **👤 Smart node identification** - Shows friendly node names instead of hex IDs
- **🎛️ Flexible message filtering** - Choose which message types to forward
- **📊 Signal strength reporting** - Includes SNR and RSSI data
- **🔄 Duplicate prevention** - Automatic deduplication of repeat messages
- **💾 Persistent node database** - Remembers node names across restarts
- **🐳 Docker ready** - Easy deployment with Docker Compose
- **🔧 Comprehensive testing** - Full unit and integration test suite

## 📋 Message Types Supported

| Type | Description | Default |
|------|-------------|---------|
| 💬 Text Messages | Chat messages between nodes | ✅ Enabled |
| 📍 Position Updates | GPS location broadcasts | ✅ Enabled |
| ℹ️ Node Info | Device information and names | ✅ Enabled |
| 📊 Telemetry | Battery, temperature, etc. | ✅ Enabled |
| ⚙️ Admin | Administrative commands | ✅ Enabled |
| 🚨 Detection Sensor | Motion/presence detection | ✅ Enabled |
| 📏 Range Test | Signal testing messages | ✅ Enabled |
| 💾 Store & Forward | Delayed message delivery | ✅ Enabled |
| 🔄 Routing | Network routing information | ❌ Disabled |
| ❓ Unknown | Unrecognized message types | ❌ Disabled |

## 🚀 Quick Start

### Docker (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/meshcord.git
   cd meshcord
   ```

2. **Set up configuration:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your settings
   ```

3. **Configure your Discord bot:**
   - Create a Discord application at https://discord.com/developers/applications
   - Create a bot and copy the token
   - Add the bot to your server with "Send Messages" permission
   - Get your channel ID (Developer Mode > Right-click channel > Copy ID)

4. **Run with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

5. **Check the logs:**
   ```bash
   docker-compose logs -f
   ```

### Python (Direct)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   ```bash
   export DISCORD_BOT_TOKEN="your_bot_token"
   export DISCORD_CHANNEL_ID="your_channel_id"
   export MESHTASTIC_HOST="192.168.1.100"  # Your radio's IP
   ```

3. **Run the bot:**
   ```bash
   python meshcord_bot.py
   ```

## ⚙️ Configuration

### Required Settings

```bash
# Discord Configuration
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_CHANNEL_ID=your_discord_channel_id_here
```

### Connection Methods

#### HTTP Connection (Default)
```bash
CONNECTION_METHOD=http
MESHTASTIC_HOST=192.168.1.100
MESHTASTIC_PORT=80
RADIO_NAME=MyRadio
POLL_INTERVAL=2  # seconds
```

#### Serial Connection (Recommended for reliability)
```bash
CONNECTION_METHOD=serial
SERIAL_PORT=/dev/ttyUSB0
```

#### Multiple Radios
```bash
RADIOS='[
  {"name": "Home", "host": "192.168.1.100", "port": "80"},
  {"name": "Mobile", "host": "192.168.1.101", "port": "80"},
  {"name": "Repeater", "host": "10.0.0.50", "port": "80"}
]'
```

### Message Filtering

```bash
# Enable/disable specific message types
SHOW_TEXT_MESSAGES=true
SHOW_POSITION_UPDATES=true
SHOW_NODE_INFO=true
SHOW_TELEMETRY=true
SHOW_ROUTING=false        # Usually disabled (noisy)
SHOW_ADMIN=true
SHOW_DETECTION_SENSOR=true
SHOW_RANGE_TEST=true
SHOW_STORE_FORWARD=true
SHOW_UNKNOWN=false        # Usually disabled
```

### Advanced Options

```bash
DEBUG_MODE=true           # Enable detailed logging
POLL_INTERVAL=1           # Faster polling (HTTP only)
```

## 💬 Discord Message Format

Messages appear in Discord with this format:

```
📻 **RadioName** | **NodeName (12345678)** | 14:32:15
💬 Hello from the mesh network!
📶 SNR: 5.2 | RSSI: -85
```

- **📻 Radio source** - Which radio received the message
- **👤 Node identification** - Friendly name with hex ID fallback
- **🕒 Timestamp** - When the message was received
- **📶 Signal strength** - SNR and RSSI values
- **📱 Message type icon** - Visual indicator of message type

## 🔧 Connection Reliability

### HTTP vs Serial

| Method | Reliability | Setup Difficulty | Use Case |
|--------|------------|------------------|----------|
| **Serial** | 99.9% | Easy | Direct USB connection |
| **HTTP** | ~85-90% | Medium | Network/WiFi connection |

**Serial connection is recommended** for maximum reliability as it receives every message in real-time without polling limitations.

### HTTP Optimization

If you must use HTTP, optimize with:
```bash
POLL_INTERVAL=1           # Faster polling
DEBUG_MODE=true           # Monitor for missed messages
```

The HTTP API only holds one message at a time, so aggressive polling helps reduce message loss.

## 🏗️ Development

### Running Tests

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=meshcord_bot --cov-report=html

# Run only unit tests
pytest tests/test_meshcord.py -v

# Run only integration tests
pytest tests/integration/ -v
```

### Code Quality

```bash
# Format code
black meshcord_bot.py

# Sort imports
isort meshcord_bot.py

# Lint code
flake8 meshcord_bot.py

# Type checking
mypy meshcord_bot.py --ignore-missing-imports
```

## 📊 Monitoring

### Health Checks

Docker includes automatic health checks:
```bash
# Check container health
docker ps

# View detailed health
docker inspect meshcord-bot | grep Health -A 10
```

### Logs

```bash
# Follow logs in real-time
docker-compose logs -f

# View recent logs
docker-compose logs --tail=50

# Enable debug logging
DEBUG_MODE=true
```

### Database

Node information and message tracking:
```bash
# Access database
docker exec -it meshcord-bot sqlite3 /app/data/message_tracking.db

# View tables
.tables

# Check node names
SELECT * FROM nodes;

# Check recent messages
SELECT * FROM processed_messages ORDER BY processed_at DESC LIMIT 10;
```

## 🛠️ Troubleshooting

### Common Issues

**No messages appearing:**
- Check Discord bot permissions
- Verify channel ID is correct
- Enable debug mode to see processing logs
- For HTTP: check radio IP and connectivity

**Missing node names:**
- Node names are learned from nodeinfo messages
- Takes time to populate as nodes broadcast info
- Check `nodes` table in database

**Serial connection issues:**
- Verify device path (`ls /dev/tty*`)
- Check permissions (`sudo usermod -a -G dialout $USER`)
- Ensure radio is in serial mode, not just USB power

**High memory usage:**
- Database cleanup runs automatically every 24 hours
- Check for debug mode enabled in production
- Restart container periodically if needed

### Debug Mode

Enable comprehensive logging:
```bash
DEBUG_MODE=true
```

This shows:
- HTTP request/response details
- Protobuf parsing information
- Message filtering decisions
- Database operations
- Discord API calls

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`pytest tests/`)
6. Run code quality checks (`flake8`, `black`, `mypy`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

### Development Setup

```bash
# Clone and setup
git clone https://github.com/yourusername/meshcord.git
cd meshcord
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
pip install -r requirements-test.txt

# Run tests
pytest tests/ -v

# Start development
python meshcord_bot.py
```

## 📄 License

This project is licensed under the Apache 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Meshtastic Project** - For the amazing mesh networking platform
- **Discord.py** - For the excellent Discord API library
- **Contributors** - Everyone who helps improve Meshcord

## 🔗 Related Projects

- [Meshtastic](https://meshtastic.org/) - The mesh networking platform
- [Meshtastic Python](https://github.com/meshtastic/Meshtastic-python) - Python API library
- [Discord.py](https://github.com/Rapptz/discord.py) - Discord API wrapper

---

**Questions? Issues? Suggestions?**

- 🐛 [Report bugs](https://github.com/yourusername/meshcord/issues)
- 💡 [Request features](https://github.com/yourusername/meshcord/discussions)
- 💬 [Join discussions](https://github.com/yourusername/meshcord/discussions)

**Made with ❤️ for the Meshtastic community**