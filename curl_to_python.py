import argparse
import json
import shlex
from urllib.parse import parse_qs, quote

from rich.console import Console

console = Console()

JUNK_FIELDS = {
    "__d",
    "__user",
    "__a",
    "__req",
    "__hs",
    "__ccg",
    "__rev",
    "__s",
    "__hsi",
    "__dyn",
    "__csr",
    "__hsdp",
    "__hblp",
    "__sjsp",
    "__comet_req",
    "__spin_r",
    "__spin_b",
    "__spin_t",
    "__crn",
    "dpr",
    "lsd",
}


def parse_curl_file(filepath):
    with open(filepath) as f:
        content = f.read()
    return parse_curl_command(content)


def parse_curl_command(text):
    lines = text.splitlines()
    joined = " ".join(line.rstrip("\\").strip() for line in lines if line.strip())
    tokens = shlex.split(joined)

    url = None
    headers = {}
    cookies = {}
    data_str = None

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "curl":
            i += 1
            continue
        if not url and not token.startswith("-"):
            url = token
        elif token in ("-H", "--header"):
            i += 1
            if ":" in tokens[i]:
                key, value = tokens[i].split(":", 1)
                headers[key.strip()] = value.strip()
        elif token in ("-b", "--cookie"):
            i += 1
            for part in tokens[i].split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies[k.strip()] = v.strip()
        elif token in ("--data-raw", "--data", "-d", "--data-urlencode"):
            i += 1
            data_str = tokens[i]
        i += 1

    return url, headers, cookies, data_str


def parse_data(data_str):
    parsed = parse_qs(data_str)
    return {k: v[0] for k, v in parsed.items()}


def build_request_components(data_dict):
    kept = {}
    junk = {}
    variables = None

    for k, v in data_dict.items():
        if k == "variables":
            variables = json.loads(v)
            kept[k] = quote(json.dumps(variables))
        elif k in JUNK_FIELDS:
            junk[k] = v
        else:
            kept[k] = v

    return kept, junk, variables


def print_verbose(url, headers, cookies, data_dict, kept, junk, variables):
    console.print("\n  [bold cyan]━━━ Curl Conversion Report ━━━[/bold cyan]\n")

    console.print("  [yellow]URL:[/yellow]")
    console.print(f"    {url}\n")

    console.print(f"  [yellow]Headers ({len(headers)}):[/yellow]")
    for key in headers:
        console.print(f"    [green]{key}[/green]")
    console.print()

    console.print(f"  [yellow]Cookies ({len(cookies)}):[/yellow]")
    for key in cookies:
        console.print(f"    [green]{key}[/green]")
    console.print()

    console.print(f"  [yellow]Data fields ({len(data_dict)}):[/yellow]")
    for key, val in data_dict.items():
        if key in kept:
            console.print(f"    [green]{key}[/green] = {val}")
        else:
            console.print(f"    {key} [dim](junk / commented out)[/dim]")

    if variables:
        console.print("\n  [yellow]Variables (decoded):[/yellow]")
        console.print(
            f"    {json.dumps(variables, indent=4).replace(chr(10), chr(10) + '    ')}"
        )

    console.print("\n  [bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert a curl command from a file into Python request components."
    )
    parser.add_argument(
        "filepath",
        nargs="?",
        default="command.txt",
        help="Path to the file containing the curl command (default: command.txt)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print detailed breakdown of parsed fields",
    )
    args = parser.parse_args()

    url, headers, cookies, data_str = parse_curl_file(args.filepath)
    data_dict = parse_data(data_str)
    kept, junk, variables = build_request_components(data_dict)

    if args.verbose:
        print_verbose(url, headers, cookies, data_dict, kept, junk, variables)

    print(
        json.dumps(
            {
                "url": url,
                "headers": headers,
                "cookies": cookies,
                "data": kept,
                "variables": variables,
            },
            indent=2,
        )
    )
