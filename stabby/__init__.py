import aiohttp

_http_client = None

async def get_http_client() -> aiohttp.ClientSession:
    global _http_client
    if _http_client is None:
        _http_client = aiohttp.ClientSession()
    return _http_client

async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.close()
