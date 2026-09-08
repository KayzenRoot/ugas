"""Fail-closed exact-head validator for the v0.23.2 review manifest."""
from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
BASE_MAIN="b08b9c3df74ef6a23046be396289e2fd72dc336b"
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("manifest",type=Path); p.add_argument("--result-output",type=Path,required=True); a=p.parse_args(); failures=[]
 try:
  v=json.loads(a.manifest.read_text(encoding="utf-8")); current=subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True,check=False).stdout.strip(); pr=v.get("pull_request",{}); scope=v.get("scope",{}); prod=v.get("production_boundary",{}); gates=v.get("gates",{}); controls=v.get("negative_controls",{}).get("controls",{})
  if v.get("schema_version")!="0.23.2" or v.get("manifest_type")!="github-ci-vfx-asset-family-v0232-review": failures.append("manifest-identity-invalid")
  if pr.get("number")!=14 or pr.get("base_sha")!=BASE_MAIN or pr.get("head_sha")!=current: failures.append("exact-head-pr-binding-invalid")
  expected={"version":"0.23.2","phase":"VFX_ASSET_FAMILY","current_gate":"VFX_ASSET_FAMILY_RUNTIME_CORRECTION_F23R_F26R_F27R_TECHNICALLY_QUALIFIED_EXTERNAL_REVIEW_REQUIRED","baseline_main_sha":BASE_MAIN,"allowed_next_actions":["external_review_vfx_asset_family_v0232"],"next_candidate":"ORCHESTRATION_RUNTIME_HARDENING","new_generation":0}; failures.extend(f"scope:{k}" for k,x in expected.items() if scope.get(k)!=x)
  expected_prod={"approved":False,"routing":"BLOCKED","new_generation":0,"real_vfx_asset_coverage":"NONE","synthetic_vfx_fixture":"TEST_ONLY","production_registry_empty":True}; failures.extend(f"production:{k}" for k,x in expected_prod.items() if prod.get(k)!=x)
  review=v.get("review_boundary",{}); failures.extend(["review-boundary"] if review.get("external_review_required") is not True or review.get("do_not_merge") is not True or review.get("merge_authorization")!="NOT_AUTHORIZED_UNTIL_SOL_APPROVAL" or review.get("pr_open_required") is not True or review.get("pr_merged") is not False else [])
  if v.get("current_state",{}).get("tracked_head_sha") is not None or v.get("current_state",{}).get("head_sha_source")!="GitHub LIVE exact-head metadata": failures.append("tracked-head-self-reference")
  if v.get("tests",{}).get("status")!="passed" or v.get("tests",{}).get("failed")!=0: failures.append("tests")
  if v.get("validation",{}).get("status")!="passed" or v.get("validation",{}).get("failed")!=0: failures.append("validation")
  if len(gates)!=32 or any(x.get("status")!="PASS" or type(x.get("observed")) is not bool or x.get("observed") is not True for x in gates.values()): failures.append("hard-gates")
  if len(controls)!=18 or any(x.get("status")!="PASS" or x.get("result")!="REJECT" or x.get("expected_rejection_class")!=x.get("observed_rejection_class") for x in controls.values()): failures.append("negative-controls")
  if v.get("determinism",{}).get("status")!="PASS" or v.get("overall_status")!="PASS": failures.append("overall")
  for relative in v.get("vfx_evidence",{}).values():
   if not (a.manifest.parent/relative).is_file(): failures.append(f"evidence-missing:{relative}")
  for relative in ("docs/evidence/vfx-asset-family-runtime-v0230/","docs/evidence/vfx-asset-family-runtime-v0231/","REVIEW-v0.23.0.md","REVIEW-v0.23.1.md"):
   if not (a.manifest.parent/relative).exists(): failures.append(f"immutable-history-missing:{relative}")
 except (OSError,json.JSONDecodeError,TypeError,ValueError) as exc: failures.append(f"manifest-read:{type(exc).__name__}:{exc}")
 result={"schema_version":"0.23.2","status":"PASS" if not failures else "FAIL","failures":failures,"checked_manifest":str(a.manifest)}; a.result_output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,ensure_ascii=False)); return 0 if not failures else 1
if __name__=="__main__": raise SystemExit(main())
