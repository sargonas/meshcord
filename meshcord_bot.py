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
import time
import concurrent.futures

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
        
        # Signal strength reporting
        self.show_signal_strength = os.getenv('SHOW_SIGNAL_STRENGTH', 'true').lower() in ['true', '1', 'yes', 'on']
        
        # Discord client setup
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        
        # Initialize database and connections
        self._init_database()
        self._setup_discord_events()
        
        # HTTP session
        self.session = None
        
        # Serial interface and packet processing
        self.meshtastic_interface = None
        self.packet_queue = asyncio.Queue()
        
        # Serial timeout monitoring
        self.last_packet_time = None
        self.serial_timeout = int(os.getenv('SERIAL_TIMEOUT', '240'))  # 4 minutes default
        
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
                asyncio.create_task(self._process_packet_queue())
            else:
                logger.info("Starting HTTP monitoring")
                self.session = aiohttp.ClientSession()
                asyncio.create_task(self._request_radio_info_http())
                asyncio.create_task(self._monitor_radios_http())
                
        @self.client.event
        async def on_disconnect():
            if self.session:
                await self.session.close()
            if self.meshtastic_interface:
                try:
                    self.meshtastic_interface.close()
                except:
                    pass
                
    # DATABASE METHODS
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
        """Serial connection with timeout-based reconnection"""
        while True:
            try:
                logger.info(f"Connecting to Meshtastic device on {self.serial_port}")
                logger.info("Note: Initial protobuf parsing errors during connection are normal")
                
                # Create interface
                interface = await self._create_serial_interface()
                if not interface:
                    logger.error("Failed to create interface, retrying in 30 seconds")
                    await asyncio.sleep(30)
                    continue
                
                self.meshtastic_interface = interface
                self.last_packet_time = datetime.now()
                logger.info("Serial interface connected successfully")
                
                # Monitor loop with simple timeout logic
                while True:
                    await asyncio.sleep(30)  # Check every 30 seconds
                    
                    # Calculate time since last packet
                    if self.last_packet_time:
                        time_since_last = (datetime.now() - self.last_packet_time).total_seconds()
                        
                        # Log heartbeat
                        logger.info(f"Serial heartbeat: {self.packet_queue.qsize()} packets queued, "
                                  f"{time_since_last:.1f}s since last packet")
                        
                        # Timeout check
                        if time_since_last > self.serial_timeout:
                            logger.warning(f"No packets for {time_since_last:.1f}s (timeout: {self.serial_timeout}s)")
                            logger.info("Reconnecting serial interface...")
                            break  # Exit inner loop to reconnect
                    
                    # Interface validity check
                    if not self.meshtastic_interface:
                        logger.warning("Interface became None, reconnecting...")
                        break
                
            except Exception as e:
                logger.error(f"Serial connection error: {e}")
            
            # Clean up before reconnecting
            await self._close_serial_interface()
            logger.info("Waiting 10 seconds before reconnection...")
            await asyncio.sleep(10)

    async def _create_serial_interface(self):
        """Create serial interface"""
        try:
            from meshtastic.serial_interface import SerialInterface
            self.loop = asyncio.get_event_loop()
            
            def create_interface():
                try:
                    # Suppress meshtastic logging during connection
                    import logging
                    loggers_to_suppress = [
                        'meshtastic', 'meshtastic.mesh_interface',
                        'meshtastic.stream_interface', 'meshtastic.serial_interface'
                    ]
                    original_levels = {}
                    
                    for logger_name in loggers_to_suppress:
                        logger_obj = logging.getLogger(logger_name)
                        original_levels[logger_name] = logger_obj.level
                        logger_obj.setLevel(logging.CRITICAL)
                    
                    try:
                        interface = SerialInterface(self.serial_port)
                        time.sleep(2)  # Stabilization time
                        
                        # Restore logging levels
                        for logger_name, original_level in original_levels.items():
                            logging.getLogger(logger_name).setLevel(original_level)
                        
                        # Set up packet interception
                        original_handle_packet = interface._handlePacketFromRadio
                        def packet_handler_wrapper(packet):
                            try:
                                self._packet_callback(packet, interface)
                                return original_handle_packet(packet)
                            except Exception as e:
                                if self.debug_mode:
                                    logger.debug(f"Packet handler error: {e}")
                                return original_handle_packet(packet)
                        
                        interface._handlePacketFromRadio = packet_handler_wrapper
                        return interface
                        
                    except Exception as e:
                        # Restore logging even on failure
                        for logger_name, original_level in original_levels.items():
                            logging.getLogger(logger_name).setLevel(original_level)
                        raise e
                        
                except Exception as e:
                    logger.error(f"Error creating interface: {e}")
                    return None
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                return await self.loop.run_in_executor(executor, create_interface)
                
        except Exception as e:
            logger.error(f"Interface creation failed: {e}")
            return None

    async def _close_serial_interface(self):
        """Clean interface closure"""
        if self.meshtastic_interface:
            try:
                logger.info("Closing serial interface...")
                self.meshtastic_interface.close()
                await asyncio.sleep(2)  # Give time to clean up
            except Exception as e:
                logger.debug(f"Error during interface cleanup: {e}")
            finally:
                self.meshtastic_interface = None

    def _packet_callback(self, packet, interface):
        """Callback for received packets"""
        try:
            # Update last packet time for timeout detection
            self.last_packet_time = datetime.now()
            
            if hasattr(self, 'loop') and self.loop:
                self.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._queue_packet(packet))
                )
        except Exception as e:
            logger.error(f"Packet callback error: {e}")
    
    async def _queue_packet(self, packet):
        """Queue packet for processing"""
        try:
            await self.packet_queue.put(('serial', packet))
        except Exception as e:
            logger.error(f"Error queuing packet: {e}")
    
    async def _process_packet_queue(self):
        """Process packets from the queue"""
        logger.info("Starting packet queue processor")
        while True:
            try:
                source, packet = await self.packet_queue.get()
                await self._process_mesh_packet(packet, source)
                self.packet_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing packet queue: {e}")
                await asyncio.sleep(1)

    # HTTP CONNECTION METHODS
    async def _monitor_radios_http(self):
        """Monitor radios via HTTP - single poll per radio per cycle"""
        poll_count = 0
        
        while True:
            try:
                # Recreate session every hour to prevent stale connections
                if poll_count % (3600 / self.poll_interval) == 0 and poll_count > 0:
                    logger.info("Recreating HTTP session to prevent stale connections")
                    await self.session.close()
                    self.session = aiohttp.ClientSession()
                
                tasks = [self._poll_radio_http(radio) for radio in self.radios]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                poll_count += 1
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
            
            if self.debug_mode:
                logger.debug(f"Polling {radio_name} at {url}")
            
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.read()
                    if data:
                        if self.debug_mode:
                            logger.debug(f"Received {len(data)} bytes from {radio_name}")
                        await self._process_protobuf_data(data, radio_name)
                    else:
                        if self.debug_mode:
                            logger.debug(f"No data from {radio_name}")
                elif response.status == 503:
                    # 503 is normal (no data available)
                    if self.debug_mode:
                        logger.debug(f"No messages available from {radio_name} (503)")
                else:
                    logger.warning(f"HTTP {response.status} from {radio_name}")
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout polling {radio_name}")
        except Exception as e:
            logger.warning(f"HTTP error from {radio_name}: {e}")

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

    # PACKET PROCESSING METHODS
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
            
    def _get_message_info(self, decoded, from_id: int, rx_time: int, source: str, snr, rssi) -> Optional[Dict]:
        """Extract message information based on port number"""
        # Use Discord timestamp format for user's local timezone
        if rx_time:
            discord_timestamp = f"<t:{rx_time}:t>"  # :t shows time only in user's timezone
        else:
            discord_timestamp = 'N/A'
            
        node_name = self._get_node_name(from_id)
        radio_info = self._get_radio_info(source)
        
        base_info = f"📻 **{radio_info}** | **{node_name}** | {discord_timestamp}\n"
        
        if self.show_signal_strength:
            signal_info = f"📶 SNR: {snr} | RSSI: {rssi}"
        else:
            signal_info = ""
        
        portnum = decoded.portnum
        
        if portnum == portnums_pb2.TEXT_MESSAGE_APP:
            try:
                text = decoded.payload.decode('utf-8', errors='ignore').strip()
                if text:
                    content = f"{base_info}💬 {text}"
                    if signal_info:
                        content += f"\n{signal_info}"
                    return {
                        'type': 'text_messages',
                        'content': content
                    }
            except:
                pass
                
        elif portnum == portnums_pb2.POSITION_APP:
            content = f"{base_info}📍 Position update"
            if signal_info:
                content += f"\n{signal_info}"
            return {
                'type': 'position_updates',
                'content': content
            }
            
        elif portnum == portnums_pb2.NODEINFO_APP:
            content = f"{base_info}ℹ️ Node info update"
            if signal_info:
                content += f"\n{signal_info}"
            return {
                'type': 'node_info',
                'content': content
            }
            
        elif portnum == portnums_pb2.TELEMETRY_APP:
            content = f"{base_info}📊 Telemetry data"
            if signal_info:
                content += f"\n{signal_info}"
            return {
                'type': 'telemetry',
                'content': content
            }
            
        elif portnum == portnums_pb2.ROUTING_APP:
            content = f"{base_info}🔄 Routing message"
            if signal_info:
                content += f"\n{signal_info}"
            return {
                'type': 'routing',
                'content': content
            }
            
        elif portnum == portnums_pb2.ADMIN_APP:
            content = f"{base_info}⚙️ Admin message"
            if signal_info:
                content += f"\n{signal_info}"
            return {
                'type': 'admin',
                'content': content
            }
            
        elif portnum == portnums_pb2.DETECTION_SENSOR_APP:
            content = f"{base_info}🚨 Detection sensor"
            if signal_info:
                content += f"\n{signal_info}"
            return {
                'type': 'detection_sensor',
                'content': content
            }
            
        elif portnum == portnums_pb2.RANGE_TEST_APP:
            content = f"{base_info}📏 Range test"
            if signal_info:
                content += f"\n{signal_info}"
            return {
                'type': 'range_test',
                'content': content
            }
            
        elif portnum == portnums_pb2.STORE_FORWARD_APP:
            content = f"{base_info}💾 Store & Forward"
            if signal_info:
                content += f"\n{signal_info}"
            return {
                'type': 'store_forward',
                'content': content
            }
            
        else:
            content = f"{base_info}❓ Unknown message (port {portnum})"
            if signal_info:
                content += f"\n{signal_info}"
            return {
                'type': 'unknown',
                'content': content
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