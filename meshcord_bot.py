import asyncio
import json
import logging
import os
import discord
import aiohttp
from datetime import datetime
import sqlite3
from typing import Dict, List, Optional
from meshtastic import mesh_pb2, portnums_pb2

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MeshtasticDiscordBot:
    def __init__(self):
        # Discord configuration
        self.discord_token = os.getenv('DISCORD_BOT_TOKEN')
        self.channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
        
        # Radio configuration
        self.radios = self._parse_radios()
        self.poll_interval = int(os.getenv('POLL_INTERVAL', '2'))  # More frequent polling
        self.debug_mode = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        
        # Message filtering
        self.message_filters = self._parse_message_filters()
        
        # Discord client setup
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        
        # Initialize database and HTTP session
        self._init_database()
        self._setup_discord_events()
        self.session = None
        
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
            radios = [{
                "name": os.getenv('RADIO_NAME', 'Radio'),
                "host": os.getenv('MESHTASTIC_HOST', 'meshtastic.local'),
                "port": os.getenv('MESHTASTIC_PORT', '80')
            }]
            
        logger.info(f"Monitoring {len(radios)} radio(s): {[r['name'] for r in radios]}")
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
        """Initialize SQLite database for message tracking and node info"""
        os.makedirs('data', exist_ok=True)
        self.conn = sqlite3.connect('data/message_tracking.db')
        cursor = self.conn.cursor()
        
        # Message tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT,
                radio_name TEXT,
                timestamp INTEGER,
                processed_at INTEGER,
                PRIMARY KEY (message_id, radio_name)
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
            self.session = aiohttp.ClientSession()
            asyncio.create_task(self._monitor_radios())
                
        @self.client.event
        async def on_disconnect():
            if self.session:
                await self.session.close()
                
    def _is_message_processed(self, message_id: str, radio_name: str) -> bool:
        """Check if message has been processed"""
        cursor = self.conn.cursor()
        cursor.execute(
            'SELECT 1 FROM processed_messages WHERE message_id = ? AND radio_name = ?',
            (message_id, radio_name)
        )
        return cursor.fetchone() is not None
        
    def _mark_message_processed(self, message_id: str, radio_name: str, timestamp: int):
        """Mark message as processed"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO processed_messages 
            (message_id, radio_name, timestamp, processed_at) 
            VALUES (?, ?, ?, ?)
        ''', (message_id, radio_name, timestamp, int(datetime.now().timestamp())))
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
            # Prefer short name if available, otherwise long name
            display_name = short_name or long_name
            if display_name:
                return f"{display_name} ({node_id:08x})"
        
        # Fallback to just the ID
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

    async def _monitor_radios(self):
        """Monitor all radios continuously"""
        logger.info("Starting radio monitoring")
        
        while True:
            try:
                tasks = [self._poll_radio(radio) for radio in self.radios]
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Radio monitoring error: {e}")
                await asyncio.sleep(self.poll_interval)
                
    async def _poll_radio(self, radio: Dict[str, str]):
        """Poll a single radio via HTTP API"""
        try:
            url = f"http://{radio['host']}:{radio['port']}/api/v1/fromradio"
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.read()
                    if data:
                        await self._process_protobuf_data(data, radio['name'])
                else:
                    logger.warning(f"HTTP {response.status} from {radio['name']}")
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout from {radio['name']} ({radio['host']})")
        except Exception as e:
            logger.error(f"Error polling {radio['name']}: {e}")
            
    async def _process_protobuf_data(self, data: bytes, radio_name: str):
        """Process protobuf data from HTTP API"""
        try:
            # Try parsing as FromRadio first
            from_radio = mesh_pb2.FromRadio()
            from_radio.ParseFromString(data)
            
            if from_radio.HasField('packet'):
                if self.debug_mode:
                    logger.debug(f"Processing packet from {radio_name}")
                await self._process_mesh_packet(from_radio.packet, radio_name)
            elif from_radio.HasField('node_info'):
                # Update node database when we receive node info
                node_info = from_radio.node_info
                if hasattr(node_info, 'num') and hasattr(node_info, 'user'):
                    self._update_node_info(node_info.num, node_info.user)
            elif self.debug_mode:
                logger.debug(f"FromRadio data with no packet or node_info from {radio_name}")
                
        except Exception as e1:
            if self.debug_mode:
                logger.debug(f"FromRadio parse failed from {radio_name}: {e1}")
            
            # Fallback to direct MeshPacket parsing
            try:
                packet = mesh_pb2.MeshPacket()
                packet.ParseFromString(data)
                if self.debug_mode:
                    logger.debug(f"Processing direct MeshPacket from {radio_name}")
                await self._process_mesh_packet(packet, radio_name)
            except Exception as e2:
                if data:  # Only log if there was actual data
                    logger.warning(f"Could not parse {len(data)} bytes from {radio_name}: {e1}, {e2}")
                    if self.debug_mode:
                        # Log first few bytes for debugging
                        logger.debug(f"Data preview: {data[:50].hex()}")
                    
    async def _process_mesh_packet(self, packet, radio_name: str):
        """Process a MeshPacket"""
        try:
            # Extract packet info
            from_id = getattr(packet, 'from', None) or getattr(packet, 'from_', None)
            packet_id = getattr(packet, 'id', 0)
            rx_time = getattr(packet, 'rx_time', 0)
            
            if from_id is None:
                if self.debug_mode:
                    logger.debug(f"Packet missing 'from' field from {radio_name}")
                return
                
            message_id = f"{from_id:08x}_{packet_id}"
            
            if self.debug_mode:
                logger.debug(f"Processing packet {message_id} from {radio_name}")
            
            # Skip if already processed
            if self._is_message_processed(message_id, radio_name):
                if self.debug_mode:
                    logger.debug(f"Skipping duplicate message {message_id} from {radio_name}")
                return
                
            # Check if packet is decoded
            if not hasattr(packet, 'decoded') or not packet.decoded:
                if self.debug_mode:
                    logger.debug(f"Skipping encrypted/undecoded packet {message_id} from {radio_name}")
                return
                
            decoded = packet.decoded
            if not hasattr(decoded, 'portnum'):
                if self.debug_mode:
                    logger.debug(f"Packet {message_id} missing portnum from {radio_name}")
                return
                
            if self.debug_mode:
                logger.debug(f"Packet {message_id} port {decoded.portnum} from {radio_name}")
                
            # Get signal info
            snr = getattr(packet, 'rx_snr', 'N/A')
            rssi = getattr(packet, 'rx_rssi', 'N/A')
            
            # Process based on port number
            message_info = self._get_message_info(decoded, from_id, rx_time, radio_name, snr, rssi)
            
            if message_info:
                if self._should_process_message_type(message_info['type']):
                    await self._send_to_discord(message_info['content'])
                    self._mark_message_processed(message_id, radio_name, rx_time)
                    
                    # Get display name for logging
                    node_name = self._get_node_name(from_id).split(' (')[0]  # Just the name part
                    logger.info(f"Forwarded {message_info['type']} from {node_name} via {radio_name}")
                else:
                    if self.debug_mode:
                        logger.debug(f"Message type {message_info['type']} filtered out for {message_id}")
                    # Still mark as processed to avoid reprocessing
                    self._mark_message_processed(message_id, radio_name, rx_time)
            else:
                if self.debug_mode:
                    logger.debug(f"No message info extracted for {message_id}")
                
            # Check if this is a nodeinfo message and extract user info
            if decoded.portnum == portnums_pb2.NODEINFO_APP and hasattr(decoded, 'payload'):
                try:
                    user_info = mesh_pb2.User()
                    user_info.ParseFromString(decoded.payload)
                    self._update_node_info(from_id, user_info)
                except Exception as e:
                    if self.debug_mode:
                        logger.debug(f"Could not parse nodeinfo payload: {e}")
                        
        except Exception as e:
            logger.error(f"Error processing packet from {radio_name}: {e}")
            if self.debug_mode:
                logger.debug(f"Packet attributes: {dir(packet)}")
                if hasattr(packet, 'decoded'):
                    logger.debug(f"Decoded attributes: {dir(packet.decoded)}")
            
    def _get_message_info(self, decoded, from_id: int, rx_time: int, radio_name: str, snr, rssi) -> Dict:
        """Extract message information based on port number"""
        timestamp = datetime.fromtimestamp(rx_time).strftime('%H:%M:%S') if rx_time else 'N/A'
        node_name = self._get_node_name(from_id)
        base_info = f"📻 **{radio_name}** | **{node_name}** | {timestamp}\n"
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