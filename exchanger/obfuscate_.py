"""Command obfuscation: PowerShell-Obfuscation-Bible + Bashfuscator style.

Techniques are layered and randomly combined for maximum variety.
"""

import base64
import random
import re


# ---------------------------------------------------------------------------
# PowerShell helpers
# ---------------------------------------------------------------------------

def _quote_interrupt(s: str, chars: str = "iex") -> str:
    """Insert empty quotes between characters (cmdlet quote interruption)."""
    if len(s) <= 1:
        return s
    q = "''" if random.choice([True, False]) else '""'
    idx = random.randint(1, len(s) - 1)
    return s[:idx] + q + s[idx:]


def _random_case(s: str) -> str:
    """Randomize character case."""
    return "".join(c.upper() if random.choice([True, False]) else c.lower() for c in s)


def _backtick_insert(s: str) -> str:
    """Insert PowerShell escape backticks mid-keyword (e.g. i`e`x)."""
    if len(s) <= 2:
        return s
    result = list(s)
    # Insert 1-2 backticks at random positions (not first or after hyphen)
    positions = [i for i in range(1, len(s)) if s[i].isalpha() and s[i - 1] != "-"]
    if not positions:
        return s
    n = min(random.randint(1, 2), len(positions))
    for pos in random.sample(positions, n):
        result[pos] = "`" + result[pos]
    return "".join(result)


def _format_string_iex() -> str:
    """Build 'iex' via -f format operator: ("{0}{1}{2}" -f 'i','e','x')."""
    return """("{0}{1}{2}" -f 'i','e','x')"""


def _gcm_wildcard_iex() -> str:
    """Invoke iex via Get-Command wildcard: & (gcm i*e*-E*n)."""
    variants = [
        "& (gcm i*e*-E*n)",
        "& (Get-Command In*ke-Ex*)",
        ". (gcm *voke-E*pr*)",
    ]
    return random.choice(variants)


def _env_spelling_iex() -> str:
    """Spell 'iex' from environment variable characters."""
    return "$ShellId[1]+$ShellId[13]+'x'"


def _obfuscate_cmdlet(name: str) -> str:
    """Obfuscate a PowerShell cmdlet with quote interrupt, case, or backtick."""
    choice = random.choice(["quote", "case", "backtick"])
    if choice == "quote":
        return _quote_interrupt(name)
    if choice == "backtick":
        return _backtick_insert(name)
    return _random_case(name)


def _ps_string_concat(parts: list[str]) -> str:
    """Build string from concatenated parts."""
    return " + ".join(f"'{p}'" for p in parts)


def _ps_encode_b64(s: str) -> str:
    """Express string via Base64 decode."""
    b = base64.b64encode(s.encode("utf-8")).decode("ascii")
    return f"[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{b}'))"


def _ps_encoded_command(cmd: str) -> str:
    """Wrap entire command in PowerShell -EncodedCommand (UTF-16LE base64)."""
    encoded = base64.b64encode(cmd.encode("utf-16-le")).decode("ascii")
    return f"powershell -enc {encoded}"


def _ps_scriptblock(cmd: str) -> str:
    """Wrap command in [scriptblock]::Create().Invoke()."""
    escaped = cmd.replace("'", "''")
    return f"[scriptblock]::Create('{escaped}').Invoke()"


def _ps_set_alias_iex(cmd: str) -> str:
    """Replace iex with a random alias."""
    alias = "_" + "".join(random.choices("abcdefghij", k=4))
    return f"Set-Alias {alias} Invoke-Expression; " + cmd.replace("iex", alias, 1)


def obfuscate_powershell(cmd: str) -> str:
    """Apply a mix of PowerShell obfuscation techniques.

    Techniques: quote interruption, case randomization, backtick insertion,
    format string iex, Get-Command wildcard, -EncodedCommand, Set-Alias,
    string concat/base64, boolean substitute, scriptblock.
    """
    # Chance to wrap the entire command in -enc or scriptblock
    wrap = random.choice(["none", "none", "none", "enc", "scriptblock"])
    if wrap == "enc":
        return _ps_encoded_command(cmd)
    if wrap == "scriptblock":
        return _ps_scriptblock(cmd)

    out = cmd

    # Obfuscate cmdlet names: iwr, certutil, bitsadmin, etc.
    for pattern, repl in [
        (r"\biwr\b", lambda m: _obfuscate_cmdlet("iwr")),
        (r"\bInvoke-WebRequest\b", lambda m: _obfuscate_cmdlet("Invoke-WebRequest")),
        (r"\bInvoke-RestMethod\b", lambda m: _obfuscate_cmdlet("Invoke-RestMethod")),
        (r"\birm\b", lambda m: _obfuscate_cmdlet("irm")),
        (r"\bcertutil\b", lambda m: _random_case("certutil")),
        (r"\bbitsadmin\b", lambda m: _random_case("bitsadmin")),
        (r"\bStart-BitsTransfer\b", lambda m: _obfuscate_cmdlet("Start-BitsTransfer")),
        (r"\bmshta\b", lambda m: _random_case("mshta")),
        (r"\bregsvr32\b", lambda m: _random_case("regsvr32")),
        (r"\bmsiexec\b", lambda m: _random_case("msiexec")),
        (r"\bcscript\b", lambda m: _random_case("cscript")),
    ]:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)

    # Obfuscate iex / Invoke-Expression with advanced techniques
    for pattern in [r"\biex\b", r"\bInvoke-Expression\b"]:
        if re.search(pattern, out, re.IGNORECASE):
            iex_choice = random.choice(["cmdlet", "cmdlet", "format", "gcm", "alias"])
            if iex_choice == "format":
                out = re.sub(pattern, _format_string_iex(), out, count=1, flags=re.IGNORECASE)
            elif iex_choice == "gcm":
                out = re.sub(pattern, _gcm_wildcard_iex(), out, count=1, flags=re.IGNORECASE)
            elif iex_choice == "alias":
                out = re.sub(pattern, lambda m: _obfuscate_cmdlet(m.group(0)), out, count=1, flags=re.IGNORECASE)
                out = _ps_set_alias_iex(out) if "iex" in out.lower() else out
            else:
                out = re.sub(pattern, lambda m: _obfuscate_cmdlet(m.group(0)), out, count=1, flags=re.IGNORECASE)
            break

    # Random case for flags
    out = re.sub(r"-UseBasicParsing", lambda m: _random_case("-UseBasicParsing"), out, flags=re.IGNORECASE)
    out = re.sub(r"-OutFile", lambda m: _random_case("-OutFile"), out, flags=re.IGNORECASE)
    out = re.sub(r"-EncodedCommand", lambda m: _random_case("-EncodedCommand"), out, flags=re.IGNORECASE)

    # Optionally obfuscate URL inside quotes: split or base64
    uri_match = re.search(r'-Uri\s+"([^"]+)"', out)
    if uri_match and random.choice([True, False]):
        url = uri_match.group(1)
        if len(url) < 200:
            url_choice = random.choice(["concat", "b64"])
            if url_choice == "concat":
                mid = len(url) // 2
                new_uri = f"-Uri (\"{url[:mid]}\" + \"{url[mid:]}\")"
                out = out.replace(f'-Uri "{url}"', new_uri)
            else:
                new_uri = f"-Uri ({_ps_encode_b64(url)})"
                out = out.replace(f'-Uri "{url}"', new_uri)

    # Optionally obfuscate DownloadString URL
    ds_match = re.search(r'DownloadString\("([^"]+)"\)', out)
    if ds_match and random.choice([True, False]):
        url = ds_match.group(1)
        mid = len(url) // 2
        new_ds = f'DownloadString("{url[:mid]}" + "{url[mid:]}")'
        out = out.replace(f'DownloadString("{url}")', new_ds)

    # $True / $False -> boolean substitute
    if "$True" in out or "$False" in out:
        out = out.replace("$True", "[bool]1")
        out = out.replace("$False", "[bool]0")

    # Optionally randomize WebClient variable name
    if "New-Object Net.WebClient" in out:
        var = "$" + "".join(random.choices("abcdefghij", k=5))
        out = re.sub(
            r'\(New-Object Net\.WebClient\)\.',
            f'{var}=New-Object Net.WebClient; {var}.',
            out, count=1,
        )

    return out


# ---------------------------------------------------------------------------
# Bash helpers
# ---------------------------------------------------------------------------

def _bash_base64_wrap(cmd: str) -> str:
    """Wrap command in base64 decode | bash."""
    encoded = base64.b64encode(cmd.encode()).decode()
    variant = random.choice(["pipe", "eval", "source"])
    if variant == "eval":
        return f"eval $(echo {encoded} | base64 -d)"
    if variant == "source":
        return f"source <(echo {encoded} | base64 -d)"
    return f"echo {encoded} | base64 -d | bash"


def _bash_hex_command(word: str) -> str:
    """Express a word entirely as $'\\xNN' hex escapes."""
    return "$'" + "".join(f"\\x{b:02x}" for b in word.encode()) + "'"


def _bash_printf_command(word: str) -> str:
    """Express a word via printf hex: $(printf '\\xNN\\xNN...')."""
    hex_str = "".join(f"\\x{b:02x}" for b in word.encode())
    return f"$(printf '{hex_str}')"


def _bash_rev_wrap(cmd: str) -> str:
    """Reverse the command string and pipe through rev."""
    reversed_cmd = cmd[::-1]
    return f"echo '{reversed_cmd}' | rev | bash"


def _bash_ifs_substitution(cmd: str) -> str:
    """Replace spaces with ${IFS} variable."""
    return cmd.replace(" ", "${IFS}")


def _bash_var_expand(cmd: str) -> str:
    """Introduce variable expansion: var=value; $var."""
    for word in ["curl", "wget", "bash", "base64", "python3", "python", "perl", "ruby", "php", "nc", "socat", "openssl"]:
        if word in cmd and f"{word} " in cmd:
            idx = cmd.index(f"{word} ")
            rest = cmd[idx + len(word) + 1:]
            var = "_" + "".join(random.choices("abcdefghij", k=6))
            return cmd[:idx] + f"{var}={word}; ${var} " + rest
    return cmd


def _bash_quote_tricks(s: str) -> str:
    """Mix quotes: split with '' (Bash concatenation)."""
    if len(s) < 4:
        return s
    i = random.randint(1, len(s) - 1)
    return s[:i] + "''" + s[i:]


def _bash_double_var_indirection(cmd: str) -> str:
    """Use double variable indirection: a=curl; b=a; ${!b} ..."""
    for word in ["curl", "wget"]:
        if word in cmd and f"{word} " in cmd:
            idx = cmd.index(f"{word} ")
            rest = cmd[idx + len(word) + 1:]
            v1 = "_" + "".join(random.choices("abcdefghij", k=4))
            v2 = "_" + "".join(random.choices("klmnopqrst", k=4))
            return cmd[:idx] + f"{v1}={word}; {v2}={v1}; ${{!{v2}}} " + rest
    return cmd


def obfuscate_bash(cmd: str) -> str:
    """Apply a mix of Bash obfuscation techniques.

    Techniques: base64 wrap (pipe/eval/source), variable expansion,
    hex command names, printf command names, rev pipe, IFS substitution,
    double variable indirection, quote tricks.
    """
    choice = random.choice([
        "base64", "var", "hex_cmd", "printf_cmd", "rev",
        "ifs", "double_var", "hex_quote", "identity",
    ])

    if choice == "base64":
        return _bash_base64_wrap(cmd)

    if choice == "var":
        return _bash_var_expand(cmd)

    if choice == "hex_cmd":
        # Replace the first command word with hex escapes
        parts = cmd.strip().split(None, 1)
        if parts:
            return f"{_bash_hex_command(parts[0])} {parts[1] if len(parts) > 1 else ''}".strip()
        return cmd

    if choice == "printf_cmd":
        parts = cmd.strip().split(None, 1)
        if parts:
            return f"{_bash_printf_command(parts[0])} {parts[1] if len(parts) > 1 else ''}".strip()
        return cmd

    if choice == "rev":
        return _bash_rev_wrap(cmd)

    if choice == "ifs":
        return _bash_ifs_substitution(cmd)

    if choice == "double_var":
        result = _bash_double_var_indirection(cmd)
        if result != cmd:
            return result
        return _bash_var_expand(cmd)

    if choice == "hex_quote":
        parts = cmd.strip().split(None, 1)
        if len(parts) >= 1:
            first = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            return f"{_bash_quote_tricks(first)} {rest}".strip()
        return cmd

    # identity: light obfuscation
    for word in ["curl", "wget", "python3", "python", "perl", "ruby", "php"]:
        if word in cmd:
            cmd = re.sub(rf"\b{word}\b", _bash_quote_tricks(word), cmd, count=1)
            break
    return cmd
