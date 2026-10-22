"""Mode 2: vLLM in the same Python process; no listening ports or API server."""
import time
from .client import result_for, text_rows
from .core import ServiceError, label_response_format, messages, parse_labels


def load_model(model_path, gpu_memory_utilization=0.45, max_model_len=8192):
    from vllm import LLM
    return LLM(model=str(model_path),dtype='bfloat16',max_model_len=max_model_len,
               gpu_memory_utilization=gpu_memory_utilization,max_num_seqs=16,
               enable_prefix_caching=True,generation_config='vllm')


def label_text(llm, text, formats=('json','txt','md'), batch_size=16):
    from vllm import SamplingParams
    from vllm.sampling_params import StructuredOutputsParams
    if not 1 <= batch_size <= 64:
        raise ValueError('batch_size must be between 1 and 64')
    start=time.perf_counter();rows=text_rows(text);labels={}
    offsets=list(range(0,len(rows),18))
    sampling=SamplingParams(temperature=0,max_tokens=512)
    for begin in range(0,len(offsets),batch_size):
        current=offsets[begin:begin+batch_size]
        outputs=llm.chat([messages(rows,i) for i in current],sampling_params=sampling,use_tqdm=False,
                         chat_template_kwargs={'enable_thinking':False})
        if len(outputs)!=len(current):raise RuntimeError('Incomplete vLLM batch')
        for offset,output in zip(current,outputs):
            ids=[r['line_id'] for r in rows[offset:offset+18]]
            try:
                if output.outputs[0].finish_reason=='length':raise ServiceError(502,'invalid_model_output','Truncated')
                predicted=parse_labels(output.outputs[0].text,ids)
            except ServiceError:
                params=SamplingParams(temperature=0,max_tokens=512,
                    structured_outputs=StructuredOutputsParams(json=label_response_format(ids)['json_schema']['schema']))
                retry=llm.chat(messages(rows,offset),sampling_params=params,use_tqdm=False,
                               chat_template_kwargs={'enable_thinking':False})
                if retry[0].outputs[0].finish_reason=='length':raise ServiceError(502,'invalid_model_output','Truncated retry')
                predicted=parse_labels(retry[0].outputs[0].text,ids)
            labels.update(predicted)
    return result_for(rows,labels,'ordo-final-2b',start,formats)
