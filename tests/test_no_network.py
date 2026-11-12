"""A diagrams conversion must never touch the network.

The conversion runs in a fresh process with a socket guard installed before
md2xarticle (or any renderer module) is imported. Every connect, DNS lookup, or
outbound send raises and is also counted, so a caller that swallows the error
still fails the test. A self-test proves the guard trips on a real attempt.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

from tests.helpers import FIXTURE_MD

GUARD = textwrap.dedent(
    """
    import socket, sys

    attempts = []

    class NetworkBlocked(OSError):
        pass

    def _block(what):
        def guard(*args, **kwargs):
            attempts.append(what)
            print(f"NETWORK ATTEMPT BLOCKED: {what}", file=sys.stderr, flush=True)
            raise NetworkBlocked(f"network access attempted: {what}")
        return guard

    for _name in ("connect", "connect_ex", "sendto", "sendmsg"):
        setattr(socket.socket, _name, _block(f"socket.{_name}"))
    socket.create_connection = _block("socket.create_connection")
    socket.getaddrinfo = _block("socket.getaddrinfo")
    socket.gethostbyname = _block("socket.gethostbyname")
    socket.gethostbyname_ex = _block("socket.gethostbyname_ex")

    def _finish(code):
        if attempts:
            print(f"FAIL: {len(attempts)} network attempt(s): {sorted(set(attempts))}", file=sys.stderr, flush=True)
            sys.exit(97)
        sys.exit(code)
    """
)


def run_guarded(body: str) -> subprocess.CompletedProcess[str]:
    code = GUARD + "\n" + textwrap.dedent(body)
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8")


def test_diagrams_conversion_makes_no_network_calls(tmp_path):
    out = tmp_path / "out"
    proc = run_guarded(
        f"""
        from md2xarticle import cli
        try:
            rc = cli.main(["diagrams", {str(FIXTURE_MD)!r}, "-o", {str(out)!r}, "--cover", "--only", "1,2,3,4"])
        except BaseException as exc:
            print(f"conversion raised {{exc!r}}", file=sys.stderr)
            rc = 98
        _finish(rc)
        """
    )
    assert "NETWORK ATTEMPT BLOCKED" not in proc.stderr, proc.stderr
    assert proc.returncode == 0, proc.stderr
    names = sorted(p.name for p in (out / "images").iterdir())
    assert names == ["01.png", "02.png", "03.png", "04.png", "cover.png"]


def test_guard_fails_visibly_on_a_network_attempt():
    """Even when the caller swallows the error, the attempt is reported and the run fails."""
    proc = run_guarded(
        """
        try:
            socket.create_connection(("192.0.2.1", 80), timeout=1)
        except OSError:
            pass
        try:
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("192.0.2.1", 80))
        except OSError:
            pass
        _finish(0)
        """
    )
    assert proc.returncode == 97, proc.stderr
    assert "NETWORK ATTEMPT BLOCKED: socket.create_connection" in proc.stderr
    assert "NETWORK ATTEMPT BLOCKED: socket.connect" in proc.stderr
    assert "FAIL: 2 network attempt(s)" in proc.stderr


def test_guard_catches_a_conversion_that_phones_home(tmp_path):
    """Mutant: a renderer that quietly fetches a URL (and ignores the failure) fails the run."""
    out = tmp_path / "out"
    proc = run_guarded(
        f"""
        import urllib.request
        from md2xarticle import cli
        from md2xarticle.render.mermaidx import MermaidxRenderer

        _render = MermaidxRenderer.render

        def phoning_render(self, source, theme):
            try:
                urllib.request.urlopen("http://example.com/", timeout=1)
            except Exception:
                pass
            return _render(self, source, theme)

        MermaidxRenderer.render = phoning_render
        _finish(cli.main(["diagrams", {str(FIXTURE_MD)!r}, "-o", {str(out)!r}, "--only", "1"]))
        """
    )
    assert proc.returncode == 97, proc.stderr
    assert "NETWORK ATTEMPT BLOCKED" in proc.stderr
