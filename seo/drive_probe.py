import json, os, sys
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
raw=os.environ.get("GCP_CREDENTIALS")
if not raw:
    print("NO_CREDS"); sys.exit(2)
info=json.loads(raw)
creds=service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"])
sess=AuthorizedSession(creds)
queries=[
  "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
  "mimeType='application/vnd.google-apps.spreadsheet' and name contains 'Performance' and trashed=false",
  "mimeType='application/vnd.google-apps.spreadsheet' and name contains 'Performance-on-Search' and trashed=false",
]
out=[]
for q in queries:
    r=sess.get("https://www.googleapis.com/drive/v3/files", params={"pageSize":100,"fields":"files(id,name,mimeType,modifiedTime)","q":q,"includeItemsFromAllDrives":"true","supportsAllDrives":"true"})
    rec={"query":q,"status":r.status_code,"files":[]}
    try:
        rec["files"]=r.json().get("files",[])
    except Exception as e:
        rec["error"]=str(e)
    out.append(rec)
with open("drive_files.json","w") as f:
    json.dump(out,f,indent=2)
with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as s:
    for rec in out:
        s.write("## Query: "+rec["query"]+"\n")
        s.write("Status: "+str(rec["status"])+"  Files: "+str(len(rec["files"]))+"\n")
        for f_ in rec["files"]:
            s.write("- "+f_["id"]+" | "+f_["name"]+" | "+f_["mimeType"]+"\n")
        s.write("\n")
print(json.dumps(out, indent=2))
