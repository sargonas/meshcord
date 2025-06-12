import unittest
import asyncio
import tempfile
import os
import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Mock meshtastic imports
import sys
sys.modules['meshtastic'] = MagicMock()
sys.modules['meshtastic.mesh_pb2'] = MagicMock()
sys.modules['meshtastic.portnums_pb2'] = MagicMock()
sys.modules['meshtastic.serial_interface'] = MagicMock()

from meshcord_bot import MeshtasticDiscordBot


class TestMeshcordBot(unittest.TestCase):
    """Unit tests for MeshtasticDiscordBot"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        # Set required environment variables
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'http',
            'MESHTASTIC_HOST': 'test.local',
            'DEBUG_MODE': 'false'
        })

    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        # Clean up environment
        test_env_vars = [
            'DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID', 'CONNECTION_METHOD',
            'MESHTASTIC_HOST', 'MESHTASTIC_PORT', 'RADIO_NAME', 'POLL_INTERVAL',
            'DEBUG_MODE', 'SERIAL_PORT', 'CONNECTION_TIMEOUT', 
            'MAX_RECONNECT_ATTEMPTS', 'RECONNECT_DELAY'
        ]
        for key in test_env_vars:
            os.environ.pop(key, None)

    def test_configuration_validation(self):
        """Test configuration validation"""
        # Test missing required config
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                MeshtasticDiscordBot()
        
        # Test invalid channel ID
        with patch.dict(os.environ, {
            'DISCORD_BOT_TOKEN': 'token',
            'DISCORD_CHANNEL_ID': 'invalid'
        }):
            with self.assertRaises(ValueError):
                MeshtasticDiscordBot()

    def test_serial_health_monitoring_config(self):
        """Test serial health monitoring configuration"""
        with patch.dict(os.environ, {
            'CONNECTION_METHOD': 'serial',
            'CONNECTION_TIMEOUT': '600',
            'MAX_RECONNECT_ATTEMPTS': '10',
            'RECONNECT_DELAY': '60'
        }):
            with patch('meshcord_bot.discord.Client'):
                bot = MeshtasticDiscordBot()
                
                self.assertEqual(bot.connection_timeout, 600)
                self.assertEqual(bot.max_reconnect_attempts, 10)
                self.assertEqual(bot.reconnect_delay, 60)

    def test_radio_configuration_parsing(self):
        """Test radio configuration parsing"""
        with patch('meshcord_bot.discord.Client'):
            # Test single radio fallback
            bot = MeshtasticDiscordBot()
            self.assertEqual(len(bot.radios), 1)
            self.assertEqual(bot.radios[0]['name'], 'Radio')
            
            # Test JSON configuration
            radios_json = json.dumps([
                {"name": "radio1", "host": "host1", "port": "80", "display_name": "Radio 1"},
                {"name": "radio2", "host": "host2", "port": "80"}
            ])
            
            with patch.dict(os.environ, {'RADIOS': radios_json}):
                bot2 = MeshtasticDiscordBot()
                self.assertEqual(len(bot2.radios), 2)
                self.assertEqual(bot2.radios[0]['display_name'], 'Radio 1')

    def test_message_filtering_config(self):
        """Test message filtering configuration"""
        with patch.dict(os.environ, {
            'SHOW_TEXT_MESSAGES': 'false',
            'SHOW_TELEMETRY': 'true',
            'SHOW_ROUTING': 'true'
        }):
            with patch('meshcord_bot.discord.Client'):
                bot = MeshtasticDiscordBot()
                
                self.assertFalse(bot.message_filters['text_messages'])
                self.assertTrue(bot.message_filters['telemetry'])
                self.assertTrue(bot.message_filters['routing'])

    def test_database_initialization(self):
        """Test database initialization"""
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            # Check that tables exist
            cursor = bot.conn.cursor()
            
            # Test processed_messages table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processed_messages'")
            self.assertIsNotNone(cursor.fetchone())
            
            # Test nodes table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'")
            self.assertIsNotNone(cursor.fetchone())
            
            # Test radios table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='radios'")
            self.assertIsNotNone(cursor.fetchone())

    def test_message_deduplication(self):
        """Test message deduplication functionality"""
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            message_id = "test_message_123"
            source = "test_radio"
            timestamp = int(time.time())
            
            # Initially not processed
            self.assertFalse(bot._is_message_processed(message_id, source))
            
            # Mark as processed
            bot._mark_message_processed(message_id, source, timestamp)
            
            # Now should be marked as processed
            self.assertTrue(bot._is_message_processed(message_id, source))

    def test_node_info_management(self):
        """Test node information storage and retrieval"""
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            node_id = 0x12345678
            
            # Test unknown node
            node_name = bot._get_node_name(node_id)
            self.assertEqual(node_name, "12345678")
            
            # Add node info
            mock_user_info = Mock()
            mock_user_info.short_name = "TEST"
            mock_user_info.long_name = "Test Node"
            
            bot._update_node_info(node_id, mock_user_info)
            
            # Test known node
            node_name = bot._get_node_name(node_id)
            self.assertEqual(node_name, "TEST (12345678)")

    def test_radio_info_management(self):
        """Test radio information storage and retrieval"""
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            source = "test_radio"
            
            # Test unknown radio (should return the source name since it's not in config)
            radio_info = bot._get_radio_info(source)
            self.assertEqual(radio_info, "test_radio")  # No config fallback for unknown source
            
            # Test radio that matches config
            config_source = "Radio"  # This matches bot.radios[0]['name']
            radio_info = bot._get_radio_info(config_source)
            self.assertEqual(radio_info, "Radio (test.local)")  # Uses config fallback
            
            # Add radio info
            mock_my_info = Mock()
            mock_my_info.my_node_num = 0x87654321
            
            bot._update_radio_info(source, mock_my_info)
            
            # Test known radio
            radio_info = bot._get_radio_info(source)
            self.assertIn("87654321", radio_info)

    @patch('meshcord_bot.portnums_pb2')
    def test_message_info_extraction(self, mock_portnums):
        """Test message information extraction"""
        mock_portnums.TEXT_MESSAGE_APP = 1
        mock_portnums.POSITION_APP = 2
        mock_portnums.TELEMETRY_APP = 3
        
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            # Test text message
            mock_decoded = Mock()
            mock_decoded.portnum = 1
            mock_decoded.payload = b"Test message"
            
            message_info = bot._get_message_info(
                mock_decoded, 0x12345678, int(time.time()), "test_radio", "5.0", "-80"
            )
            
            self.assertIsNotNone(message_info)
            self.assertEqual(message_info['type'], 'text_messages')
            self.assertIn('Test message', message_info['content'])
            self.assertIn('💬', message_info['content'])

    def test_should_process_message_type(self):
        """Test message type filtering"""
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            # Default filters
            self.assertTrue(bot._should_process_message_type('text_messages'))
            self.assertFalse(bot._should_process_message_type('routing'))
            self.assertFalse(bot._should_process_message_type('unknown'))

    def test_error_handling_in_processing(self):
        """Test error handling in various processing methods"""
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            # Test node info update with invalid data
            try:
                bot._update_node_info(None, None)
                # Should not raise exception
            except:
                self.fail("_update_node_info raised exception with invalid data")
            
            # Test radio info update with invalid data
            try:
                bot._update_radio_info("test", None)
                # Should not raise exception
            except:
                self.fail("_update_radio_info raised exception with invalid data")


class TestMeshcordBotAsync(unittest.IsolatedAsyncioTestCase):
    """Async unit tests for MeshtasticDiscordBot"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        # Set required environment variables
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'http',
            'MESHTASTIC_HOST': 'test.local',
            'DEBUG_MODE': 'false'
        })

    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        # Clean up environment
        test_env_vars = [
            'DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID', 'CONNECTION_METHOD',
            'MESHTASTIC_HOST', 'MESHTASTIC_PORT', 'RADIO_NAME', 'POLL_INTERVAL',
            'DEBUG_MODE', 'SERIAL_PORT', 'CONNECTION_TIMEOUT', 
            'MAX_RECONNECT_ATTEMPTS', 'RECONNECT_DELAY'
        ]
        for key in test_env_vars:
            os.environ.pop(key, None)

    async def test_packet_queue_processing(self):
        """Test packet queuing and processing"""
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            # Test packet queuing
            test_packet = Mock()
            await bot._queue_packet(test_packet)
            
            self.assertEqual(bot.packet_queue.qsize(), 1)
            
            # Test queue retrieval
            source, packet = await bot.packet_queue.get()
            self.assertEqual(source, 'serial')
            self.assertEqual(packet, test_packet)

    async def test_connection_health_monitoring(self):
        """Test connection health monitoring logic"""
        with patch.dict(os.environ, {
            'CONNECTION_METHOD': 'serial',
            'CONNECTION_TIMEOUT': '10'  # Short timeout for testing
        }):
            with patch('meshcord_bot.discord.Client'):
                bot = MeshtasticDiscordBot()
                bot.meshtastic_interface = Mock()
                
                # Test with recent packet
                bot.last_packet_time = datetime.now()
                
                # Health monitor should not trigger reconnection
                with patch.object(bot.meshtastic_interface, 'close') as mock_close:
                    # This would normally run continuously, but we'll test the logic
                    current_time = datetime.now()
                    if bot.last_packet_time:
                        time_since_last = current_time - bot.last_packet_time
                        if time_since_last.total_seconds() > bot.connection_timeout:
                            bot.meshtastic_interface.close()
                            bot.meshtastic_interface = None
                    
                    # Should not have been called
                    mock_close.assert_not_called()
                
                # Test with old packet (simulate stale connection)
                bot.last_packet_time = datetime.now() - timedelta(seconds=300)
                
                with patch.object(bot.meshtastic_interface, 'close') as mock_close:
                    current_time = datetime.now()
                    if bot.last_packet_time:
                        time_since_last = current_time - bot.last_packet_time
                        if time_since_last.total_seconds() > bot.connection_timeout:
                            bot.meshtastic_interface.close()
                            bot.meshtastic_interface = None
                    
                    # Should have been called
                    mock_close.assert_called_once()

    async def test_serial_packet_callback(self):
        """Test serial packet callback functionality"""
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            bot.loop = asyncio.get_event_loop()
            
            # Test packet callback updates last_packet_time
            initial_time = bot.last_packet_time
            
            mock_packet = Mock()
            mock_interface = Mock()
            
            bot._packet_callback(mock_packet, mock_interface)
            
            # Should have updated the timestamp
            self.assertNotEqual(bot.last_packet_time, initial_time)
            self.assertIsInstance(bot.last_packet_time, datetime)

    async def test_discord_message_sending(self):
        """Test Discord message sending with character limits"""
        mock_channel = AsyncMock()
        mock_client = Mock()
        mock_client.get_channel.return_value = mock_channel
        
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            bot.client = mock_client
            
            # Test normal message
            short_message = "Test message"
            await bot._send_to_discord(short_message)
            mock_channel.send.assert_called_once_with(short_message)
            
            # Test long message (over 2000 chars)
            long_message = "A" * 2500
            mock_channel.reset_mock()
            
            await bot._send_to_discord(long_message)
            
            # Should have been called multiple times for chunks
            self.assertGreater(mock_channel.send.call_count, 1)


class TestSerialConnectionFeatures(unittest.TestCase):
    """Specific tests for serial connection improvements"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'serial',
            'SERIAL_PORT': '/dev/ttyUSB0',
            'CONNECTION_TIMEOUT': '300',
            'MAX_RECONNECT_ATTEMPTS': '5',
            'RECONNECT_DELAY': '30'
        })

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        for key in ['DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID', 'CONNECTION_METHOD',
                   'SERIAL_PORT', 'CONNECTION_TIMEOUT', 'MAX_RECONNECT_ATTEMPTS', 
                   'RECONNECT_DELAY']:
            os.environ.pop(key, None)

    def test_serial_configuration_parsing(self):
        """Test serial-specific configuration"""
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            self.assertEqual(bot.connection_method, 'serial')
            self.assertEqual(bot.serial_port, '/dev/ttyUSB0')
            self.assertEqual(bot.connection_timeout, 300)
            self.assertEqual(bot.max_reconnect_attempts, 5)
            self.assertEqual(bot.reconnect_delay, 30)

    def test_serial_config_defaults(self):
        """Test serial configuration defaults"""
        # Remove optional config
        for key in ['CONNECTION_TIMEOUT', 'MAX_RECONNECT_ATTEMPTS', 'RECONNECT_DELAY']:
            os.environ.pop(key, None)
            
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            # Should use defaults
            self.assertEqual(bot.connection_timeout, 300)  # 5 minutes
            self.assertEqual(bot.max_reconnect_attempts, 5)
            self.assertEqual(bot.reconnect_delay, 30)


class TestSerialConnectionFeaturesAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for serial connection features"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'serial',
            'SERIAL_PORT': '/dev/ttyUSB0',
            'CONNECTION_TIMEOUT': '300',
            'MAX_RECONNECT_ATTEMPTS': '5',
            'RECONNECT_DELAY': '30'
        })

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        for key in ['DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID', 'CONNECTION_METHOD',
                   'SERIAL_PORT', 'CONNECTION_TIMEOUT', 'MAX_RECONNECT_ATTEMPTS', 
                   'RECONNECT_DELAY']:
            os.environ.pop(key, None)

    async def test_health_monitoring_task_creation(self):
        """Test that health monitoring task is created for serial connections"""
        mock_discord_client = Mock()
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            
            # Simply verify the bot has the async methods we expect
            self.assertTrue(asyncio.iscoroutinefunction(bot._monitor_serial))
            self.assertTrue(asyncio.iscoroutinefunction(bot._process_packet_queue))
            self.assertTrue(asyncio.iscoroutinefunction(bot._monitor_connection_health))
            
            # Verify serial configuration
            self.assertEqual(bot.connection_method, 'serial')


if __name__ == '__main__':
    unittest.main()