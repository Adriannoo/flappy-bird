"""Gera o EXE; --installer também compila o instalador com Inno Setup."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(command):
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", action="store_true")
    parser.add_argument("--iscc", help="Caminho do ISCC.exe do Inno Setup 6 ou 7")
    parser.add_argument("--onedir", action="store_true", help="Build em pasta para diagnóstico")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        parser.error("Este build requer Windows e Python 64 bits.")
    if args.installer and args.onedir:
        parser.error("Use o build padrão de arquivo único para gerar o instalador.")
    compiler = None
    if args.installer:
        candidates = [args.iscc, shutil.which("ISCC.exe")]
        for folder in [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")]:
            if folder:
                candidates.extend(str(Path(folder) / f"Inno Setup {version}" / "ISCC.exe") for version in (6, 7))
        compiler = next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)
        if not compiler:
            parser.error("Inno Setup não encontrado. Instale-o ou informe --iscc CAMINHO_DO_ISCC.exe.")
    try:
        from PIL import Image
        import PyInstaller
    except ImportError:
        parser.error("Instale as ferramentas com: python -m pip install -r requirements-build.txt")
    (ROOT / "build").mkdir(exist_ok=True)
    with Image.open(ROOT / "assets" / "bluebird-midflap.png") as image:
        # Conversão de formato para o ícone do Windows; o sprite é preservado.
        image.resize((256, 256), Image.Resampling.NEAREST).save(ROOT / "build" / "flappy.ico", sizes=[(16,16),(32,32),(48,48),(256,256)])
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir" if args.onedir else "--onefile", "--windowed", "--name", "FlappyBird", "--icon", str(ROOT / "build" / "flappy.ico"), "--add-data", f"{ROOT / 'assets'}:assets", "--add-data", f"{ROOT / 'sound'}:sound", "--specpath", str(ROOT / "build"), "--workpath", str(ROOT / "build" / "pyinstaller"), "--distpath", str(ROOT / "dist"), str(ROOT / "main.py")])
    if compiler:
        run([compiler, str(ROOT / "installer" / "game.iss")])
        print("Instalador gerado em:", ROOT / "releases" / "FlappyBird-Setup.exe")
    print("Executável gerado em:", ROOT / "dist" / ("FlappyBird" if args.onedir else "FlappyBird.exe"))


if __name__ == "__main__":
    main()
