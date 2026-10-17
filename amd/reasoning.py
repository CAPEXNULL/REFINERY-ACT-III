"""Small typed reasoning graph; empirical causation is never silently transitive."""
from collections import deque
import hashlib
import json

TRANSITIVE={'part_of','is_a','precedes'}


class KnowledgeGraph:
    def __init__(self,records=None):self.records=list(records or [])

    def add(self,source,relation,target,evidence,status='CONFIRMED'):
        if status not in ('CONFIRMED','HYPOTHESIS'):raise ValueError('Unknown assertion status')
        if not evidence:raise ValueError('An assertion needs provenance')
        identifier=hashlib.sha256(json.dumps([source,relation,target,evidence],sort_keys=True).encode()).hexdigest()[:20]
        if any(r['id']==identifier for r in self.records):return identifier
        self.records.append({'id':identifier,'source':source,'relation':relation,'target':target,'evidence':evidence,
                             'status':status,'rule':'observed assertion','premises':[]})
        return identifier

    def infer(self,source,relation,target):
        if relation not in TRANSITIVE:return None
        queue=deque([(source,[])]);seen={source}
        while queue:
            node,path=queue.popleft()
            for edge in sorted(self.records,key=lambda r:r['id']):
                if edge['source']!=node or edge['relation']!=relation or edge['status']!='CONFIRMED':continue
                chain=path+[edge['id']]
                if edge['target']==target:
                    return {'source':source,'relation':relation,'target':target,'status':'DEDUCED',
                            'rule':'transitivity:'+relation,'premises':chain}
                if edge['target'] not in seen:seen.add(edge['target']);queue.append((edge['target'],chain))
        return None

    def retract(self,identifier,reason):
        invalid={identifier};changed=True
        while changed:
            changed=False
            for record in self.records:
                if record['id'] in invalid or any(p in invalid for p in record['premises']):
                    if record['status']!='RETRACTED':
                        record['status']='RETRACTED';record['retraction_reason']=reason;invalid.add(record['id']);changed=True
        return invalid
