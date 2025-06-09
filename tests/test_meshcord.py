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

    def test_configuration_validation_success(self):
        """Test successful configuration validation"""
        # Should not raise exception
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
        self.assertIsNotNone(bot)

    def test_configuration_validation_missing_token(self):
        """Test configuration validation with missing token"""
        with patch.dict(os.environ, {}, clear=True):
            os.environ['DISCORD_CHANNEL_ID'] = '12345'
            
            with self.assertRaises(ValueError) as cm:
                with patch('meshcord_bot.discord.Client'):
                    MeshtasticDiscordBot()
            
            self.assertIn("DISCORD_BOT_TOKEN is required", str(cm.exception))

    def test_configuration_validation_invalid_channel_id(self):
        """Test configuration validation with invalid channel ID"""
        with patch.dict(os.environ, {'DISCORD_BOT_TOKEN': 'test', 'DISCORD_CHANNEL_ID': 'invalid'}):
            with self.assertRaises(ValueError) as cm:
                with patch('meshcord_bot.discord.Client'):
                    MeshtasticDiscordBot()
            
            self.assertIn("DISCORD_CHANNEL_ID must be a valid integer", str(cm.exception))

    def test_parse_radios_single_config(self):
        """Test parsing single radio configuration"""
        radios = self.bot._parse_radios()
        
        self.assertEqual(len(radios), 1)
        self.assertEqual(radios[0]['name'], 'TestRadio')
        self.assertEqual(radios[0]['host'], 'test.local')
        self.assertEqual(radios[0]['port'], '80')

    def test_parse_radios_single_config_with_display_name(self):
        """Test parsing single radio configuration with display name"""
        with patch.dict(os.environ, {'RADIO_DISPLAY_NAME': 'Test Base Station'}):
            with patch('meshcord_bot.discord.Client'):
                bot = MeshtasticDiscordBot()
                radios = bot._parse_radios()
        
        self.assertEqual(len(radios), 1)
        self.assertEqual(radios[0]['name'], 'TestRadio')
        self.assertEqual(radios[0]['display_name'], 'Test Base Station')

    def test_parse_radios_json_config(self):
        """Test parsing JSON radio configuration"""
        json_config = json.dumps([
            {"name": "Radio1", "host": "192.168.1.100", "port": "80", "display_name": "Home Base"},
            {"name": "Radio2", "host": "192.168.1.101", "port": "80"}
        ])
        
        with patch.dict(os.environ, {'RADIOS': json_config}):
            with patch('meshcord_bot.discord.Client'):
                bot = MeshtasticDiscordBot()
                radios = bot._parse_radios()
        
        self.assertEqual(len(radios), 2)
        self.assertEqual(radios[0]['name'], 'Radio1')
        self.assertEqual(radios[0]['display_name'], 'Home Base')
        self.assertEqual(radios[1]['name'], 'Radio2')

    def test_database_initialization(self):
        """Test database tables are created correctly"""
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

    def test_get_radio_info_with_display_name(self):
        """Test radio info display with custom display names"""
        self.bot.radios = [
            {"name": "TestRadio", "host": "test.local", "port": "80", "display_name": "Test Base Station"}
        ]
        
        radio_info = self.bot._get_radio_info("TestRadio")
        self.assertEqual(radio_info, "Test Base Station (test.local)")

    def test_get_radio_info_without_display_name(self):
        """Test radio info display without custom display names"""
        radio_info = self.bot._get_radio_info("TestRadio")
        self.assertEqual(radio_info, "TestRadio (test.local)")

    def test_message_filtering(self):
        """Test message type filtering"""
        # Text messages should be processed by default
        self.assertTrue(self.bot._should_process_message_type('text_messages'))
        
        # Routing should not be processed by default
        self.assertFalse(self.bot._should_process_message_type('routing'))


class TestMeshtasticDiscordBotAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for MeshtasticDiscordBot"""
    
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

    async def test_send_to_discord_success(self):
        """Test successful Discord message sending"""
        # Mock Discord channel
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()
        
        self.bot.client = Mock()
        self.bot.client.get_channel.return_value = mock_channel
        
        await self.bot._send_to_discord("Test message")
        
        mock_channel.send.assert_called_once_with("Test message")

    async def test_send_to_discord_long_message(self):
        """Test sending long messages that get split"""
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock()
        
        self.bot.client = Mock()
        self.bot.client.get_channel.return_value = mock_channel
        
        # Create a message longer than Discord's limit
        long_message = "A" * 2500
        
        await self.bot._send_to_discord(long_message)
        
        # Should have been called multiple times for chunks
        self.assertGreater(mock_channel.send.call_count, 1)


if __name__ == '__main__':
    unittest.main()