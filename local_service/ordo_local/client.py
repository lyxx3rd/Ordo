"""Mode 3: label directly through an independently managed vLLM endpoint."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx

from .core import ServiceError, artifacts, label_response_format, messages, parse_labels, units


def text_rows(text):
    text = text.removeprefix('\ufeff')
    if len(text.encode('utf-8')) > 2 * 1024 * 1024 or len(text.splitlines()) > 20000:
        raise ServiceError(413, 'input_too_large', 'Limit: 2 MiB UTF-8 / 20,000 physical lines.')
    if any(ord(c) < 32 and c not in '\t\r\n' for c in text):
        raise ServiceError(415, 'invalid_text', 'Plain text only; binary control characters are unsupported.')
    rows = units(text)
    if not rows:
        raise ServiceError(400, 'empty_text', 'No nonempty input lines.')
    return rows


def result_for(rows, labels, model, start, formats):
    formats = list(formats)
    if not formats or len(set(formats)) != len(formats) or not set(formats) <= {'json', 'txt', 'md'}:
        raise ValueError('formats must be a nonempty, distinct subset of json/txt/md')
    output = [dict(r, label=labels[r['line_id']]) for r in rows]
    return {'request_id':uuid4().hex, 'files':artifacts(output,formats),
            'meta':{'model':model, 'nonempty_lines':len(rows), 'windows':(len(rows)+17)//18,
                    'elapsed_seconds':round(time.perf_counter()-start,3)}}


def save_result(result, output):
    output = Path(output)
    names = [f['filename'] for f in result['files']] + ['run.json']
    if any((output / n).exists() for n in names):
        raise FileExistsError('Output files already exist. Choose a new output directory.')
    output.mkdir(parents=True,exist_ok=True)
    for item in result['files']:
        (output / item['filename']).write_text(item['content'],encoding='utf-8')
    (output/'run.json').write_text(json.dumps({'request_id':result['request_id'],'meta':result['meta']},indent=2)+'\n')


class RemoteLabeler:
    def __init__(self, base_url='http://127.0.0.1:8010/v1', model='ordo-final-2b', concurrency=16,
                 retries=2, timeout=120, transport=None):
        if not 1 <= concurrency <= 64 or not 0 <= retries <= 5:
            raise ValueError('Invalid concurrency/retry limit')
        self.url, self.model = base_url.rstrip('/'), model
        self.concurrency, self.retries = concurrency, retries
        token = os.environ.get('ORDO_MODEL_API_KEY')
        self.client = httpx.AsyncClient(timeout=timeout, trust_env=False, transport=transport,
            headers={'Authorization':'Bearer '+token} if token else {},
            limits=httpx.Limits(max_connections=concurrency+1))
        self.slots = asyncio.Semaphore(concurrency)

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self.client.__aexit__(*args)

    async def label_text(self, text, formats=('json','txt','md')):
        start = time.perf_counter();rows = text_rows(text)
        response = await self.client.get(self.url+'/models')
        response.raise_for_status()
        if not any(m.get('id')==self.model for m in response.json()['data']):
            raise ServiceError(503,'model_unavailable','Requested model is not registered.')

        async def call(offset):
            ids = [r['line_id'] for r in rows[offset:offset+18]]
            payload = {'model':self.model,'messages':messages(rows,offset),'temperature':0,'max_tokens':512,
                       'chat_template_kwargs':{'enable_thinking':False}}
            for attempt in range(self.retries+1):
                try:
                    async with self.slots:
                        r = await self.client.post(self.url+'/chat/completions',json=payload)
                        r.raise_for_status()
                        choice = r.json()['choices'][0]
                        if choice.get('finish_reason')=='length':
                            raise ServiceError(502,'invalid_model_output','Output token limit reached.')
                        return parse_labels(choice['message']['content'],ids)
                except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError,ServiceError) as exc:
                    if attempt == self.retries:
                        raise
                    if isinstance(exc,ServiceError) and exc.code=='invalid_model_output':
                        payload['response_format'] = label_response_format(ids)
                    await asyncio.sleep(min(2**attempt,4))

        labels = {};offsets = iter(range(0,len(rows),18))
        async def worker():
            for offset in offsets:
                labels.update(await call(offset))
        tasks=[asyncio.create_task(worker()) for _ in range(min(self.concurrency,(len(rows)+17)//18))]
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                if not t.done():t.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
        return result_for(rows,labels,self.model,start,formats)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',type=Path);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--base-url',default='http://127.0.0.1:8010/v1')
    ap.add_argument('--model',default='ordo-final-2b');ap.add_argument('--concurrency',type=int,default=16)
    ap.add_argument('--format',nargs='+',choices=['json','txt','md'],default=['json','txt','md'])
    args=ap.parse_args()
    async def run():
        async with RemoteLabeler(args.base_url,args.model,args.concurrency) as client:
            result=await client.label_text(args.input.read_text(encoding='utf-8-sig'),args.format)
        save_result(result,args.output)
        print(json.dumps(result['meta'],ensure_ascii=False))
    asyncio.run(run())

if __name__=='__main__':main()
