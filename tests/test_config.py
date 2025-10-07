"""Tests for configuration parsing and validation"""
import pytest
import os
import json
import tempfile
import shutil
from unittest.mock import patch, Mock


@pytest.fixture
def clean_env():
    """Fixture to clean up environment variables after tests"""
    original_env = dict(os.environ)
    yield
    # Restore original environment
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


@pytest.mark.unit
class TestConfigurationValidation:
    """Test configuration validation"""

    def test_missing_discord_token(self, clean_env, temp_dir):
        """Should raise error when DISCORD_BOT_TOKEN is missing"""
        os.environ['DISCORD_CHANNEL_ID'] = '123456'

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            with pytest.raises(ValueError, match="DISCORD_BOT_TOKEN is required"):
                MeshtasticDiscordBot()

    def test_missing_channel_id(self, clean_env, temp_dir):
        """Should raise error when DISCORD_CHANNEL_ID is missing"""
        os.environ['DISCORD_BOT_TOKEN'] = 'test_token'

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            with pytest.raises(ValueError, match="DISCORD_CHANNEL_ID is required"):
                MeshtasticDiscordBot()

    def test_invalid_channel_id(self, clean_env, temp_dir):
        """Should raise error when DISCORD_CHANNEL_ID is not a valid integer"""
        os.environ.update({
            'DISCORD_BOT_TOKEN': 'test_token',
            'DISCORD_CHANNEL_ID': 'not_a_number'
        })

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            with pytest.raises(ValueError, match="DISCORD_CHANNEL_ID must be a valid integer"):
                MeshtasticDiscordBot()

    def test_valid_configuration(self, test_env, temp_dir):
        """Should initialize successfully with valid configuration"""
        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()

            assert bot.discord_token == 'test_token_123'
            assert bot.channel_id == 123456789
            assert bot.connection_method == 'serial'


@pytest.mark.unit
class TestRadioConfiguration:
    """Test radio configuration parsing"""

    def test_single_radio_fallback(self, test_env, temp_dir):
        """Should create single radio from environment variables"""
        os.environ.update({
            'MESHTASTIC_HOST': 'radio1.local',
            'MESHTASTIC_PORT': '8080',
            'RADIO_NAME': 'TestRadio'
        })

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()

            assert len(bot.radios) == 1
            assert bot.radios[0]['name'] == 'TestRadio'
            assert bot.radios[0]['host'] == 'radio1.local'
            assert bot.radios[0]['port'] == '8080'

    def test_single_radio_with_display_name(self, test_env, temp_dir):
        """Should include display name if configured"""
        os.environ.update({
            'MESHTASTIC_HOST': 'radio1.local',
            'RADIO_NAME': 'radio1',
            'RADIO_DISPLAY_NAME': 'My Radio'
        })

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()

            assert bot.radios[0]['display_name'] == 'My Radio'

    def test_multiple_radios_json(self, test_env, temp_dir):
        """Should parse multiple radios from JSON"""
        radios_json = json.dumps([
            {"name": "radio1", "host": "host1.local", "port": "80", "display_name": "Radio 1"},
            {"name": "radio2", "host": "host2.local", "port": "8080"}
        ])
        os.environ['RADIOS'] = radios_json

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()

            assert len(bot.radios) == 2
            assert bot.radios[0]['name'] == 'radio1'
            assert bot.radios[0]['display_name'] == 'Radio 1'
            assert bot.radios[1]['name'] == 'radio2'
            assert bot.radios[1]['host'] == 'host2.local'

    def test_invalid_radios_json_fallback(self, test_env, temp_dir):
        """Should fallback to single radio on invalid JSON"""
        os.environ['RADIOS'] = '{invalid json'
        os.environ['RADIO_NAME'] = 'FallbackRadio'

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()

            # Should fall back to single radio
            assert len(bot.radios) == 1
            assert bot.radios[0]['name'] == 'FallbackRadio'


@pytest.mark.unit
class TestMessageFilters:
    """Test message filtering configuration"""

    def test_default_filters(self, test_env, temp_dir):
        """Should use correct defaults for message filters"""
        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()

            # Check defaults
            assert bot.message_filters['text_messages'] is True
            assert bot.message_filters['position_updates'] is True
            assert bot.message_filters['node_info'] is True
            assert bot.message_filters['telemetry'] is True
            assert bot.message_filters['routing'] is False
            assert bot.message_filters['admin'] is True
            assert bot.message_filters['unknown'] is False

    def test_custom_filters(self, test_env, temp_dir):
        """Should parse custom filter settings from environment"""
        os.environ.update({
            'SHOW_TEXT_MESSAGES': 'false',
            'SHOW_ROUTING': 'true',
            'SHOW_POSITION_UPDATES': '0',
            'SHOW_TELEMETRY': '1'
        })

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()

            assert bot.message_filters['text_messages'] is False
            assert bot.message_filters['routing'] is True
            assert bot.message_filters['position_updates'] is False
            assert bot.message_filters['telemetry'] is True


@pytest.mark.unit
class TestOtherConfiguration:
    """Test other configuration options"""

    def test_serial_timeout_default(self, test_env, temp_dir):
        """Should use default serial timeout"""
        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()

            assert bot.serial_timeout == 240  # 4 minutes default

    def test_serial_timeout_custom(self, test_env, temp_dir):
        """Should parse custom serial timeout"""
        os.environ['SERIAL_TIMEOUT'] = '300'

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()

            assert bot.serial_timeout == 300

    def test_signal_strength_display(self, test_env, temp_dir):
        """Should parse signal strength display setting"""
        # Test default (true)
        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()
            assert bot.show_signal_strength is True

        # Test explicit false
        os.environ['SHOW_SIGNAL_STRENGTH'] = 'false'
        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()
            assert bot.show_signal_strength is False

    def test_debug_mode(self, test_env, temp_dir):
        """Should parse debug mode setting"""
        # Test default (false)
        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()
            assert bot.debug_mode is False

        # Test enabled
        os.environ['DEBUG_MODE'] = 'true'
        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()
            assert bot.debug_mode is True

    def test_connection_method_default(self, test_env, temp_dir):
        """Should default to http connection method"""
        os.environ.pop('CONNECTION_METHOD', None)

        with patch('meshcord_bot.discord.Client'):
            from meshcord_bot import MeshtasticDiscordBot
            bot = MeshtasticDiscordBot()
            assert bot.connection_method == 'http'
