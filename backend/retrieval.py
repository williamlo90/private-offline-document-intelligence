"""Deterministic page/chunk keyword baseline; does not generate answers."""
from datetime import date
import re

STOP = frozenset('what is the a an of for to and are does do in on how when from can i it this that apa yang dan di ke dari kapan berapa'.split())


def tokens(text):
    return set(re.findall(r'\w+', text.lower())) - STOP


def document_status(document, documents, as_of):
    state = 'active'
    if document.effective and date.fromisoformat(document.effective) > as_of: state = 'future'
    if document.expires and date.fromisoformat(document.expires) < as_of: state = 'expired'
    if state == 'active' and document.family:
        peers = [d for d in documents if d.id != document.id and d.family == document.family and d.digest != document.digest
                 and (not d.effective or date.fromisoformat(d.effective) <= as_of)
                 and (not d.expires or date.fromisoformat(d.expires) >= as_of)]
        if peers: state = 'conflicting'
    return state


def document_chunks(document):
    for page in document.pages:
        # Character offsets are stable within this immutable page/version.
        for offset in range(0, len(page.text), 700):
            excerpt = page.text[offset:offset+900]
            if excerpt:
                yield {'page':page.number,'start':offset,'end':offset+len(excerpt),'quote':excerpt,
                       'quality':page.quality}


def keyword_search(documents, query, as_of: date, limit=5):
    terms = tokens(query)
    if not terms:
        return []
    results = []
    for document in documents:
        state=document_status(document,documents,as_of)
        for chunk in document_chunks(document):
            overlap = len(terms & tokens(chunk['quote']))
            if overlap:
                results.append({'document_id': document.id, 'version': document.version, 'sha256': document.digest,
                                'page': chunk['page'], 'start': chunk['start'], 'end': chunk['end'], 'quote': chunk['quote'],
                                'status': 'review' if chunk['quality'] == 'review' else state, 'score': overlap/len(terms),
                                'method': 'keyword-v1'})
    return sorted(results, key=lambda r: (-r['score'], r['document_id'], r['page'], r['start']))[:max(1,min(limit,20))]
