import pytest_asyncio  # noqa: F401  (registers the pytest-asyncio plugin)

# Enable asyncio mode for the whole suite
def pytest_collection_modifyitems(config, items):
    for item in items:
        if "asyncio" in item.keywords:
            continue
