"""Synthetic staging acceptance: OIDC, API, queue consumption, reversal and reconciliation."""
import argparse
import json
import os
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.parse import urlparse


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urlopen(request, timeout):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True)
    p.add_argument('--confirm-synthetic-staging',action='store_true',required=True)
    args=p.parse_args()
    if urlparse(args.base_url).scheme!='https':
        p.error('Use approved HTTPS staging endpoint')
    writer,operator=os.environ['LEDGER_TEST_WRITER_TOKEN'],os.environ['LEDGER_TEST_OPERATOR_TOKEN']
    if writer==operator:
        p.error('Use distinct scoped access tokens')
    def call(path, token=None, payload=None, key=None):
        headers={'Authorization':'Bearer '+token} if token else {}
        if payload is not None:
            headers.update({'Content-Type':'application/json','Idempotency-Key':key})
        req=Request(args.base_url.rstrip('/')+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
        try:
            with urlopen(req,timeout=15) as res:
                return res.status,json.load(res)
        except HTTPError as exc:
            return exc.code,{}
    ref='SYN-CLOUD-'+uuid.uuid4().hex[:20].upper()
    key='smoke-'+uuid.uuid4().hex
    payload={'loan_ref':ref,'amount_cents':12500,'currency':'USD','effective_date':'2026-01-01'}
    path='/v1/servicing-entries'
    assert call(path,None,payload,key)[0]==401
    assert call(path,operator,payload,key)[0]==403
    status,entry=call(path,writer,payload,key)
    assert status==201
    status,replay=call(path,writer,payload,key)
    assert status==200 and replay['entry_id']==entry['entry_id']
    assert call(path,writer,{**payload,'amount_cents':1},key)[0]==409
    reverse_path=path+'/'+entry['entry_id']+'/reversal'
    assert call(reverse_path,writer,{'reversal_reason':'DUPLICATE','effective_date':payload['effective_date']},key+'-r')[0]==403
    status,rev=call(reverse_path,operator,{'reversal_reason':'DUPLICATE','effective_date':payload['effective_date']},key+'-r')
    assert status==201 and rev['reversal_of']==entry['entry_id']
    status,net=call('/v1/loans/'+ref+'/reconciliation',operator)
    assert status==200 and net['net_recorded_cents']==0
    # Require a quiescent isolated staging environment, not proof of per-event delivery.
    for _ in range(60):
        status,report=call('/v1/operations/reconciliation',operator)
        if status==200 and report['status']=='ok' and report['pending']==0 and report['awaiting_consumer']==0:
            print('PASS: staging HTTPS, OIDC roles, idempotency, reversal, net journal total and drained queue indicators')
            return
        time.sleep(5)
    raise SystemExit('FAIL: reconciliation did not reach clean drained state; inspect DLQ/outbox')


if __name__=='__main__':
    main()
