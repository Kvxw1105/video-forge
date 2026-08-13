import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from vforge import client
from vforge import cli

PACK_ID = "kvxw/knowledge-cinematic"
PACK_VERSION = "1.0.0"
BASE = "http://test:8000"


def _args(**kw):
    """Build a SimpleNamespace carrying the args a cmd_* function needs."""
    base = {"base": BASE}
    base.update(kw)
    return types.SimpleNamespace(**base)


# ── client contract: fixed HTTP endpoints ─────────────────

def test_client_director_pack_endpoints(monkeypatch, tmp_path):
    """Every client fn must hit the fixed API endpoint with the right verb/body."""
    calls = []
    monkeypatch.setattr(client, "_request", lambda *a, **k: calls.append((a, k)) or {"ok": True})

    client.list_director_packs(base=BASE)
    method, path, kw = *calls[-1][0], calls[-1][1]
    assert (method, path) == ("GET", "/api/director-packs")
    assert kw == {"base": BASE}

    client.get_director_pack(PACK_ID, PACK_VERSION, base=BASE)
    assert calls[-1][0][:2] == ("GET", "/api/director-packs/kvxw/knowledge-cinematic/1.0.0")

    client.resolve_director_pack(PACK_ID, PACK_VERSION, "review", base=BASE)
    method, path, kw = *calls[-1][0], calls[-1][1]
    assert (method, path) == ("POST", "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/resolve")
    assert kw["json_body"] == {"runMode": "review"}

    client.derive_director_pack(PACK_ID, PACK_VERSION, {"name": "D"}, base=BASE)
    method, path, kw = *calls[-1][0], calls[-1][1]
    assert (method, path) == ("POST", "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/derive")
    assert kw["json_body"] == {"name": "D"}

    client.enable_director_pack(PACK_ID, PACK_VERSION, base=BASE)
    assert calls[-1][0][:2] == ("POST", "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/enable")
    client.disable_director_pack(PACK_ID, PACK_VERSION, base=BASE)
    assert calls[-1][0][:2] == ("POST", "/api/director-packs/kvxw/knowledge-cinematic/1.0.0/disable")
    client.uninstall_director_pack(PACK_ID, PACK_VERSION, base=BASE)
    assert calls[-1][0][:2] == ("DELETE", "/api/director-packs/kvxw/knowledge-cinematic/1.0.0")


def test_client_director_pack_import_sends_file(monkeypatch):
    calls = []
    monkeypatch.setattr(client, "_request", lambda *a, **k: calls.append((a, k)) or {"id": PACK_ID})
    client.import_director_pack("pack.vfdirector", base=BASE)
    method, path, kw = *calls[-1][0], calls[-1][1]
    assert (method, path) == ("POST", "/api/director-packs/import")
    assert kw["files"] == {"file": "pack.vfdirector"}


def test_client_director_pack_export_writes_bytes(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "_request", lambda *a, **k: b"PK\x03\x04archive")
    out = tmp_path / "out.vfdirector"
    saved = client.export_director_pack(PACK_ID, PACK_VERSION, str(out), base=BASE)
    assert saved == str(out)
    assert out.read_bytes() == b"PK\x03\x04archive"


def test_client_director_pack_rejects_malformed_id():
    try:
        client._pack_path("no-slash", PACK_VERSION)
    except ValueError:
        pass
    else:
        raise AssertionError("pack id without publisher/slug must raise ValueError")


# ── CLI: cmd_* forward args and print JSON ────────────────

def test_cmd_director_pack_list(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(client, "list_director_packs", lambda base: seen.append(base) or [{"id": PACK_ID}])
    cli.cmd_director_pack_list(_args())
    out = json.loads(capsys.readouterr().out)
    assert out == [{"id": PACK_ID}]
    assert seen == [BASE]


def test_cmd_director_pack_import(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(client, "import_director_pack", lambda f, base: seen.append((f, base)) or {"status": "installed"})
    cli.cmd_director_pack_import(_args(file="pack.vfdirector"))
    assert json.loads(capsys.readouterr().out) == {"status": "installed"}
    assert seen == [("pack.vfdirector", BASE)]


def test_cmd_director_pack_show(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(client, "get_director_pack", lambda i, v, base: seen.append((i, v, base)) or {"id": PACK_ID})
    cli.cmd_director_pack_show(_args(id=PACK_ID, version=PACK_VERSION))
    assert json.loads(capsys.readouterr().out) == {"id": PACK_ID}
    assert seen == [(PACK_ID, PACK_VERSION, BASE)]


def test_cmd_director_pack_resolve(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(client, "resolve_director_pack", lambda i, v, m, base: seen.append((i, v, m, base)) or {"pack": {"id": PACK_ID}})
    cli.cmd_director_pack_resolve(_args(id=PACK_ID, version=PACK_VERSION, mode="review"))
    assert json.loads(capsys.readouterr().out) == {"pack": {"id": PACK_ID}}
    assert seen == [(PACK_ID, PACK_VERSION, "review", BASE)]


def test_cmd_director_pack_export(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(client, "export_director_pack", lambda i, v, o, base: seen.append((i, v, o, base)) or o)
    cli.cmd_director_pack_export(_args(id=PACK_ID, version=PACK_VERSION, output="out.vfdirector"))
    err = capsys.readouterr().err
    assert "[+] saved to out.vfdirector" in err
    assert seen == [(PACK_ID, PACK_VERSION, "out.vfdirector", BASE)]


def test_cmd_director_pack_derive_reads_atfile(monkeypatch, capsys, tmp_path):
    derive = tmp_path / "derive.json"
    derive.write_text(json.dumps({"id": "kvxw/knowledge-cinematic-x", "version": "1.1.0", "style": {"anchor": "new"}}), encoding="utf-8")
    seen = []
    monkeypatch.setattr(client, "derive_director_pack", lambda i, v, d, base: seen.append((i, v, d, base)) or {"id": "kvxw/knowledge-cinematic-x"})
    cli.cmd_director_pack_derive(_args(id=PACK_ID, version=PACK_VERSION, data=f"@{derive}"))
    assert json.loads(capsys.readouterr().out) == {"id": "kvxw/knowledge-cinematic-x"}
    assert seen[0][:3] == (PACK_ID, PACK_VERSION, {"id": "kvxw/knowledge-cinematic-x", "version": "1.1.0", "style": {"anchor": "new"}})


def test_cmd_director_pack_derive_inline_json(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(client, "derive_director_pack", lambda i, v, d, base: seen.append(d) or {"id": "derived"})
    cli.cmd_director_pack_derive(_args(id=PACK_ID, version=PACK_VERSION, data='{"name": "D"}'))
    assert json.loads(capsys.readouterr().out) == {"id": "derived"}
    assert seen == [{"name": "D"}]


def test_cmd_director_pack_enable_disable_uninstall(monkeypatch, capsys):
    for fn, client_fn in [
        (cli.cmd_director_pack_enable, "enable_director_pack"),
        (cli.cmd_director_pack_disable, "disable_director_pack"),
        (cli.cmd_director_pack_uninstall, "uninstall_director_pack"),
    ]:
        seen = []
        monkeypatch.setattr(client, client_fn, lambda i, v, base, _seen=seen: _seen.append((i, v, base)) or {"status": "ok"})
        fn(_args(id=PACK_ID, version=PACK_VERSION))
        assert json.loads(capsys.readouterr().out) == {"status": "ok"}
        assert seen == [(PACK_ID, PACK_VERSION, BASE)]


# ── CLI parser registration ───────────────────────────────

def test_parser_registers_director_pack_commands():
    parser = cli.build_parser()
    subparsers = next(a for a in parser._actions if getattr(a, "choices", None))
    commands = set(subparsers.choices)
    for name in ["director-pack-list", "director-pack-import", "director-pack-show",
                 "director-pack-resolve", "director-pack-export", "director-pack-derive",
                 "director-pack-enable", "director-pack-disable", "director-pack-uninstall"]:
        assert name in cli.COMMAND_MAP
        assert name in commands


def test_resolve_mode_defaults_to_auto_and_validates_choices():
    args = cli.build_parser().parse_args(["director-pack-resolve", "--id", PACK_ID, "--version", PACK_VERSION])
    assert args.mode == "auto"
    try:
        cli.build_parser().parse_args(["director-pack-resolve", "--id", PACK_ID, "--version", PACK_VERSION, "--mode", "bogus"])
    except SystemExit:
        pass
    else:
        raise AssertionError("--mode must reject values outside auto/review")
