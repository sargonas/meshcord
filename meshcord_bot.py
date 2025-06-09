import asyncio
import json
import logging
import os
import discord
import aiohttp
from datetime import datetime
import sqlite3
from typing import Optional, Dict, Any, List
import base64

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MeshtasticDiscordBot:
    def __init__(self):
        # Discord configuration
        self.discord_token = os.getenv('DISCORD_BOT_TOKEN')
        self.channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
        
        # HTTP API configuration for local radios
        self.radios = self.parse_radios()
        self.poll_interval = int(os.getenv('POLL_INTERVAL', '10'))  # seconds
        
        # Message filtering configuration
        self.show_config = self.parse_message_filters()
        
        # Discord client setup
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        
        # Message tracking to avoid duplicates
        self.init_database()
        
        # Setup Discord event handlers
        self.setup_discord_events()
        
        # HTTP session
        self.session = None
        
    def parse_radios(self) -> List[Dict[str, str]]:
        """Parse radio configuration from environment variables"""
        radios = []
        
        # Support multiple radios via RADIOS env var (JSON format)
        # Example: [{"name": "Home", "host": "192.168.1.100", "port": "80"}, {"name": "Mobile", "host": "meshtastic.local", "port": "80"}]
        radio_configs = os.getenv('RADIOS')
        if radio_configs:
            try:
                radios = json.loads(radio_configs)
            except json.JSONDecodeError:
                logger.error("Invalid RADIOS JSON format")
                
        # Fallback to single radio configuration
        if not radios:
            single_host = os.getenv('MESHTASTIC_HOST', 'meshtastic.local')
            single_port = os.getenv('MESHTASTIC_PORT', '80')
            single_name = os.getenv('RADIO_NAME', 'Radio')
            radios = [{"name": single_name, "host": single_host, "port": single_port}]
            
        logger.info(f"Monitoring {len(radios)} radio(s): {[r['name'] for r in radios]}")
        return radios
        
    def parse_message_filters(self) -> Dict[str, bool]:
        """Parse message filtering configuration from environment variables"""
        # Default to showing all message types
        default_settings = {
            'text_messages': True,
            'position_updates': True,
            'node_info': True,
            'telemetry': True,
            'routing': False,  # Usually noise, default off
            'admin': True,
            'detection_sensor': True,
            'range_test': True,
            'store_forward': True,
            'unknown': False  # Unknown message types, default off
        }
        
        # Allow override via environment variables
        settings = {}
        for msg_type, default_value in default_settings.items():
            env_key = f"SHOW_{msg_type.upper()}"
            env_value = os.getenv(env_key, str(default_value)).lower()
            settings[msg_type] = env_value in ['true', '1', 'yes', 'on']
            
        enabled_types = [k for k, v in settings.items() if v]
        disabled_types = [k for k, v in settings.items() if not v]
        
        logger.info(f"Message types enabled: {enabled_types}")
        if disabled_types:
            logger.info(f"Message types disabled: {disabled_types}")
            
        return settings
        
    def init_database(self):
        """Initialize SQLite database for tracking processed messages"""
        self.conn = sqlite3.connect('data/message_tracking.db')
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT,
                radio_name TEXT,
                timestamp INTEGER,
                processed_at INTEGER,
                PRIMARY KEY (message_id, radio_name)
            )
        ''')
        # Clean up old messages (older than 24 hours)
        cursor.execute('''
            DELETE FROM processed_messages 
            WHERE processed_at < ?
        ''', (int(datetime.now().timestamp()) - 86400,))
        self.conn.commit()
        
    def setup_discord_events(self):
        """Setup Discord client event handlers"""
        @self.client.event
        async def on_ready():
            logger.info(f'Discord bot logged in as {self.client.user}')
            self.session = aiohttp.ClientSession()
            asyncio.create_task(self.monitor_radios())
                
        @self.client.event
        async def on_disconnect():
            if self.session:
                await self.session.close()
                
    def is_message_processed(self, message_id: str, radio_name: str) -> bool:
        """Check if message has already been processed"""
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT 1 FROM processed_messages WHERE message_id = ? AND radio_name = ?', 
            (message_id, radio_name)
        )
        return cursor.fetchone() is not None
        
    def mark_message_processed(self, message_id: str, radio_name: str, timestamp: int):
        """Mark message as processed"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO processed_messages 
            (message_id, radio_name, timestamp, processed_at) 
            VALUES (?, ?, ?, ?)
        ''', (message_id, radio_name, timestamp, int(datetime.now().timestamp())))
        self.conn.commit()

    async def monitor_radios(self):
        """Monitor all radios via HTTP API"""
        logger.info("Starting radio monitoring")
        
        while True:
            try:
                # Poll all radios concurrently
                tasks = [self.poll_radio(radio) for radio in self.radios]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Radio monitoring error: {e}")
                await asyncio.sleep(self.poll_interval)
                
    async def poll_radio(self, radio: Dict[str, str]):
        """Poll a single radio via HTTP API using proper protobuf parsing"""
        try:
            url = f"http://{radio['host']}:{radio['port']}/api/v1/fromradio"
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.read()
                    if len(data) > 0:
                        # Parse protobuf data
                        await self.process_protobuf_data(data, radio['name'])
                        
                else:
                    logger.warning(f"HTTP {response.status} from {radio['name']} ({radio['host']})")
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout connecting to {radio['name']} ({radio['host']})")
        except Exception as e:
            logger.error(f"Error polling {radio['name']}: {e}")
            
    async def process_protobuf_data(self, data: bytes, radio_name: str):
        """Process protobuf data from HTTP API"""
        try:
            from meshtastic import mesh_pb2, portnums_pb2
            
            # The /api/v1/fromradio endpoint returns a FromRadio protobuf
            from_radio = mesh_pb2.FromRadio()
            from_radio.ParseFromString(data)
            
            # Check what type of data we received
            if from_radio.HasField('packet'):
                packet = from_radio.packet
                await self.process_mesh_packet(packet, radio_name)
            elif from_radio.HasField('my_info'):
                logger.debug(f"Received node info from {radio_name}")
            elif from_radio.HasField('node_info'):
                logger.debug(f"Received node database entry from {radio_name}")
            elif from_radio.HasField('config'):
                logger.debug(f"Received config from {radio_name}")
            else:
                logger.debug(f"Received other FromRadio data from {radio_name}")
                
        except Exception as e:
            logger.debug(f"Could not parse as FromRadio protobuf from {radio_name}: {e}")
            # Sometimes the endpoint returns raw MeshPacket instead
            try:
                from meshtastic import mesh_pb2
                packet = mesh_pb2.MeshPacket()
                packet.ParseFromString(data)
                await self.process_mesh_packet(packet, radio_name)
            except Exception as e2:
                logger.debug(f"Could not parse as MeshPacket either from {radio_name}: {e2}")
                # Log the actual data for debugging
                if len(data) > 0:
                    logger.debug(f"Received {len(data)} bytes of unparseable data from {radio_name}")
                    
    async def process_mesh_packet(self, packet, radio_name: str):
        """Process a MeshPacket"""
        try:
            from meshtastic import portnums_pb2
            
            # Get the from field - it might be named differently
            from_id = getattr(packet, 'from', None) or getattr(packet, 'from_', None)
            packet_id = getattr(packet, 'id', 0)
            rx_time = getattr(packet, 'rx_time', 0)
            
            if from_id is None:
                logger.debug(f"Packet missing 'from' field from {radio_name}")
                return
                
            # Create message ID
            message_id = f"{from_id:08x}_{packet_id}"
            
            # Check if already processed
            if self.is_message_processed(message_id, radio_name):
                return
            
            # Only process decoded packets
            if not hasattr(packet, 'decoded') or not packet.decoded:
                logger.debug(f"Skipping encrypted/undecoded packet from {radio_name}")
                return
                
            decoded = packet.decoded
            if not hasattr(decoded, 'portnum'):
                logger.debug(f"Packet missing portnum from {radio_name}")
                return
                
            # Process based on port number
            if decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP:
                if not self.show_config['text_messages']:
                    logger.debug(f"Skipping text message (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                try:
                    if hasattr(decoded, 'payload') and decoded.payload:
                        text = decoded.payload.decode('utf-8', errors='ignore')
                        if text.strip():  # Only process non-empty messages
                            discord_message = self.format_text_message(
                                from_id, rx_time, text, radio_name,
                                getattr(packet, 'rx_snr', 'N/A'),
                                getattr(packet, 'rx_rssi', 'N/A')
                            )
                            
                            if discord_message:
                                await self.send_to_discord(discord_message)
                                self.mark_message_processed(message_id, radio_name, rx_time)
                                logger.info(f"Forwarded text message from {from_id:08x} via {radio_name}")
                except Exception as e:
                    logger.error(f"Error processing text message: {e}")
                    
            elif decoded.portnum == portnums_pb2.POSITION_APP:
                if not self.show_config['position_updates']:
                    logger.debug(f"Skipping position update (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                # Handle position updates
                timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
                discord_message = f"📻 **{radio_name}** | `{from_id:08x}` | {timestamp}\n" \
                                f"📍 Position update\n" \
                                f"📶 SNR: {getattr(packet, 'rx_snr', 'N/A')} | RSSI: {getattr(packet, 'rx_rssi', 'N/A')}"
                
                await self.send_to_discord(discord_message)
                self.mark_message_processed(message_id, radio_name, rx_time)
                logger.info(f"Forwarded position update from {from_id:08x} via {radio_name}")
                
            elif decoded.portnum == portnums_pb2.NODEINFO_APP:
                if not self.show_config['node_info']:
                    logger.debug(f"Skipping node info (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                # Handle node info
                timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
                discord_message = f"📻 **{radio_name}** | `{from_id:08x}` | {timestamp}\n" \
                                f"ℹ️ Node info update\n" \
                                f"📶 SNR: {getattr(packet, 'rx_snr', 'N/A')} | RSSI: {getattr(packet, 'rx_rssi', 'N/A')}"
                
                await self.send_to_discord(discord_message)
                self.mark_message_processed(message_id, radio_name, rx_time)
                logger.info(f"Forwarded node info from {from_id:08x} via {radio_name}")
                
            elif decoded.portnum == portnums_pb2.TELEMETRY_APP:
                if not self.show_config['telemetry']:
                    logger.debug(f"Skipping telemetry (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
                discord_message = f"📻 **{radio_name}** | `{from_id:08x}` | {timestamp}\n" \
                                f"📊 Telemetry data\n" \
                                f"📶 SNR: {getattr(packet, 'rx_snr', 'N/A')} | RSSI: {getattr(packet, 'rx_rssi', 'N/A')}"
                
                await self.send_to_discord(discord_message)
                self.mark_message_processed(message_id, radio_name, rx_time)
                logger.info(f"Forwarded telemetry from {from_id:08x} via {radio_name}")
                
            elif decoded.portnum == portnums_pb2.ROUTING_APP:
                if not self.show_config['routing']:
                    logger.debug(f"Skipping routing message (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
                discord_message = f"📻 **{radio_name}** | `{from_id:08x}` | {timestamp}\n" \
                                f"🔄 Routing message\n" \
                                f"📶 SNR: {getattr(packet, 'rx_snr', 'N/A')} | RSSI: {getattr(packet, 'rx_rssi', 'N/A')}"
                
                await self.send_to_discord(discord_message)
                self.mark_message_processed(message_id, radio_name, rx_time)
                logger.info(f"Forwarded routing message from {from_id:08x} via {radio_name}")
                
            elif decoded.portnum == portnums_pb2.ADMIN_APP:
                if not self.show_config['admin']:
                    logger.debug(f"Skipping admin message (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
                discord_message = f"📻 **{radio_name}** | `{from_id:08x}` | {timestamp}\n" \
                                f"⚙️ Admin message\n" \
                                f"📶 SNR: {getattr(packet, 'rx_snr', 'N/A')} | RSSI: {getattr(packet, 'rx_rssi', 'N/A')}"
                
                await self.send_to_discord(discord_message)
                self.mark_message_processed(message_id, radio_name, rx_time)
                logger.info(f"Forwarded admin message from {from_id:08x} via {radio_name}")
                
            elif decoded.portnum == portnums_pb2.DETECTION_SENSOR_APP:
                if not self.show_config['detection_sensor']:
                    logger.debug(f"Skipping detection sensor (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
                discord_message = f"📻 **{radio_name}** | `{from_id:08x}` | {timestamp}\n" \
                                f"🚨 Detection sensor\n" \
                                f"📶 SNR: {getattr(packet, 'rx_snr', 'N/A')} | RSSI: {getattr(packet, 'rx_rssi', 'N/A')}"
                
                await self.send_to_discord(discord_message)
                self.mark_message_processed(message_id, radio_name, rx_time)
                logger.info(f"Forwarded detection sensor from {from_id:08x} via {radio_name}")
                
            elif decoded.portnum == portnums_pb2.RANGE_TEST_APP:
                if not self.show_config['range_test']:
                    logger.debug(f"Skipping range test (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
                discord_message = f"📻 **{radio_name}** | `{from_id:08x}` | {timestamp}\n" \
                                f"📏 Range test\n" \
                                f"📶 SNR: {getattr(packet, 'rx_snr', 'N/A')} | RSSI: {getattr(packet, 'rx_rssi', 'N/A')}"
                
                await self.send_to_discord(discord_message)
                self.mark_message_processed(message_id, radio_name, rx_time)
                logger.info(f"Forwarded range test from {from_id:08x} via {radio_name}")
                
            elif decoded.portnum == portnums_pb2.STORE_FORWARD_APP:
                if not self.show_config['store_forward']:
                    logger.debug(f"Skipping store & forward (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
                discord_message = f"📻 **{radio_name}** | `{from_id:08x}` | {timestamp}\n" \
                                f"💾 Store & Forward\n" \
                                f"📶 SNR: {getattr(packet, 'rx_snr', 'N/A')} | RSSI: {getattr(packet, 'rx_rssi', 'N/A')}"
                
                await self.send_to_discord(discord_message)
                self.mark_message_processed(message_id, radio_name, rx_time)
                logger.info(f"Forwarded store & forward from {from_id:08x} via {radio_name}")
                
            else:
                if not self.show_config['unknown']:
                    logger.debug(f"Skipping unknown message type {decoded.portnum} (disabled) from {from_id:08x} via {radio_name}")
                    return
                    
                timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
                discord_message = f"📻 **{radio_name}** | `{from_id:08x}` | {timestamp}\n" \
                                f"❓ Unknown message (port {decoded.portnum})\n" \
                                f"📶 SNR: {getattr(packet, 'rx_snr', 'N/A')} | RSSI: {getattr(packet, 'rx_rssi', 'N/A')}"
                
                await self.send_to_discord(discord_message)
                self.mark_message_processed(message_id, radio_name, rx_time)
                logger.info(f"Forwarded unknown message type {decoded.portnum} from {from_id:08x} via {radio_name}")
                
        except Exception as e:
            logger.error(f"Error processing mesh packet from {radio_name}: {e}")
            # Add more debugging info
            logger.debug(f"Packet attributes: {dir(packet)}")
            if hasattr(packet, 'decoded'):
                logger.debug(f"Decoded attributes: {dir(packet.decoded)}")
            
    def format_text_message(self, from_id: int, rx_time: int, text: str, 
                           radio_name: str, snr, rssi) -> str:
        """Format text message for Discord"""
        sender_id = f"{from_id:08x}"
        timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
        
        return f"📻 **{radio_name}** | `{sender_id}` | {timestamp}\n" \
               f"💬 {text}\n" \
               f"📶 SNR: {snr} | RSSI: {rssi}"
            
    async def process_packet(self, packet: Dict, radio_name: str):
        """Process packet from HTTP API"""
        try:
            # Create message ID from packet
            from_id = packet.get('from', 0)
            packet_id = packet.get('id', 0)
            rx_time = packet.get('rxTime', 0)
            
            message_id = f"{from_id:08x}_{packet_id}"
            
            # Check if already processed
            if self.is_message_processed(message_id, radio_name):
                return
                
            # Extract decoded payload
            decoded = packet.get('decoded', {})
            payload = decoded.get('payload')
            portnum = decoded.get('portnum', 0)
            
            if not payload:
                return
                
            # Decode message based on port
            decoded_message = self.decode_payload(payload, portnum)
            
            if decoded_message:
                # Get signal info
                snr = packet.get('rxSnr', 'N/A')
                rssi = packet.get('rxRssi', 'N/A')
                
                # Format and send to Discord
                discord_message = self.format_discord_message(
                    from_id, rx_time, decoded_message, radio_name, snr, rssi
                )
                
                if discord_message:
                    await self.send_to_discord(discord_message)
                    self.mark_message_processed(message_id, radio_name, rx_time)
                    
        except Exception as e:
            logger.error(f"Error processing packet: {e}")
            
    def decode_payload(self, payload: str, portnum: int) -> Optional[Dict[str, Any]]:
        """Decode message payload based on port number"""
        try:
            if portnum == 1:  # TEXT_MESSAGE_APP
                # Payload is base64 encoded
                decoded_bytes = base64.b64decode(payload)
                return {
                    'type': 'text',
                    'content': decoded_bytes.decode('utf-8', errors='ignore')
                }
            elif portnum == 3:  # POSITION_APP
                # Position data (would need protobuf parsing for full decode)
                return {
                    'type': 'position',
                    'raw': True
                }
            elif portnum == 4:  # NODEINFO_APP
                # Node info (would need protobuf parsing for full decode)
                return {
                    'type': 'nodeinfo', 
                    'raw': True
                }
            elif portnum == 67:  # TELEMETRY_APP
                # Telemetry data (would need protobuf parsing for full decode)
                return {
                    'type': 'telemetry',
                    'raw': True
                }
            elif portnum == 68:  # ROUTING_APP
                return {
                    'type': 'routing',
                    'raw': True
                }
            else:
                return {
                    'type': 'unknown',
                    'portnum': portnum,
                    'raw': True
                }
                
        except Exception as e:
            logger.error(f"Error decoding payload: {e}")
            return None
            
    def format_discord_message(self, from_id: int, rx_time: int, decoded_message: Dict, 
                              radio_name: str, snr, rssi) -> Optional[str]:
        """Format message for Discord"""
        try:
            sender_id = f"{from_id:08x}"
            timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
            
            if decoded_message['type'] == 'text':
                return f"📻 **{radio_name}** | `{sender_id}` | {timestamp}\n" \
                       f"💬 {decoded_message['content']}\n" \
                       f"📶 SNR: {snr} | RSSI: {rssi}"
                       
            elif decoded_message['type'] == 'position':
                return f"📻 **{radio_name}** | `{sender_id}` | {timestamp}\n" \
                       f"📍 Position update\n" \
                       f"📶 SNR: {snr} | RSSI: {rssi}"
                       
            elif decoded_message['type'] == 'nodeinfo':
                return f"📻 **{radio_name}** | `{sender_id}` | {timestamp}\n" \
                       f"ℹ️ Node info update\n" \
                       f"📶 SNR: {snr} | RSSI: {rssi}"
                       
            elif decoded_message['type'] == 'telemetry':
                return f"📻 **{radio_name}** | `{sender_id}` | {timestamp}\n" \
                       f"📊 Telemetry data\n" \
                       f"📶 SNR: {snr} | RSSI: {rssi}"
                       
            elif decoded_message['type'] == 'routing':
                # Skip routing messages to reduce noise
                return None
                       
            else:
                return f"📻 **{radio_name}** | `{sender_id}` | {timestamp}\n" \
                       f"❓ {decoded_message['type'].title()} (port {decoded_message.get('portnum', 'N/A')})\n" \
                       f"📶 SNR: {snr} | RSSI: {rssi}"
                       
        except Exception as e:
            logger.error(f"Error formatting Discord message: {e}")
            return None
            
    async def send_to_discord(self, message: str):
        """Send message to Discord channel"""
        try:
            channel = self.client.get_channel(self.channel_id)
            if channel:
                await channel.send(message)
                logger.info(f"Sent message to Discord: {message[:50]}...")
            else:
                logger.error(f"Discord channel {self.channel_id} not found")
        except Exception as e:
            logger.error(f"Error sending to Discord: {e}")
            
    async def run(self):
        """Start the bot"""
        try:
            await self.client.start(self.discord_token)
        except Exception as e:
            logger.error(f"Error starting Discord client: {e}")
        finally:
            if self.conn:
                self.conn.close()

# Main execution
async def main():
    bot = MeshtasticDiscordBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())