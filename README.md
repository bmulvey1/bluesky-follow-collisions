# bluesky-follow-collisions

a tool to find if any people you follow on bluesky are blocked by any blocklists you subscribe to

## usage

``python bsky_follow_collisions.py <handle> <app_password>``

unauthenticated mode is used by omitting ``app_password``, that will determine who is blocked as well as if they are suspended/deactivated/deleted, but not why they are blocked (whether they are blocked via a blocklist or just manually)
