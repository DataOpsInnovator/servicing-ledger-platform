"""Bounded synthetic write load against an explicitly approved nonproduction API."""
import argparse
import concurrent.futures
import json
import math
import os
import time
import uuid
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlparse


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urlopen(request, timeout):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


def run(base, token, count, workers, max_p95_ms=None):
    run_id = uuid.uuid4().hex[:16].upper()
    def send(i):
        body = {'loan_ref':'SYN-LOAD-'+run_id,'amount_cents':100+i,'currency':'USD','effective_date':'2026-01-01'}
        request = Request(base.rstrip('/')+'/v1/servicing-entries',data=json.dumps(body).encode(),
                          headers={'Authorization':'Bearer '+token,'Idempotency-Key':f'load-{run_id}-{i}','Content-Type':'application/json'})
        start = time.perf_counter()
        try:
            with urlopen(request,timeout=15) as res:
                status = res.status
                res.read()
        except HTTPError as exc:
            status = exc.code
            exc.close()
        except OSError:
            status = 0
        return status, (time.perf_counter()-start)*1000
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(send,range(count)))
    elapsed = time.perf_counter()-start
    latencies = sorted(x[1] for x in results)
    p95 = latencies[math.ceil(.95*len(latencies))-1]
    report = {'synthetic_entries_requested':count,'concurrency':workers,'created':sum(s==201 for s,_ in results),
              'elapsed_seconds':round(elapsed,3),'requests_per_second':round(count/elapsed,2),
              'p50_ms':round(latencies[math.ceil(.5*len(latencies))-1],2),'p95_ms':round(p95,2),
              'p99_ms':round(latencies[math.ceil(.99*len(latencies))-1],2)}
    print(json.dumps(report,indent=2))
    if report['created'] != count or (max_p95_ms is not None and p95 > max_p95_ms):
        raise RuntimeError('Load test failed acceptance threshold')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8080')
    parser.add_argument('--requests',type=int,default=200)
    parser.add_argument('--concurrency',type=int,default=8)
    parser.add_argument('--max-p95-ms',type=float)
    parser.add_argument('--allow-nonlocal-synthetic',action='store_true')
    args=parser.parse_args()
    parsed=urlparse(args.base_url)
    if not (parsed.hostname in ('127.0.0.1','localhost','::1') or (parsed.scheme=='https' and args.allow_nonlocal_synthetic)):
        parser.error('Only local endpoints by default; explicit synthetic staging approval required for HTTPS remote endpoints')
    if not (1<=args.requests<=10000 and 1<=args.concurrency<=64):
        parser.error('Bound requests to 1–10000 and concurrency to 1–64')
    token=os.environ.get('LEDGER_TEST_WRITER_TOKEN') or os.environ.get('SERVICING_WRITER_TOKEN')
    if not token:
        parser.error('Set LEDGER_TEST_WRITER_TOKEN or SERVICING_WRITER_TOKEN')
    run(args.base_url,token,args.requests,args.concurrency,args.max_p95_ms)


if __name__=='__main__':
    main()
