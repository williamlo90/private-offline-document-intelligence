"""Real inference only; invoked by the memory-monitoring supervisor."""
import json
from pathlib import Path
import sys
import time
import psutil
from backend.embeddings import LocalEmbeddings

root=Path(__file__).resolve().parents[1]
profile=json.loads((root/'config/embedding-profile.json').read_text(encoding='utf-8-sig'))
started=time.monotonic()
model=LocalEmbeddings(root/'local/models/multilingual-minilm',profile)
rss_after_load=psutil.Process().memory_info().rss
texts=['Check the backup job status.','Periksa status pekerjaan pencadangan.','The restaurant serves fresh noodles.']
vectors=model.embed(texts)
rss_after_embed=psutil.Process().memory_info().rss
similar=lambda a,b:sum(x*y for x,y in zip(a,b))
related=similar(vectors[0],vectors[1]);unrelated=similar(vectors[0],vectors[2])
assert related>unrelated,'Cross-language smoke ranking failed'
result={'status':'passed','native_inference':True,'dimensions':[len(v) for v in vectors],
        'related_cosine':related,'unrelated_cosine':unrelated,'seconds':time.monotonic()-started,
        'worker_rss_after_load_gib':round(rss_after_load/1024**3,3),
        'worker_rss_after_embed_gib':round(rss_after_embed/1024**3,3),
        'scope':'Three-text multilingual smoke ranking only; not retrieval quality acceptance',
        'model_revision':profile['revision']}
Path(sys.argv[1]).write_text(json.dumps(result,indent=2),encoding='utf-8')
