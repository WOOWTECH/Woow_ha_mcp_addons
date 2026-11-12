"""Real SDK 2 client against the owned gateway (called only by the focused test)."""
import asyncio
import json
import os

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult


async def main():
    async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + os.environ['WOOW_TOKEN']}) as http:
        async with Client(streamable_http_client(os.environ['WOOW_URL'], http_client=http)) as client:
            listed = await client.list_tools()
            schemas = {t.name: t.output_schema for t in listed.tools if t.output_schema is not None}
            results=[]
            for name,args,expect_error in json.loads(os.environ['WOOW_CALLS']):
                result=await client.call_tool(name,args)
                assert result.is_error == expect_error, result
                if not expect_error:
                    assert name in schemas and isinstance(result.structured_content,dict)
                    # Prove client validation is active, not just an unexamined list.
                    try:
                        await client.session.validate_tool_result(name,CallToolResult(content=[]))
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError('missing structured content was accepted')
                results.append({'name':name,'error':result.is_error,'structured':result.structured_content})
            print(json.dumps({'schemas':schemas,'results':results,'protocol':client.protocol_version}))

asyncio.run(main())
