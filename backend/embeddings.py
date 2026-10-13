"""Strictly local ONNX adapter. Provisioning is a separate explicit script."""
import hashlib
import json
from pathlib import Path
from threading import Lock
from backend.resources import require_memory

def checksum(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def verify_assets(directory,profile):
    directory=Path(directory).resolve()
    manifest=json.loads((directory/'asset-manifest.json').read_text(encoding='utf-8'))
    if manifest['revision']!=profile['revision'] or manifest['model_id']!=profile['model_id']:
        raise ValueError('embedding_revision_mismatch')
    for filename in profile['files']:
        path=(directory/filename).resolve()
        if not path.is_relative_to(directory) or checksum(path)!=manifest['sha256'][filename]:
            raise ValueError('embedding_checksum_mismatch')
    return manifest

def configure_tokenizer(tokenizer,directory,max_tokens):
    config=json.loads((Path(directory)/'tokenizer_config.json').read_text(encoding='utf-8'))
    pad_token=config['pad_token']
    if isinstance(pad_token,dict):pad_token=pad_token['content']
    pad_id=tokenizer.token_to_id(pad_token)
    if pad_id is None:raise ValueError('embedding_padding_token_missing')
    tokenizer.enable_truncation(max_length=max_tokens)
    tokenizer.enable_padding(pad_id=pad_id,pad_token=pad_token)

class LocalEmbeddings:
    def __init__(self,directory,profile):
        require_memory(profile['minimum_available_ram_gib'])
        self.manifest=verify_assets(directory,profile)
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.profile=profile;self.lock=Lock()
        options=ort.SessionOptions();options.intra_op_num_threads=profile['threads'];options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(Path(directory)/profile['model_file']),sess_options=options,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(Path(directory)/'tokenizer.json'))
        configure_tokenizer(self.tokenizer,directory,profile['max_tokens'])

    def embed(self,texts):
        import numpy as np
        if not 1<=len(texts)<=32 or any(not t.strip() or len(t)>5000 for t in texts):
            raise ValueError('embedding_input_limit')
        vectors=[]
        with self.lock:
            for text in texts:
                # Single-item batches avoid padding amplification and memory spikes.
                require_memory(self.profile['minimum_runtime_available_ram_gib'])
                encoded=self.tokenizer.encode(text)
                arrays={'input_ids':np.array([encoded.ids],dtype=np.int64),'attention_mask':np.array([encoded.attention_mask],dtype=np.int64),'token_type_ids':np.array([encoded.type_ids],dtype=np.int64)}
                outputs=self.session.run(None,{i.name:arrays[i.name] for i in self.session.get_inputs()})
                hidden=outputs[0]
                if hidden.ndim!=3:raise ValueError('unexpected_embedding_output')
                mask=arrays['attention_mask'][...,None]
                vector=(hidden*mask).sum(axis=1)/np.maximum(mask.sum(axis=1),1)
                vector=vector[0];vector=vector/max(float(np.linalg.norm(vector)),1e-12)
                if vector.shape!=(self.profile['dimensions'],) or not np.isfinite(vector).all():raise ValueError('invalid_embedding')
                vectors.append(vector.tolist())
        return vectors
