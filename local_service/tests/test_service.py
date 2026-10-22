import json
import asyncio
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ordo_local.app import create_app
from ordo_local.config import Settings
from ordo_local.core import artifacts, messages, parse_labels, ServiceError, units


class Tests(unittest.TestCase):
    def client(self, handler=None, **kwargs):
        def default(request):
            if request.url.path == '/v1/models':
                return httpx.Response(200, json={'data': [{'id': 'ordo-final-2b'}]})
            body = json.loads(request.content)
            self.assertEqual(body['temperature'], 0)
            self.assertFalse(body['chat_template_kwargs']['enable_thinking'])
            text = body['messages'][1]['content'].split('【当前 batch：需要标注】\n')[1].split('\n\n【下一 batch')[0]
            ids = re.findall(r'^\[(L\d+)\]', text, re.M)
            return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({k: 'TEXT' for k in ids})}, 'finish_reason': 'stop'}]})
        kwargs.setdefault('retries', 0)
        return TestClient(create_app(Settings(**kwargs), httpx.MockTransport(handler or default)))

    def test_health_and_ready(self):
        with self.client() as c:
            self.assertEqual(c.get('/health').status_code, 200)
            self.assertEqual(c.get('/ready').json()['status'], 'ready')

    def test_all_outputs_and_blank_line_ids(self):
        text = '  title  \r\n\r\n' + '很长的正文' * 100
        with self.client() as c:
            r = c.post('/v1/label', json={'text': text, 'format': ['json', 'txt', 'md']})
            self.assertEqual(r.status_code, 200, r.text)
            files = r.json()['files'];self.assertEqual(len(files), 3)
            rows = json.loads(files[0]['content'])
            self.assertEqual([r['line_id'] for r in rows], ['L0001', 'L0003'])
            self.assertEqual(rows[0]['text'], '  title  ')
            self.assertEqual(rows[1]['text'], text.splitlines()[2])
            self.assertIn(text.splitlines()[2], files[1]['content'])
            self.assertEqual(r.headers['x-request-id'], r.json()['request_id'])

    def test_multiple_windows(self):
        with self.client() as c:
            r = c.post('/v1/label', json={'text': '\n'.join(f'row{i}' for i in range(40))})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()['meta']['windows'], 3)
            self.assertEqual(len(json.loads(r.json()['files'][0]['content'])), 40)

    def test_file_bom(self):
        with self.client() as c:
            r = c.post('/v1/label/file', files={'file': ('sample.txt', b'\xef\xbb\xbfhello\n\nworld', 'text/plain')},
                       data={'format': '["txt","json"]'})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()['files'][0]['filename'], 'labeled.txt')

    def test_invalid_inputs(self):
        with self.client(max_input_bytes=1024) as c:
            for body in [{'text': '  '}, {'text': 'x', 'format': ['pdf']}, {'text': 'x', 'format': []},
                         {'text': 'x', 'format': ['json', 'json']}, {'text': 3}, {'text': 'x', 'unexpected': True}]:
                self.assertEqual(c.post('/v1/label', json=body).status_code, 400)
            self.assertEqual(c.post('/v1/label', json={'text': 'x' * 1025}).status_code, 413)
            self.assertEqual(c.post('/v1/label', json={'text': 'x\x00y'}).status_code, 415)

    def test_oversized_body_preparse(self):
        with self.client(max_input_bytes=1024) as c:
            r = c.post('/v1/label', content=b'x' * 80000, headers={'Content-Type': 'application/json'})
            self.assertEqual(r.status_code, 413)

    def test_bad_uploads(self):
        with self.client() as c:
            for filename, content, status in [('x.pdf', b'%PDF', 415), ('x.txt', b'\xff', 400), ('x.txt', b'\x00', 415)]:
                r = c.post('/v1/label/file', files={'file': (filename, content)})
                self.assertEqual(r.status_code, status, r.text)
            r = c.post('/v1/label/file', files={'file': ('x.txt', b'hello')}, data={'format': 'txt'})
            self.assertEqual(r.status_code, 400)

    def test_unavailable_and_wrong_model(self):
        with self.client(lambda r: httpx.Response(200, json={'data': [{'id': 'wrong'}]})) as c:
            self.assertEqual(c.get('/health').status_code, 200)
            self.assertEqual(c.get('/ready').status_code, 503)
            self.assertEqual(c.post('/v1/label', json={'text': 'x'}).status_code, 503)

    def test_bad_model_output(self):
        def handler(r):
            return httpx.Response(200, json={'data': [{'id': 'ordo-final-2b'}]} if r.url.path.endswith('models') else
                                  {'choices': [{'message': {'content': '{"L0001":"H9"}'}}]})
        with self.client(handler) as c:
            r = c.post('/v1/label', json={'text': 'x'})
            self.assertEqual(r.status_code, 502)
            self.assertEqual(r.json()['error'], 'invalid_model_output')

    def test_retry_then_success(self):
        calls = []
        def handler(r):
            if r.url.path.endswith('models'):
                return httpx.Response(200, json={'data': [{'id': 'ordo-final-2b'}]})
            calls.append(1)
            if len(calls) == 2:
                schema = json.loads(r.content)['response_format']['json_schema']['schema']
                self.assertEqual(schema['required'], ['L0001'])
                self.assertFalse(schema['additionalProperties'])
            content = '{}' if len(calls) == 1 else '{"L0001":"TEXT"}'
            return httpx.Response(200, json={'choices': [{'message': {'content': content}}]})
        with self.client(handler, retries=1) as c:
            self.assertEqual(c.post('/v1/label', json={'text': 'x'}).status_code, 200)
            self.assertEqual(len(calls), 2)

    def test_shared_concurrency_and_admission(self):
        async def scenario():
            active = peak = 0
            async def handler(r):
                nonlocal active, peak
                if r.url.path.endswith('models'):
                    await asyncio.sleep(0.005)
                    return httpx.Response(200, json={'data': [{'id': 'ordo-final-2b'}]})
                active += 1;peak = max(active, peak)
                try:
                    await asyncio.sleep(0.01)
                    body = json.loads(r.content)
                    text = body['messages'][1]['content'].split('【当前 batch：需要标注】\n')[1].split('\n\n【下一 batch')[0]
                    ids = re.findall(r'^\[(L\d+)\]', text, re.M)
                    return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({k:'TEXT' for k in ids})}}]})
                finally:active -= 1
            app = create_app(Settings(concurrency=2, max_documents=2), httpx.MockTransport(handler))
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as c:
                    responses = await asyncio.gather(*(c.post('/v1/label', json={'text': '\n'.join(['x']*40)}) for _ in range(3)))
                    self.assertEqual(sorted(r.status_code for r in responses), [200,200,503])
                self.assertEqual(app.state.active_documents, 0)
            self.assertLessEqual(peak, 2)
        asyncio.run(scenario())

    def test_document_timeout_releases_admission(self):
        async def handler(r):
            await asyncio.sleep(0.1)
            return httpx.Response(200, json={'data': [{'id': 'ordo-final-2b'}]})
        with self.client(handler, document_timeout=0.01, max_documents=1) as c:
            self.assertEqual(c.post('/v1/label', json={'text': 'x'}).status_code, 504)
            self.assertEqual(c.post('/v1/label', json={'text': 'x'}).status_code, 504)

    def test_auth_and_external_binding(self):
        with patch.dict(os.environ, {'ORDO_API_TOKEN': 'example-test-token'}):
            with self.client(api_host='0.0.0.0') as c:
                self.assertEqual(c.get('/health').status_code, 200)
                self.assertEqual(c.post('/v1/label', json={'text': 'x'}).status_code, 401)
                self.assertEqual(c.post('/v1/label', json={'text': 'x'}, headers={'Authorization': 'Bearer example-test-token'}).status_code, 200)
        with patch.dict(os.environ, {'ORDO_API_TOKEN': ''}):
            with self.assertRaises(RuntimeError):
                with self.client(api_host='0.0.0.0'):
                    pass

    def test_explicit_no_auth(self):
        with patch.dict(os.environ, {'ORDO_API_TOKEN': 'existing-token-is-ignored'}):
            with self.client(api_host='0.0.0.0', auth_enabled=False) as c:
                r = c.post('/v1/label', json={'text':'hello','format':['json','txt','md']})
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(len(r.json()['files']), 3)

    def test_parser_and_render(self):
        self.assertEqual(parse_labels('<think></think>{"L0001":"TEXT"}', ['L0001']), {'L0001': 'TEXT'})
        for raw in ['{"L0001":"TEXT","L0001":"H1"}', '{}', '{"L0001":"H4"}']:
            with self.assertRaises(ServiceError):parse_labels(raw, ['L0001'])
        rows = [{'line_id': 'L0001', 'line_number': 1, 'text': 'a ``` b', 'label': 'TABLE'},
                {'line_id': 'L0002', 'line_number': 2, 'text': 'Header', 'label': 'HEADER'}]
        md = artifacts(rows, ['md'])[0]['content']
        self.assertIn('````text', md)
        self.assertIn('> [HEADER] Header', md)

    def test_frozen_prompt_parity(self):
        # Full source checkout only: no runtime dataset dependency in the package.
        root = Path(__file__).resolve().parents[2]
        data = root / 'results/mixed_lora_reviewed2/data'
        if not data.exists():self.skipTest('Original training artifact not present in portable repository')
        docs = [json.loads(l) for l in (data / 'test.documents.jsonl').read_text().splitlines()]
        samples = [json.loads(l) for l in (data / 'test.jsonl').read_text().splitlines()]
        indexes = [json.loads(l) for l in (data / 'test_index.jsonl').read_text().splitlines()]
        offsets = {};lookup = {d['id']: d['rows'] for d in docs}
        for sample, index in zip(samples, indexes):
            docid = index['document_id'];offset = offsets.get(docid, 0)
            self.assertEqual(messages(lookup[docid], offset), sample['messages'][:2], (docid, offset))
            offsets[docid] = offset + len(index['line_ids'])


if __name__ == '__main__':unittest.main()
