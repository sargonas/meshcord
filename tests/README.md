# Meshcord Tests

This directory contains the test suite for Meshcord.

## Test Structure

The tests are organized into focused modules:

- **test_config.py** - Configuration parsing and validation
- **test_database.py** - Database operations and data persistence
- **test_message_processing.py** - Message extraction and processing logic

## Running Tests

### Run all unit tests:
```bash
pytest tests/ -v -m unit
```

### Run all tests:
```bash
pytest tests/ -v
```

### Run specific test file:
```bash
pytest tests/test_config.py -v
```

### Run specific test class:
```bash
pytest tests/test_config.py::TestConfigurationValidation -v
```

### Run specific test:
```bash
pytest tests/test_config.py::TestConfigurationValidation::test_missing_discord_token -v
```

## Test Philosophy

These tests follow a pragmatic approach:

1. **Test behavior, not implementation** - Tests focus on what the code does, not how it does it
2. **Minimal mocking** - Use real SQLite databases, real data structures where possible
3. **Fast and reliable** - Unit tests run quickly without external dependencies
4. **Clear test names** - Test names describe what they're testing

## Test Markers

- `@pytest.mark.unit` - Fast tests with no external dependencies (always run in CI)
- `@pytest.mark.integration` - Tests requiring real Discord/Meshtastic connections (optional)
- `@pytest.mark.slow` - Tests that take longer to run

## What We Test

### Configuration (`test_config.py`)
- Environment variable validation
- Radio configuration parsing (single and multiple)
- Message filter configuration
- Connection method settings

### Database (`test_database.py`)
- Database initialization and schema
- Message deduplication tracking
- Node information storage and retrieval
- Radio information storage
- Message type filtering

### Message Processing (`test_message_processing.py`)
- Message info extraction for all message types
- Text message content parsing
- Signal strength display (enabled/disabled)
- Discord message formatting
- Long message chunking
- Duplicate message filtering
- Node info extraction from packets

## What We Don't Test

- Actual Discord API calls (requires real bot token)
- Actual Meshtastic radio communication (requires real hardware)
- Serial connection management (hardware dependent)
- HTTP connection management (requires running radio)
- Async task orchestration (too complex, covered by manual testing)

These aspects are covered by:
1. Manual testing with real hardware
2. Integration tests (when credentials available)
3. Production monitoring

## Adding New Tests

When adding new tests:

1. Add the test to the appropriate file (or create a new one)
2. Mark it with `@pytest.mark.unit` if it's a fast unit test
3. Use fixtures for common setup (see existing fixtures)
4. Focus on testing public API behavior
5. Keep tests simple and readable

## Dependencies

Test dependencies are in `requirements-test.txt`:
- pytest - Test framework
- pytest-asyncio - Async test support
