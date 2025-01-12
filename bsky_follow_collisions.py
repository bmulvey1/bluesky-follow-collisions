import argparse
import re
import sys
try:
    import requests
except ImportError as e:
    raise SystemExit("Requests module not installed! Install it with``pip install requests``") from e

REQUEST_TIMEOUT = (5,15)

parser = argparse.ArgumentParser("bsky_follow_collisions")
parser.add_argument("handle", help="Bluesky handle")
parser.add_argument("app_password", help="Bluesky app password", nargs='?')

args = parser.parse_args()

bsky_handle = args.handle

if args.app_password is None:
    print("No app password provided, running in unauthenticated mode. Will only determine what follows are blocked but not what lists are blocking them.")
    authenticated = False
else:
    authenticated = True
bsky_app_password = args.app_password

if authenticated:
    app_password_regex = r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}"
    match = re.match(app_password_regex, bsky_app_password)
    if match is None or len(bsky_app_password) != 19:
        print("Use an app password instead of your actual password! Generate one at https://bsky.app/settings/app-passwords.")
        sys.exit(1)
    else:
        pass
 
bsky_resolve_handle_url = f"https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle=\
{bsky_handle}"
try:
    resolved_handle_resp = requests.get(bsky_resolve_handle_url, timeout=REQUEST_TIMEOUT)
except requests.exceptions.Timeout as e:
    raise SystemExit(e)
if resolved_handle_resp.status_code != 200:
    print(f"Response status code {resolved_handle_resp.status_code} from request {resolved_handle_resp.url} with error '{resolved_handle_resp.json()['error']}' and message '{resolved_handle_resp.json()['message']}'", file=sys.stderr)
    raise SystemExit(resolved_handle_resp.json()['error'])
resolved_handle = resolved_handle_resp.json()['did']

# figure out what PDS to connect to

plc_directory_url = f"https://plc.directory/{resolved_handle}"
try:
    resp = requests.get(plc_directory_url, timeout=REQUEST_TIMEOUT)
except requests.exceptions.Timeout as e:
    raise SystemExit(e)
if resp.status_code != 200:
    print(f"Response status code {resp.status_code} from request {resp.url} with error {resp.json()['error']} and message {resp.json()['message']} ", file=sys.stderr)
    raise SystemExit(resp.json()['error'])

endpoint = resp.json()['service'][0]['serviceEndpoint']

print(f"using {endpoint} as PDS")

if authenticated:

    session_url = f"{endpoint}/xrpc/com.atproto.server.createSession"

    headers = {"Content-Type": "application/json",
               "Accept": "application/json"}

    raw_data = '{"identifier": "%s", "password": "%s"}' % (
        bsky_handle, bsky_app_password)
    try:
        auth_req = requests.post(session_url, headers=headers,
                                 data=raw_data, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout as e:
        raise SystemExit(e)
    if auth_req.status_code != 200:
        print(f"Response status code {auth_req.status_code} from request {auth_req.url} with error '{auth_req.json()['error']}' and message '{auth_req.json()['message']}'", file=sys.stderr)
        raise SystemExit(auth_req.json()['error'])
    bsky_token = auth_req.json()['accessJwt']

    headers = {"Authorization": f"Bearer {bsky_token}"}
else:
    headers = None

def paginate_request(url, keys):
    resp_list = []
    cursor = ""
    while 1:
        if authenticated:
            try:
                resp = requests.get(url + f"&limit=100&cursor={cursor}", headers=headers, timeout=REQUEST_TIMEOUT)
            except requests.exceptions.Timeout as e: # bail!
                raise SystemExit(e)
        else:
            try:
                resp = requests.get(url + f"&limit=100&cursor={cursor}", timeout=REQUEST_TIMEOUT)
            except requests.exceptions.Timeout as e:
                raise SystemExit(e)
        resp_json = resp.json()
        if resp.status_code != 200:
            print(f"Response status code {resp.status_code} from request {resp.url} with error {resp_json['error']} and message {resp_json['message']} ", file=sys.stderr)
            raise SystemExit(resp_json['error'])
        for i in resp_json[keys[0]]:
            resp_list.append(i[keys[1]])
        if "cursor" in resp_json:
            cursor = resp_json["cursor"]
        else:
            break
        print(".", end="", flush=True)
    return resp_list

bsky_follows_url = f"{endpoint}/xrpc/com.atproto.repo.listRecords?repo=\
{bsky_handle}&collection=app.bsky.graph.follow"
if authenticated:
    bsky_filtered_follows_url = f"{endpoint}/xrpc/app.bsky.graph.getFollows?actor={bsky_handle}"
else:
    bsky_filtered_follows_url = f"https://public.api.bsky.app/xrpc/app.bsky.graph.getFollows?actor={bsky_handle}"


print("Finding follow records...", end="")
follows = paginate_request(bsky_follows_url, ['records', 'value'])
follow_dids = [follow['subject'] for follow in follows]

print("\nFinding follows presented on profile...", end="")
presented_follows = paginate_request(bsky_filtered_follows_url, ['follows', 'did'])
presented_follow_count = len(presented_follows)

print(f"\npresented # of follows: {presented_follow_count}")
print(f"# of follow records: {len(follow_dids)}")

if presented_follow_count == len(follow_dids):
    print("follow count consistent, none are blocked or deleted")
    sys.exit(0)
else:
    print("🚨🚨🚨 follow count inconsistent 🚨🚨🚨")
   
missing_follows = set(follow_dids) - set(presented_follows)

if authenticated:
    bsky_profile_url = f"{endpoint}/xrpc/app.bsky.actor.getProfile"
else:
    bsky_profile_url = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"
    print("Authentication needed to determine what lists are blocking follows! Only blocked follows will be shown.")

for follow in missing_follows:
    try:
        profile_resp = requests.get(bsky_profile_url + f"?actor={follow}", headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout as e: # bail!
        print(f"Request timed out! Unformatted missing follows: {missing_follows}")
        raise SystemExit(e)
    profile_resp_json = profile_resp.json()
    if profile_resp.status_code != 200:
        if profile_resp_json['error'] == "InvalidRequest":
            print(f"{follow} is likely missing because the account has been deleted")
        else:
            print(f"{follow} is missing because the {profile_resp_json['message'].lower()}")
        continue
    if authenticated:
        if "blockingByList" in profile_resp_json['viewer']:
            print(f"{profile_resp_json['handle']} is blocked by the list {profile_resp_json['viewer']['blockingByList']['name']}")
        else:
            print(f"{profile_resp_json['handle']} has been manually blocked")
    else:
        print(f"{profile_resp_json['handle']} is blocked")
