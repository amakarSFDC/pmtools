# icymi

Generates a "In Case You Missed It" weekly digest by reading a fixed list of Slack channels
and writing one Markdown file, grouped by channel, in chronological order.

Reads Slack through the `claude` CLI's own Slack MCP connection — **no Slack bot app, token,
or admin rights needed.** The script shells out to `claude -p` once per channel, asking it to
resolve the channel name and return that channel's message history as JSON.

## Setup

1. Install the `claude` CLI and make sure it's on `$PATH` and logged in.
2. Make sure the Slack MCP plugin is connected: `claude mcp list` should show
   `plugin:slack:slack` as `Connected`. If not, connect it via AI Suite / Claude Code's
   Slack integration first — that's a one-time interactive step, not something this script
   can do for you.

That's it — no `config/` folder, no `.env`, no bot invites required. Any channel the Slack
account behind that connection can already see (public or private) is readable.

## Usage

```bash
python3 scripts/1_slack_digest.py
```

Fetches the last 7 days from the default channel list and writes
`data/icymi_digest_YYYY-MM-DD.md`.

| Argument | Required | Default | Description |
|---|---|---|---|
| `--channels` | No | fixed 8-channel list (below) | Space-separated channel names, with or without leading `#` |
| `--days` | No | `7` | How many days back to fetch |
| `--output` | No | `data/icymi_digest_YYYY-MM-DD.md` | Output Markdown path |
| `--today` | No | system date | Override today's date (YYYY-MM-DD) — shifts the lookback window and default filename |
| `--timeout` | No | `300` | Per-channel timeout (seconds) for the `claude -p` call — busier channels can take a couple of minutes |

Default channel list:

- `#csg-proservices-amers-tmtcbs-ou`
- `#fy27-cbs-delivery-acct-mgmt-team-proserv`
- `#all-salesforce`
- `#broadcast-the-daily`
- `#csg-proservices-all`
- `#csg-proservices-go-lives`
- `#csg-proservices-amers-recognition`
- `#csg-service-alerts`

Override with `--channels` to run a one-off digest for a different set:

```bash
python3 scripts/1_slack_digest.py --channels csg-proservices-all all-salesforce
```

## Output

One Markdown file with a `## #channel-name` section per channel (in the order given), each
message as a bullet: `**timestamp** — *author*: message text`. Channels that can't be
resolved or read are skipped with a warning and listed at the top of the digest under
"Not fetched".

**Note:** Only top-level channel messages are fetched — thread replies are not included.
System messages (joins/leaves, channel renames, etc.) are filtered out. Message text is
passed through as-is, including raw Slack markup (`:emoji:`, `<url|link text>`, `<!here>`).

## How it works

Each channel read is one `claude -p` invocation with a prompt asking Claude to: resolve the
channel name via `slack_search_channels`, page through `slack_read_channel` for the requested
window, resolve author names, and reply with a single JSON object. The script parses that JSON
and assembles the Markdown file. Because it depends on model output, treat runs as
best-effort — always skim the result before sharing, and re-run a single channel with
`--channels <name>` if something looks off or times out.

## Project layout

```
scripts/
  1_slack_digest.py
data/      # git-ignored — generated digests
```
