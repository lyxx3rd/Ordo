import asyncio
import importlib.util
import json
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'local_service'))
sys.path.insert(0,str(ROOT/'ordo'))
import httpx
from ordo_local.client import RemoteLabeler
from ordo_local.offline import label_text


def prediction(ms):
    user=ms[1]['content'].split('【当前 batch：需要标注】\n')[1].split('\n\n【下一 batch')[0]
    return json.dumps({k:'TEXT' for k in re.findall(r'^\[(L\d+)\]',user,re.M)})


class Modes(unittest.TestCase):
    def test_direct_endpoint_client(self):
        def handler(r):
            if r.url.path.endswith('models'):
                return httpx.Response(200,json={'data':[{'id':'ordo-final-2b'}]})
            return httpx.Response(200,json={'choices':[{'message':{'content':prediction(json.loads(r.content)['messages'])}}]})
        async def run():
            async with RemoteLabeler(transport=httpx.MockTransport(handler)) as client:
                result=await client.label_text('\n'.join(['line']*40))
                self.assertEqual(len(result['files']),3)
                self.assertEqual(result['meta']['windows'],3)
                self.assertEqual(len(json.loads(result['files'][0]['content'])),40)
        asyncio.run(run())

    def test_offline_without_real_gpu(self):
        vllm=ModuleType('vllm');params=ModuleType('vllm.sampling_params')
        vllm.SamplingParams=lambda **kw:kw
        params.StructuredOutputsParams=lambda **kw:kw
        class LLM:
            def chat(self,batch,**kwargs):
                if isinstance(batch[0],dict):batch=[batch]
                return [SimpleNamespace(outputs=[SimpleNamespace(text=prediction(ms),finish_reason='stop')]) for ms in batch]
        with patch.dict(sys.modules,{'vllm':vllm,'vllm.sampling_params':params}):
            result=label_text(LLM(),'title\n\nbody')
            rows=json.loads(result['files'][0]['content'])
            self.assertEqual([r['line_id'] for r in rows],['L0001','L0003'])

    def test_online_key_environment_and_prompt(self):
        import qwen_probe
        import qwen_label_document as online
        with patch.dict('os.environ',{'ORDO_ONLINE_API_KEY':'not-a-real-key'}):
            self.assertEqual(qwen_probe.load_api_key(Path('no-such-file')),'not-a-real-key')
        prompt=online.build_prompt(label_rules='RULES',example='EXAMPLE',global_structure={'has_h1':True},state='',
            previous=[],all_labels={},current=[online.Unit(1,'Title')],following=[],current_char_limit=200,output_format='json_map')
        self.assertIn('EXAMPLE',prompt)
        self.assertIn('JSON',prompt)

    def test_release_metadata_and_notebook(self):
        spec=json.loads((ROOT/'notebooks/local_inprocess.ipynb').read_text())
        self.assertEqual(spec['nbformat'],4)
        for c in spec['cells']:
            if c['cell_type']=='code':
                self.assertEqual(c['outputs'],[])
                self.assertIsNone(c['execution_count'])
                compile(''.join(c['source']),'notebook','exec')
        self.assertEqual((ROOT/'VERSION').read_text().strip(),'1.0.0')
        manifest = json.loads((ROOT/'MODEL_MANIFEST.example.json').read_text())
        self.assertEqual(manifest['download_url'], 'https://modelscope.cn/models/l424102993/Ordo_2B')
        self.assertEqual(manifest['source_checkpoint_step'], 3296)


if __name__=='__main__':unittest.main()
