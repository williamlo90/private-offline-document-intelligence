"""Summarize connect(2) destinations from an owned strace run."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

root=Path(__file__).resolve().parents[1]
trace=Path(sys.argv[1]) if len(sys.argv)>1 else root/'local/phase-5/offline-connect.log'
data=trace.read_bytes();lines=data.decode(errors='replace').splitlines()
calls=[line for line in lines if 'connect(' in line or 'sendto(' in line]
ipv4=Counter();ipv6=Counter();unix=0;netlink=0;unparsed=[]
for line in calls:
    if 'sa_family=AF_UNIX' in line:unix+=1;continue
    if 'sa_family=AF_NETLINK' in line:netlink+=1;continue
    if 'sa_family=AF_INET6' in line:
        match=re.search(r'inet_pton\(AF_INET6, "([^"]+)"\)',line)
        if match:ipv6[match.group(1)]+=1
        else:unparsed.append(line[:200])
    elif 'sa_family=AF_INET' in line:
        match=re.search(r'inet_addr\("([^"]+)"\)',line)
        if match:ipv4[match.group(1)]+=1
        else:unparsed.append(line[:200])
    elif 'sendto(' in line and ('NULL, 0)' in line or 'NULL, 0,' in line):
        # A send on an already connected socket has no new destination.
        continue
    else:unparsed.append(line[:200])
external={address:count for address,count in ipv4.items() if not address.startswith('127.')}
external.update({address:count for address,count in ipv6.items() if address!='::1'})
report={'status':'passed' if calls and not external and not unparsed else 'failed',
        'trace_sha256':hashlib.sha256(data).hexdigest(),'observed_syscalls':len(calls),
        'ipv4_destinations':dict(ipv4),'ipv6_destinations':dict(ipv6),'unix_calls':unix,'netlink_calls':netlink,
        'external_destinations':external,'unparsed_calls':len(unparsed),
        'scope':'connect(2) and sendto(2) destinations from one native assistant run and descendants; other runs/full stack excluded'}
output=Path(sys.argv[2]) if len(sys.argv)>2 else root/'local/phase-5/offline-connect-audit.json'
output.write_text(json.dumps(report,indent=2)+'\n')
if report['status']!='passed':raise RuntimeError('External or unparsed connect attempt')
print(json.dumps(report))
