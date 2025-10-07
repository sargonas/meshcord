# Testing Guide for Meshcord

## Overview

This document explains the new testing approach for Meshcord after the test suite overhaul.

## What Changed

### Old Approach (Removed)
- Heavy mocking of Discord and Meshtastic libraries
- Mock import hacks using `sys.modules`
- Integration tests with mock HTTP servers
- 1200+ lines of complex test code
- Frequent test failures despite working app
- Coverage-focused testing

### New Approach (Current)
- **Pragmatic testing** - Test what matters, not implementation details
- **Minimal mocking** - Use real SQLite databases, real data structures
- **Fast unit tests** - 54 tests run in ~2 seconds
- **Focused coverage** - Test business logic, not framework integration
- **Maintainable** - Simple tests that won't break on refactors

## Test Structure

```
tests/
├── __init__.py
├── README.md                    # Detailed test documentation
├── test_config.py              # Configuration parsing (15 tests)
├── test_database.py            # Database operations (19 tests)
└── test_message_processing.py  # Message logic (20 tests)
```

## Running Tests

### Quick Start
```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Run all unit tests
pytest tests/ -v -m unit
```

### Common Commands
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_config.py -v

# Run specific test
pytest tests/test_config.py::TestConfigurationValidation::test_missing_discord_token -v

# Run with minimal output
pytest tests/ -q

# Run with coverage (optional)
pytest tests/ --cov=meshcord_bot --cov-report=term-missing
```

## What We Test

### ✅ Configuration (`test_config.py`)
- Environment variable validation
- Radio configuration parsing (single/multiple)
- Message filter configuration
- Connection settings
- **Why:** Configuration bugs cause immediate failures

### ✅ Database (`test_database.py`)
- Database initialization and schema
- Message deduplication
- Node information storage/retrieval
- Radio information storage
- **Why:** Data integrity is critical for message handling

### ✅ Message Processing (`test_message_processing.py`)
- Message type extraction
- Text message parsing
- Signal strength display
- Discord formatting
- Message chunking (2000 char limit)
- Duplicate filtering
- **Why:** Core business logic that must work correctly

## What We Don't Test

### ❌ Discord API Integration
**Why:** Requires real bot token, tested manually

### ❌ Meshtastic Radio Communication
**Why:** Requires real hardware, tested manually

### ❌ Serial Connection Management
**Why:** Hardware dependent, complex async patterns

### ❌ HTTP Connection Management
**Why:** Requires running radio, tested manually

### ❌ Async Task Orchestration
**Why:** Too complex to mock reliably, tested in production

**These are covered by:**
1. Manual testing with real hardware
2. Production monitoring
3. User reports

## Test Philosophy

### 1. Test Behavior, Not Implementation
❌ Bad:
```python
def test_internal_method():
    bot._internal_helper_function()  # Testing private method
```

✅ Good:
```python
def test_message_deduplication():
    bot.process_message(msg)
    bot.process_message(msg)  # Same message
    assert sent_once  # Test the outcome
```

### 2. Minimal Mocking
❌ Bad:
```python
with patch('sqlite3.connect') as mock_db:
    mock_cursor = Mock()
    # 20 lines of mock setup...
```

✅ Good:
```python
# Use real SQLite in-memory database
bot = MeshtasticDiscordBot()  # Uses real database
bot._mark_message_processed('msg_id', 'source', timestamp)
assert bot._is_message_processed('msg_id', 'source')
```

### 3. Fast and Focused
- Unit tests should run in seconds
- Each test should test one thing
- Clear test names that describe behavior

## CI/CD Integration

Tests run automatically on:
- Push to `main` or `develop`
- Pull requests to `main`

See `.github/workflows/ci.yml`:
```yaml
- name: Run unit tests
  run: |
    pytest tests/ -v -m unit
```

## Test Markers

```python
@pytest.mark.unit          # Fast tests, no external deps (run in CI)
@pytest.mark.integration   # Tests requiring real credentials (optional)
@pytest.mark.slow          # Long-running tests (optional)
```

## Adding New Tests

When adding a feature:

1. **Determine what to test:**
   - Does it involve parsing/validation? → `test_config.py`
   - Does it involve data storage? → `test_database.py`
   - Does it involve message processing? → `test_message_processing.py`

2. **Write a focused test:**
   ```python
   @pytest.mark.unit
   def test_new_feature(bot):
       """Should do X when Y happens"""
       # Setup
       input_data = create_test_data()

       # Execute
       result = bot.new_feature(input_data)

       # Assert
       assert result == expected_output
   ```

3. **Use existing fixtures:**
   - `clean_env` - Cleans environment variables
   - `test_env` - Provides valid test environment
   - `temp_dir` - Provides temporary directory
   - `bot` - Provides initialized bot instance

4. **Keep it simple:**
   - One assertion per test (mostly)
   - Clear test names
   - Minimal setup

## Troubleshooting

### Tests fail but app works
This was the old problem! New tests avoid this by testing behavior, not implementation.

### Import errors
```bash
# Make sure all dependencies are installed
pip install -r requirements.txt
pip install -r requirements-test.txt
```

### Database errors
Tests use temporary directories and in-memory databases. If you see database errors, check that:
- Tests clean up after themselves (use fixtures)
- No leftover `data/` directories from previous runs

### Async test issues
Make sure tests are marked with `@pytest.mark.asyncio`:
```python
@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result
```

## Test Coverage

Current coverage (54 tests):
- **Configuration:** 15 tests
- **Database:** 19 tests
- **Message Processing:** 20 tests

**Note:** We prioritize meaningful tests over coverage percentage. 100% coverage with brittle tests is worse than 70% coverage with reliable tests.

## Migration from Old Tests

If you're looking at the old tests (commit `9cf16d0^`):

| Old Approach | New Approach |
|--------------|--------------|
| Mock entire Discord/Meshtastic | Test business logic only |
| sys.modules hacks | Import normally |
| Mock HTTP servers | Test data processing |
| 477 lines (unit) + 674 lines (integration) | 300 lines total |
| Brittle, frequently broken | Stable, maintainable |

## Questions?

See `tests/README.md` for more detailed documentation.
