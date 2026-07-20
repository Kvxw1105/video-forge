from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


ROOT = Path(SPEC).resolve().parent.parent
datas = [
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "templates"), "templates"),
]
binaries = []
hiddenimports = collect_submodules("routers") + collect_submodules("services") + collect_submodules("adapters")
for package in ("pyJianYingDraft", "uvicorn", "fastapi", "pydantic"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hidden)

a = Analysis(
    [str(ROOT / "portable_entry.py")],
    pathex=[str(ROOT / "backend"), str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "tests", "numpy.tests", "librosa.tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="VideoForge", console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VideoForge")
