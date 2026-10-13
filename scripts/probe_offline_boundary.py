"""Inspect a Linux process network namespace; run via unshare -Urn, never host-wide."""
import json
import socket
import sys
from pathlib import Path


def probe():
    interfaces=sorted(name for _,name in socket.if_nameindex())
    if interfaces!=['lo']:
        raise RuntimeError('Expected an isolated loopback-only namespace')
    server=socket.socket()
    server.bind(('127.0.0.1',0));server.listen(1)
    client=socket.socket();client.settimeout(2)
    client.connect(('127.0.0.1',server.getsockname()[1]))
    accepted,_=server.accept();accepted.close();client.close();server.close()
    outbound=socket.socket();outbound.settimeout(2)
    try:outbound.connect(('1.1.1.1',443));external='connected'
    except OSError as error:external=f'{type(error).__name__}:{error.errno}'
    finally:outbound.close()
    if external=='connected':raise RuntimeError('External route unexpectedly available')
    try:socket.getaddrinfo('example.com',443);dns='resolved'
    except OSError as error:dns=f'{type(error).__name__}:{error.errno}'
    if dns=='resolved':raise RuntimeError('External DNS unexpectedly available')
    return {'boundary':'Linux user+network namespace; process scope', 'interfaces':interfaces,
            'loopback':'connected','external_tcp':external,'external_dns':dns,
            'offline_boundary_passed':True,'host_network_modified':False,
            'scope':'Network boundary only; does not prove application cold start or absence of attempted telemetry'}


if __name__=='__main__':
    result=probe();Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
