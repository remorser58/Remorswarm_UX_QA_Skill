"""Live model capability probe; synthetic sessions only, no browser or real-user evidence."""
from __future__ import annotations
import argparse, concurrent.futures, json, time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uxpersonas.model_router import ModelRoute, ModelRouter
PERSONAS = [
("first_time","First-time visitor who needs clear labels and reassurance"),
("price_careful","Price-conscious shopper who checks final totals"),
("speed_focused","Time-pressed shopper who wants the shortest safe path"),
("detail_reader","Careful reader who checks terms before committing"),
("mobile_thumb","Mobile-first user who prefers large, separated controls"),
("keyboard_user","Keyboard-first user who expects visible focus and shortcuts"),
("accessibility","User who relies on clear structure and descriptive controls"),
("privacy_careful","Privacy-conscious user who avoids unnecessary personal data"),
("returning","Returning shopper who expects remembered non-sensitive choices"),
("uncertain","User who is unsure whether a coupon was applied"),
("error_sensitive","User who needs clear recovery after validation errors"),
("multitasker","User who may leave and return without losing progress"),
("low_bandwidth","User on a slow connection who needs progress feedback"),
("comparison","User who compares delivery fees and final prices"),
("minimalist","User who wants a quiet interface with few decisions"),
("high_assurance","User who checks irreversible actions before confirming"),
("international","User who needs unambiguous currency and address labels"),
("form_averse","User who dislikes long forms and repeated entry"),
("trust_cautious","User who needs to understand why information is requested"),
("goal_directed","User who follows a specific task and avoids distractions"),
("novice_checkout","New online shopper unfamiliar with checkout conventions"),
("repeat_checkout","Experienced shopper expecting predictable controls"),
("small_screen","User with a compact phone viewport"),
("notification_averse","User who does not want unnecessary interruptions"),
("delivery_focused","User who prioritizes delivery date and address accuracy"),
("coupon_focused","User who prioritizes applying a discount correctly"),
("cart_cautious","User who worries about accidentally deleting cart contents"),
("language_simple","User who prefers plain, concrete wording"),
("feedback_seeking","User who needs confirmation after every important action"),
("recovery_focused","User who wants to correct mistakes without restarting"),
("decision_tired","User who prefers a sensible default and fewer choices"),
("control_seeking","User who wants to review and change every selected option"),
]
SYSTEM = ("You are one isolated synthetic UX test participant. Use only the supplied fictional interface description and your own stated preferences. "
          "Do not claim to have seen or clicked a real interface. Return one JSON object only with keys action, expectation, concern, confidence. "
          "action, expectation and concern must be short strings; confidence must be a number from 0 to 1.")
def parse_json(content):
    text=content.strip()
    if text.startswith(chr(96)*3): text=text.split("\n",1)[-1].rsplit(chr(96)*3,1)[0].strip()
    value=json.loads(text)
    return isinstance(value,dict) and set(value)=={"action","expectation","concern","confidence"} and all(isinstance(value[k],str) and value[k].strip() for k in ("action","expectation","concern")) and type(value["confidence"]) in (int,float) and 0 <= value["confidence"] <= 1
def run_session(index, profile, router):
    pid, preference=profile
    messages=[{"role":"system","content":SYSTEM}]
    receipts=[]; outputs=[]
    scenario=("Fictional mobile checkout: cart total 48,000 KRW; delivery address form; optional coupon field; coupon may be rejected; primary button says Continue. Task: apply a valid coupon and continue without losing address details.")
    turns=[
        f"Session {pid}. Your preference: {preference}. Starting screen: {scenario} What is your next action?",
        "The coupon was rejected as expired. The address form is still filled, but the error message is a small red line under the coupon field. What do you do next?",
        "You remove the expired coupon. The total returns to 48,000 KRW and the Continue button remains visible. What do you do now, and what would make you confident it worked?"
    ]
    for prompt in turns:
        messages.append({"role":"user","content":prompt})
        content, receipt=router.complete(messages,max_tokens=384,temperature=0.1,quality_check=parse_json)
        text=content.strip()
        if text.startswith(chr(96)*3): text=text.split("\n",1)[-1].rsplit(chr(96)*3,1)[0].strip()
        outputs.append(json.loads(text)); receipts.append(receipt)
        messages.append({"role":"assistant","content":content})
    return {"session_id":f"probe-{index:03d}-{pid}","persona_id":pid,"synthetic_preference":preference,
        "turns":outputs,"usage":{"input_tokens":sum(x["input_tokens"] for x in receipts),"output_tokens":sum(x["output_tokens"] for x in receipts)},
        "providers":[x["provider"] for x in receipts],"elapsed_seconds":round(sum(x["elapsed_seconds"] for x in receipts),3),"responses":receipts}
def _parse_routes(values):
    routes = []
    for raw in values:
        provider, sep, model = raw.partition(":")
        if not sep or not provider.strip() or not model.strip():
            raise ValueError("Routes must have PROVIDER:MODEL format")
        routes.append(ModelRoute(provider.strip(), model.strip()))
    return routes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--base-url",default="http://127.0.0.1:10100/v1")
    parser.add_argument("--route",action="append",dest="routes",required=True,
                        help="Model route in PROVIDER:MODEL format (repeatable for fallback).")
    parser.add_argument("--stages",default="1,4,16,32")
    parser.add_argument("--concurrency",type=int,default=2)
    parser.add_argument("--offset",type=int,default=0)
    args=parser.parse_args()
    stages=[int(x) for x in args.stages.split(",")]
    if len(set(stages))!=len(stages) or any(n < 1 or n > len(PERSONAS) for n in stages) or not 1<=args.concurrency<=4 or args.offset < 0 or args.offset + max(stages) > len(PERSONAS): parser.error("stage counts and offset must fit the available distinct profiles; concurrency 1..4")
    routes=_parse_routes(args.routes)
    primary_provider=routes[0].provider
    args.out.mkdir(parents=True,exist_ok=False,mode=0o700)
    router=ModelRouter(args.base_url,routes,timeout=120,max_retries=2,backoff_initial=2,backoff_max=30,ledger_path=args.out/"usage-ledger.json")
    all_sessions=[]; offset=args.offset; stage_reports=[]
    for count in stages:
        batch=list(enumerate(PERSONAS[offset:offset+count],offset+1))
        if len(batch)!=count: raise RuntimeError("not enough distinct synthetic persona profiles")
        started=time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures=[pool.submit(run_session,i,p,router) for i,p in batch]
            rows=[f.result() for f in futures]
        stage={"sessions":count,"cumulative_sessions":offset+count,"elapsed_seconds":round(time.monotonic()-started,3),
            "calls":sum(len(x["responses"]) for x in rows),"input_tokens":sum(x["usage"]["input_tokens"] for x in rows),
            "output_tokens":sum(x["usage"]["output_tokens"] for x in rows),"fallback_sessions":sum(any(p != primary_provider for p in x["providers"]) for x in rows),
            "providers":sorted({p for x in rows for p in x["providers"]})}
        all_sessions.extend(rows); offset+=count; stage_reports.append(stage)
        (args.out/f"stage-{offset}.json").write_text(json.dumps({"stage":stage,"sessions":rows,"router":router.report()},ensure_ascii=False,indent=2))
        print(json.dumps(stage,ensure_ascii=False),flush=True)
    summary={"mode":"live_model_synthetic_persona_probe_not_product_qa","stages":stage_reports,"new_sessions":len(all_sessions),"total_sessions":args.offset+len(all_sessions),
        "total_calls":sum(len(x["responses"]) for x in all_sessions),"input_tokens":sum(x["usage"]["input_tokens"] for x in all_sessions),
        "output_tokens":sum(x["usage"]["output_tokens"] for x in all_sessions),"fallback_sessions":sum(any(p != primary_provider for p in x["providers"]) for x in all_sessions),
        "router":router.report(),"browser_actions":0,"real_user_evidence":False,"product_readiness_claim":False}
    (args.out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({"summary":str(args.out/"summary.json"),"totals":{k:summary[k] for k in ("total_sessions","total_calls","input_tokens","output_tokens","fallback_sessions")}},ensure_ascii=False))
if __name__=="__main__": main()
