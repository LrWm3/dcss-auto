"""Train and validate the globally visible player-centered map policy."""
import json,pathlib,subprocess,sys,time,traceback
ROOT=pathlib.Path(__file__).resolve().parents[3]
SUITE=ROOT/'learning-runs/vision15-centered-map'
def main():
 SUITE.mkdir(parents=True,exist_ok=True);start=time.time();status=SUITE/'pipeline-status.json'
 def record(stage,**kw):status.write_text(json.dumps(dict(stage=stage,started_at=start,updated_at=time.time(),**kw),indent=2)+'\n')
 try:
  record('training')
  subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_experiment.py'))],check=True)
  record('complete',wall_seconds=time.time()-start)
 except Exception:
  record('failed',error=traceback.format_exc());raise
if __name__=='__main__':main()
