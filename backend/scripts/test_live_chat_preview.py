import urllib.request
import json

base = 'https://iveri-ai-support.onrender.com'
slug = 'nishant-dattas-workspace-a7cecc'
req_sess = urllib.request.Request(
    f'{base}/api/chat/session',
    data=json.dumps({'business_slug_or_token': slug, 'channel': 'public_link'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req_sess) as res:
    sess = json.loads(res.read())
    s_id = sess['id']

def ask(q):
    r = urllib.request.Request(
        f'{base}/api/chat/message',
        data=json.dumps({'session_id': s_id, 'message': q}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(r) as resp:
        d = json.loads(resp.read())
        print(f"=== Query: {q} ===")
        print("Answer:", d.get("content"))
        print("Is Answered:", d.get("is_answered"))
        print("Confidence:", d.get("confidence_score"))
        print("Citations:")
        for c in d.get("citations", []):
            print(f"  - {c.get('document_name')} (p.{c.get('page_number')}) [preview: {c.get('has_pdf_preview')}]")
            print(f"    Excerpt: {c.get('excerpt')}")
            print(f"    Doc ID: {c.get('document_id')}, Chunk ID: {c.get('chunk_id')}")

ask('how much is this worth')
print()
ask('how much brewpoints worth')
