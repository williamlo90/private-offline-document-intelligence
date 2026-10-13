"""Verify frozen split independence and source-grounded answer/extraction labels."""
import hashlib
import json
from pathlib import Path
import re

from backend.pdf_parser import parse_pdf

ROOT=Path(__file__).resolve().parents[1]
SPLITS=('development','heldout-v1','heldout-v2','heldout-v3','heldout-v4','heldout-v5','heldout-v6')


def sentences(text):
    return {re.sub(r'\s+',' ',part).casefold().strip() for part in re.split(r'(?<=[.!?])\s+',text)
            if len(part.strip())>=45 and 'synthetic laboratory source' not in part.casefold()}


def main():
    seen_ids=set();seen_families=set();seen_hashes=set();seen_sentences=set();summary={}
    for split in SPLITS:
        folder=ROOT/'evaluation'/split
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        expected=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
        extraction=json.loads((folder/'extraction-expected.json').read_text(encoding='utf-8'))
        ids=set();families=set();hashes=set();phrases=set();documents={}
        for item in manifest['documents']:
            path=folder/item['file'];data=path.read_bytes()
            assert hashlib.sha256(data).hexdigest()==item['sha256']
            assert item['id'] not in ids and item['id'] not in seen_ids
            ids.add(item['id']);families.add(item['family']);hashes.add(item['sha256'])
            parsed=parse_pdf(data,language=item.get('language','eng'))
            assert len(parsed.pages)==len(item['pages'])
            for page in parsed.pages:
                phrases.update(sentences(page.text))
            documents[item['id']]=(item,parsed)
        assert not (families & seen_families),('shared family',split,families&seen_families)
        assert not (hashes & seen_hashes),('shared PDF',split)
        assert not (phrases & seen_sentences),('shared sentence',split,phrases&seen_sentences)
        for case in expected['cases']:
            for identifier,page,quote in case['evidence']:
                item,parsed=documents[identifier]
                assert item['tenant']==case['tenant']
                source=parsed.pages[page-1].text
                assert re.sub(r'\s+',' ',quote).casefold() in re.sub(r'\s+',' ',source).casefold(),case['id']
        field_total=0
        for entry in extraction['documents']:
            item,parsed=documents[entry['document_id']]
            assert item['tenant']==entry['tenant']
            for field in entry['fields']:
                source=parsed.pages[field['page']-1].text
                assert re.sub(r'\s+',' ',field['value']).casefold() in re.sub(r'\s+',' ',source).casefold(),field
                field_total+=1
        summary[split]={'documents':len(ids),'families':len(families),'cases':len(expected['cases']),
                        'extraction_fields':field_total,'distinct_source_sentences':len(phrases)}
        seen_ids.update(ids);seen_families.update(families);seen_hashes.update(hashes);seen_sentences.update(phrases)
    print(json.dumps({'status':'passed','splits':summary,'shared_document_ids':0,'shared_families':0,
                      'shared_pdf_hashes':0,'shared_source_sentences':0}))


if __name__=='__main__':main()
