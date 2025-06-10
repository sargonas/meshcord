import unittest
import asyncio
import tempfile
import os
import json
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

# Mock meshtastic imports
import sys
sys.modules['meshtastic'] = MagicMock()
sys.modules['meshtastic.mesh_pb2'] = MagicMock()
sys.modules['meshtastic.portnums_pb2'] = MagicMock()
sys.modules['meshtastic.serial_interface'] = MagicMock()

from meshcord_bot import MeshtasticDiscordBot


class MockMeshtasticServer:
    """Simple mock HTTP server for testing"""
    
    def __init__(self):
        self.messages = []
        self.current_index = 0
        
    def add_message(self, data: bytes):
        """Add a message to be returned by the server"""
        self.messages.append(data)
        
    async def fromradio_handler(self, request):
        """Mock /api/v1/fromradio endpoint"""
        if self.current_index < len(self.messages):
            message = self.messages[self.current_index]
            self.current_index += 1
            return web.Response(body=message, content_type='application/octet-stream')
        else:
            # No more messages - return empty (normal behavior)
            return web.Response(body=b'', content_type='application/octet-stream')


class TestMeshcordIntegration(AioHTTPTestCase):
    """Integration tests for the complete Meshcord system"""

    async def get_application(self):
        """Set up mock Meshtastic HTTP server"""
        self.mock_server = MockMeshtasticServer()
        app = web.Application()
        app.router.add_get('/api/v1/fromradio', self.mock_server.fromradio_handler)
        app.router.add_get('/api/v1/nodeinfo', self.mock_server.fromradio_handler)
        return app

    async def setUpAsync(self):
        """Set up integration test environment"""
        await super().setUpAsync()
        
        # Create temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        # Set environment variables for the bot
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token_integration',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'http',
            'MESHTASTIC_HOST': '127.0.0.1',
            'MESHTASTIC_PORT': str(self.server.port),
            'RADIO_NAME': 'IntegrationTestRadio',
            'POLL_INTERVAL': '0.1',  # Fast for testing
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
                   'DEBUG_MODE', 'SERIAL_PORT']:
            os.environ.pop(key, None)

    async def test_http_connection_and_polling(self):
        """Test that HTTP connection and polling works end-to-end"""
        
        # Add a simple message to the mock server
        test_message = b'test_protobuf_data'
        self.mock_server.add_message(test_message)
        
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
                # Test that radio configuration is correctly parsed
                self.assertEqual(len(bot.radios), 1)
                self.assertEqual(bot.radios[0]['name'], 'IntegrationTestRadio')
                self.assertEqual(bot.radios[0]['host'], '127.0.0.1')
                self.assertEqual(bot.radios[0]['port'], str(self.server.port))
                
                # Test HTTP polling
                radio_config = bot.radios[0]
                
                # Mock the protobuf processing to avoid parsing errors
                with patch.object(bot, '_process_protobuf_data') as mock_process:
                    await bot._poll_radio_http(radio_config)
                    
                    # Verify that the mock server was called and data was processed
                    mock_process.assert_called_once_with(test_message, 'IntegrationTestRadio')
                
            finally:
                await bot.session.close()

    async def test_multiple_radio_configuration(self):
        """Test that multiple radios can be configured"""
        
        # Set up multiple radio configuration
        radios_config = json.dumps([
            {"name": "Radio1", "host": "127.0.0.1", "port": str(self.server.port)},
            {"name": "Radio2", "host": "127.0.0.1", "port": str(self.server.port)}
        ])
        
        with patch.dict(os.environ, {'RADIOS': radios_config}):
            mock_discord_client = Mock()
            
            with patch('meshcord_bot.discord.Client') as MockDiscordClient:
                MockDiscordClient.return_value = mock_discord_client
                
                bot = MeshtasticDiscordBot()
                
                # Verify multiple radios were configured
                self.assertEqual(len(bot.radios), 2)
                self.assertEqual(bot.radios[0]['name'], 'Radio1')
                self.assertEqual(bot.radios[1]['name'], 'Radio2')

    async def test_radio_display_names(self):
        """Test that radio display names work correctly"""
        
        radios_config = json.dumps([
            {"name": "radio1", "host": "127.0.0.1", "port": str(self.server.port), "display_name": "Home Base"},
            {"name": "radio2", "host": "127.0.0.1", "port": str(self.server.port)}  # No display name
        ])
        
        with patch.dict(os.environ, {'RADIOS': radios_config}):
            mock_discord_client = Mock()
            
            with patch('meshcord_bot.discord.Client') as MockDiscordClient:
                MockDiscordClient.return_value = mock_discord_client
                
                bot = MeshtasticDiscordBot()
                
                # Test radio info display
                radio1_info = bot._get_radio_info("radio1")
                radio2_info = bot._get_radio_info("radio2")
                
                # Radio1 should show display name
                self.assertEqual(radio1_info, f"Home Base (127.0.0.1)")
                
                # Radio2 should show regular name
                self.assertEqual(radio2_info, f"radio2 (127.0.0.1)")

    async def test_message_deduplication(self):
        """Test that duplicate messages are properly handled"""
        
        mock_discord_client = Mock()
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            
            # Test message deduplication
            message_id = "12345678_42"
            source = "IntegrationTestRadio"
            timestamp = int(time.time())
            
            # First time should not be processed
            self.assertFalse(bot._is_message_processed(message_id, source))
            
            # Mark as processed
            bot._mark_message_processed(message_id, source, timestamp)
            
            # Second time should be marked as processed
            self.assertTrue(bot._is_message_processed(message_id, source))

    async def test_database_functionality(self):
        """Test that database operations work correctly"""
        
        mock_discord_client = Mock()
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            
            # Test node info storage
            node_id = 0xAABBCCDD
            
            mock_user_info = Mock()
            mock_user_info.short_name = "TestNode"
            mock_user_info.long_name = "Test Node Long Name"
            
            bot._update_node_info(node_id, mock_user_info)
            
            # Verify node info was stored
            node_name = bot._get_node_name(node_id)
            self.assertEqual(node_name, "TestNode (aabbccdd)")
            
            # Verify in database
            cursor = bot.conn.cursor()
            cursor.execute('SELECT short_name, long_name FROM nodes WHERE node_id = ?', (node_id,))
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertEqual(result[0], "TestNode")
            self.assertEqual(result[1], "Test Node Long Name")

    async def test_error_handling(self):
        """Test that errors are handled gracefully"""
        
        mock_discord_client = Mock()
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            
            import aiohttp
            bot.session = aiohttp.ClientSession()
            
            try:
                # Test with invalid radio configuration
                invalid_radio = {
                    'name': 'InvalidRadio',
                    'host': 'nonexistent.invalid',
                    'port': '80'
                }
                
                # Should not raise exception, just handle error gracefully
                await bot._poll_radio_http(invalid_radio)
                
                # Test should complete without exceptions
                
            finally:
                await bot.session.close()

    async def test_serial_connection_integration(self):
        """Test serial connection integration end-to-end"""
        
        # Set up serial mode environment
        with patch.dict(os.environ, {
            'CONNECTION_METHOD': 'serial',
            'SERIAL_PORT': '/dev/ttyUSB0'
        }):
            mock_discord_client = Mock()
            mock_channel = AsyncMock()
            mock_discord_client.get_channel.return_value = mock_channel
            
            with patch('meshcord_bot.discord.Client') as MockDiscordClient:
                MockDiscordClient.return_value = mock_discord_client
                
                bot = MeshtasticDiscordBot()
                bot.client = mock_discord_client
                
                # Verify serial configuration
                self.assertEqual(bot.connection_method, 'serial')
                self.assertEqual(bot.serial_port, '/dev/ttyUSB0')
                
                # Test packet processing pipeline
                mock_packet = Mock()
                setattr(mock_packet, 'from', 0x12345678)
                mock_packet.id = 42
                mock_packet.rx_time = int(time.time())
                mock_packet.decoded = Mock()
                mock_packet.decoded.portnum = 1  # TEXT_MESSAGE_APP
                mock_packet.decoded.payload = b"Integration test message"
                mock_packet.rx_snr = 5.2
                mock_packet.rx_rssi = -85
                
                # Mock the portnum constants
                with patch('meshcord_bot.portnums_pb2') as mock_portnums:
                    mock_portnums.TEXT_MESSAGE_APP = 1
                    mock_portnums.NODEINFO_APP = 4
                    
                    # Test the complete packet processing pipeline
                    await bot._queue_packet(mock_packet)
                    
                    # Verify packet was queued
                    self.assertEqual(bot.packet_queue.qsize(), 1)
                    
                    # Process the packet
                    source, packet = await bot.packet_queue.get()
                    self.assertEqual(source, 'serial')
                    self.assertEqual(packet, mock_packet)
                    
                    # Process through the mesh packet handler
                    with patch.object(bot, '_send_to_discord', new_callable=AsyncMock) as mock_send:
                        await bot._process_mesh_packet(packet, source)
                        
                        # Verify message was formatted and sent to Discord
                        mock_send.assert_called_once()
                        call_args = mock_send.call_args[0][0]
                        self.assertIn('Integration test message', call_args)
                        self.assertIn('12345678', call_args)  # Node ID
                        self.assertIn('📻', call_args)  # Radio icon
                        self.assertIn('💬', call_args)  # Text message icon


if __name__ == '__main__':
    unittest.main()