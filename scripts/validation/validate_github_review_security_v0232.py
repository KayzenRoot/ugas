"""Validate bounded v0.23.2 artifact security boundaries."""
from __future__ import annotations
import argparse,json
from pathlib import Path
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--artifact-dir",type=Path,required=True); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); failures=[]
 for path in a.artifact_dir.rglob("*"):
  if path.is_file() and (path.suffix.casefold() in {".safetensors",".ckpt",".gguf",".onnx",".sqlite",".db"} or path.name.casefold() in {".env",".npmrc","credentials.json"}): failures.append(f"forbidden-file:{path.relative_to(a.artifact_dir).as_posix()}")
 try:
  v=json.loads(a.manifest.read_text(encoding="utf-8")); b=v.get("security_boundary",{})
  if v.get("schema_version")!="0.23.2": failures.append("schema-version")
  for key in ("secrets_included","model_weights_included","telemetry_db_included","local_credentials_included"):
   if b.get(key) is not False: failures.append(f"security-boundary:{key}")
 except (OSError,json.JSONDecodeError) as exc: failures.append(f"manifest:{type(exc).__name__}")
 result={"schema_version":"0.23.2","status":"PASS" if not failures else "FAIL","failures":failures,"file_count":sum(1 for x in a.artifact_dir.rglob("*") if x.is_file())}; a.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result)); return 0 if not failures else 1
if __name__=="__main__": raise SystemExit(main())
