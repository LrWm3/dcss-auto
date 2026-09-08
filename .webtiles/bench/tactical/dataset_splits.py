"""Seed-level development partitions shared across dataset versions."""
import json
from pathlib import Path
from bench import sha

MANIFEST=Path(__file__).with_name('dataset-split-v1.json')


def partition_map(manifest):
    mapping={}
    for partition in ('train','validation','test'):
        seeds=manifest[partition]
        if not seeds: raise ValueError('Empty partition: '+partition)
        for seed in seeds:
            if not isinstance(seed,str): raise ValueError('Seed must be a string')
            if seed in mapping: raise ValueError('Seed appears in multiple partitions: '+seed)
            mapping[seed]=partition
    return mapping


def enforce(cfg, entries, manifest_path=MANIFEST):
    manifest=json.loads(manifest_path.read_text());mapping=partition_map(manifest)
    # The trainer is deliberately validation-only. A future frozen-model test
    # runner must have a separate interface, never an in_sample escape hatch.
    if cfg.get('evaluation_mode')!='held_out':
        raise ValueError('Registered split requires held_out validation, not in_sample')
    for entry in entries:
        if entry['seed'] not in mapping: raise ValueError('Unassigned seed: '+entry['seed'])
        if entry.get('split_group',entry['seed'])!=entry['seed']:
            raise ValueError('Seed metadata mismatch')
    by_id={e['id']:e for e in entries}
    for field,partition in (('train_cases','train'),('eval_cases','validation')):
        cfg.setdefault(field,[e['id'] for e in entries if e.get('eligible') and mapping[e['seed']]==partition])
        for id_ in cfg[field]:
            if mapping[by_id[id_]['seed']]!=partition:
                raise ValueError(f'{id_} belongs to {mapping[by_id[id_]["seed"]]}, not {partition}')
    cfg['split_provenance']=dict(manifest=manifest,sha256=sha(manifest_path),evaluation_partition='validation')
