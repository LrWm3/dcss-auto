"""Train with the original deadline, then evaluate every retained milestone."""
import argparse
import pathlib
import subprocess
import sys


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--suite',type=pathlib.Path,required=True)
    ap.add_argument('--results',type=pathlib.Path,required=True)
    args=ap.parse_args()
    here=pathlib.Path(__file__).resolve().parent
    subprocess.run([sys.executable,str(here/'run_ring_ablations.py'),'--output',str(args.suite),
                    '--steps','10000000','--seeds','0','--variants','vision15_no_travel'],check=True)
    subprocess.run([sys.executable,str(here/'evaluate_snapshots.py'),'--suite',str(args.suite),
                    '--output',str(args.results)],check=True)


if __name__=='__main__':
    main()
