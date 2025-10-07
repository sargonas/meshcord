"""Tests for message processing logic"""
import pytest
import os
import tempfile
import shutil
from unittest.mock import patch, Mock, AsyncMock
from meshtastic import mesh_pb2, portnums_pb2


@pytest.fixture
def clean_env():
    """Fixture to clean up environment variables after tests"""
    original_env = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def test_env(clean_env):
    """Fixture providing minimal valid environment"""
    os.environ.update({
        'DISCORD_BOT_TOKEN': 'test_token_123',
        'DISCORD_CHANNEL_ID': '123456789',
        'CONNECTION_METHOD': 'serial',
        'SERIAL_PORT': '/dev/ttyUSB0'
    })
    return os.environ


@pytest.fixture
def temp_dir():
    """Fixture providing temporary directory"""
    tmpdir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(tmpdir)
    yield tmpdir
    os.chdir(original_cwd)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def bot(test_env, temp_dir):
    """Fixture providing initialized bot instance"""
    with patch('meshcord_bot.discord.Client'):
        from meshcord_bot import MeshtasticDiscordBot
        bot = MeshtasticDiscordBot()
        yield bot
        if bot.conn:
            bot.conn.close()


@pytest.mark.unit
class TestMessageInfoExtraction:
    """Test message information extraction"""

    def test_text_message_extraction(self, bot):
        """Should extract text message content"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.TEXT_MESSAGE_APP
        decoded.payload = b'Hello World'

        from_id = 0x12345678
        rx_time = 1234567890
        source = 'radio1'

        message_info = bot._get_message_info(decoded, from_id, rx_time, source, '5.0', '-80')

        assert message_info is not None
        assert message_info['type'] == 'text_messages'
        assert 'Hello World' in message_info['content']
        assert '12345678' in message_info['content']

    def test_position_update_message(self, bot):
        """Should identify position update messages"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.POSITION_APP
        decoded.payload = b''

        message_info = bot._get_message_info(decoded, 0x11111111, 1234567890, 'radio1', '3.5', '-85')

        assert message_info is not None
        assert message_info['type'] == 'position_updates'
        assert 'Position update' in message_info['content']

    def test_node_info_message(self, bot):
        """Should identify node info messages"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.NODEINFO_APP
        decoded.payload = b''

        message_info = bot._get_message_info(decoded, 0x22222222, 1234567890, 'radio1', '4.0', '-75')

        assert message_info is not None
        assert message_info['type'] == 'node_info'
        assert 'Node info' in message_info['content']

    def test_telemetry_message(self, bot):
        """Should identify telemetry messages"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.TELEMETRY_APP
        decoded.payload = b''

        message_info = bot._get_message_info(decoded, 0x33333333, 1234567890, 'radio1', '6.0', '-70')

        assert message_info is not None
        assert message_info['type'] == 'telemetry'
        assert 'Telemetry' in message_info['content']

    def test_routing_message(self, bot):
        """Should identify routing messages"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.ROUTING_APP
        decoded.payload = b''

        message_info = bot._get_message_info(decoded, 0x44444444, 1234567890, 'radio1', '2.5', '-90')

        assert message_info is not None
        assert message_info['type'] == 'routing'
        assert 'Routing' in message_info['content']

    def test_admin_message(self, bot):
        """Should identify admin messages"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.ADMIN_APP
        decoded.payload = b''

        message_info = bot._get_message_info(decoded, 0x55555555, 1234567890, 'radio1', '5.5', '-72')

        assert message_info is not None
        assert message_info['type'] == 'admin'
        assert 'Admin' in message_info['content']

    def test_unknown_message_type(self, bot):
        """Should handle unknown message types"""
        decoded = Mock()
        decoded.portnum = 9999  # Unknown port number
        decoded.payload = b''

        message_info = bot._get_message_info(decoded, 0x66666666, 1234567890, 'radio1', '4.2', '-78')

        assert message_info is not None
        assert message_info['type'] == 'unknown'
        assert 'Unknown message' in message_info['content']
        assert '9999' in message_info['content']

    def test_signal_strength_included_when_enabled(self, bot):
        """Should include signal strength when enabled"""
        bot.show_signal_strength = True

        decoded = Mock()
        decoded.portnum = portnums_pb2.TEXT_MESSAGE_APP
        decoded.payload = b'Test'

        message_info = bot._get_message_info(decoded, 0x77777777, 1234567890, 'radio1', '7.5', '-65')

        assert 'SNR: 7.5' in message_info['content']
        assert 'RSSI: -65' in message_info['content']

    def test_signal_strength_excluded_when_disabled(self, bot):
        """Should exclude signal strength when disabled"""
        bot.show_signal_strength = False

        decoded = Mock()
        decoded.portnum = portnums_pb2.TEXT_MESSAGE_APP
        decoded.payload = b'Test'

        message_info = bot._get_message_info(decoded, 0x88888888, 1234567890, 'radio1', '5.0', '-80')

        assert 'SNR' not in message_info['content']
        assert 'RSSI' not in message_info['content']

    def test_empty_text_message_returns_none(self, bot):
        """Should return None for empty text messages"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.TEXT_MESSAGE_APP
        decoded.payload = b''

        message_info = bot._get_message_info(decoded, 0x99999999, 1234567890, 'radio1', '5.0', '-80')

        assert message_info is None

    def test_whitespace_only_text_message_returns_none(self, bot):
        """Should return None for whitespace-only text messages"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.TEXT_MESSAGE_APP
        decoded.payload = b'   \n\t  '

        message_info = bot._get_message_info(decoded, 0xAAAAAAAA, 1234567890, 'radio1', '5.0', '-80')

        assert message_info is None

    def test_discord_timestamp_format(self, bot):
        """Should format timestamps in Discord format"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.TEXT_MESSAGE_APP
        decoded.payload = b'Test'

        rx_time = 1234567890

        message_info = bot._get_message_info(decoded, 0xBBBBBBBB, rx_time, 'radio1', '5.0', '-80')

        # Discord timestamp format
        assert '<t:1234567890:t>' in message_info['content']

    def test_no_timestamp_shows_na(self, bot):
        """Should show N/A when timestamp is not available"""
        decoded = Mock()
        decoded.portnum = portnums_pb2.TEXT_MESSAGE_APP
        decoded.payload = b'Test'

        message_info = bot._get_message_info(decoded, 0xCCCCCCCC, 0, 'radio1', '5.0', '-80')

        assert 'N/A' in message_info['content']


@pytest.mark.unit
class TestDiscordMessageSending:
    """Test Discord message sending"""

    @pytest.mark.asyncio
    async def test_send_normal_message(self, bot):
        """Should send normal messages directly"""
        mock_channel = AsyncMock()
        bot.client.get_channel = Mock(return_value=mock_channel)

        message = "Test message"
        await bot._send_to_discord(message)

        mock_channel.send.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_long_message_chunks(self, bot):
        """Should chunk messages over 2000 characters"""
        mock_channel = AsyncMock()
        bot.client.get_channel = Mock(return_value=mock_channel)

        # Create message over 2000 chars
        long_message = "A" * 2500

        await bot._send_to_discord(long_message)

        # Should be called multiple times
        assert mock_channel.send.call_count > 1

        # Verify chunks don't exceed safe limit (1900)
        for call in mock_channel.send.call_args_list:
            chunk = call[0][0]
            assert len(chunk) <= 1900

    @pytest.mark.asyncio
    async def test_channel_not_found_error(self, bot, caplog):
        """Should log error when channel not found"""
        bot.client.get_channel = Mock(return_value=None)

        await bot._send_to_discord("Test message")

        # Check error was logged
        assert any("channel" in record.message.lower() and "not found" in record.message.lower()
                   for record in caplog.records)


@pytest.mark.unit
class TestPacketProcessing:
    """Test packet processing workflow"""

    @pytest.mark.asyncio
    async def test_duplicate_message_filtered(self, bot):
        """Should filter duplicate messages"""
        # Create mock packet
        packet = Mock()
        packet.id = 123
        setattr(packet, 'from', 0x11111111)
        packet.rx_time = 1234567890
        packet.rx_snr = 5.0
        packet.rx_rssi = -80

        # Create decoded data
        decoded = Mock()
        decoded.portnum = portnums_pb2.TEXT_MESSAGE_APP
        decoded.payload = b'Test message'
        packet.decoded = decoded

        # Mock Discord sending
        bot.client.get_channel = Mock(return_value=AsyncMock())

        # Process once
        await bot._process_mesh_packet(packet, 'radio1')

        # Message should be marked as processed
        assert bot._is_message_processed('11111111_123', 'radio1')

        # Process again
        mock_channel = AsyncMock()
        bot.client.get_channel = Mock(return_value=mock_channel)

        await bot._process_mesh_packet(packet, 'radio1')

        # Should not send again
        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_packet_without_decoded_ignored(self, bot):
        """Should ignore packets without decoded data"""
        packet = Mock()
        packet.id = 456
        setattr(packet, 'from', 0x22222222)
        packet.rx_time = 1234567890
        packet.decoded = None

        mock_channel = AsyncMock()
        bot.client.get_channel = Mock(return_value=mock_channel)

        await bot._process_mesh_packet(packet, 'radio1')

        # Should not send anything
        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_filtered_message_type_not_sent(self, bot):
        """Should not send messages of filtered types"""
        bot.message_filters['routing'] = False

        packet = Mock()
        packet.id = 789
        setattr(packet, 'from', 0x33333333)
        packet.rx_time = 1234567890
        packet.rx_snr = 4.0
        packet.rx_rssi = -85

        decoded = Mock()
        decoded.portnum = portnums_pb2.ROUTING_APP
        decoded.payload = b''
        packet.decoded = decoded

        mock_channel = AsyncMock()
        bot.client.get_channel = Mock(return_value=mock_channel)

        await bot._process_mesh_packet(packet, 'radio1')

        # Should not send
        mock_channel.send.assert_not_called()

        # But should still mark as processed
        assert bot._is_message_processed('33333333_789', 'radio1')


@pytest.mark.unit
class TestNodeInfoExtraction:
    """Test node info extraction from packets"""

    @pytest.mark.asyncio
    async def test_node_info_updates_database(self, bot):
        """Should update node database from NODEINFO_APP packets"""
        packet = Mock()
        packet.id = 999
        setattr(packet, 'from', 0x44444444)
        packet.rx_time = 1234567890
        packet.rx_snr = 5.0
        packet.rx_rssi = -75

        # Create user info protobuf
        user_info = mesh_pb2.User()
        user_info.short_name = 'TST'
        user_info.long_name = 'Test Node'

        decoded = Mock()
        decoded.portnum = portnums_pb2.NODEINFO_APP
        decoded.payload = user_info.SerializeToString()
        packet.decoded = decoded

        # Mock Discord sending
        bot.client.get_channel = Mock(return_value=AsyncMock())

        await bot._process_mesh_packet(packet, 'radio1')

        # Check node was updated
        node_name = bot._get_node_name(0x44444444)
        assert 'TST' in node_name
