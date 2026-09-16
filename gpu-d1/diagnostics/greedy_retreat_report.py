"""Check sampled/greedy comparability and summarize tough-roster, 12-HP cases."""
import json
import pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]

def main():
    result={}
    for name in ['hallway-six-retreat','distant-pocket-4-retreat','distant-pocket-6-retreat']:
        original=json.loads((ROOT/'results'/f'{name}.json').read_text())
        path=ROOT/'results'/f'{name}-greedy.json';greedy=json.loads(path.read_text())
        assert set(original['arms'])==set(greedy['arms'])
        for arm,a in greedy['arms'].items():
            old=original['arms'][arm]
            if arm in ['hold_fight','retreat_fight']:assert a==old
            else:assert a['checkpoint_sha256']==old['checkpoint_sha256'] and a['first']==old['first']
            for i in range(24):assert a['win'][i]+a['death'][i]+a['unresolved'][i]==1
        greedy['sampled_reference_checks']=dict(scripted_controls_exact=True,checkpoint_hashes_exact=True,initial_policy_probabilities_exact=True)
        path.write_text(json.dumps(greedy,indent=2)+'\n')
        result[name]={}
        for mode,data in [('sampled',original),('greedy',greedy)]:
            for arm,a in data['arms'].items():
                contact='pocket_contact_turns' if 'pocket_contact_turns' in a else 'protected_contact_turns'
                wait=contact.replace('contact','wait');denom=sum(a[contact][16:20])
                reached='reached_pocket' if 'reached_pocket' in a else 'reached_hallway'
                row={k:sum(a[k][16:20])/4 for k in ['win','death','unresolved',reached]}
                row.update(rotation_wins=a['win'][16:20],contact_wait_fraction=sum(a[wait][16:20])/denom if denom else None)
                result[name][mode+'_'+arm]=row
    (ROOT/'results/greedy-retreat-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    for name,data in result.items():
        print(name,{k:round(v['win']*100,2) for k,v in data.items() if k in ['sampled_ordinary','greedy_ordinary','sampled_mixed','greedy_mixed']})
if __name__=='__main__':main()
