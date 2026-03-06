import base64
import random
import re


def _quote_interrupt(s: str, chars: str = "iex") -> str:
    """Insert empty quotes between characters (PowerShell: cmdlet quote interruption)."""
    if len(s) <= 1:
        return s
    q = "''" if random.choice([True, False]) else '""'
    idx = random.randint(1, len(s) - 1)
    return s[:idx] + q + s[idx:]


def _random_case(s: str) -> str:
    """Randomize character case (PowerShell/Bash)."""
    return "".join(c.upper() if random.choice([True, False]) else c.lower() for c in s)


def _obfuscate_cmdlet(name: str) -> str:
    """Obfuscate a PowerShell cmdlet name with quote interruption and/or case."""
    if random.choice([True, False]):
        return _quote_interrupt(name)
    return _random_case(name)


def _ps_string_concat(parts: list[str]) -> str:
    """Build string from concatenated parts (lower entropy than random names)."""
    return " + ".join(f"'{p}'" for p in parts)


def _ps_encode_b64(s: str) -> str:
    """Express string via Base64 decode (PowerShell)."""
    b = base64.b64encode(s.encode("utf-8")).decode("ascii")
    return f"[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{b}'))"


def obfuscate_powershell(cmd: str) -> str:
    """Apply a mix of PowerShell obfuscation techniques (PowerShell-Obfuscation-Bible style).
    Techniques: quote interruption, case randomization, Get-Command, string concat/base64,
    boolean substitute, extra params.
    """
    out = cmd

    # iwr / Invoke-WebRequest / certutil / bitsadmin
    for pattern, repl in [
        (r"\biwr\b", lambda m: _obfuscate_cmdlet("iwr")),
        (r"\bInvoke-WebRequest\b", lambda m: _obfuscate_cmdlet("Invoke-WebRequest")),
        (r"\bInvoke-RestMethod\b", lambda m: _obfuscate_cmdlet("Invoke-RestMethod")),
        (r"\birm\b", lambda m: _obfuscate_cmdlet("irm")),
        (r"\bcertutil\b", lambda m: _random_case("certutil")),
        (r"\bbitsadmin\b", lambda m: _random_case("bitsadmin")),
    ]:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)

    # iex / Invoke-Expression
    for pattern in [r"\biex\b", r"\bInvoke-Expression\b"]:
        if re.search(pattern, out, re.IGNORECASE):
            out = re.sub(pattern, lambda m: _obfuscate_cmdlet(m.group(0)), out, count=1, flags=re.IGNORECASE)
            break

    # -UseBasicParsing, -OutFile -> random case
    out = re.sub(r"-UseBasicParsing", lambda m: _random_case("-UseBasicParsing"), out, flags=re.IGNORECASE)
    out = re.sub(r"-OutFile", lambda m: _random_case("-OutFile"), out, flags=re.IGNORECASE)

    # Optionally obfuscate URL inside quotes: split or base64 (only for in-memory short URLs we control)
    uri_match = re.search(r'-Uri\s+"([^"]+)"', out)
    if uri_match and random.choice([True, False]):
        url = uri_match.group(1)
        if len(url) < 200:
            # Concatenate parts to break signature
            mid = len(url) // 2
            part1, part2 = url[:mid], url[mid:]
            new_uri = f"-Uri (\"{part1}\" + \"{part2}\")"
            out = out.replace(f'-Uri "{url}"', new_uri)

    # $True / $False -> boolean substitute
    if "$True" in out or "$False" in out:
        out = out.replace("$True", "[bool]1")
        out = out.replace("$False", "[bool]0")

    return out


def _bash_base64_wrap(cmd: str) -> str:
    """Wrap command in base64 decode | bash (Bashfuscator-style encoding)."""
    encoded = base64.b64encode(cmd.encode()).decode()
    return f"echo {encoded} | base64 -d | bash"


def _bash_hex_chars(s: str) -> str:
    """Express string using $'\\xNN' escapes for some chars (Bash)."""
    result = []
    for c in s:
        if c in " \t\n\"'$`\\|&;<>()" or random.random() < 0.3:
            result.append(f"$'\\x{c.encode().hex()}'")
        else:
            result.append(c)
    return "".join(result)


def _bash_var_expand(cmd: str) -> str:
    """Introduce variable expansion: var=value; $var (Bashfuscator-style)."""
    # Pick a substring that looks like a command (e.g. curl, wget, base)
    for word in ["curl", "wget", "bash", "base64"]:
        if word in cmd and f"{word} " in cmd:
            idx = cmd.index(f"{word} ")
            rest = cmd[idx + len(word) + 1 :]
            var = "_" + "".join(random.choices("abcdefghij", k=6))
            return cmd[:idx] + f"{var}={word}; ${var} " + rest
    return cmd


def _bash_quote_tricks(s: str) -> str:
    """Mix quotes: split with '' or $'' (Bash)."""
    if len(s) < 4:
        return s
    i = random.randint(1, len(s) - 1)
    return s[:i] + "''" + s[i:]


def obfuscate_bash(cmd: str) -> str:
    """Apply a mix of Bash obfuscation techniques (Bashfuscator-style).
    Techniques: base64 wrap, variable expansion, hex escapes, quote interruption.
    """
    choice = random.choice(["base64", "var", "hex_quote", "identity"])

    if choice == "base64":
        return _bash_base64_wrap(cmd)

    if choice == "var":
        return _bash_var_expand(cmd)

    if choice == "hex_quote":
        # Obfuscate the command name (curl/wget) with quote tricks
        parts = cmd.strip().split(None, 1)
        if len(parts) >= 1:
            first, rest = parts[0], (parts[1] if len(parts) > 1 else "")
            for c in ["curl", "wget", "bash", "base64"]:
                if first == c or first.startswith(c):
                    return f"{_bash_quote_tricks(first)} {rest}".strip()
            return f"{_bash_quote_tricks(first)} {rest}".strip()
        return cmd

    # identity: optional light obfuscation
    if "curl" in cmd:
        cmd = re.sub(r"\bcurl\b", _bash_quote_tricks("curl"), cmd, count=1)
    if "wget" in cmd:
        cmd = re.sub(r"\bwget\b", _bash_quote_tricks("wget"), cmd, count=1)
    return cmd
