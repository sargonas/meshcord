import unittest
import asyncio
import tempfile
import os
import sqlite3
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

# Mock the meshtastic imports before importing the main module
import sys
sys.modules['meshtastic'] = MagicMock()
sys.modules['meshtastic.mesh_pb2'] = MagicMock()
sys.modules['meshtastic.portnums_pb2'] = MagicMock()

# Import after mocking
from meshcord_bot import MeshtasticDiscordBot


class TestMeshtasticDiscordBot(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        # Create temporary directory for test database
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        # Set test environment variables
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'http',
            'MESHTASTIC_HOST': 'test.local',
            'MESHTASTIC_PORT': '80',
            'RADIO_NAME': 'TestRadio'
        })
        
        # Mock discord client
        with patch('meshcord_bot.discord.Client'):
            self.bot = MeshtasticDiscordBot()
        
    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_cwd)
        if hasattr(self.bot, 'conn') and self.bot.conn:
            self.bot.conn.close()
        
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        # Clean up environment
        for key in ['DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID', 'CONNECTION_METHOD',
                   'MESHTASTIC_HOST', 'MESHTASTIC_PORT', 'RADIO_NAME']:
            os.environ.pop(key, None)

    def test_parse_radios_single_config(self):
        """Test parsing single radio configuration"""
        radios = self.bot._parse_radios()
        
        self.assertEqual(len(radios), 1)
        self.assertEqual(radios[0]['name'], 'TestRadio')
        self.assertEqual(radios[0]['host'], 'test.local')
        self.assertEqual(radios[0]['port'], '80')

    def test_parse_radios_json_config(self):
        """Test parsing JSON radio configuration"""
        json_config = json.dumps([
            {"name": "Radio1", "host": "192.168.1.100", "port": "80"},
            {"name": "Radio2", "host": "192.168.1.101", "port": "80"}
        ])
        
        with patch.dict(os.environ, {'RADIOS': json_config}):
            with patch('meshcord_bot.discord.Client'):
                bot = MeshtasticDiscordBot()
                radios = bot._parse_radios()
        
        self.assertEqual(len(radios), 2)
        self.assertEqual(radios[0]['name'], 'Radio1')
        self.assertEqual(radios[1]['name'], 'Radio2')

    def test_parse_radios_invalid_json(self):
        """Test handling of invalid JSON configuration"""
        with patch.dict(os.environ, {'RADIOS': 'invalid json'}):
            with patch('meshcord_bot.discord.Client'):
                bot = MeshtasticDiscordBot()
                radios = bot._parse_radios()
        
        # Should fallback to single radio config
        self.assertEqual(len(radios), 1)

    def test_parse_message_filters_defaults(self):
        """Test default message filter configuration"""
        filters = self.bot._parse_message_filters()
        
        # Check some expected defaults
        self.assertTrue(filters['text_messages'])
        self.assertTrue(filters['position_updates'])
        self.assertFalse(filters['routing'])  # Should be disabled by default
        self.assertFalse(filters['unknown'])

    def test_parse_message_filters_overrides(self):
        """Test message filter environment variable overrides"""
        with patch.dict(os.environ, {
            'SHOW_TEXT_MESSAGES': 'false',
            'SHOW_ROUTING': 'true',
            'SHOW_UNKNOWN': '1'
        }):
            with patch('meshcord_bot.discord.Client'):
                bot = MeshtasticDiscordBot()
                filters = bot._parse_message_filters()
        
        self.assertFalse(filters['text_messages'])
        self.assertTrue(filters['routing'])
        self.assertTrue(filters['unknown'])

    def test_database_initialization(self):
        """Test database tables are created correctly"""
        # Check that tables exist
        cursor = self.bot.conn.cursor()
        
        # Check processed_messages table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processed_messages'")
        self.assertIsNotNone(cursor.fetchone())
        
        # Check nodes table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'")
        self.assertIsNotNone(cursor.fetchone())

    def test_message_processing_tracking(self):
        """Test message duplicate detection"""
        message_id = "12345678_42"
        source = "TestRadio"
        timestamp = int(datetime.now().timestamp())
        
        # Should not be processed initially
        self.assertFalse(self.bot._is_message_processed(message_id, source))
        
        # Mark as processed
        self.bot._mark_message_processed(message_id, source, timestamp)
        
        # Should now be marked as processed
        self.assertTrue(self.bot._is_message_processed(message_id, source))

    def test_node_name_storage_and_retrieval(self):
        """Test node information storage and name resolution"""
        node_id = 0x12345678
        
        # Initially should return hex ID
        name = self.bot._get_node_name(node_id)
        self.assertEqual(name, "12345678")
        
        # Mock user info
        mock_user_info = Mock()
        mock_user_info.short_name = "Alice"
        mock_user_info.long_name = "Alice's Radio"
        
        # Update node info
        self.bot._update_node_info(node_id, mock_user_info)
        
        # Should now return name with ID
        name = self.bot._get_node_name(node_id)
        self.assertEqual(name, "Alice (12345678)")

    def test_node_name_fallback_to_long_name(self):
        """Test fallback to long name when short name is empty"""
        node_id = 0x87654321
        
        mock_user_info = Mock()
        mock_user_info.short_name = ""
        mock_user_info.long_name = "Bob's Station"
        
        self.bot._update_node_info(node_id, mock_user_info)
        
        name = self.bot._get_node_name(node_id)
        self.assertEqual(name, "Bob's Station (87654321)")

    def test_should_process_message_type(self):
        """Test message type filtering"""
        # Text messages should be processed by default
        self.assertTrue(self.bot._should_process_message_type('text_messages'))
        
        # Routing should not be processed by default
        self.assertFalse(self.bot._should_process_message_type('routing'))
        
        # Unknown type should default to False
        self.assertFalse(self.bot._should_process_message_type('nonexistent_type'))

    def test_get_message_info_text_message(self):
        """Test text message formatting"""
        # Mock decoded message
        mock_decoded = Mock()
        mock_decoded.portnum = 1  # TEXT_MESSAGE_APP
        mock_decoded.payload = b"Hello World"
        
        # Mock portnums_pb2
        with patch('meshcord_bot.portnums_pb2') as mock_portnums:
            mock_portnums.TEXT_MESSAGE_APP = 1
            
            message_info = self.bot._get_message_info(
                mock_decoded, 0x12345678, 1640995200, "TestRadio", 5.2, -85
            )
        
        self.assertIsNotNone(message_info)
        self.assertEqual(message_info['type'], 'text_messages')
        self.assertIn('Hello World', message_info['content'])
        self.assertIn('12345678', message_info['content'])

    def test_get_message_info_position_update(self):
        """Test position update formatting"""
        mock_decoded = Mock()
        mock_decoded.portnum = 3  # POSITION_APP
        
        with patch('meshcord_bot.portnums_pb2') as mock_portnums:
            mock_portnums.POSITION_APP = 3
            
            message_info = self.bot._get_message_info(
                mock_decoded, 0x12345678, 1640995200, "TestRadio", 3.1, -92
            )
        
        self.assertIsNotNone(message_info)
        self.assertEqual(message_info['type'], 'position_updates')
        self.assertIn('Position update', message_info['content'])

    def test_get_message_info_unknown_port(self):
        """Test unknown message type handling"""
        mock_decoded = Mock()
        mock_decoded.portnum = 999  # Unknown port
        
        message_info = self.bot._get_message_info(
            mock_decoded, 0x12345678, 1640995200, "TestRadio", 1.0, -100
        )
        
        self.assertIsNotNone(message_info)
        self.assertEqual(message_info['type'], 'unknown')
        self.assertIn('Unknown message', message_info['content'])
        self.assertIn('port 999', message_info['content'])

    def test_get_message_info_empty_text(self):
        """Test handling of empty text messages"""
        mock_decoded = Mock()
        mock_decoded.portnum = 1  # TEXT_MESSAGE_APP
        mock_decoded.payload = b""  # Empty payload
        
        with patch('meshcord_bot.portnums_pb2') as mock_portnums:
            mock_portnums.TEXT_MESSAGE_APP = 1
            
            message_info = self.bot._get_message_info(
                mock_decoded, 0x12345678, 1640995200, "TestRadio", 5.2, -85
            )
        
        # Should return None for empty text messages
        self.assertIsNone(message_info)


class TestMeshtasticDiscordBotAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """Set up async test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'http'
        })
        
        with patch('meshcord_bot.discord.Client'):
            self.bot = MeshtasticDiscordBot()

    async def asyncTearDown(self):
        """Clean up async test environment"""
        os.chdir(self.original_cwd)
        if hasattr(self.bot, 'conn') and self.bot.conn:
            self.bot.conn.close()
        
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch('meshcord_bot.aiohttp.ClientSession.get')
    async def test_poll_radio_http_success(self, mock_get):
        """Test successful HTTP polling"""
        # Mock successful HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b'test_data')
        mock_get.return_value.__aenter__.return_value = mock_response
        
        # Mock session
        self.bot.session = AsyncMock()
        self.bot.session.get = mock_get
        
        # Mock protobuf processing
        with patch.object(self.bot, '_process_protobuf_data') as mock_process:
            radio = {"name": "TestRadio", "host": "test.local", "port": "80"}
            await self.bot._poll_radio_http(radio)
            
            mock_process.assert_called_once_with(b'test_data', 'TestRadio')

    @patch('meshcord_bot.aiohttp.ClientSession.get')
    async def test_poll_radio_http_no_data(self, mock_get):
        """Test HTTP polling with no data"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b'')
        mock_get.return_value.__aenter__.return_value = mock_response
        
        self.bot.session = AsyncMock()
        self.bot.session.get = mock_get
        
        with patch.object(self.bot, '_process_protobuf_data') as mock_process:
            radio = {"name": "TestRadio", "host": "test.local", "port": "80"}
            await self.bot._poll_radio_http(radio)
            
            # Should not process empty data
            mock_process.assert_not_called()

    @patch('meshcord_bot.aiohttp.ClientSession.get')
    async def test_poll_radio_http_timeout(self, mock_get):
        """Test HTTP polling timeout handling"""
        mock_get.side_effect = asyncio.TimeoutError()
        
        self.bot.session = AsyncMock()
        self.bot.session.get = mock_get
        self.bot.debug_mode = True
        
        radio = {"name": "TestRadio", "host": "test.local", "port": "80"}
        
        # Should not raise exception
        await self.bot._poll_radio_http(radio)

    async def test_send_to_discord_success(self):
        """Test successful Discord message sending"""
        # Mock Discord channel
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()
        
        self.bot.client = Mock()
        self.bot.client.get_channel.return_value = mock_channel
        
        await self.bot._send_to_discord("Test message")
        
        mock_channel.send.assert_called_once_with("Test message")

    async def test_send_to_discord_channel_not_found(self):
        """Test Discord message sending when channel not found"""
        self.bot.client = Mock()
        self.bot.client.get_channel.return_value = None
        
        # Should not raise exception
        await self.bot._send_to_discord("Test message")

    async def test_process_mesh_packet_success(self):
        """Test successful mesh packet processing"""
        # Mock packet
        mock_packet = Mock()
        mock_packet.id = 42
        setattr(mock_packet, 'from', 0x12345678)
        mock_packet.rx_time = 1640995200
        mock_packet.rx_snr = 5.2
        mock_packet.rx_rssi = -85
        
        # Mock decoded data
        mock_decoded = Mock()
        mock_decoded.portnum = 1
        mock_decoded.payload = b"Test message"
        mock_packet.decoded = mock_decoded
        
        # Mock dependencies
        with patch('meshcord_bot.portnums_pb2') as mock_portnums:
            mock_portnums.TEXT_MESSAGE_APP = 1
            
            with patch.object(self.bot, '_send_to_discord') as mock_send:
                self.bot.message_filters['text_messages'] = True
                
                await self.bot._process_mesh_packet(mock_packet, "TestRadio")
                
                # Should send to Discord
                mock_send.assert_called_once()

    async def test_process_mesh_packet_filtered(self):
        """Test mesh packet processing with filtering"""
        mock_packet = Mock()
        mock_packet.id = 42
        setattr(mock_packet, 'from', 0x12345678)
        mock_packet.rx_time = 1640995200
        
        mock_decoded = Mock()
        mock_decoded.portnum = 1
        mock_decoded.payload = b"Test message"
        mock_packet.decoded = mock_decoded
        
        with patch('meshcord_bot.portnums_pb2') as mock_portnums:
            mock_portnums.TEXT_MESSAGE_APP = 1
            
            with patch.object(self.bot, '_send_to_discord') as mock_send:
                # Disable text messages
                self.bot.message_filters['text_messages'] = False
                
                await self.bot._process_mesh_packet(mock_packet, "TestRadio")
                
                # Should not send to Discord
                mock_send.assert_not_called()

    async def test_process_mesh_packet_duplicate(self):
        """Test duplicate packet handling"""
        mock_packet = Mock()
        mock_packet.id = 42
        setattr(mock_packet, 'from', 0x12345678)
        mock_packet.rx_time = 1640995200
        
        # Mark as already processed
        self.bot._mark_message_processed("12345678_42", "TestRadio", 1640995200)
        
        with patch.object(self.bot, '_send_to_discord') as mock_send:
            await self.bot._process_mesh_packet(mock_packet, "TestRadio")
            
            # Should not send duplicate
            mock_send.assert_not_called()


if __name__ == '__main__':
    # Run the tests
    unittest.main()