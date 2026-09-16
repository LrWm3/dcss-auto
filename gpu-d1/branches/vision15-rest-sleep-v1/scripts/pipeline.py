"""Train both sleep-aware policies, then run the existing diagnostic suite."""
import json,pathlib,subprocess,sys,time,traceback
ROOT=pathlib.Path(__file__).resolve().parents[3]
SUITE=ROOT/'learning-runs/vision15-rest-sleep'
def main():
 SUITE.mkdir(parents=True,exist_ok=True);start=time.time();status=SUITE/'pipeline-status.json'
 def record(stage,**kw):status.write_text(json.dumps(dict(stage=stage,started_at=start,updated_at=time.time(),**kw),indent=2)+'\n')
 try:
  record('training')
  subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_experiment.py'))],check=True)
  record('recovery_evaluation')
  subprocess.run([sys.executable,str(ROOT/'diagnostics/rest-recovery/run.py'),'--sleep-status','--arms','wait','rest','--reps','128','--greedy'],check=True)
  subprocess.run([sys.executable,str(ROOT/'diagnostics/rest-recovery/compare_sleep.py')],check=True)
  record('complete',wall_seconds=time.time()-start)
 except Exception:
  record('failed',error=traceback.format_exc());raise
if __name__=='__main__':main()
