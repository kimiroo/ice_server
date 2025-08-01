import asyncio

def run_async_in_eventlet(awaitable):
    """
    Helper function to run an asyncio awaitable in an eventlet green thread.
    This bypasses the problematic eventlet.asyncio module.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(awaitable)
    finally:
        loop.close()
        asyncio.set_event_loop(None)