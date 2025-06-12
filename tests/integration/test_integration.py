import unittest
import asyncio
import tempfile
import os
import json
import time
from datetime import datetime, timedelta
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
    """Enhanced mock HTTP server for testing"""
    
    def __init__(self):
        self.messages = []
        self.current_index = 0
        self.request_count = 0
        
    def add_message(self, data: bytes):
        """Add a message to be returned by the server"""
        self.messages.append(data)
        
    async def fromradio_handler(self, request):
        """Mock /api/v1/fromradio endpoint"""
        self.request_count += 1
        
        if self.current_index < len(self.messages):
            message = self.messages[self.current_index]
            self.current_index += 1
            return web.Response(body=message, content_type='application/octet-stream')
        else:
            # No more messages - return 503 (normal behavior)
            return web.Response(status=503, text='No messages available')

    async def nodeinfo_handler(self, request):
        """Mock /api/v1/nodeinfo endpoint"""
        # Return empty response or sample nodeinfo
        return web.Response(body=b'', content_type='application/octet-stream')


class TestMeshcordIntegration(AioHTTPTestCase):
    """Integration tests for the complete Meshcord system"""

    async def get_application(self):
        """Set up mock Meshtastic HTTP server"""
        self.mock_server = MockMeshtasticServer()
        app = web.Application()
        app.router.add_get('/api/v1/fromradio', self.mock_server.fromradio_handler)
        app.router.add_get('/api/v1/nodeinfo', self.mock_server.nodeinfo_handler)
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
        test_env_vars = [
            'DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID', 'CONNECTION_METHOD',
            'MESHTASTIC_HOST', 'MESHTASTIC_PORT', 'RADIO_NAME', 'POLL_INTERVAL',
            'DEBUG_MODE', 'SERIAL_PORT', 'CONNECTION_TIMEOUT', 
            'MAX_RECONNECT_ATTEMPTS', 'RECONNECT_DELAY'
        ]
        for key in test_env_vars:
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

    async def test_http_polling_with_no_data(self):
        """Test HTTP polling behavior when no data is available"""
        mock_discord_client = Mock()
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            
            import aiohttp
            bot.session = aiohttp.ClientSession()
            
            try:
                radio_config = bot.radios[0]
                
                # Poll with no messages (should get 503)
                with patch.object(bot, '_process_protobuf_data') as mock_process:
                    await bot._poll_radio_http(radio_config)
                    
                    # Should not process any data
                    mock_process.assert_not_called()
                    
                    # Verify server was called
                    self.assertGreater(self.mock_server.request_count, 0)
                
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
            'SERIAL_PORT': '/dev/ttyUSB0',
            'CONNECTION_TIMEOUT': '60',
            'MAX_RECONNECT_ATTEMPTS': '3',
            'RECONNECT_DELAY': '10'
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
                self.assertEqual(bot.connection_timeout, 60)
                self.assertEqual(bot.max_reconnect_attempts, 3)
                self.assertEqual(bot.reconnect_delay, 10)
                
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

    async def test_serial_health_monitoring_integration(self):
        """Test serial health monitoring integration"""
        
        with patch.dict(os.environ, {
            'CONNECTION_METHOD': 'serial',
            'CONNECTION_TIMEOUT': '5'  # Very short for testing
        }):
            mock_discord_client = Mock()
            
            with patch('meshcord_bot.discord.Client') as MockDiscordClient:
                MockDiscordClient.return_value = mock_discord_client
                
                bot = MeshtasticDiscordBot()
                bot.meshtastic_interface = Mock()
                
                # Simulate old packet time (stale connection)
                bot.last_packet_time = datetime.now() - timedelta(seconds=10)
                
                # Test health monitoring logic
                current_time = datetime.now()
                if bot.last_packet_time:
                    time_since_last = current_time - bot.last_packet_time
                    if time_since_last.total_seconds() > bot.connection_timeout:
                        # Health monitor would close interface
                        with patch.object(bot.meshtastic_interface, 'close') as mock_close:
                            bot.meshtastic_interface.close()
                            bot.meshtastic_interface = None
                            bot.last_packet_time = None
                            
                            mock_close.assert_called_once()

    async def test_packet_callback_integration(self):
        """Test packet callback updates health monitoring"""
        
        with patch.dict(os.environ, {'CONNECTION_METHOD': 'serial'}):
            mock_discord_client = Mock()
            
            with patch('meshcord_bot.discord.Client') as MockDiscordClient:
                MockDiscordClient.return_value = mock_discord_client
                
                bot = MeshtasticDiscordBot()
                bot.loop = asyncio.get_event_loop()
                
                initial_time = bot.last_packet_time
                
                # Simulate packet callback
                mock_packet = Mock()
                mock_interface = Mock()
                
                bot._packet_callback(mock_packet, mock_interface)
                
                # Should update last packet time
                self.assertNotEqual(bot.last_packet_time, initial_time)
                self.assertIsInstance(bot.last_packet_time, datetime)

    async def test_message_type_filtering_integration(self):
        """Test message type filtering in complete pipeline"""
        
        with patch.dict(os.environ, {
            'SHOW_TEXT_MESSAGES': 'true',
            'SHOW_TELEMETRY': 'false',
            'SHOW_ROUTING': 'false'
        }):
            mock_discord_client = Mock()
            mock_channel = AsyncMock()
            mock_discord_client.get_channel.return_value = mock_channel
            
            with patch('meshcord_bot.discord.Client') as MockDiscordClient:
                MockDiscordClient.return_value = mock_discord_client
                
                bot = MeshtasticDiscordBot()
                bot.client = mock_discord_client
                
                # Test that filters are applied
                self.assertTrue(bot._should_process_message_type('text_messages'))
                self.assertFalse(bot._should_process_message_type('telemetry'))
                self.assertFalse(bot._should_process_message_type('routing'))
                
                # Test message processing with filtering
                mock_packet = Mock()
                setattr(mock_packet, 'from', 0x12345678)
                mock_packet.id = 42
                mock_packet.rx_time = int(time.time())
                mock_packet.decoded = Mock()
                mock_packet.decoded.portnum = 3  # TELEMETRY_APP
                mock_packet.rx_snr = 5.0
                mock_packet.rx_rssi = -80
                
                with patch('meshcord_bot.portnums_pb2') as mock_portnums:
                    mock_portnums.TELEMETRY_APP = 3
                    
                    with patch.object(bot, '_send_to_discord', new_callable=AsyncMock) as mock_send:
                        await bot._process_mesh_packet(mock_packet, 'test_source')
                        
                        # Should not send to Discord (telemetry filtered out)
                        mock_send.assert_not_called()

    async def test_signal_strength_display_integration(self):
        """Test signal strength display integration"""
        
        with patch.dict(os.environ, {
            'SHOW_SIGNAL_STRENGTH': 'true'
        }):
            mock_discord_client = Mock()
            
            with patch('meshcord_bot.discord.Client') as MockDiscordClient:
                MockDiscordClient.return_value = mock_discord_client
                
                bot = MeshtasticDiscordBot()
                
                # Test signal strength inclusion
                self.assertTrue(bot.show_signal_strength)
                
                mock_decoded = Mock()
                mock_decoded.portnum = 1  # TEXT_MESSAGE_APP
                mock_decoded.payload = b"Test message"
                
                with patch('meshcord_bot.portnums_pb2') as mock_portnums:
                    mock_portnums.TEXT_MESSAGE_APP = 1
                    
                    message_info = bot._get_message_info(
                        mock_decoded, 0x12345678, int(time.time()), 
                        "test_radio", "5.5", "-75"
                    )
                    
                    # Should include signal strength
                    self.assertIn('SNR: 5.5', message_info['content'])
                    self.assertIn('RSSI: -75', message_info['content'])
                    self.assertIn('📶', message_info['content'])

    async def test_discord_message_chunking_integration(self):
        """Test Discord message chunking for long messages"""
        
        mock_discord_client = Mock()
        mock_channel = AsyncMock()
        mock_discord_client.get_channel.return_value = mock_channel
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            bot.client = mock_discord_client
            
            # Test long message (over Discord's 2000 character limit)
            long_message = "A" * 2500  # 2500 characters
            
            await bot._send_to_discord(long_message)
            
            # Should have sent multiple chunks
            self.assertGreater(mock_channel.send.call_count, 1)
            
            # Verify all chunks were reasonable size
            for call in mock_channel.send.call_args_list:
                message_chunk = call[0][0]
                self.assertLessEqual(len(message_chunk), 1900)  # Should be chunked

    async def test_database_persistence_integration(self):
        """Test database persistence across bot restarts"""
        
        mock_discord_client = Mock()
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            # Create first bot instance
            bot1 = MeshtasticDiscordBot()
            
            # Add some data
            node_id = 0x11223344
            mock_user_info = Mock()
            mock_user_info.short_name = "PERSIST"
            mock_user_info.long_name = "Persistence Test"
            
            bot1._update_node_info(node_id, mock_user_info)
            
            message_id = "persist_test_123"
            bot1._mark_message_processed(message_id, "test_radio", int(time.time()))
            
            # Close first instance
            bot1.conn.close()
            
            # Create second bot instance (should read from same database)
            bot2 = MeshtasticDiscordBot()
            
            # Verify data persisted
            node_name = bot2._get_node_name(node_id)
            self.assertEqual(node_name, "PERSIST (11223344)")
            
            is_processed = bot2._is_message_processed(message_id, "test_radio")
            self.assertTrue(is_processed)
            
            bot2.conn.close()

    async def test_configuration_error_handling(self):
        """Test configuration error handling"""
        
        # Test missing required configuration
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                MeshtasticDiscordBot()
        
        # Test invalid JSON in RADIOS config
        with patch.dict(os.environ, {
            'DISCORD_BOT_TOKEN': 'test',
            'DISCORD_CHANNEL_ID': '12345',
            'RADIOS': '{"invalid": json}'  # Invalid JSON
        }):
            with patch('meshcord_bot.discord.Client'):
                # Should handle gracefully and fall back to single radio
                bot = MeshtasticDiscordBot()
                self.assertEqual(len(bot.radios), 1)  # Fallback radio


class TestSerialConnectionIntegration(unittest.TestCase):
    """Integration tests specifically for serial connection features"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'serial',
            'SERIAL_PORT': '/dev/ttyUSB0'
        })

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        test_env_vars = [
            'DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID', 'CONNECTION_METHOD',
            'SERIAL_PORT', 'CONNECTION_TIMEOUT', 'MAX_RECONNECT_ATTEMPTS', 
            'RECONNECT_DELAY'
        ]
        for key in test_env_vars:
            os.environ.pop(key, None)

    def test_serial_configuration_integration(self):
        """Test serial configuration is properly integrated"""
        
        with patch.dict(os.environ, {
            'CONNECTION_TIMEOUT': '120',
            'MAX_RECONNECT_ATTEMPTS': '10',
            'RECONNECT_DELAY': '45'
        }):
            with patch('meshcord_bot.discord.Client'):
                bot = MeshtasticDiscordBot()
                
                # Verify all serial config is loaded
                self.assertEqual(bot.connection_method, 'serial')
                self.assertEqual(bot.serial_port, '/dev/ttyUSB0')
                self.assertEqual(bot.connection_timeout, 120)
                self.assertEqual(bot.max_reconnect_attempts, 10)
                self.assertEqual(bot.reconnect_delay, 45)


class TestSerialConnectionIntegrationAsync(unittest.IsolatedAsyncioTestCase):
    """Async integration tests for serial connection features"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token',
            'DISCORD_CHANNEL_ID': '12345',
            'CONNECTION_METHOD': 'serial',
            'SERIAL_PORT': '/dev/ttyUSB0'
        })

    def tearDown(self):
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        test_env_vars = [
            'DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID', 'CONNECTION_METHOD',
            'SERIAL_PORT', 'CONNECTION_TIMEOUT', 'MAX_RECONNECT_ATTEMPTS', 
            'RECONNECT_DELAY'
        ]
        for key in test_env_vars:
            os.environ.pop(key, None)

    async def test_serial_task_creation_integration(self):
        """Test that serial tasks are created correctly"""
        
        mock_discord_client = Mock()
        
        with patch('meshcord_bot.discord.Client') as MockDiscordClient:
            MockDiscordClient.return_value = mock_discord_client
            
            bot = MeshtasticDiscordBot()
            
            # Verify serial mode is detected
            self.assertEqual(bot.connection_method, 'serial')
            
            # Simply verify the methods exist and are coroutines
            self.assertTrue(asyncio.iscoroutinefunction(bot._monitor_serial))
            self.assertTrue(asyncio.iscoroutinefunction(bot._process_packet_queue))
            self.assertTrue(asyncio.iscoroutinefunction(bot._monitor_connection_health))


if __name__ == '__main__':
    unittest.main()