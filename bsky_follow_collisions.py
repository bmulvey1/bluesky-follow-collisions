import argparse
import re
import requests

parser = argparse.ArgumentParser("bsky_follow_collisions")
parser.add_argument("handle", help="Bluesky handle")
parser.add_argument("app_password", help="Bluesky app password", nargs='?')

args = parser.parse_args()

bsky_handle = args.handle
if args.app_password is None:
    print("No app password provided, running in unauthenticated mode. Will only determine if there are blocked follows but not who they are.")
    authenticated = False
else:
    authenticated = True
bsky_app_password = args.app_password

if authenticated:
    app_password_regex = r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}"
    match = re.match(app_password_regex, bsky_app_password)
    if match is None or len(bsky_app_password) != 19:
        print("Use an app password instead of your actual password! Generate one at https://bsky.app/settings/app-passwords.")
        exit(1)
    else:
        pass


bsky_resolve_handle_url = f"https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle=\
{bsky_handle}"

resolved_handle = requests.get(
    bsky_resolve_handle_url, timeout=5).json()['did']

# figure out what PDS to connect to

plc_directory_url = f"https://plc.directory/{resolved_handle}"
resp = requests.get(plc_directory_url, timeout=5).json()
endpoint = resp['service'][0]['serviceEndpoint']

print(f"using {endpoint} as PDS")

if authenticated:

    session_url = f"{endpoint}/xrpc/com.atproto.server.createSession"

    headers = {"Content-Type": "application/json",
               "Accept": "application/json"}

    raw_data = '{"identifier": "%s", "password": "%s"}' % (
        bsky_handle, bsky_app_password)
    auth_req = requests.post(session_url, headers=headers,
                             data=raw_data, timeout=5)
    bsky_token = auth_req.json()['accessJwt']

    headers = {"Authorization": f"Bearer {bsky_token}"}

bsky_follows_url = f"{endpoint}/xrpc/com.atproto.repo.listRecords?repo=\
{bsky_handle}&collection=app.bsky.graph.follow"
if authenticated:
    bsky_filtered_follows_url = f"{endpoint}/xrpc/app.bsky.graph.getFollows?actor={bsky_handle}"
else:
    bsky_filtered_follows_url = f"https://public.api.bsky.app/xrpc/app.bsky.graph.getFollows?actor={bsky_handle}"

follow_dids = []
cursor = ""

while 1:
    follows_resp = requests.get(
        bsky_follows_url + f"&limit=100&cursor={cursor}", timeout=5)
    follows_json = follows_resp.json()
    for i in follows_json['records']:
        follow_dids.append(i['value']['subject'])
    if "cursor" in follows_json:
        cursor = follows_json['cursor']
    else:
        break

presented_follow_count = 0
cursor = ""

while 1:
    if authenticated:
        follows_resp = requests.get(
            bsky_filtered_follows_url + f"&limit=100&cursor={cursor}", timeout=5, headers=headers)
    else:
        follows_resp = requests.get(
            bsky_filtered_follows_url + f"&limit=100&cursor={cursor}", timeout=5)
    follows_json = follows_resp.json()
    presented_follow_count += len(follows_json['follows'])
    if "cursor" in follows_json:
        cursor = follows_json['cursor']
    else:
        break

print(f"presented # follows: {presented_follow_count}")
print(f"# follow DIDs: {len(follow_dids)}")

if presented_follow_count == len(follow_dids):
    print("follow count consistent, none are blocked or deleted")
    exit(0)
else:
    print("🚨🚨🚨 follow count inconsistent 🚨🚨🚨")

if not authenticated:
    print("Cannot proceed without authentication, exiting.")
    exit(0)

bsky_listblocks_url = f"{endpoint}/xrpc/app.bsky.graph.getListBlocks"

listblocks = []
cursor = ""

while 1:
    listblocks_resp = requests.get(
        bsky_listblocks_url + f"?limit=100&cursor={cursor}", headers=headers, timeout=5) # cursor seems to not exist for this endpoint currently
    listblocks_json = listblocks_resp.json()
    for i in listblocks_json['lists']:
        listblocks.append(i['uri'])
    if "cursor" in listblocks_json:
        cursor = listblocks_json['cursor']
    else:
        break

print(f"# subscribed blocklists: {len(listblocks)}")

# no auth required
bsky_list_details_url = f"{endpoint}/xrpc/app.bsky.graph.getList"

collisions = []

for l in listblocks:
    members = []
    cursor = ""
    while 1:
        resp = requests.get(
            bsky_list_details_url + f"?list={l}&limit=100&cursor={cursor}", headers=headers, timeout=5)
        members_json = resp.json()
        for i in members_json["items"]:
            members.append(i['subject']['did'])
        if "cursor" in members_json:
            cursor = members_json["cursor"]
        else:
            break

    intersections = set(follow_dids).intersection(set(members))
    for collision in intersections:
        collisions.append((l, collision))

print(collisions)
