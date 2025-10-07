"""Tests for database operations"""
import pytest
import os
import tempfile
import shutil
import sqlite3
from datetime import datetime
from unittest.mock import patch, Mock


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
        # Cleanup
        if bot.conn:
            bot.conn.close()


@pytest.mark.unit
class TestDatabaseInitialization:
    """Test database initialization"""

    def test_database_created(self, bot):
        """Should create database file and tables"""
        import os
        assert os.path.exists('data/message_tracking.db')

        cursor = bot.conn.cursor()

        # Check tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        assert 'processed_messages' in tables
        assert 'nodes' in tables
        assert 'radios' in tables

    def test_processed_messages_table_schema(self, bot):
        """Should have correct schema for processed_messages table"""
        cursor = bot.conn.cursor()
        cursor.execute("PRAGMA table_info(processed_messages)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert 'message_id' in columns
        assert 'source' in columns
        assert 'timestamp' in columns
        assert 'processed_at' in columns

    def test_nodes_table_schema(self, bot):
        """Should have correct schema for nodes table"""
        cursor = bot.conn.cursor()
        cursor.execute("PRAGMA table_info(nodes)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert 'node_id' in columns
        assert 'short_name' in columns
        assert 'long_name' in columns
        assert 'last_seen' in columns

    def test_radios_table_schema(self, bot):
        """Should have correct schema for radios table"""
        cursor = bot.conn.cursor()
        cursor.execute("PRAGMA table_info(radios)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert 'source_name' in columns
        assert 'node_id' in columns
        assert 'short_name' in columns
        assert 'long_name' in columns
        assert 'last_updated' in columns


@pytest.mark.unit
class TestMessageTracking:
    """Test message processing tracking"""

    def test_message_not_processed_initially(self, bot):
        """New message should not be marked as processed"""
        is_processed = bot._is_message_processed('test_msg_123', 'radio1')
        assert is_processed is False

    def test_mark_message_processed(self, bot):
        """Should mark message as processed"""
        message_id = 'test_msg_456'
        source = 'radio1'
        timestamp = int(datetime.now().timestamp())

        bot._mark_message_processed(message_id, source, timestamp)

        is_processed = bot._is_message_processed(message_id, source)
        assert is_processed is True

    def test_different_sources_tracked_separately(self, bot):
        """Same message ID from different sources should be tracked separately"""
        message_id = 'test_msg_789'
        timestamp = int(datetime.now().timestamp())

        bot._mark_message_processed(message_id, 'radio1', timestamp)

        # Should be processed from radio1
        assert bot._is_message_processed(message_id, 'radio1') is True

        # Should NOT be processed from radio2
        assert bot._is_message_processed(message_id, 'radio2') is False

        # Mark from radio2
        bot._mark_message_processed(message_id, 'radio2', timestamp)

        # Now should be processed from radio2
        assert bot._is_message_processed(message_id, 'radio2') is True

    def test_message_data_persisted(self, bot):
        """Message tracking data should be persisted in database"""
        message_id = 'test_persist_123'
        source = 'radio1'
        timestamp = 1234567890

        bot._mark_message_processed(message_id, source, timestamp)

        # Query database directly
        cursor = bot.conn.cursor()
        cursor.execute(
            'SELECT message_id, source, timestamp FROM processed_messages WHERE message_id = ? AND source = ?',
            (message_id, source)
        )
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == message_id
        assert result[1] == source
        assert result[2] == timestamp


@pytest.mark.unit
class TestNodeDatabase:
    """Test node information storage"""

    def test_node_name_fallback_to_id(self, bot):
        """Should return hex ID when node not in database"""
        node_id = 0x12345678
        name = bot._get_node_name(node_id)

        assert name == '12345678'

    def test_update_and_retrieve_node_info(self, bot):
        """Should store and retrieve node information"""
        node_id = 0xABCDEF01

        # Create mock user info
        user_info = Mock()
        user_info.short_name = 'TST1'
        user_info.long_name = 'Test Node 1'

        bot._update_node_info(node_id, user_info)

        # Retrieve node name
        name = bot._get_node_name(node_id)

        assert 'TST1' in name
        assert 'abcdef01' in name.lower()

    def test_node_short_name_preferred(self, bot):
        """Should prefer short name over long name"""
        node_id = 0x11223344

        user_info = Mock()
        user_info.short_name = 'SHT'
        user_info.long_name = 'Very Long Name Here'

        bot._update_node_info(node_id, user_info)

        name = bot._get_node_name(node_id)

        assert 'SHT' in name
        assert 'Very Long Name Here' not in name

    def test_node_long_name_when_no_short_name(self, bot):
        """Should use long name when short name is empty"""
        node_id = 0x55667788

        user_info = Mock()
        user_info.short_name = ''
        user_info.long_name = 'LongName'

        bot._update_node_info(node_id, user_info)

        name = bot._get_node_name(node_id)

        assert 'LongName' in name

    def test_node_info_update_timestamp(self, bot):
        """Should update last_seen timestamp"""
        node_id = 0x99887766

        user_info = Mock()
        user_info.short_name = 'TST'
        user_info.long_name = 'Test'

        before_time = int(datetime.now().timestamp())
        bot._update_node_info(node_id, user_info)
        after_time = int(datetime.now().timestamp())

        # Query database
        cursor = bot.conn.cursor()
        cursor.execute('SELECT last_seen FROM nodes WHERE node_id = ?', (node_id,))
        result = cursor.fetchone()

        assert result is not None
        last_seen = result[0]
        assert before_time <= last_seen <= after_time


@pytest.mark.unit
class TestRadioDatabase:
    """Test radio information storage"""

    def test_radio_info_fallback(self, bot):
        """Should return source name when radio not in database"""
        info = bot._get_radio_info('unknown_radio')
        assert 'unknown_radio' in info

    def test_update_and_retrieve_radio_info(self, bot):
        """Should store and retrieve radio information"""
        source = 'test_radio'
        node_id = 0xAABBCCDD

        # Add radio to config
        bot.radios.append({
            'name': source,
            'host': 'test.local',
            'port': '80',
            'display_name': 'Test Radio'
        })

        # Create mock my_info
        my_info = Mock()
        my_info.my_node_num = node_id

        bot._update_radio_info(source, my_info)

        # Retrieve radio info
        info = bot._get_radio_info(source)

        assert 'Test Radio' in info
        assert 'aabbccdd' in info.lower()

    def test_radio_uses_display_name(self, bot):
        """Should use display_name from config"""
        source = 'radio_xyz'

        bot.radios.append({
            'name': source,
            'host': 'xyz.local',
            'port': '80',
            'display_name': 'My Custom Radio'
        })

        my_info = Mock()
        my_info.my_node_num = 0x12345678

        bot._update_radio_info(source, my_info)

        info = bot._get_radio_info(source)

        assert 'My Custom Radio' in info


@pytest.mark.unit
class TestMessageFiltering:
    """Test message type filtering"""

    def test_should_process_enabled_types(self, bot):
        """Should process message types that are enabled"""
        bot.message_filters['text_messages'] = True
        bot.message_filters['telemetry'] = True

        assert bot._should_process_message_type('text_messages') is True
        assert bot._should_process_message_type('telemetry') is True

    def test_should_not_process_disabled_types(self, bot):
        """Should not process message types that are disabled"""
        bot.message_filters['routing'] = False
        bot.message_filters['unknown'] = False

        assert bot._should_process_message_type('routing') is False
        assert bot._should_process_message_type('unknown') is False

    def test_should_handle_unknown_types(self, bot):
        """Should return False for unknown message types"""
        result = bot._should_process_message_type('nonexistent_type')
        assert result is False
