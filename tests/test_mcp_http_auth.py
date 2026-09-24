from asteria_researcher.mcp.client import MCPClientManager


def test_http_auth_headers_are_not_discarded_by_transport_detection():
    headers = {'Authorization': 'Bearer fixture-token', 'X-Client': 'test'}
    source = {'name': 'research', 'connection_url': 'https://mcp.consensus.app/mcp',
              'connection_headers': headers}
    config = MCPClientManager([source]).convert_configs_to_langchain_format()['research']
    assert config['transport'] == 'streamable_http'
    assert config['headers'] == headers


def test_http_token_uses_bearer_header_not_unsupported_client_argument():
    source = {'name': 'research', 'connection_url': 'https://mcp.consensus.app/mcp',
              'connection_token': 'fixture-token'}
    config = MCPClientManager([source]).convert_configs_to_langchain_format()['research']
    assert config['headers']['Authorization'] == 'Bearer fixture-token'
    assert 'token' not in config
