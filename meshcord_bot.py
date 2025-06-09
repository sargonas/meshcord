import asyncio
import json
import logging
import os
import discord
import aiohttp
import serial_asyncio
from datetime import datetime
import sqlite3
from typing import Dict, List, Optional
from meshtastic import mesh_pb2, portnums_pb2

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MeshtasticDiscordBot:
    def __init__(self):
        # Basic config validation
        self._validate_required_config()
        
        # Discord configuration
        self.discord_token = os.getenv('DISCORD_BOT_TOKEN')
        self.channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
        
        # Connection method configuration
        self.connection_method = os.getenv('CONNECTION_METHOD', 'http').lower()
        self.serial_port = os.getenv('SERIAL_PORT', '/dev/ttyUSB0')
        
        # HTTP configuration
        self.radios = self._parse_radios()
        self.poll_interval = float(os.getenv('POLL_INTERVAL', '2'))
        self.debug_mode = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        
        # Message filtering
        self.message_filters = self._parse_message_filters()
        
        # Discord client setup
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        
        # Initialize database and connections
        self._init_database()
        self._setup_discord_events()
        self.session = None
        self.serial_reader = None
        self.serial_writer = None
        
        # Serial buffer for improved parsing
        self.serial_buffer = bytearray()
        
    def _validate_required_config(self):
        """Validate required configuration"""
        if not os.getenv('DISCORD_BOT_TOKEN'):
            raise ValueError("DISCORD_BOT_TOKEN is required")
        if not os.getenv('DISCORD_CHANNEL_ID'):
            raise ValueError("DISCORD_CHANNEL_ID is required")
        try:
            int(os.getenv('DISCORD_CHANNEL_ID'))
        except ValueError:
            raise ValueError("DISCORD_CHANNEL_ID must be a valid integer")
        
    def _parse_radios(self) -> List[Dict[str, str]]:
        """Parse radio configuration from environment variables"""
        radios = []
        
        # Try JSON format first
        radio_configs = os.getenv('RADIOS')
        if radio_configs:
            try:
                radios = json.loads(radio_configs)
            except json.JSONDecodeError:
                logger.error("Invalid RADIOS JSON format")
                
        # Fallback to single radio
        if not radios:
            radio = {
                "name": os.getenv('RADIO_NAME', 'Radio'),
                "host": os.getenv('MESHTASTIC_HOST', 'meshtastic.local'),
                "port": os.getenv('MESHTASTIC_PORT', '80')
            }
            # Add display name if configured
            display_name = os.getenv('RADIO_DISPLAY_NAME')
            if display_name:
                radio["display_name"] = display_name
            radios = [radio]
            
        logger.info(f"Configured radios: {[r.get('display_name', r['name']) for r in radios]}")
        return radios
        
    def _parse_message_filters(self) -> Dict[str, bool]:
        """Parse message filtering configuration"""
        defaults = {
            'text_messages': True,
            'position_updates': True,
            'node_info': True,
            'telemetry': True,
            'routing': False,
            'admin': True,
            'detection_sensor': True,
            'range_test': True,
            'store_forward': True,
            'unknown': False
        }
        
        filters = {}
        for msg_type, default in defaults.items():
            env_key = f"SHOW_{msg_type.upper()}"
            env_value = os.getenv(env_key, str(default)).lower()
            filters[msg_type] = env_value in ['true', '1', 'yes', 'on']
            
        enabled = [k for k, v in filters.items() if v]
        logger.info(f"Enabled message types: {enabled}")
        return filters
        
    def _init_database(self):
        """Initialize SQLite database for message tracking, node info, and radio info"""
        os.makedirs('data', exist_ok=True)
        self.conn = sqlite3.connect('data/message_tracking.db')
        cursor = self.conn.cursor()
        
        # Message tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT,
                source TEXT,
                timestamp INTEGER,
                processed_at INTEGER,
                PRIMARY KEY (message_id, source)
            )
        ''')
        
        # Node database table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                node_id INTEGER PRIMARY KEY,
                short_name TEXT,
                long_name TEXT,
                last_seen INTEGER
            )
        ''')
        
        # Radio info table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS radios (
                source_name TEXT PRIMARY KEY,
                node_id INTEGER,
                short_name TEXT,
                long_name TEXT,
                last_updated INTEGER
            )
        ''')
        
        # Clean up old messages (24+ hours)
        cursor.execute(
            'DELETE FROM processed_messages WHERE processed_at < ?',
            (int(datetime.now().timestamp()) - 86400,)
        )
        self.conn.commit()
        
    def _setup_discord_events(self):
        """Setup Discord event handlers"""
        @self.client.event
        async def on_ready():
            logger.info(f'Discord bot logged in as {self.client.user}')
            
            if self.connection_method == 'serial':
                logger.info(f"Starting serial connection to {self.serial_port}")
                asyncio.create_task(self._monitor_serial())
            else:
                logger.info("Starting HTTP monitoring")
                self.session = aiohttp.ClientSession()
                asyncio.create_task(self._request_radio_info_http())
                asyncio.create_task(self._monitor_radios_http())
                
        @self.client.event
        async def on_disconnect():
            if self.session:
                await self.session.close()
            if self.serial_writer:
                self.serial_writer.close()
                await self.serial_writer.wait_closed()
                
    def _is_message_processed(self, message_id: str, source: str) -> bool:
        """Check if message has been processed"""
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT 1 FROM processed_messages WHERE message_id = ? AND source = ?',
            (message_id, source)
        )
        return cursor.fetchone() is not None
        
    def _mark_message_processed(self, message_id: str, source: str, timestamp: int):
        """Mark message as processed"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO processed_messages 
            (message_id, source, timestamp, processed_at) 
            VALUES (?, ?, ?, ?)
        ''', (message_id, source, timestamp, int(datetime.now().timestamp())))
        self.conn.commit()
        
    def _get_node_name(self, node_id: int) -> str:
        """Get node name from database, fallback to ID"""
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT short_name, long_name FROM nodes WHERE node_id = ?',
            (node_id,)
        )
        result = cursor.fetchone()
        
        if result:
            short_name, long_name = result
            display_name = short_name or long_name
            if display_name:
                return f"{display_name} ({node_id:08x})"
        
        return f"{node_id:08x}"
        
    def _update_node_info(self, node_id: int, user_info):
        """Update node information in database"""
        try:
            short_name = getattr(user_info, 'short_name', '').strip()
            long_name = getattr(user_info, 'long_name', '').strip()
            
            if short_name or long_name:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO nodes 
                    (node_id, short_name, long_name, last_seen) 
                    VALUES (?, ?, ?, ?)
                ''', (node_id, short_name, long_name, int(datetime.now().timestamp())))
                self.conn.commit()
                
                display_name = short_name or long_name
                logger.info(f"Updated node info: {display_name} ({node_id:08x})")
                
        except Exception as e:
            logger.error(f"Error updating node info: {e}")
            
    def _get_radio_info(self, source: str) -> str:
        """Get radio identification info from database"""
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT node_id, short_name, long_name FROM radios WHERE source_name = ?',
            (source,)
        )
        result = cursor.fetchone()
        
        if result:
            node_id, short_name, long_name = result
            display_name = short_name or long_name or source
            if node_id:
                return f"{display_name} ({node_id:08x})"
            else:
                return display_name
        
        # Fallback: find radio config and show display name
        for radio in self.radios:
            if radio['name'] == source:
                display_name = radio.get('display_name', radio['name'])
                return f"{display_name} ({radio['host']})"
        
        return source
        
    def _update_radio_info(self, source: str, my_info):
        """Update radio information from my_info message"""
        try:
            node_id = getattr(my_info, 'my_node_num', None)
            
            if node_id:
                # Find display name from config
                display_name = source
                for radio in self.radios:
                    if radio['name'] == source:
                        display_name = radio.get('display_name', source)
                        break
                
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO radios 
                    (source_name, node_id, short_name, long_name, last_updated) 
                    VALUES (?, ?, ?, ?, ?)
                ''', (source, node_id, display_name, '', int(datetime.now().timestamp())))
                self.conn.commit()
                
                logger.info(f"Updated radio info for {display_name}: node {node_id:08x}")
                
        except Exception as e:
            logger.error(f"Error updating radio info: {e}")

    # SERIAL CONNECTION METHODS
    async def _monitor_serial(self):
        """Monitor serial connection with reconnection"""
        while True:
            try:
                logger.info(f"Connecting to serial port {self.serial_port}")
                self.serial_reader, self.serial_writer = await serial_asyncio.open_serial_connection(
                    url=self.serial_port,
                    baudrate=115200
                )
                
                logger.info("Serial connection established")
                await self._request_radio_info_serial()
                await self._read_serial_stream()
                
            except Exception as e:
                logger.error(f"Serial connection error: {e}")
                if self.serial_writer:
                    self.serial_writer.close()
                    try:
                        await self.serial_writer.wait_closed()
                    except:
                        pass
                self.serial_reader = None
                self.serial_writer = None
                self.serial_buffer.clear()
                await asyncio.sleep(5)

    async def _request_radio_info_serial(self):
        """Request radio information via serial"""
        try:
            if self.debug_mode:
                logger.debug("Requesting radio info via serial")
        except Exception as e:
            logger.error(f"Error requesting radio info via serial: {e}")
                
    async def _read_serial_stream(self):
        """Read serial stream with improved parsing"""
        while self.serial_reader and not self.serial_reader.at_eof():
            try:
                data = await asyncio.wait_for(self.serial_reader.read(1024), timeout=1.0)
                if not data:
                    logger.warning("Serial connection closed")
                    break
                    
                self.serial_buffer.extend(data)
                await self._process_serial_buffer()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Serial read error: {e}")
                break

    async def _process_serial_buffer(self):
        """Process serial buffer with better message detection"""
        while len(self.serial_buffer) >= 4:
            found_message = False
            
            for start_pos in range(len(self.serial_buffer) - 3):
                for end_pos in range(start_pos + 4, min(start_pos + 200, len(self.serial_buffer) + 1)):
                    try:
                        candidate = bytes(self.serial_buffer[start_pos:end_pos])
                        from_radio = mesh_pb2.FromRadio()
                        from_radio.ParseFromString(candidate)
                        
                        await self._process_from_radio(from_radio, "serial")
                        self.serial_buffer = self.serial_buffer[end_pos:]
                        found_message = True
                        break
                        
                    except Exception:
                        continue
                
                if found_message:
                    break
            
            if not found_message:
                self.serial_buffer = self.serial_buffer[1:]
                if len(self.serial_buffer) < 4:
                    break

    # HTTP CONNECTION METHODS
    async def _monitor_radios_http(self):
        """Monitor radios via HTTP - single poll per radio per cycle"""
        while True:
            try:
                tasks = [self._poll_radio_http(radio) for radio in self.radios]
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"HTTP monitoring error: {e}")
                await asyncio.sleep(self.poll_interval)
                
    async def _poll_radio_http(self, radio: Dict[str, str]):
        """Poll a single radio via HTTP API"""
        radio_name = radio['name']
        
        try:
            url = f"http://{radio['host']}:{radio['port']}/api/v1/fromradio"
            timeout = aiohttp.ClientTimeout(total=3)
            
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.read()
                    if data:
                        await self._process_protobuf_data(data, radio_name)
                elif response.status != 503:  # 503 is normal (no data)
                    if self.debug_mode:
                        logger.debug(f"HTTP {response.status} from {radio_name}")
                    
        except asyncio.TimeoutError:
            if self.debug_mode:
                logger.debug(f"Timeout from {radio_name}")
        except Exception as e:
            if self.debug_mode:
                logger.debug(f"HTTP error from {radio_name}: {e}")

    async def _request_radio_info_http(self):
        """Request radio information from all HTTP radios"""
        try:
            await asyncio.sleep(1)
            
            for radio in self.radios:
                try:
                    url = f"http://{radio['host']}:{radio['port']}/api/v1/nodeinfo"
                    timeout = aiohttp.ClientTimeout(total=5)
                    
                    async with self.session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.read()
                            if data:
                                await self._process_protobuf_data(data, radio['name'])
                        
                except Exception as e:
                    if self.debug_mode:
                        logger.debug(f"Could not get nodeinfo from {radio['name']}: {e}")
                        
        except Exception as e:
            logger.error(f"Error requesting radio info via HTTP: {e}")

    async def _process_protobuf_data(self, data: bytes, source: str):
        """Process protobuf data from HTTP API"""
        try:
            from_radio = mesh_pb2.FromRadio()
            from_radio.ParseFromString(data)
            await self._process_from_radio(from_radio, source)
            
        except Exception:
            try:
                packet = mesh_pb2.MeshPacket()
                packet.ParseFromString(data)
                await self._process_mesh_packet(packet, source)
            except Exception as e:
                if data and self.debug_mode:
                    logger.debug(f"Parse error from {source}: {e}")

    async def _process_from_radio(self, from_radio, source: str):
        """Process a FromRadio protobuf message"""
        try:
            if from_radio.HasField('packet'):
                await self._process_mesh_packet(from_radio.packet, source)
            elif from_radio.HasField('node_info'):
                node_info = from_radio.node_info
                if hasattr(node_info, 'num') and hasattr(node_info, 'user'):
                    self._update_node_info(node_info.num, node_info.user)
            elif from_radio.HasField('my_info'):
                my_info = from_radio.my_info
                self._update_radio_info(source, my_info)
                if self.debug_mode:
                    logger.debug(f"Received radio info from {source}")
            elif from_radio.HasField('config'):
                if self.debug_mode:
                    logger.debug(f"Received config from {source}")
                    
        except Exception as e:
            logger.error(f"Error processing FromRadio from {source}: {e}")
                    
    async def _process_mesh_packet(self, packet, source: str):
        """Process a MeshPacket"""
        try:
            from_id = getattr(packet, 'from', None) or getattr(packet, 'from_', None)
            packet_id = getattr(packet, 'id', 0)
            rx_time = getattr(packet, 'rx_time', 0)
            
            if from_id is None:
                return
                
            message_id = f"{from_id:08x}_{packet_id}"
            
            if self._is_message_processed(message_id, source):
                return
                
            if not hasattr(packet, 'decoded') or not packet.decoded:
                return
                
            decoded = packet.decoded
            if not hasattr(decoded, 'portnum'):
                return
                
            # Get signal info
            snr = getattr(packet, 'rx_snr', None)
            rssi = getattr(packet, 'rx_rssi', None)
            
            snr_str = f"{snr:.1f}" if snr is not None else "N/A"
            rssi_str = str(rssi) if rssi is not None else "N/A"
            
            message_info = self._get_message_info(decoded, from_id, rx_time, source, snr_str, rssi_str)
            
            if message_info:
                if self._should_process_message_type(message_info['type']):
                    await self._send_to_discord(message_info['content'])
                    
                    node_name = self._get_node_name(from_id).split(' (')[0]
                    radio_info = self._get_radio_info(source).split(' (')[0]
                    logger.info(f"Forwarded {message_info['type']} from {node_name} via {radio_info}")
                    
                self._mark_message_processed(message_id, source, rx_time)
                
            # Extract nodeinfo if present
            if decoded.portnum == portnums_pb2.NODEINFO_APP and hasattr(decoded, 'payload'):
                try:
                    user_info = mesh_pb2.User()
                    user_info.ParseFromString(decoded.payload)
                    self._update_node_info(from_id, user_info)
                except Exception:
                    pass
                        
        except Exception as e:
            logger.error(f"Error processing packet from {source}: {e}")
            
    def _get_message_info(self, decoded, from_id: int, rx_time: int, source: str, snr, rssi) -> Dict:
        """Extract message information based on port number"""
        timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
        node_name = self._get_node_name(from_id)
        radio_info = self._get_radio_info(source)
        
        base_info = f"📻 **{radio_info}** | **{node_name}** | {timestamp}\n"
        signal_info = f"📶 SNR: {snr} | RSSI: {rssi}"
        
        portnum = decoded.portnum
        
        if portnum == portnums_pb2.TEXT_MESSAGE_APP:
            try:
                text = decoded.payload.decode('utf-8', errors='ignore').strip()
                if text:
                    return {
                        'type': 'text_messages',
                        'content': f"{base_info}💬 {text}\n{signal_info}"
                    }
            except:
                pass
                
        elif portnum == portnums_pb2.POSITION_APP:
            return {
                'type': 'position_updates',
                'content': f"{base_info}📍 Position update\n{signal_info}"
            }
            
        elif portnum == portnums_pb2.NODEINFO_APP:
            return {
                'type': 'node_info',
                'content': f"{base_info}ℹ️ Node info update\n{signal_info}"
            }
            
        elif portnum == portnums_pb2.TELEMETRY_APP:
            return {
                'type': 'telemetry',
                'content': f"{base_info}📊 Telemetry data\n{signal_info}"
            }
            
        elif portnum == portnums_pb2.ROUTING_APP:
            return {
                'type': 'routing',
                'content': f"{base_info}🔄 Routing message\n{signal_info}"
            }
            
        elif portnum == portnums_pb2.ADMIN_APP:
            return {
                'type': 'admin',
                'content': f"{base_info}⚙️ Admin message\n{signal_info}"
            }
            
        elif portnum == portnums_pb2.DETECTION_SENSOR_APP:
            return {
                'type': 'detection_sensor',
                'content': f"{base_info}🚨 Detection sensor\n{signal_info}"
            }
            
        elif portnum == portnums_pb2.RANGE_TEST_APP:
            return {
                'type': 'range_test',
                'content': f"{base_info}📏 Range test\n{signal_info}"
            }
            
        elif portnum == portnums_pb2.STORE_FORWARD_APP:
            return {
                'type': 'store_forward',
                'content': f"{base_info}💾 Store & Forward\n{signal_info}"
            }
            
        else:
            return {
                'type': 'unknown',
                'content': f"{base_info}❓ Unknown message (port {portnum})\n{signal_info}"
            }
            
        return None
        
    def _should_process_message_type(self, message_type: str) -> bool:
        """Check if message type should be processed"""
        return self.message_filters.get(message_type, False)
            
    async def _send_to_discord(self, message: str):
        """Send message to Discord channel"""
        try:
            channel = self.client.get_channel(self.channel_id)
            if channel:
                # Handle Discord's 2000 character limit
                if len(message) > 2000:
                    chunks = [message[i:i+1900] for i in range(0, len(message), 1900)]
                    for chunk in chunks:
                        await channel.send(chunk)
                else:
                    await channel.send(message)
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

async def main():
    bot = MeshtasticDiscordBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())