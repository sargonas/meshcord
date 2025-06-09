# tests/integration/test_integration.py
import unittest
import asyncio
import tempfile
import os
import json
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
import threading
import sqlite3

# Mock meshtastic imports but create realistic protobuf-like objects
import sys

# Create mock protobuf classes that behave like real ones
class MockFromRadio:
    def __init__(self):
        self.packet = None
        self.node_info = None
        self.my_info = None
        self.config = None
        
    def ParseFromString(self, data):
        # Simple parsing logic for test data
        if data.startswith(b'PACKET:'):
            self.packet = MockMeshPacket()
            self.packet.ParseFromString(data[7:])  # Remove prefix
        elif data.startswith(b'NODE:'):
            self.node_info = MockNodeInfo()
        # else: leave fields as None
            
    def HasField(self, field_name):
        return getattr(self, field_name) is not None
        
    def ByteSize(self):
        return 50  # Mock size

class MockMeshPacket:
    def __init__(self):
        self.id = 0
        self.rx_time = 0
        self.rx_snr = 0.0
        self.rx_rssi = 0
        self.decoded = None
        self._from = 0
        
    def ParseFromString(self, data):
        # Parse our mock format: "from:id:time:snr:rssi:port:payload"
        try:
            parts = data.decode('utf-8').split(':')
            if len(parts) >= 6:
                self._from = int(parts[0], 16)
                self.id = int(parts[1])
                self.rx_time = int(parts[2])
                self.rx_snr = float(parts[3])
                self.rx_rssi = int(parts[4])
                
                self.decoded = MockDecoded()
                self.decoded.portnum = int(parts[5])
                if len(parts) > 6:
                    self.decoded.payload = parts[6].encode('utf-8')
                else:
                    self.decoded.payload = b''
        except (ValueError, IndexError):
            pass
    
    @property
    def from_(self):
        return self._from
    
    def __getattr__(self, name):
        if name == 'from':
            return self._from
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

class MockDecoded:
    def __init__(self):
        self.portnum = 0
        self.payload = b''

class MockNodeInfo:
    def __init__(self):
        self.num = 0
        self.user = MockUser()

class MockUser:
    def __init__(self):
        self.short_name = ""
        self.long_name = ""
        
    def ParseFromString(self, data):
        # Parse format "short_name|long_name"
        try:
            parts = data.decode('utf-8').split('|')
            self.short_name = parts[0] if len(parts) > 0 else ""
            self.long_name = parts[1] if len(parts) > 1 else ""
        except:
            pass

# Mock the protobuf modules with our realistic mocks
mock_mesh_pb2 = MagicMock()
mock_mesh_pb2.FromRadio = MockFromRadio
mock_mesh_pb2.MeshPacket = MockMeshPacket
mock_mesh_pb2.User = MockUser

mock_portnums_pb2 = MagicMock()
mock_portnums_pb2.TEXT_MESSAGE_APP = 1
mock_portnums_pb2.POSITION_APP = 3
mock_portnums_pb2.NODEINFO_APP = 4
mock_portnums_pb2.TELEMETRY_APP = 67

sys.modules['meshtastic'] = MagicMock()
sys.modules['meshtastic.mesh_pb2'] = mock_mesh_pb2
sys.modules['meshtastic.portnums_pb2'] = mock_portnums_pb2

from meshcord_bot import MeshtasticDiscordBot


class MockMeshtasticServer:
    """Mock HTTP server that simulates a Meshtastic radio with realistic protobuf data"""
    
    def __init__(self):
        self.messages = []
        self.current_message_index = 0
        
    def add_text_message(self, from_node, message_id, text, snr=5.0, rssi=-85):
        """Add a realistic text message"""
        timestamp = int(time.time())
        # Format: PACKET:from:id:time:snr:rssi:port:payload
        packet_data = f"PACKET:{from_node:08x}:{message_id}:{timestamp}:{snr}:{rssi}:1:{text}"
        self.messages.append(packet_data.encode('utf-8'))
        
    def add_position_update(self, from_node, message_id, snr=3.0, rssi=-92):
        """Add a realistic position update"""
        timestamp = int(time.time())
        packet_data = f"PACKET:{from_node:08x}:{message_id}:{timestamp}:{snr}:{rssi}:3:"
        self.messages.append(packet_data.encode('utf-8'))
        
    def add_node_info(self, node_id, short_name, long_name):
        """Add a realistic node info message"""
        # Format: NODE:node_id followed by user data
        node_data = f"NODE:{node_id:08x}"
        user_data = f"{short_name}|{long_name}"
        # Combine both parts
        full_data = node_data.encode('utf-8') + b'\x00' + user_data.encode('utf-8')
        self.messages.append(full_data)
        
    def add_telemetry(self, from_node, message_id, snr=2.5, rssi=-95):
        """Add a realistic telemetry message"""
        timestamp = int(time.time())
        packet_data = f"PACKET:{from_node:08x}:{message_id}:{timestamp}:{snr}:{rssi}:67:"
        self.messages.append(packet_data.encode('utf-8'))
        
    async def fromradio_handler(self, request):
        """Mock /api/v1/fromradio endpoint with realistic responses"""
        if self.current_message_index < len(self.messages):
            message = self.messages[self.current_message_index]
            self.current_message_index += 1
            return web.Response(body=message, content_type='application/octet-stream')
        else:
            # No more messages - return empty response (this is normal)
            return web.Response(body=b'', content_type='application/octet-stream')


class TestMeshcordIntegration(AioHTTPTestCase):
    """Integration tests for the complete Meshcord system"""

    async def get_application(self):
        """Set up mock Meshtastic HTTP server"""
        self.mock_server = MockMeshtasticServer()
        app = web.Application()
        app.router.add_get('/api/v1/fromradio', self.mock_server.fromradio_handler)
        return app

    async def setUpAsync(self):
        """Set up integration test environment"""
        await super().setUpAsync()
        
        # Create temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        # Get the mock server URL
        server_url = f"http://127.0.0.1:{self.server.port}"
        
        # Set environment variables for the bot
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token_integration',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'http',
            'MESHTASTIC_HOST': '127.0.0.1',
            'MESHTASTIC_PORT': str(self.server.port),
            'RADIO_NAME': 'IntegrationTestRadio',
            'POLL_INTERVAL': '0.1',  # Very fast for testing
            'DEBUG_MODE': 'true'
        })

    async def tearDownAsync(self):
        """Clean up integration test environment"""
        await super().tearDownAsync()
        
        # Clean up temp directory
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        # Clean up environment
        for key in ['DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID', 'CONNECTION_METHOD',
                   'MESHTASTIC_HOST', 'MESHTASTIC_PORT', 'RADIO_NAME', 'POLL_INTERVAL',
                   'DEBUG_MODE']:
            os.environ.pop(key, None)

    @unittest_run_loop
    async def test_end_to_end_text_message_flow(self):
        """Test complete flow from HTTP API to Discord message"""
        
        # Add a realistic text message using our mock protobuf format
        self.mock_server.add_text_message(
            from_node=0x12345678,
            message_id=42,
            text="Hello Integration Test",
            snr=5.2,
            rssi=-85
        )
        
        # Mock Discord components
        mock_channel = AsyncMock()
        mock_discord_client = Mock()
        mock_discord_client.get_channel.return_value = mock_channel
        
        # Create bot instance
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            bot.client = mock_discord_client
            
            # Set up aiohttp session
            import aiohttp
            bot.session = aiohttp.ClientSession()
            
            try:
                # Run one poll cycle
                radio_config = {
                    'name': 'IntegrationTestRadio',
                    'host': '127.0.0.1',
                    'port': str(self.server.port)
                }
                
                await bot._poll_radio_http(radio_config)
                
                # Verify Discord message was sent
                mock_channel.send.assert_called_once()
                sent_message = mock_channel.send.call_args[0][0]
                
                # Verify message content
                self.assertIn('Hello Integration Test', sent_message)
                self.assertIn('IntegrationTestRadio', sent_message)
                self.assertIn('12345678', sent_message)
                self.assertIn('SNR: 5.2', sent_message)
                self.assertIn('RSSI: -85', sent_message)
                
            finally:
                await bot.session.close()

    @unittest_run_loop
    async def test_position_update_flow(self):
        """Test position update message flow"""
        
        # Add a position update
        self.mock_server.add_position_update(
            from_node=0x87654321,
            message_id=100,
            snr=3.1,
            rssi=-92
        )
        
        mock_channel = AsyncMock()
        mock_discord_client = Mock()
        mock_discord_client.get_channel.return_value = mock_channel
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            bot.client = mock_discord_client
            
            import aiohttp
            bot.session = aiohttp.ClientSession()
            
            try:
                radio_config = {
                    'name': 'TestRadio',
                    'host': '127.0.0.1',
                    'port': str(self.server.port)
                }
                
                await bot._poll_radio_http(radio_config)
                
                # Verify position update was sent
                mock_channel.send.assert_called_once()
                sent_message = mock_channel.send.call_args[0][0]
                
                self.assertIn('Position update', sent_message)
                self.assertIn('87654321', sent_message)
                self.assertIn('SNR: 3.1', sent_message)
                self.assertIn('RSSI: -92', sent_message)
                
            finally:
                await bot.session.close()

    @unittest_run_loop
    async def test_message_deduplication_across_polls(self):
        """Test that duplicate messages are not sent to Discord"""
        
        # Add the same message twice
        self.mock_server.add_text_message(0x12345678, 123, "Duplicate test")
        self.mock_server.add_text_message(0x12345678, 123, "Duplicate test")  # Same ID
        
        mock_channel = AsyncMock()
        mock_discord_client = Mock()
        mock_discord_client.get_channel.return_value = mock_channel
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            bot.client = mock_discord_client
            
            import aiohttp
            bot.session = aiohttp.ClientSession()
            
            try:
                radio_config = {
                    'name': 'TestRadio',
                    'host': '127.0.0.1',
                    'port': str(self.server.port)
                }
                
                # Poll twice - should only get one Discord message
                await bot._poll_radio_http(radio_config)
                await bot._poll_radio_http(radio_config)
                
                # Should only send once (first time), second should be deduplicated
                self.assertEqual(mock_channel.send.call_count, 1)
                
                # Verify the message content
                sent_message = mock_channel.send.call_args[0][0]
                self.assertIn('Duplicate test', sent_message)
                
            finally:
                await bot.session.close()

    @unittest_run_loop
    async def test_different_message_types(self):
        """Test handling of different Meshtastic message types"""
        
        # Add various message types
        self.mock_server.add_text_message(0x11111111, 1, "Text message")
        self.mock_server.add_position_update(0x22222222, 2)
        self.mock_server.add_telemetry(0x33333333, 3)
        
        mock_channel = AsyncMock()
        mock_discord_client = Mock()
        mock_discord_client.get_channel.return_value = mock_channel
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            bot.client = mock_discord_client
            
            import aiohttp
            bot.session = aiohttp.ClientSession()
            
            try:
                radio_config = {
                    'name': 'TestRadio',
                    'host': '127.0.0.1',
                    'port': str(self.server.port)
                }
                
                # Poll multiple times to get all messages
                for _ in range(3):
                    await bot._poll_radio_http(radio_config)
                
                # Should have sent 3 different messages
                self.assertEqual(mock_channel.send.call_count, 3)
                
                # Verify different message types were processed
                sent_messages = [call[0][0] for call in mock_channel.send.call_args_list]
                
                # Check for text message
                text_msg = next((msg for msg in sent_messages if "Text message" in msg), None)
                self.assertIsNotNone(text_msg)
                
                # Check for position update
                pos_msg = next((msg for msg in sent_messages if "Position update" in msg), None)
                self.assertIsNotNone(pos_msg)
                
                # Check for telemetry
                tel_msg = next((msg for msg in sent_messages if "Telemetry data" in msg), None)
                self.assertIsNotNone(tel_msg)
                
            finally:
                await bot.session.close()

    @unittest_run_loop
    async def test_multiple_radios_integration(self):
        """Test polling multiple radios simultaneously"""
        
        # Set up multiple radio configuration
        radios_config = json.dumps([
            {"name": "Radio1", "host": "127.0.0.1", "port": str(self.server.port)},
            {"name": "Radio2", "host": "127.0.0.1", "port": str(self.server.port)}
        ])
        
        with patch.dict(os.environ, {'RADIOS': radios_config}):
            mock_channel = AsyncMock()
            mock_discord_client = Mock()
            mock_discord_client.get_channel.return_value = mock_channel
            
            with patch('meshcord_bot.discord.Client') as MockDiscordClient:
                MockDiscordClient.return_value = mock_discord_client
                
                bot = MeshtasticDiscordBot()
                bot.client = mock_discord_client
                
                # Verify multiple radios were configured
                self.assertEqual(len(bot.radios), 2)
                self.assertEqual(bot.radios[0]['name'], 'Radio1')
                self.assertEqual(bot.radios[1]['name'], 'Radio2')

    @unittest_run_loop
    async def test_node_info_integration(self):
        """Test node information handling with realistic data"""
        
        # Add a node info message
        self.mock_server.add_node_info(0xAABBCCDD, "Alice", "Alice's Base Station")
        
        mock_channel = AsyncMock()
        mock_discord_client = Mock()
        mock_discord_client.get_channel.return_value = mock_channel
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            bot.client = mock_discord_client
            
            import aiohttp
            bot.session = aiohttp.ClientSession()
            
            try:
                radio_config = {
                    'name': 'TestRadio',
                    'host': '127.0.0.1',
                    'port': str(self.server.port)
                }
                
                await bot._poll_radio_http(radio_config)
                
                # Check that node info was stored
                display_name = bot._get_node_name(0xAABBCCDD)
                self.assertEqual(display_name, "Alice (aabbccdd)")
                
                # Verify in database
                cursor = bot.conn.cursor()
                cursor.execute('SELECT short_name, long_name FROM nodes WHERE node_id = ?', (0xAABBCCDD,))
                result = cursor.fetchone()
                self.assertIsNotNone(result)
                self.assertEqual(result[0], "Alice")
                self.assertEqual(result[1], "Alice's Base Station")
                
            finally:
                await bot.session.close()

    @unittest_run_loop
    async def test_message_filtering_integration(self):
        """Test that message filtering works end-to-end"""
        
        # Disable text messages, enable position updates
        with patch.dict(os.environ, {
            'SHOW_TEXT_MESSAGES': 'false',
            'SHOW_POSITION_UPDATES': 'true'
        }):
            mock_channel = AsyncMock()
            mock_discord_client = Mock()
            mock_discord_client.get_channel.return_value = mock_channel
            
            with patch('meshcord_bot.discord.Client') as MockDiscordClient:
                MockDiscordClient.return_value = mock_discord_client
                
                bot = MeshtasticDiscordBot()
                bot.client = mock_discord_client
                
                # Verify filter configuration
                self.assertFalse(bot.message_filters['text_messages'])
                self.assertTrue(bot.message_filters['position_updates'])
                
                # Test that filtering is applied
                self.assertFalse(bot._should_process_message_type('text_messages'))
                self.assertTrue(bot._should_process_message_type('position_updates'))

    @unittest_run_loop
    async def test_error_handling_integration(self):
        """Test error handling in real HTTP scenarios"""
        
        mock_channel = AsyncMock()
        mock_discord_client = Mock()
        mock_discord_client.get_channel.return_value = mock_channel
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            bot.client = mock_discord_client
            
            import aiohttp
            bot.session = aiohttp.ClientSession()
            
            try:
                # Test with invalid host (should handle connection error gracefully)
                invalid_radio = {
                    'name': 'InvalidRadio',
                    'host': 'nonexistent.invalid',
                    'port': '80'
                }
                
                # Should not raise exception
                await bot._poll_radio_http(invalid_radio)
                
                # Should not have sent any messages due to connection failure
                mock_channel.send.assert_not_called()
                
            finally:
                await bot.session.close()

    def test_database_cleanup_integration(self):
        """Test that old messages are cleaned up properly"""
        
        with patch('meshcord_bot.discord.Client'):
            bot = MeshtasticDiscordBot()
            
            # Add an old message (more than 24 hours ago)
            old_timestamp = int(time.time()) - 90000  # 25 hours ago
            bot._mark_message_processed("old_message_123", "TestRadio", old_timestamp)
            
            # Add a recent message
            recent_timestamp = int(time.time()) - 3600  # 1 hour ago
            bot._mark_message_processed("recent_message_456", "TestRadio", recent_timestamp)
            
            # Trigger cleanup by creating a new bot instance
            with patch('meshcord_bot.discord.Client'):
                new_bot = MeshtasticDiscordBot()
                
                # Old message should be gone
                self.assertFalse(new_bot._is_message_processed("old_message_123", "TestRadio"))
                
                # Recent message should still exist
                self.assertTrue(new_bot._is_message_processed("recent_message_456", "TestRadio"))
                
                new_bot.conn.close()


if __name__ == '__main__':
    unittest.main()