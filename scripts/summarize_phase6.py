"""Summarize frozen native quality reports with category/language denominators."""
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'local/phase-6'/sys.argv[1] if len(sys.argv)>1 else ROOT/'local/phase-6/final-8'
SPLITS={
    'development':'development',
    'regression-v1':'heldout-v1',
    'regression-v2':'heldout-v2',
    'regression-v3':'heldout-v3',
    'regression-v4':'heldout-v4',
    'regression-v5':'heldout-v5',
    'heldout-v6':'heldout-v6',
}


def main():
    output=ROOT/'local/phase-6/quality-summary.json'
    if output.exists():raise RuntimeError('Refusing to overwrite quality summary')
    result={'run':RUN.name,'splits':{},'combined_regression':{}}
    combined=defaultdict(lambda:{'correct':0,'total':0})
    for split,folder in SPLITS.items():
        report=json.loads((RUN/f'{split}-native.json').read_text(encoding='utf-8'))
        manifest=json.loads((ROOT/'evaluation'/folder/'manifest.json').read_text(encoding='utf-8'))
        language={item['id']:item.get('language','eng') for item in manifest['documents']}
        by_language=defaultdict(lambda:{'answerable_passed':0,'answerable_total':0,
                                        'uncertain_passed':0,'uncertain_total':0,
                                        'fields_correct':0,'fields_total':0,'extraction_documents':0})
        for row in report['rows']:
            bucket=by_language[row['language']]
            name='answerable' if row['expected_status'] in {'answered','draft'} else 'uncertain'
            bucket[f'{name}_total']+=1
            bucket[f'{name}_passed']+=int(row['passed'])
        for row in report['extraction_rows']:
            bucket=by_language[language[row['document_id']]]
            bucket['extraction_documents']+=1
            bucket['fields_total']+=len(row['fields'])
            bucket['fields_correct']+=sum(field['correct'] for field in row['fields'])
        result['splits'][split]={'gate_passed':report['gate_passed'],'cases':report['case_count'],
                                'extraction_documents':report['extraction_document_count'],
                                'metrics':report['counts'],'by_category':report['by_category'],
                                'by_language':dict(by_language),'baseline':report['baseline'],
                                'latency_seconds':report['latency_seconds'],'errors':report['errors']}
        if split!='heldout-v6':
            for key,counts in report['counts'].items():
                combined[key]['correct']+=counts['correct']
                combined[key]['total']+=counts['total']
    result['combined_regression']=dict(combined)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'run':RUN.name,'gates':{key:value['gate_passed'] for key,value in result['splits'].items()},
                      'heldout':result['splits']['heldout-v6']['metrics']}))


if __name__=='__main__':main()
