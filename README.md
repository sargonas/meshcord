# 🌐 Meshcord - Enhanced Meshtastic Discord Bridge

[![CI/CD Pipeline](https://github.com/sargonas/meshcord/actions/workflows/ci.yml/badge.svg)](https://github.com/sargonas/meshcord/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/sargonas/meshcord/branch/main/graph/badge.svg)](https://codecov.io/gh/sargonas/meshcord)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Docker Pulls](https://img.shields.io/docker/pulls/sargonas/meshcord)](https://hub.docker.com/r/sargonas/meshcord)

A robust, feature-rich Discord bridge for Meshtastic networks with enterprise-grade reliability, comprehensive monitoring, and advanced message handling capabilities.

## ✨ Enhanced Features

### 🔌 **Dual Connection Methods**
- **Serial Connection** (Recommended): 99.9% message reliability with direct USB connection
- **HTTP API Connection**: Network-based with circuit breaker protection and retry logic
- **Multi-Radio Support**: Monitor multiple Meshtastic devices simultaneously

### 📊 **Advanced Monitoring & Observability**
- **Real-time Statistics**: Message processing metrics, error tracking, duplicate detection
- **Health Checks**: Comprehensive container and application health monitoring
- **Prometheus Integration**: Built-in metrics endpoint for monitoring dashboards
- **Database Analytics**: Historical statistics and performance tracking

### 🛡️ **Enterprise-Grade Reliability**
- **Circuit Breaker Pattern**: Automatic failure detection and recovery
- **Exponential Backoff**: Intelligent retry mechanisms for network failures
- **Graceful Shutdown**: Clean resource cleanup and connection handling
- **Message Deduplication**: Prevents duplicate messages across polling cycles

### 🎛️ **Flexible Configuration**
- **Granular Message Filtering**: Control exactly which message types are forwarded
- **Dynamic Polling**: Adaptive polling intervals based on network activity
- **Enhanced Message Formatting**: Rich Discord messages with signal strength data
- **Multi-Environment Support**: Development, staging, and production configurations
- **Custom Radio Names**: Friendly display names for multi-radio setups

### 🗄️ **Enhanced Data Management**
- **Automatic Database Cleanup**: Configurable retention policies for messages and statistics
- **Node Information Tracking**: Persistent storage of node names and hardware details
- **Backup Integration**: Automated database backups with compression
- **Performance Optimization**: WAL mode SQLite with proper indexing

## 📋 Message Types & Icons

| Type | Description | Icon | Default |
|------|-------------|------|---------|
| 💬 Text Messages | Chat messages between nodes | 💬 | ✅ Enabled |
| 📍 Position Updates | GPS location broadcasts with coordinates | 📍 | ✅ Enabled |
| ℹ️ Node Information | Device information and friendly names | ℹ️ | ✅ Enabled |
| 📊 Telemetry | Battery, temperature, and system metrics | 📊 | ✅ Enabled |
| ⚙️ Admin Messages | Administrative commands and responses | ⚙️ | ✅ Enabled |
| 🚨 Detection Sensor | Motion/presence detection alerts | 🚨 | ✅ Enabled |
| 📏 Range Testing | Signal testing and range validation | 📏 | ✅ Enabled |
| 💾 Store & Forward | Delayed message delivery notifications | 💾 | ✅ Enabled |
| 🔄 Routing | Network routing information | 🔄 | ❌ Disabled |
| ❓ Unknown | Unrecognized message types | ❓ | ❌ Disabled |

## 🚀 Quick Start

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
```bash
# Create data volume
docker volume create meshcord_data

# Start the service
docker-compose up -d

# Check logs
docker-compose logs -f meshcord
```

## 🔧 Configuration Options

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
RADIOS=[
  {"name": "radio1", "host": "192.168.1.100", "port": "80", "display_name": "Home Base Station"},
  {"name": "radio2", "host": "192.168.1.101", "port": "80", "display_name": "Mobile Unit"},
  {"name": "radio3", "host": "10.0.0.50", "port": "80", "display_name": "Remote Repeater"}
]
```

### Advanced Configuration

#### Performance Tuning
```bash
# Circuit breaker settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=60

# HTTP optimization
MAX_CONCURRENT_REQUESTS=10
HTTP_TIMEOUT=5
```

#### Database Management
```bash
# Retention policies
MESSAGE_RETENTION_HOURS=24
STATS_RETENTION_DAYS=30

# Backup settings
ENABLE_BACKUPS=true
BACKUP_SCHEDULE="0 2 * * *"  # Daily at 2 AM
BACKUP_RETENTION=7
```

#### Monitoring
```bash
# Enable metrics endpoint
ENABLE_METRICS=true
METRICS_PORT=8080

# Statistics reporting
STATS_REPORT_INTERVAL=5  # Minutes
```

## 📊 Monitoring and Observability

### Built-in Health Checks
The container includes comprehensive health checks:
```bash
# Check container health
docker ps
docker inspect meshcord-bot | grep Health -A 10
```

### Prometheus Metrics
Enable metrics collection:
```bash
ENABLE_METRICS=true
```

Access metrics at `http://localhost:8080/metrics`

### Database Analytics
```bash
# Access database directly
docker exec -it meshcord-bot sqlite3 /app/data/message_tracking.db

# View recent statistics
SELECT * FROM statistics ORDER BY timestamp DESC LIMIT 10;

# Check node information
SELECT * FROM nodes WHERE last_seen > strftime('%s', 'now', '-1 day');
```

### Log Analysis
```bash
# Real-time logs
docker-compose logs -f meshcord

# Structured logging with timestamps
docker-compose logs --timestamps meshcord

# Filter by log level
docker-compose logs meshcord | grep ERROR
```

## 🔧 Development Setup

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

# Run tests
pytest tests/ -v --cov=meshcord_bot

# Format code
black meshcord_bot.py
isort meshcord_bot.py

# Type checking
mypy meshcord_bot.py --ignore-missing-imports
```

### Testing
```bash
# Unit tests
pytest tests/test_meshcord.py -v

# Integration tests
pytest tests/integration/ -v

# Coverage report
pytest tests/ --cov=meshcord_bot --cov-report=html
```

### Docker Development
```bash
# Build development image
docker build -t meshcord:dev .

# Run with development settings
docker run -it --env-file .env.dev meshcord:dev
```

## 📈 Message Format Examples

### Text Message
```
📻 **Home Base Station (192.168.1.100)** | **Alice (12345678)** | 14:32:15
💬 Hello from the mesh network!
📶 SNR: 5.2 | RSSI: -85
```

### Position Update
```
📻 **Mobile Repeater (192.168.1.101)** | **Bob's Radio (87654321)** | 09:15:43
📍 Position: 34.052235, -118.243685 (Alt: 123m)
📶 SNR: 3.1 | RSSI: -92
```

### Telemetry Data
```
📻 **Remote Cabin (10.0.0.50)** | **Weather Station (abcdef12)** | 16:45:22
📊 Batt: 85% | Volt: 4.12V | Chan: 12.3% | Air: 8.7%
📶 SNR: 7.8 | RSSI: -78
```

## 🚨 Troubleshooting

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
LOG_LEVEL=DEBUG
```

## 📊 Performance Recommendations

### Production Deployment
- **Serial Connection**: Use for maximum reliability
- **Polling Interval**: 2-5 seconds for HTTP connections
- **Resource Limits**: 256MB RAM, 0.5 CPU cores
- **Monitoring**: Enable Prometheus metrics
- **Backups**: Configure automatic database backups

### High-Volume Networks
- **Message Filtering**: Disable noisy message types (routing, unknown)
- **Retention Policy**: Reduce `MESSAGE_RETENTION_HOURS` for busy networks
- **Circuit Breaker**: Lower failure threshold for faster recovery
- **Database**: Consider external database for very high volume

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`pytest tests/`)
6. Run code quality checks (`black`, `flake8`, `mypy`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

### Development Guidelines
- Follow PEP 8 style guidelines
- Add type hints for new functions
- Write comprehensive tests
- Update documentation for new features
- Use conventional commit messages

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Meshtastic Project** - For the amazing mesh networking platform
- **Discord.py** - For the excellent Discord API library
- **Contributors** - Everyone who helps improve Meshcord
- **Community** - For testing, feedback, and feature requests

## 🔗 Related Projects

- [Meshtastic](https://meshtastic.org/) - The mesh networking platform
- [Meshtastic Python](https://github.com/meshtastic/Meshtastic-python) - Python API library
- [Discord.py](https://github.com/Rapptz/discord.py) - Discord API wrapper

## 📞 Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/sargonas/meshcord/issues)
- **GitHub Discussions**: [Community support and questions](https://github.com/sargonas/meshcord/discussions)
- **Discord**: [Meshtastic Discord Community](https://discord.gg/ktMAKGBnBs)

---

<div align="center">

**Made with ❤️ for the Meshtastic community**

[⭐ Star this project](https://github.com/sargonas/meshcord) | [🐛 Report issues](https://github.com/sargonas/meshcord/issues) | [💡 Request features](https://github.com/sargonas/meshcord/issues/new)

</div>